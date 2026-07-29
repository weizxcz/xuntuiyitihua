"""
测试长方体创建的 NCTI CAD 脚本

参考 run_sketch_script.py 的实现，用于测试以下脚本：
    # 创建一个长方体
    doc.RunCommand("cmd_ncti_create_box", "box1", NCTI.Point(0, 0, 0), 10, 20, 30)

    print("长方体创建成功")
"""

import ctypes
import importlib
import io
import os
import sys
import traceback

# 确保当前目录在 sys.path 中，以便能导入 config 模块
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# 从 config 导入配置
from config import settings

# 全局变量
NCTI = None
YH = None

# 全局作用域
global_scope = {}

# 模型文件存储目录
STORAGE_DIR = settings.STORAGE_DIR


def initcad(need_yh: bool = True):
    """
    初始化 CAD 环境，加载必要的 DLL 和模块。

    Args:
        need_yh: 是否需要初始化 YH 模块（建模脚本不需要，草图脚本需要）
    """
    global NCTI
    global YH

    dllpath = settings.DLL_PATH

    # 保存当前工作目录
    original_cwd = os.getcwd()

    # 检查是否需要改变工作目录
    if original_cwd != dllpath:
        os.chdir(dllpath)

    # 如果 NCTI 已经缓存，直接返回
    if NCTI is not None:
        if need_yh and YH is not None:
            print("NCTI 和 YH 已初始化，直接返回")
            return YH, NCTI
        elif not need_yh:
            print("NCTI 已初始化，直接返回")
            return None, NCTI

    # 检查 dllpath 是否已经在 sys.path 中，避免重复添加
    if dllpath not in sys.path:
        sys.path.insert(0, dllpath)
        print(f"已将路径添加到 sys.path: {dllpath}")
    else:
        print(f"路径已在 sys.path 中，跳过添加：{dllpath}")

    # 清理 sys.path 中的空字符串
    if '' in sys.path:
        sys.path.remove('')

    print(f"sys.path: {sys.path}")

    # 添加 DLL 目录
    directories_to_add = ["OCC", "PK", "MeshGems"]
    for directory in directories_to_add:
        try:
            os.add_dll_directory(os.path.join(dllpath, directory))
            print(f"已添加 DLL 目录：{directory}")
        except Exception as e:
            print(f"添加目录 {directory} 时出错：{e}")

    # 加载 NCTI 相关的 DLL
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
            ctypes.CDLL(os.path.join(dllpath, dll_name))
            print(f"已加载：{dll_name}")
        except Exception as e:
            print(f"加载 {dll_name} 时出错：{e}")

    # 如果需要 YH，加载 YH 相关的 DLL
    if need_yh:
        yh_dlls = ["yh_command.dll", "yh_object.dll"]
        for dll_name in yh_dlls:
            try:
                ctypes.CDLL(os.path.join(dllpath, dll_name))
                print(f"已加载：{dll_name}")
            except Exception as e:
                print(f"加载 {dll_name} 时出错：{e}")

    print("所有 DLL 加载完成")

    # 初始化 NCTI Python 扩展模块
    NCTI = importlib.import_module("ncti_python")
    NCTI.Init(dllpath)

    # 如果需要 YH，初始化 YH Python 扩展模块
    YH = None
    if need_yh:
        YH = importlib.import_module("yh_python")
        YH.Init(dllpath)

    return YH, NCTI


def safe_execute_script(script: str, global_scope: dict) -> tuple:
    """
    安全地执行脚本（在当前进程中），捕获所有可能的异常。

    返回：(success, output_message, error_message)
    """
    output_buffer = io.StringIO()
    old_stdout = sys.stdout
    old_stderr = sys.stderr

    try:
        sys.stdout = output_buffer
        sys.stderr = output_buffer
        exec(script, global_scope)
        output = output_buffer.getvalue()
        return True, output, None

    except SystemExit as e:
        output = output_buffer.getvalue()
        return False, output, f"脚本调用了 sys.exit()，退出码：{e.code}"

    except MemoryError as e:
        output = output_buffer.getvalue()
        return False, output, f"内存不足：{str(e)}"

    except KeyboardInterrupt as e:
        output = output_buffer.getvalue()
        return False, output, f"脚本被中断：{str(e)}"

    except Exception as e:
        output = output_buffer.getvalue()
        tb_str = traceback.format_exc()
        return False, output, f"脚本执行失败:\n{tb_str}"

    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr


def test_box_creation():
    """
    测试长方体创建功能的主函数。
    """
    print("=" * 50)
    print("开始测试长方体创建脚本")
    print("=" * 50)

    # 自动生成模型文件路径
    os.makedirs(STORAGE_DIR, exist_ok=True)
    model_path = os.path.join(STORAGE_DIR, "test_box.ncti")

    # 定义长方体创建脚本（建模脚本不需要 YH 和 yh_doc）
    box_script = """
# 创建一个长方体
# 命令格式：cmd_ncti_create_box
# 参数：对象名称，角点坐标，长度，宽度，高度
doc.RunCommand("cmd_ncti_create_box", "box1", NCTI.Point(0, 0, 0), 10, 20, 30)

print("长方体创建成功")
"""

    # 初始化 CAD 环境（建模脚本不需要 YH）
    need_yh = False
    try:
        print("正在初始化 CAD 环境...")
        YH, NCTI = initcad(need_yh=need_yh)
        print(f"CAD 环境初始化成功（need_yh={need_yh}）")
    except Exception as e:
        print(f"CAD 环境初始化失败：{e}")
        return False, str(e), None

    try:
        print("正在创建文档对象...")
        doc = NCTI.Document()

        # 建模脚本不需要 yh_doc，直接使用 doc.New()
        if not need_yh:
            print("正在创建新文档（NCTI 模式）...")
            doc.New("OCC")
            print("文档创建成功")
        else:
            print("正在创建文档对象...")
            yh_doc = YH.YHDocument()

            # 如果模型文件存在则打开，否则创建新文档
            if os.path.exists(model_path):
                print(f"正在打开现有模型：{model_path}")
                yh_doc.Open(model_path)
                doc.ID = yh_doc.GetID()
            else:
                print("正在创建新文档...")
                yh_doc.NewPart()
                doc.ID = yh_doc.GetID()

            print("文档创建成功")

        # 设置全局变量
        global_scope["NCTI"] = NCTI
        global_scope["doc"] = doc

        # 如果需要 YH，也添加到全局作用域
        if need_yh and YH:
            global_scope["YH"] = YH
            global_scope["yh_doc"] = yh_doc

        print('开始执行长方体创建脚本')
        success, output, error = safe_execute_script(box_script, global_scope)

        if not success:
            print(error)
            try:
                if doc:
                    doc.Delete()
            except:
                pass
            return False, error, None

        print('脚本执行完成')
        captured_output = output
        print(f"输出：{captured_output}")

        # 检查文档是否被修改并保存
        need_save = doc.IsModified()
        if need_save:
            print(f"正在保存文档到：{model_path}")
            doc.Save(model_path)
            print("文档保存成功")

        # 清理
        doc.Delete()
        print("文档删除成功")

        msg = "脚本执行成功"
        if captured_output != "":
            msg = captured_output

        print("=" * 50)
        print("测试通过！")
        print("=" * 50)

        return True, msg, {"is_modified": need_save}

    except Exception as e:
        error_msg = f"执行过程中发生错误：{str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        try:
            if 'doc' in locals() and doc:
                doc.Delete()
        except:
            pass
        return False, error_msg, None


if __name__ == "__main__":
    # 运行测试
    success, message, data = test_box_creation()

    # 退出码
    sys.exit(0 if success else 1)
