"""AI 服务模块 - 与 DeerFlow API 交互"""
import json
import threading
from typing import Optional, Dict, Any
import requests

from config import DEERFLOW_BASE_URL, DEERFLOW_ASSISTANT_ID


class AIService:
    """AI 服务 - 与 DeerFlow API 交互"""

    def __init__(self, base_url: str = DEERFLOW_BASE_URL, assistant_id: str = DEERFLOW_ASSISTANT_ID):
        self.base_url = base_url.rstrip('/')
        self.assistant_id = assistant_id
        self.session = requests.Session()
        self._thread_id: Optional[str] = None
        self._current_response: Optional[requests.Response] = None  # 当前正在使用的响应对象

    def create_thread(self) -> dict:
        """创建新线程"""
        url = f"{self.base_url}/api/threads"
        data = {"assistant_id": self.assistant_id}
        resp = self.session.post(url, json=data)
        resp.raise_for_status()
        return resp.json()

    def get_or_create_thread(self) -> str:
        """获取或创建线程 ID"""
        if not self._thread_id:
            thread = self.create_thread()
            self._thread_id = thread.get('thread_id')
        return self._thread_id

    def stream_message(self, thread_id: str, content: str, stop_flag: Optional[threading.Event] = None):
        """流式发送消息到 AI

        Args:
            thread_id: 线程 ID
            content: 要发送的消息内容
            stop_flag: 停止标志
        """
        url = f"{self.base_url}/api/threads/{thread_id}/runs/stream"

        # 构建消息：只发送当前用户消息，历史由 thread 自动维护
        data = {
            "input": {
                "messages": [{
                    "type": "human",
                    "content": [{"type": "text", "text": content}]
                }]
            },
            "config": {
                "recursion_limit": 1000
            },
            "context": {
                "thread_id": thread_id
            },
            # messages-tuple: 用于展示聊天记录（每条消息增量）
            # messages-last: 用于解析工具事件并执行
            "stream_mode": ["messages-tuple", "messages-last"],
            "assistant_id": self.assistant_id,
            "on_disconnect": "continue"
        }

        resp = self.session.post(url, json=data, stream=True)
        # 记录当前响应对象，以便外部中断
        self._current_response = resp

        current_event = ""  # 存储当前事件类型

        try:
            for line in resp.iter_lines():
                if stop_flag and stop_flag.is_set():
                    break
                if line:
                    try:
                        line_str = line.decode('utf-8')

                        # 解析 event: 行
                        if line_str.startswith("event: "):
                            current_event = line_str[7:].strip()
                            continue

                        # 解析 data: 行
                        if line_str.startswith("data: "):
                            data_str = line_str[6:]
                            if data_str.strip() == "[DONE]":
                                break
                            try:
                                parsed = json.loads(data_str)
                                # 添加 event type 到 parsed 对象
                                yield {"type": current_event, "data": parsed}
                                # 重置 currentEvent
                                current_event = ""
                            except json.JSONDecodeError:
                                pass
                    except Exception as e:
                        print(f"解析事件失败：{e}")
        finally:
            # 清理响应对象
            self._current_response = None
            resp.close()

    def stop_stream(self):
        """停止当前的流式请求"""
        if self._current_response:
            try:
                self._current_response.close()
            except Exception:
                pass
