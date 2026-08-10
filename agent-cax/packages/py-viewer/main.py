"""
炎核 AI 画图工具 - 主入口

使用方式：
    python main.py
"""
import sys
import os

# 确保包路径正确
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import init_NCTI_Config, DEFAULT_DLL_PATH


def main():
    """主函数"""
    dll_path = DEFAULT_DLL_PATH
    if not os.path.exists(dll_path):
        print(f"错误：DLL 路径不存在：{dll_path}")
        sys.exit(1)

    NCTI = init_NCTI_Config(dll_path)
    if NCTI is None:
        print("错误：NCTI 初始化失败")
        sys.exit(1)

    doc = NCTI.Document()

    import wx
    from ui.main_window import MainWindow

    app = wx.App()
    frame = MainWindow(NCTI, doc, dll_path)

    # 启动 HTTP 服务器（后台线程）
    try:
        from services.http_server import get_http_server
        from config import HTTP_SERVER_HOST, HTTP_SERVER_PORT

        http_server = get_http_server(host=HTTP_SERVER_HOST, port=HTTP_SERVER_PORT)
        http_server.set_script_executor(frame.run_sketch_script_http)
        http_server.set_status_callback(frame.capture_document_status)
        http_server.start(blocking=False)
        print(f"\nHTTP 服务器已启动：http://{http_server.get_real_host_ip()}:{HTTP_SERVER_PORT}")
        print(f"API 文档：http://{http_server.get_real_host_ip()}:{HTTP_SERVER_PORT}/")
        print()
    except Exception as e:
        print(f"HTTP 服务器启动失败：{e}")

    app.MainLoop()


if __name__ == '__main__':
    main()
