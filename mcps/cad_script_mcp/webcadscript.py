"""Web CAD Script 辅助函数"""
from typing import List, Any, Dict, Tuple


def ensure_list(value: Any) -> List[Any]:
    """确保值是列表类型。"""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def notify_go_api_for_input(
    task_id: str,
    args_json: Dict,
    callback_url: str
) -> Tuple[bool, Any]:
    """通知 Go API 处理输入对话框。

    当前实现返回空结果，因为 MCP 环境下不需要 Go API 回调。

    Args:
        task_id: 任务 ID
        args_json: 参数 JSON
        callback_url: 回调 URL

    Returns:
        (success, output) 元组
    """
    # MCP 环境下不需要回调，直接返回空结果
    return True, []
