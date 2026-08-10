import re
from typing import Annotated

from langchain.tools import InjectedToolCallId, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from deerflow.tools.types import Runtime

# URL 匹配模式：http:// 或 https:// 开头的完整 URL
URL_PATTERN = re.compile(r"^https?://.+")


@tool("present_model", parse_docstring=True)
def present_model_tool(
    _runtime: Runtime,
    filepath: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Present a 3D model file for the user to view and interact with.

    Use this tool when you have obtained a 3D model URL from an MCP server or external API
    and want the user to be able to view, rotate, and inspect it in the 3D model viewer.

    When to use the present_model tool:
    - After getting a 3D model URL from an MCP server (e.g., cad_script_get_file_url)
    - When you have a complete HTTP/HTTPS URL pointing to a 3D model file

    When NOT to use the present_model tool:
    - For local file paths (use present_files instead)
    - For 2D images (use view_image instead)
    - For documents, code files, or other non-3D files (use present_files instead)

    Notes:
    - Supported file formats: .yha, .yhp, and other CAD model formats
    - Only accepts complete HTTP/HTTPS URLs from MCP servers
    - The model will be displayed in an interactive 3D viewer with rotation, zoom, and selection

    Args:
        filepath: Complete HTTP/HTTPS URL to the 3D model file. Example: http://127.0.0.1:8310/files/uuid/example.yh
    """
    # Validate that the filepath is a complete URL
    if not URL_PATTERN.match(filepath):
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        f"Error: present_model only accepts complete HTTP/HTTPS URLs. Got: {filepath}",
                        tool_call_id=tool_call_id,
                    )
                ]
            },
        )

    # The merge_artifacts reducer will handle merging and deduplication
    return Command(
        update={
            "artifacts": [filepath],
            "messages": [ToolMessage(f"Successfully presented 3D model: {filepath}", tool_call_id=tool_call_id)],
        },
    )
