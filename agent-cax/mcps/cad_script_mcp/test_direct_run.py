"""
直接执行 CAD 测试脚本。

将所有代码写在一个文件中，直接运行即可测试。
后续可以替换 test_cad() 函数中的代码来自定义测试内容。
"""

import ctypes
import importlib
import os
import sys
import traceback

# 确保当前目录在 sys.path 中
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from config import settings

DLL_PATH = settings.DLL_PATH


def init_cad():
    """初始化 CAD 环境，加载 DLL 和模块。"""
    print(f"初始化 CAD 环境，dll_path={DLL_PATH}")

    # 切换到 DLL 目录
    os.chdir(DLL_PATH)
    print(f"已切换到目录：{DLL_PATH}")

    # 添加 DLL 路径到 sys.path
    if DLL_PATH not in sys.path:
        sys.path.insert(0, DLL_PATH)

    # 添加 DLL 子目录
    for subdir in ["OCC", "PK", "MeshGems"]:
        try:
            full_path = os.path.join(DLL_PATH, subdir)
            if os.path.exists(full_path):
                os.add_dll_directory(full_path)
        except Exception:
            pass

    # 加载 NCTI DLL
    ncti_dlls = [
        "ncti_doc_occ.dll",
        "ncti_occ_plugin.dll",
        "ncti_dcm_project.dll",
        "ncti_dcm_plugin.dll",
        "ncti_dcm3_project.dll",
        "ncti_dcm3_plugin.dll",
        "ncti_command.dll",
        "ncti_sketch.dll",
    ]

    for dll_name in ncti_dlls:
        try:
            ctypes.CDLL(os.path.join(DLL_PATH, dll_name))
        except Exception:
            pass

    # 加载 YH DLL
    try:
        ctypes.CDLL(os.path.join(DLL_PATH, "yh_command.dll"))
        ctypes.CDLL(os.path.join(DLL_PATH, "yh_object.dll"))
    except Exception:
        pass

    # 导入 Python 模块
    NCTI = importlib.import_module("ncti_python")
    NCTI.Init(DLL_PATH)

    YH = importlib.import_module("yh_python")
    YH.Init(DLL_PATH)

    print("CAD 环境初始化成功")
    return YH, NCTI


def test_cad():
    """
    测试函数 - 在此处编写你的测试代码。
    """
    # 初始化 CAD
    YH, NCTI = init_cad()

    # 创建文档
    doc = NCTI.Document()
    yh_doc = YH.YHDocument()
    yh_doc.NewPart()
    doc.ID = yh_doc.GetID()
    print("文档创建成功")

    # 创建草图
    skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
    # skt.Open()
    print("草图已打开")

    # 绘制圆
    skt.AddCircle(NCTI.Point(0, 0, 0), 20)
    print("圆已绘制")

    # 关闭草图
    # skt.Close()
    print("草图已关闭")

    # 保存文档
    save_path = os.path.join(settings.STORAGE_DIR, "test_output.ncti")
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    doc.Save(save_path)
    print(f"文档已保存到：{save_path}")

    # 清理
    doc.Delete()
    print("文档删除成功")


if __name__ == "__main__":
    try:
        test_cad()
        print("\n测试通过！")
        sys.exit(0)
    except Exception as e:
        print(f"\n测试失败！")
        print(traceback.format_exc())
        sys.exit(1)
