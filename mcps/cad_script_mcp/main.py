"""CAD Script MCP Server implementation supporting both stdio and HTTP/SSE protocols."""

import json
import logging
import os
import sys
import traceback
import socket
from pathlib import Path
from typing import Any, Dict
from datetime import datetime

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.cors import CORSMiddleware

# 导入本地配置
from config import settings, HTTP_PORT, HTTP_HOST, STORAGE_DIR as CONFIG_STORAGE_DIR

# 日志配置 - 添加详细调试输出
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 记录服务器启动时间
_SERVER_START_TIME = datetime.now()
_REQUEST_COUNTER = 0


def _log_connection_debug(message: str):
    """记录连接调试信息"""
    logger.debug(f"[CONN] {message}")
    print(f"[CONN DEBUG] {message}", file=sys.stderr, flush=True)


# 当前目录
_CURRENT_DIR = Path(__file__).parent

# 默认存储目录
_STORAGE_DIR = Path(CONFIG_STORAGE_DIR) if CONFIG_STORAGE_DIR.startswith("./") else Path(CONFIG_STORAGE_DIR)
if not _STORAGE_DIR.is_absolute():
    _STORAGE_DIR = _CURRENT_DIR / CONFIG_STORAGE_DIR

# HTTP 服务配置（合并文件服务和 MCP 服务到同一个端口）
# 优先级：环境变量 > 配置文件 > 默认值
_HTTP_PORT = int(os.getenv("CAD_HTTP_SERVER_PORT", HTTP_PORT))
_HTTP_HOST = os.getenv("CAD_HTTP_SERVER_HOST", HTTP_HOST)

# SDK DLL 路径配置
# 优先级：环境变量 > 配置文件 > 默认值
_SDK_DLL_PATH = os.getenv("SDK_DLL_PATH", settings.DLL_PATH)


def get_real_host_ip() -> str:
    """获取真实的本机 IP 地址，用于构建可访问的 URL。"""
    # 如果配置的是 0.0.0.0 或 *, 需要替换为真实 IP
    if _HTTP_HOST in ("0.0.0.0", "*", "::"):
        try:
            # 创建一个临时 socket 连接来获取本机 IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            # 如果获取失败，回退到 127.0.0.1
            return "127.0.0.1"
    return _HTTP_HOST


def get_file_url(file_path: str) -> str:
    """获取文件的 HTTP URL，添加时间戳参数防止缓存。"""
    host = get_real_host_ip()
    timestamp = datetime.now().timestamp()
    return f"http://{host}:{_HTTP_PORT}/files/{file_path}?t={timestamp}"


def handle_run_scripts(scripts: list, model_path: str, need_yh: bool = True) -> Dict[str, Any]:
    """执行 CAD 脚本 - 使用 run_sketch_script.py 中的 handle_execute_sketch_command 函数。

    如果模型文件不存在则创建新文档，存在则打开现有文档再执行脚本。
    使用子进程执行脚本，防止主进程崩溃。

    Args:
        scripts: 脚本列表
        model_path: 模型文件路径
        need_yh: 是否需要 YH 模块和 yh_doc 对象（草图脚本需要，建模脚本不需要）
    """
    logger.info(f"[handle_run_scripts] 开始处理，model_path={model_path}, scripts 数量={len(scripts)}")

    try:
        from run_sketch_script import handle_execute_sketch_command
        from params import ExecScriptParams
        logger.info("[handle_run_scripts] run_sketch_script 模块导入成功")
    except ImportError as e:
        logger.error(f"无法导入 run_sketch_script 模块：{e}")
        return {
            "success": False,
            "error": f"无法加载 run_sketch_script 模块：{str(e)}"
        }

    try:
        results = {}
        type_counts = {}

        for script in scripts:
            base_type = script.get("script_type", "unknown")
            script_content = script.get("script_content", "")
            should_execute = script.get("should_execute", False)

            # 处理脚本类型计数
            if base_type in results:
                type_counts[base_type] = type_counts.get(base_type, 0) + 1
                key = f"{base_type}{type_counts[base_type]}"
            else:
                key = base_type

            if not should_execute:
                results[key] = {"skipped": True, "reason": "should_execute=false"}
                continue

            if not script_content:
                results[key] = {"success": False, "error": "脚本内容为空"}
                continue

            # 调用 run_sketch_script.py 中的 handle_execute_sketch_command 函数
            # 使用子进程执行（use_subprocess=True）防止主进程崩溃
            logger.info(f"[handle_run_scripts] 执行脚本：{key}")

            # 构建完整路径
            full_model_path = str(_STORAGE_DIR / model_path)
            new_model_path = str(_STORAGE_DIR / model_path)

            # 确保目录存在
            Path(new_model_path).parent.mkdir(parents=True, exist_ok=True)

            params = ExecScriptParams(
                obj_names=[],
                cell_ids=[],
                script=script_content,
                ncti_path=full_model_path,
                new_ncti_path=new_model_path,
                task_id="mcp_task",
                need_yh=need_yh  # 根据参数决定是否初始化 YH
            )
            # 使用子进程执行（use_subprocess=True）
            success, msg, resp = handle_execute_sketch_command(params, use_subprocess=True)

            if success:
                results[key] = {"success": True, "message": msg or "脚本执行成功"}
            else:
                results[key] = {"success": False, "error": msg or "脚本执行失败"}

        logger.info(f"[handle_run_scripts] 脚本执行完成，结果：{results}")

        # 添加文件 URL 到结果，拼接 need_yh 参数方便模型查看器根据模型类型切换展示模式
        file_url = get_file_url(model_path)
        # 拼接 need_yh 参数
        separator = "&" if "?" in file_url else "?"
        file_url = f"{file_url}{separator}need_yh={1 if need_yh else 0}"
        results["file_url"] = file_url
        logger.info(f"[handle_run_scripts] 添加 file_url: {file_url}")

        return results

    except Exception as e:
        logger.exception("[handle_run_scripts] 脚本执行失败")
        return {
            "success": False,
            "error": f"脚本执行失败：{str(e)}"
        }


def handle_get_file_url(file_path: str) -> Dict[str, Any]:
    """获取文件的 URL。"""
    full_path = _STORAGE_DIR / file_path

    # 安全检查
    try:
        full_path.resolve().relative_to(_STORAGE_DIR.resolve())
    except ValueError:
        return {
            "success": False,
            "error": f"文件路径超出允许范围：{file_path}"
        }

    if not full_path.exists():
        return {
            "success": False,
            "error": f"文件不存在：{file_path}"
        }

    return {
        "success": True,
        "file_url": get_file_url(file_path),
        "file_path": file_path
    }


def handle_request(request: dict) -> dict:
    """处理 MCP 请求。"""
    global _REQUEST_COUNTER
    _REQUEST_COUNTER += 1
    req_id = _REQUEST_COUNTER

    method = request.get("method")
    params = request.get("params", {})
    request_id = request.get("id")

    _log_connection_debug(f"[请求 #{req_id}] 处理请求: method={method}, id={request_id}, params={params}")

    if method == "initialize":
        _log_connection_debug(f"[请求 #{req_id}] initialize 请求处理完成")
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "cad-script-mcp",
                    "version": "0.1.0"
                }
            }
        }

    elif method == "tools/list":
        _log_connection_debug(f"[请求 #{req_id}] tools/list 请求处理完成")
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {
                "tools": [
                    {
                        "name": "run_scripts",
                        "description": "执行 CAD 操作脚本。",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "scripts": {
                                    "type": "array",
                                    "description": "脚本列表",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "script_type": {"type": "string"},
                                            "script_content": {"type": "string"},
                                            "should_execute": {"type": "boolean"}
                                        }
                                    }
                                },
                                "model_path": {
                                    "type": "string",
                                    "description": "模型文件路径（相对路径，不要包含 /mnt/user-data/outputs/ 前缀），格式为 {session_id}/{filename}.yha，例如：abc-123/model.yha"
                                },
                                "need_yh": {
                                    "type": "boolean",
                                    "description": "是否需要 YH 模块和 yh_doc 对象（草图脚本需要设为 true，建模脚本设为 false）",
                                    "default": True
                                }
                            },
                            "required": ["scripts", "model_path"]
                        }
                    },
                    {
                        "name": "get_file_url",
                        "description": "获取 CAD 文件的下载 URL。",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "file_path": {
                                    "type": "string",
                                    "description": "文件路径（相对于 storage 目录）"
                                }
                            },
                            "required": ["file_path"]
                        }
                    }
                ]
            }
        }

    elif method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        _log_connection_debug(f"[请求 #{req_id}] tools/call: tool={tool_name}, args={arguments}")

        if tool_name == "run_scripts":
            result = handle_run_scripts(
                arguments.get("scripts", []),
                arguments.get("model_path", ""),
                arguments.get("need_yh", True)  # 默认需要 YH（兼容草图脚本）
            )
        elif tool_name == "get_file_url":
            result = handle_get_file_url(arguments.get("file_path", ""))
        else:
            result = {"success": False, "error": f"未知工具：{tool_name}"}

        _log_connection_debug(f"[请求 #{req_id}] tools/call 响应：{result}")
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, indent=2, ensure_ascii=False)
                    }
                ]
            }
        }

    elif method == "ping":
        _log_connection_debug(f"[请求 #{req_id}] ping 请求处理完成")
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {}
        }

    # 通知类方法不需要响应，直接返回 None
    elif method == "notifications/initialized":
        _log_connection_debug(f"[请求 #{req_id}] 收到初始化完成通知（通知类，无需响应）")
        return None

    else:
        _log_connection_debug(f"[请求 #{req_id}] 未实现的方法：{method}")
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "error": {
                "code": -32601,
                "message": f"方法未实现：{method}"
            }
        }


def create_http_app() -> FastAPI:
    """创建 FastAPI 应用，合并 MCP 服务和文件服务。"""
    app = FastAPI(title="CAD Script MCP Server", version="0.1.0")

    # 添加 CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.post("/mcp")
    async def mcp_endpoint(request: Dict[str, Any]):
        """MCP HTTP 端点。"""
        _log_connection_debug(f"[HTTP] MCP 请求收到：{request.get('method', 'unknown')}")
        result = handle_request(request)
        _log_connection_debug(f"[HTTP] MCP 响应发送")
        return result

    @app.get("/health")
    async def health_check():
        """健康检查端点。"""
        return {"status": "ok", "service": "cad-script-mcp"}

    @app.get("/files/{file_path:path}")
    async def file_handler(file_path: str):
        """文件下载端点。"""
        _log_connection_debug(f"[HTTP] 文件请求：{file_path}")
        full_path = _STORAGE_DIR / file_path

        try:
            full_path.resolve().relative_to(_STORAGE_DIR.resolve())
        except ValueError:
            _log_connection_debug(f"[HTTP] 文件路径越界：{file_path}")
            return JSONResponse(status_code=403, content={"error": "Forbidden"})

        if not full_path.exists():
            _log_connection_debug(f"[HTTP] 文件不存在：{file_path}")
            return JSONResponse(status_code=404, content={"error": "Not found"})

        _log_connection_debug(f"[HTTP] 文件发送：{full_path}")
        return FileResponse(full_path)

    return app


# 创建全局 FastAPI 应用
http_app = create_http_app()


def main():
    """主函数 - 通过 stdio 处理 MCP 协议。"""
    # 获取用于显示的 host（如果是 0.0.0.0，显示真实 IP）
    display_host = get_real_host_ip() if _HTTP_HOST in ("0.0.0.0", "*", "::") else _HTTP_HOST

    # 打印启动信息
    _log_connection_debug(f"CAD Script MCP Server 启动")
    _log_connection_debug(f"  HTTP 服务器：http://{display_host}:{_HTTP_PORT}")
    _log_connection_debug(f"  MCP 端点：http://{display_host}:{_HTTP_PORT}/mcp")
    _log_connection_debug(f"  文件端点：http://{display_host}:{_HTTP_PORT}/files/{{path}}")
    _log_connection_debug(f"  健康检查：http://{display_host}:{_HTTP_PORT}/health")
    _log_connection_debug(f"  存储目录：{_STORAGE_DIR}")
    if _SDK_DLL_PATH:
        _log_connection_debug(f"  SDK DLL 路径：{_SDK_DLL_PATH}")
    else:
        _log_connection_debug("  SDK_DLL_PATH 未配置，NCTI 功能将不可用")

    # 记录进程 ID 和启动时间
    _log_connection_debug(f"  进程 ID: {os.getpid()}")
    _log_connection_debug(f"  启动时间：{_SERVER_START_TIME}")
    _log_connection_debug(f"  Python 版本：{sys.version}")
    _log_connection_debug(f"  平台：{sys.platform}")

    # 设置未捕获异常处理器
    def unhandled_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        _log_connection_debug(f"未捕获异常:\n{''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))}")

    sys.excepthook = unhandled_exception

    # 读取标准输入，写入标准输出
    import sys

    # 缓冲输入
    buffer = ""
    _request_id = 0

    while True:
        try:
            # 添加读取超时检查
            _log_connection_debug(f"等待输入... (buffer 长度：{len(buffer)})")
            line = sys.stdin.readline()

            if not line:
                _log_connection_debug("EOF 收到，连接关闭")
                break

            _request_id += 1
            current_req_id = _request_id
            _log_connection_debug(f"[请求 #{current_req_id}] 收到输入行，长度：{len(line)}, buffer 总长度：{len(buffer) + len(line)}")

            buffer += line

            # 检查是否是完整的 JSON-RPC 消息
            if "\r\n\r\n" in buffer or buffer.startswith("{"):
                _log_connection_debug(f"[请求 #{current_req_id}] 检测到完整消息，尝试解析 JSON")
                try:
                    # 尝试解析 JSON
                    if buffer.strip().startswith("{"):
                        request = json.loads(buffer.strip())
                        _log_connection_debug(f"[请求 #{current_req_id}] JSON 解析成功，方法：{request.get('method', 'unknown')}")
                        response = handle_request(request)

                        # 通知类方法返回 None，不需要发送响应
                        if response is not None:
                            # 写入响应
                            response_str = json.dumps(response, ensure_ascii=False)
                            _log_connection_debug(f"[请求 #{current_req_id}] 发送响应，长度：{len(response_str)}")
                            sys.stdout.write(f"Content-Length: {len(response_str)}\r\n\r\n{response_str}")
                            sys.stdout.flush()
                        else:
                            _log_connection_debug(f"[请求 #{current_req_id}] 通知类方法，跳过响应发送")
                        buffer = ""
                        _log_connection_debug(f"[请求 #{current_req_id}] 响应已发送并清空 buffer")
                except json.JSONDecodeError as e:
                    _log_connection_debug(f"[请求 #{current_req_id}] JSON 解析失败：{e}")
                    _log_connection_debug(f"  缓冲内容预览：{buffer[:500]}")

        except KeyboardInterrupt:
            _log_connection_debug("收到 KeyboardInterrupt，退出循环")
            break
        except Exception as e:
            _log_connection_debug(f"处理请求时发生异常：{e}")
            _log_connection_debug(f"  详细堆栈:\n{traceback.format_exc()}")
            break


def run_http_server():
    """运行 HTTP 服务器模式。"""
    import uvicorn

    # 获取用于显示的 host（如果是 0.0.0.0，显示真实 IP）
    display_host = get_real_host_ip() if _HTTP_HOST in ("0.0.0.0", "*", "::") else _HTTP_HOST

    # 打印启动信息
    print(f"\nCAD Script MCP Server")
    print(f"  HTTP 服务器：http://{display_host}:{_HTTP_PORT}")
    print(f"  MCP 端点：http://{display_host}:{_HTTP_PORT}/mcp")
    print(f"  文件端点：http://{display_host}:{_HTTP_PORT}/files/{{path}}")
    print(f"  健康检查：http://{display_host}:{_HTTP_PORT}/health")
    print(f"  存储目录：{_STORAGE_DIR}")
    if _SDK_DLL_PATH:
        print(f"  SDK DLL 路径：{_SDK_DLL_PATH}")
    else:
        print(f"  ⚠️  SDK_DLL_PATH 未配置，NCTI 功能将不可用")
    print()

    uvicorn.run(http_app, host=_HTTP_HOST, port=_HTTP_PORT)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--http":
        # HTTP 模式
        run_http_server()
    else:
        # stdio 模式（默认）
        main()
