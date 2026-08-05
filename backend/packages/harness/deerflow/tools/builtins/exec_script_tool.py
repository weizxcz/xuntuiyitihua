"""exec_script tool - Returns script content to Frontend for MCP execution."""

import json
from langchain_core.tools import tool


@tool
def exec_script(
    script: str,
    description: str = "",
    need_yh: bool = True
) -> dict:
    """Execute a script for CAD modeling operations.

    此工具将脚本返回给 Frontend，由 Frontend 调用 MCP 执行并展示模型。

    使用场景：
    - 草图脚本：need_yh 设为 true（需要 YH 模块）
    - 建模脚本：need_yh 设为 false（不需要 YH 模块）

    Args:
        script: The Python script content to execute.
        description: Description of what the script does.
        need_yh: 是否需要 YH 模块（草图脚本设为 true，建模脚本设为 false）

    Returns:
        A dictionary with the script content and metadata.
    """
    return {
        "success": True,
        "script": script,
        "description": description,
        "need_yh": need_yh,
        "message": "Script returned to Frontend for execution."
    }


# Export the tool
exec_script_tool = exec_script
