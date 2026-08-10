import uuid
from typing import Annotated

from langchain.tools import InjectedToolCallId, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from deerflow.tools.types import Runtime


@tool("get_session_id", parse_docstring=True)
def get_session_id_tool(
    runtime: Runtime,
    tool_call_id: Annotated[str, InjectedToolCallId],
    generate: bool = False,
) -> Command:
    """Get the current session (thread) ID or generate a random UUID.

    Use this tool to obtain a unique identifier for the current conversation session.
    This is useful for creating isolated file paths per session without using bash.

    When to use the get_session_id tool:
    - When you need to create session-specific file paths (e.g., for CAD models, outputs)
    - When you need a unique identifier for the current conversation
    - When generating a new UUID is preferred over using the thread_id

    Args:
        generate: If True, generate a random UUID instead of returning the thread_id.
                  Use this when you want a shorter, more readable identifier.
    """
    from deerflow.runtime.user_context import get_effective_user_id

    # Get thread_id from runtime context
    thread_id = runtime.context.get("thread_id") if runtime.context else None

    if generate:
        # Generate a random UUID
        session_id = str(uuid.uuid4())
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        f"Generated session UUID: {session_id}",
                        tool_call_id=tool_call_id,
                    )
                ],
            },
        )

    if thread_id:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        f"Current session (thread) ID: {thread_id}",
                        tool_call_id=tool_call_id,
                    )
                ],
            },
        )

    # Fallback: generate a UUID if thread_id is not available
    session_id = str(uuid.uuid4())
    return Command(
        update={
            "messages": [
                ToolMessage(
                    f"Thread ID not available, generated session UUID: {session_id}",
                    tool_call_id=tool_call_id,
                )
            ],
        },
    )


__all__ = ["get_session_id_tool"]
