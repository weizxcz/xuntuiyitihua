"""Session management endpoints (maps session_id to thread_id).

This module provides a session management API that is compatible with the
original CAX system while leveraging DeerFlow's thread infrastructure.

Key mappings:
- session_id ↔ thread_id
- agent_type ↔ assistant_id
- Server configuration stored in thread metadata
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from langgraph.checkpoint.base import empty_checkpoint
from pydantic import BaseModel, Field

from app.gateway.authz import require_permission
from app.gateway.deps import get_checkpointer, get_thread_store
from app.gateway.internal_auth import get_trusted_internal_owner_user_id
from app.gateway.utils import sanitize_log_param
from deerflow.utils.time import coerce_iso, now_iso

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sessions", tags=["sessions"])


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class SessionInfo:
    """Session information (internal representation)."""

    session_id: str
    user_id: str
    agent_type: str
    created_at: str
    project_id: Optional[int] = None
    token: Optional[str] = None
    logic_server_ip: Optional[str] = None
    logic_server_port: Optional[int] = None
    schedule_server_ip: Optional[str] = None
    schedule_server_port: Optional[int] = None
    resource_pool_server_ip: Optional[str] = None
    resource_pool_server_port: Optional[int] = None
    local_execution_server_ip: Optional[str] = None
    local_execution_server_port: Optional[int] = None


class CreateSessionRequest(BaseModel):
    """Request model for creating a session."""

    user_id: str = Field(..., description="User ID")
    agent_type: str = Field(default="fea", description="Agent type (e.g., 'fea', 'doe')")
    project_id: Optional[int] = Field(default=None, description="Project ID")
    token: Optional[str] = Field(default=None, description="JWT access token")
    logic_server_ip: Optional[str] = Field(default=None, description="Logic server IP")
    logic_server_port: Optional[int] = Field(default=None, ge=1, le=65535, description="Logic server port")
    schedule_server_ip: Optional[str] = Field(default=None, description="Schedule server IP")
    schedule_server_port: Optional[int] = Field(default=None, ge=1, le=65535, description="Schedule server port")
    resource_pool_server_ip: Optional[str] = Field(default=None, description="Resource pool server IP")
    resource_pool_server_port: Optional[int] = Field(default=None, ge=1, le=65535, description="Resource pool server port")
    local_execution_server_ip: Optional[str] = Field(default=None, description="Local execution server IP")
    local_execution_server_port: Optional[int] = Field(default=None, ge=1, le=65535, description="Local execution server port")


class SessionResponse(BaseModel):
    """Response model for a session."""

    session_id: str = Field(..., description="Session ID (mapped to thread_id)")
    user_id: str = Field(..., description="User ID")
    created_at: str = Field(..., description="ISO timestamp")
    project_id: int = Field(..., description="Project ID")
    agent_type: str = Field(..., description="Agent type")
    token: str = Field(..., description="JWT access token")
    logic_server_ip: str = Field(..., description="Logic server IP")
    logic_server_port: int = Field(..., description="Logic server port")
    schedule_server_ip: str = Field(..., description="Schedule server IP")
    schedule_server_port: int = Field(..., description="Schedule server port")
    resource_pool_server_ip: str = Field(..., description="Resource pool server IP")
    resource_pool_server_port: int = Field(..., description="Resource pool server port")
    local_execution_server_ip: str = Field(..., description="Local execution server IP")
    local_execution_server_port: int = Field(..., description="Local execution server port")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_session_metadata(request: CreateSessionRequest) -> dict[str, Any]:
    """Build metadata dict from request fields for thread storage."""
    return {
        "agent_type": request.agent_type,
        "project_id": request.project_id,
        "token": request.token,
        "logic_server_ip": request.logic_server_ip,
        "logic_server_port": request.logic_server_port,
        "schedule_server_ip": request.schedule_server_ip,
        "schedule_server_port": request.schedule_server_port,
        "resource_pool_server_ip": request.resource_pool_server_ip,
        "resource_pool_server_port": request.resource_pool_server_port,
        "local_execution_server_ip": request.local_execution_server_ip,
        "local_execution_server_port": request.local_execution_server_port,
    }


def _session_info_to_response(info: SessionInfo) -> SessionResponse:
    """Convert SessionInfo to SessionResponse, handling None values."""
    return SessionResponse(
        session_id=info.session_id,
        user_id=info.user_id,
        created_at=info.created_at,
        project_id=info.project_id or 0,
        agent_type=info.agent_type,
        token=info.token or "",
        logic_server_ip=info.logic_server_ip or "",
        logic_server_port=info.logic_server_port or 0,
        schedule_server_ip=info.schedule_server_ip or "",
        schedule_server_port=info.schedule_server_port or 0,
        resource_pool_server_ip=info.resource_pool_server_ip or "",
        resource_pool_server_port=info.resource_pool_server_port or 0,
        local_execution_server_ip=info.local_execution_server_ip or "",
        local_execution_server_port=info.local_execution_server_port or 0,
    )


def _metadata_to_session_info(thread_id: str, metadata: dict[str, Any]) -> SessionInfo:
    """Convert thread metadata to SessionInfo."""
    return SessionInfo(
        session_id=thread_id,
        user_id=metadata.get("user_id", ""),
        agent_type=metadata.get("agent_type", ""),
        created_at=metadata.get("created_at", ""),
        project_id=metadata.get("project_id"),
        token=metadata.get("token"),
        logic_server_ip=metadata.get("logic_server_ip"),
        logic_server_port=metadata.get("logic_server_port"),
        schedule_server_ip=metadata.get("schedule_server_ip"),
        schedule_server_port=metadata.get("schedule_server_port"),
        resource_pool_server_ip=metadata.get("resource_pool_server_ip"),
        resource_pool_server_port=metadata.get("resource_pool_server_port"),
        local_execution_server_ip=metadata.get("local_execution_server_ip"),
        local_execution_server_port=metadata.get("local_execution_server_port"),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=SessionResponse)
async def create_session(request: CreateSessionRequest, req: Request) -> SessionResponse:
    """Create a new session (maps to thread creation).

    session_id is equivalent to thread_id in DeerFlow.
    Server configuration is stored in thread metadata.

    For DOE agent type with token, server configuration is persisted.
    """
    checkpointer = get_checkpointer(req)
    thread_store = get_thread_store(req)

    session_id = str(uuid.uuid4())
    now = now_iso()

    thread_owner_user_id = get_trusted_internal_owner_user_id(req)
    thread_owner_kwargs = {"user_id": thread_owner_user_id} if thread_owner_user_id else {}

    metadata = _build_session_metadata(request)
    metadata["user_id"] = request.user_id
    metadata["created_at"] = now

    existing_record = await thread_store.get(session_id, **thread_owner_kwargs)
    if existing_record is not None:
        info = _metadata_to_session_info(session_id, existing_record)
        return _session_info_to_response(info)

    try:
        await thread_store.create(
            session_id,
            assistant_id=request.agent_type,
            **thread_owner_kwargs,
            metadata=metadata,
        )
    except Exception:
        logger.exception("Failed to write thread_meta for session %s", sanitize_log_param(session_id))
        raise HTTPException(status_code=500, detail="Failed to create session")

    config = {"configurable": {"thread_id": session_id, "checkpoint_ns": ""}}
    try:
        ckpt_metadata = {
            "step": -1,
            "source": "input",
            "writes": None,
            "parents": {},
            **metadata,
            "created_at": now,
        }
        await checkpointer.aput(config, empty_checkpoint(), ckpt_metadata, {})
    except Exception:
        logger.exception("Failed to create checkpoint for session %s", sanitize_log_param(session_id))
        raise HTTPException(status_code=500, detail="Failed to create session")

    logger.info("Session created: %s (agent_type: %s)", sanitize_log_param(session_id), request.agent_type)

    info = SessionInfo(
        session_id=session_id,
        user_id=request.user_id,
        agent_type=request.agent_type,
        created_at=now,
        project_id=request.project_id,
        token=request.token,
        logic_server_ip=request.logic_server_ip,
        logic_server_port=request.logic_server_port,
        schedule_server_ip=request.schedule_server_ip,
        schedule_server_port=request.schedule_server_port,
        resource_pool_server_ip=request.resource_pool_server_ip,
        resource_pool_server_port=request.resource_pool_server_port,
        local_execution_server_ip=request.local_execution_server_ip,
        local_execution_server_port=request.local_execution_server_port,
    )

    return _session_info_to_response(info)


@router.get("/{session_id}", response_model=SessionResponse)
@require_permission("threads", "read", owner_check=True)
async def get_session(session_id: str, request: Request) -> SessionResponse:
    """Get session info by session_id (thread_id)."""
    thread_store = get_thread_store(request)
    record = await thread_store.get(session_id)

    if record is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    info = _metadata_to_session_info(session_id, record)
    return _session_info_to_response(info)


@router.delete("/{session_id}")
@require_permission("threads", "delete", owner_check=True, require_existing=True)
async def delete_session(session_id: str, request: Request):
    """Delete a session by session_id (thread_id)."""
    thread_store = get_thread_store(request)
    checkpointer = get_checkpointer(request)

    try:
        await thread_store.delete(session_id)
    except Exception:
        logger.exception("Failed to delete thread_meta for session %s", sanitize_log_param(session_id))

    try:
        if hasattr(checkpointer, "adelete_thread"):
            await checkpointer.adelete_thread(session_id)
    except Exception:
        logger.debug("Could not delete checkpoints for session %s (not critical)", sanitize_log_param(session_id))

    logger.info("Session deleted: %s", sanitize_log_param(session_id))
    return {"success": True, "message": f"Session {session_id} deleted"}