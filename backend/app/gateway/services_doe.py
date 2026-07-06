from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

from fastapi import HTTPException, Request
from langchain_core.messages import BaseMessage
from langchain_core.messages.utils import convert_to_messages
from langgraph.types import Command

from app.gateway.deps import get_checkpointer, get_run_context, get_run_manager, get_stream_bridge
from app.gateway.internal_auth import INTERNAL_SYSTEM_ROLE, get_trusted_internal_owner_user_id
from app.gateway.services import resolve_agent_factory, normalize_input, build_run_config, \
    apply_checkpoint_to_run_config, merge_run_context_overrides, inject_authenticated_user_context, \
    normalize_stream_modes
from app.gateway.utils import sanitize_log_param
from deerflow.config.app_config import get_app_config
from deerflow.runtime import (
    END_SENTINEL,
    HEARTBEAT_SENTINEL,
    ConflictError,
    DisconnectMode,
    RunManager,
    RunRecord,
    RunStatus,
    StreamBridge,
    UnsupportedStrategyError,
    run_agent,
)
from deerflow.runtime.runs.naming import resolve_root_run_name
from deerflow.runtime.user_context import reset_current_user, set_current_user

logger = logging.getLogger(__name__)

async def start_run(
    body: Any,
    thread_id: str,
    request: Request,
) -> RunRecord:
    """Create a RunRecord and launch the background agent task.

    Parameters
    ----------
    body : RunCreateRequest
        The validated request body (typed as Any to avoid circular import
        with the router module that defines the Pydantic model).
    thread_id : str
        Target thread.
    request : Request
        FastAPI request — used to retrieve singletons from ``app.state``.
    """
    bridge = get_stream_bridge(request)
    run_mgr = get_run_manager(request)
    run_ctx = get_run_context(request)

    disconnect = DisconnectMode.cancel if body.on_disconnect == "cancel" else DisconnectMode.continue_

    body_context = getattr(body, "context", None) or {}
    model_name = body_context.get("model_name")

    # Coerce non-string model_name values to str before truncation.
    if model_name is not None and not isinstance(model_name, str):
        model_name = str(model_name)

    # Validate model against the allowlist when a model_name is provided.
    if model_name:
        app_config = get_app_config()
        resolved = app_config.get_model_config(model_name)
        if resolved is None:
            raise HTTPException(
                status_code=400,
                detail=f"Model {model_name!r} is not in the configured model allowlist",
            )

    # owner_user_id = get_trusted_internal_owner_user_id(request)
    owner_user_id = getattr(body, "user_id")
    # Stateless run endpoints carry thread_id in the request *body*, so the
    # @require_permission(owner_check=True) decorator -- which resolves ownership
    # from the path param -- cannot protect them. Enforce thread ownership here,
    # before any run is created, so one user cannot start runs on (or read /wait
    # checkpoint state from) another user's thread. Missing rows (auto-created
    # temp threads) and NULL-owner rows (shared / pre-auth data) stay accessible
    # via check_access; only a thread already owned by another user is rejected
    # with 404, matching thread_runs.py's anti-enumeration behaviour. Internal
    # channel runs act on behalf of the connection owner carried in
    # X-DeerFlow-Owner-User-Id, so they are scoped to that owner instead of
    # bypassing the check -- a leaked internal token must not grant cross-user
    # thread access.
    # user = getattr(request.state, "user", None)
    # if user is not None:
    #     allowed = await run_ctx.thread_store.check_access(thread_id, str(user.id))
    #     if not allowed and owner_user_id and getattr(user, "system_role", None) == INTERNAL_SYSTEM_ROLE:
    #         # Channel workers may also act for the connection owner named in
    #         # the trusted header (e.g. claiming a legacy default-owned channel
    #         # thread for its real owner).
    #         allowed = await run_ctx.thread_store.check_access(thread_id, owner_user_id)
    #     if not allowed:
    #         raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
    #
    owner_context_token = set_current_user(SimpleNamespace(id=owner_user_id)) if owner_user_id else None
    try:
        try:
            record = await run_mgr.create_or_reject(
                thread_id,
                body.assistant_id,
                on_disconnect=disconnect,
                metadata=body.metadata or {},
                kwargs={"input": body.input, "config": body.config},
                multitask_strategy=body.multitask_strategy,
                model_name=model_name,
                user_id=owner_user_id,
            )
        except ConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except UnsupportedStrategyError as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc

        # Upsert thread metadata so the thread appears in /threads/search,
        # even for threads that were never explicitly created via POST /threads
        # (e.g. stateless runs).
        try:
            existing = await run_ctx.thread_store.get(thread_id)
            if existing is None and owner_user_id:
                unscoped_existing = await run_ctx.thread_store.get(thread_id, user_id=None)
                if unscoped_existing is not None:
                    if unscoped_existing.get("user_id") != owner_user_id:
                        await run_ctx.thread_store.update_owner(thread_id, owner_user_id, user_id=None)
                    existing = await run_ctx.thread_store.get(thread_id)
            if existing is None:
                await run_ctx.thread_store.create(
                    thread_id,
                    assistant_id=body.assistant_id,
                    metadata=body.metadata,
                )
            else:
                await run_ctx.thread_store.update_status(thread_id, "running")
        except Exception:
            logger.warning("Failed to upsert thread_meta for %s (non-fatal)", sanitize_log_param(thread_id))

        agent_factory = resolve_agent_factory(body.assistant_id)
        command = getattr(body, "command", None)
        if command and command.get("resume") is not None:
            graph_input = Command(resume=command["resume"])
        else:
            graph_input = normalize_input(body.input)
        config = build_run_config(thread_id, body.config, body.metadata, assistant_id=body.assistant_id)
        await apply_checkpoint_to_run_config(config, body=body, thread_id=thread_id, request=request)

        # Merge DeerFlow-specific context overrides into both ``configurable`` and ``context``.
        # The ``context`` field is a custom extension for the langgraph-compat layer
        # that carries agent configuration (model_name, thinking_enabled, etc.).
        # Only agent-relevant keys are forwarded; unknown keys (e.g. thread_id) are ignored.
        merge_run_context_overrides(config, getattr(body, "context", None))
        inject_authenticated_user_context(config, request)

        stream_modes = normalize_stream_modes(body.stream_mode)

        task = asyncio.create_task(
            run_agent(
                bridge,
                run_mgr,
                record,
                ctx=run_ctx,
                agent_factory=agent_factory,
                graph_input=graph_input,
                config=config,
                stream_modes=stream_modes,
                stream_subgraphs=body.stream_subgraphs,
                interrupt_before=body.interrupt_before,
                interrupt_after=body.interrupt_after,
            )
        )
        record.task = task

        # Title sync is handled by worker.py's finally block which reads the
        # title from the checkpoint and calls thread_store.update_display_name
        # after the run completes.

        return record
    finally:
        if owner_context_token is not None:
            reset_current_user(owner_context_token)