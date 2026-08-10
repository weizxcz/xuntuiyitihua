"""CAD Script MCP Server 配置文件"""
from types import SimpleNamespace

# NCTI SDK DLL 路径配置
# 必须指向包含以下文件的目录：
#   - ncti_command.dll
#   - ncti_occ_plugin.dll
#   - ncti_render_vulkan.dll
#   - OCC/ (子目录)
#
# 示例 (Linux):
#   SDK_DLL_PATH = "/opt/ncti-sdk/lib"
#
# 示例 (Windows):
#   SDK_DLL_PATH = "C:/Program Files/NCTI/sdk"
#
# 留空则不启用 NCTI SDK 功能（仅用于测试 MCP 连接）
DLL_PATH = "C:/Users/epro/Downloads/YHCAD/YHCAD_Setup_2026.1.0.62_Beta_Windows_x86-64"

# HTTP 服务器配置
HTTP_PORT = 8310
HTTP_HOST = "0.0.0.0"

# 存储目录配置
STORAGE_DIR = "./storage"

# 临时目录配置
TEMP_DIR = "./storage/temp"

# 创建 settings 对象供其他模块使用
settings = SimpleNamespace(
    DLL_PATH=DLL_PATH,
    HTTP_PORT=HTTP_PORT,
    HTTP_HOST=HTTP_HOST,
    STORAGE_DIR=STORAGE_DIR,
    TEMP_DIR=TEMP_DIR
)
