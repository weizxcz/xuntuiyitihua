"""HTTP 服务器模块 - 提供远程脚本执行 API"""
import json
import logging
import socket
from typing import Optional, Dict, Any, Callable
from pathlib import Path

logger = logging.getLogger(__name__)


class HTTPServer:
    """轻量级 HTTP 服务器 - 提供远程脚本执行 API"""

    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self.script_executor: Optional[Callable[[str, str], tuple]] = None
        self.status_callback: Optional[Callable[[], dict]] = None
        self._server_thread: Optional[Any] = None
        self._running = False

    def set_script_executor(self, executor: Callable[[str, str], tuple]):
        """设置脚本执行回调函数

        Args:
            executor: 执行函数，签名 (script: str, description: str) -> (output: str, error: str, status: dict)
        """
        self.script_executor = executor
        logger.info("脚本执行器已设置")

    def set_status_callback(self, callback: Callable[[], dict]):
        """设置状态获取回调函数

        Args:
            callback: 状态获取函数，签名 () -> dict
        """
        self.status_callback = callback
        logger.info("状态获取回调已设置")

    def get_real_host_ip(self) -> str:
        """获取真实的本机 IP 地址"""
        if self.host in ("0.0.0.0", "*", "::"):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                s.close()
                return ip
            except Exception:
                return "127.0.0.1"
        return self.host

    def start(self, blocking: bool = False):
        """启动 HTTP 服务器

        Args:
            blocking: 是否阻塞运行，默认 False（后台线程运行）
        """
        try:
            import uvicorn
            from fastapi import FastAPI, HTTPException
            from fastapi.responses import JSONResponse
            from pydantic import BaseModel
            from typing import List

            # 创建 FastAPI 应用
            app = FastAPI(title="py-viewer API", version="1.0.0")

            # 请求模型
            class ExecuteScriptRequest(BaseModel):
                script: str
                description: str = ""

            class HealthResponse(BaseModel):
                status: str
                host: str
                port: int

            @app.get("/health")
            async def health_check():
                """健康检查端点"""
                return {
                    "status": "ok",
                    "host": self.get_real_host_ip(),
                    "port": self.port
                }

            @app.post("/api/execute")
            async def execute_script(request: ExecuteScriptRequest):
                """执行脚本端点

                Request Body:
                    script: Python 脚本代码
                    description: 脚本描述（可选）

                Response:
                    success: 是否成功
                    output: 输出内容
                    error: 错误信息
                    description: 脚本描述
                    status: 文档状态（执行成功后返回）
                """
                if not self.script_executor:
                    raise HTTPException(status_code=500, detail="脚本执行器未配置")

                try:
                    output, error, status = self.script_executor(request.script, request.description)
                    return {
                        "success": not error,
                        "output": output,
                        "error": error,
                        "description": request.description,
                        "status": status
                    }
                except Exception as e:
                    logger.exception("脚本执行失败")
                    return {
                        "success": False,
                        "output": "",
                        "error": str(e),
                        "description": request.description,
                        "status": None
                    }

            @app.get("/api/status")
            async def get_status():
                """获取当前文档状态"""
                if not self.status_callback:
                    raise HTTPException(status_code=500, detail="状态获取回调未配置")

                try:
                    status = self.status_callback()
                    return status
                except Exception as e:
                    logger.exception("获取状态失败")
                    raise HTTPException(status_code=500, detail=str(e))

            @app.get("/")
            async def root():
                """API 根路径"""
                return {
                    "name": "py-viewer API",
                    "version": "1.0.0",
                    "endpoints": {
                        "GET /health": "健康检查",
                        "POST /api/execute": "执行脚本",
                        "GET /api/status": "获取文档状态"
                    },
                    "example_request": 'Body: {"script": "...", "description": "..."}'
                }

            # 启动服务器
            self._running = True
            display_host = self.get_real_host_ip()
            logger.info(f"py-viewer HTTP 服务器启动：http://{display_host}:{self.port}")
            logger.info(f"  健康检查：http://{display_host}:{self.port}/health")
            logger.info(f"  脚本执行：http://{display_host}:{self.port}/api/execute")

            if blocking:
                uvicorn.run(app, host=self.host, port=self.port, log_level="info")
            else:
                # 在后台线程运行
                import threading
                self._server_thread = threading.Thread(
                    target=lambda: uvicorn.run(app, host=self.host, port=self.port, log_level="warning"),
                    daemon=True
                )
                self._server_thread.start()

        except ImportError as e:
            logger.error(f"启动 HTTP 服务器失败，缺少依赖：{e}")
            logger.info("请安装：pip install fastapi uvicorn")
            raise

    def stop(self):
        """停止 HTTP 服务器"""
        self._running = False
        logger.info("HTTP 服务器已停止")

    @property
    def is_running(self) -> bool:
        """服务器是否正在运行"""
        return self._running

    @property
    def api_url(self) -> str:
        """获取 API 基础 URL"""
        return f"http://{self.get_real_host_ip()}:{self.port}"


# 单例模式
_http_server_instance: Optional[HTTPServer] = None


def get_http_server(host: str = "0.0.0.0", port: int = 8765) -> HTTPServer:
    """获取 HTTP 服务器单例

    Args:
        host: 监听地址
        port: 监听端口

    Returns:
        HTTPServer 实例
    """
    global _http_server_instance
    if _http_server_instance is None:
        _http_server_instance = HTTPServer(host=host, port=port)
    return _http_server_instance
