"""配置和初始化模块"""
import sys
import os
import ctypes
import importlib

# DeerFlow API 配置
DEERFLOW_BASE_URL = os.environ.get('DEERFLOW_BASE_URL', 'http://172.16.34.129:8301')
DEERFLOW_ASSISTANT_ID = 'lead_agent'

DEFAULT_DLL_PATH = 'C:/Users/epro/Downloads/YHCAD/YHCAD_Setup_2026.1.0.61_Beta_Windows_x86-64'

# HTTP 服务器配置
HTTP_SERVER_HOST = os.environ.get('HTTP_SERVER_HOST', '0.0.0.0')
HTTP_SERVER_PORT = int(os.environ.get('HTTP_SERVER_PORT', '8311'))


def init_NCTI_Config(dll_path: str):
    """初始化 NCTI 配置

    Args:
        dll_path: DLL 文件所在路径

    Returns:
        NCTI 模块实例，失败返回 None
    """
    try:
        # 加载炎核开发引擎的建模内核、渲染引擎、Python 接口
        sys.path.insert(0, dll_path)
        os.add_dll_directory(dll_path + '/OCC')
        ctypes.CDLL(dll_path + "/ncti_command.dll")
        ctypes.CDLL(dll_path + "/ncti_occ_plugin.dll")
        ctypes.CDLL(dll_path + "/ncti_render_vulkan.dll")
        NCTI = importlib.import_module("ncti_python")
        if 1 != NCTI.Init(dll_path):
            return None
        return NCTI
    except:
        print("System path error or loading dll failure!")
        return None
