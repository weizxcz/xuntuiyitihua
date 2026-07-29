"""
测试长方体创建的 NCTI CAD 脚本

在子进程中执行脚本，防止主进程崩溃。
"""

import ctypes
import importlib
import io
import json
import os
import sys
import subprocess
import tempfile
import traceback

# 确保当前目录在 sys.path 中，以便能导入 config 模块
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# 从 config 导入配置
from config import settings

# 模型文件存储目录
STORAGE_DIR = settings.STORAGE_DIR

# 默认超时时间
DEFAULT_SCRIPT_TIMEOUT = 60


def execute_script_in_subprocess(script: str, dll_path: str, need_yh: bool = True, timeout: int = DEFAULT_SCRIPT_TIMEOUT) -> dict:
    """
    在独立的子进程中执行脚本，防止主进程崩溃。

    返回：(success, output, error)
    """
    temp_script = f"""
import sys
import json
import io
import os
import ctypes
import importlib
import traceback

# 立即重定向 stdout 和 stderr
output_buffer = io.StringIO()
sys.stdout = output_buffer
sys.stderr = output_buffer

# 是否需要 YH 模块
need_yh = {need_yh}

def run_script():
    try:
        # 添加 DLL 路径
        dll_path = {json.dumps(dll_path)}
        if dll_path not in sys.path:
            sys.path.insert(0, dll_path)

        # 改变工作目录到 DLL 目录
        os.chdir(dll_path)

        # 添加 DLL 目录
        for subdir in ["OCC", "PK", "MeshGems"]:
            try:
                os.add_dll_directory(os.path.join(dll_path, subdir))
            except:
                pass

        # 加载 DLL
        dlls = [
            "ncti_doc_occ.dll", "ncti_occ_plugin.dll", "ncti_dcm_project.dll",
            "ncti_dcm_plugin.dll", "ncti_dcm3_project.dll", "ncti_dcm3_plugin.dll",
            "ncti_command.dll", "ncti_sketch.dll"
        ]
        for dll in dlls:
            try:
                ctypes.CDLL(os.path.join(dll_path, dll))
            except:
                pass

        # 如果需要 YH，加载 YH DLL
        if need_yh:
            try:
                ctypes.CDLL(os.path.join(dll_path, "yh_command.dll"))
                ctypes.CDLL(os.path.join(dll_path, "yh_object.dll"))
            except:
                pass

        # 导入模块
        NCTI = importlib.import_module("ncti_python")
        NCTI.Init(dll_path)

        YH = None
        if need_yh:
            YH = importlib.import_module("yh_python")
            YH.Init(dll_path)

        # 初始化文档
        doc = NCTI.Document()
        yh_doc = None

        # 创建新文档（建模脚本）
        if need_yh and YH:
            yh_doc = YH.YHDocument()
            yh_doc.NewPart()
            doc.ID = yh_doc.GetID()
        else:
            doc.New("OCC")

        print("文档创建成功")

        # 设置全局变量
        script = {json.dumps(script)}
        global_scope = {{
            "NCTI": NCTI,
            "doc": doc,
            "print": print,
        }}

        # 如果需要 YH，添加到全局作用域
        if need_yh and YH:
            global_scope["YH"] = YH
            global_scope["yh_doc"] = yh_doc

        exec(script, global_scope)

        print("脚本执行完成")

        # 保存文档
        if doc.IsModified():
            print("文档已修改，准备保存")

        # 获取输出
        output = output_buffer.getvalue()

        # 清理
        doc.Delete()
        print("文档删除成功")

        return {{
            "success": True,
            "output": output,
            "error": None
        }}

    except Exception as e:
        output = output_buffer.getvalue()
        tb = traceback.format_exc()
        return {{
            "success": False,
            "output": output,
            "error": tb
        }}

if __name__ == "__main__":
    sys.stdout = sys.__stdout__
    result = run_script()
    print(json.dumps(result, ensure_ascii=False))
"""

    # 创建临时 Python 文件
    temp_script_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='_script.py',
            delete=False,
            encoding='utf-8'
        ) as f:
            f.write(temp_script)
            temp_script_path = f.name

        # 启动子进程
        python_executable = sys.executable

        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        # 设置许可证路径
        env['DCUBED_LICENSE'] = dll_path
        env['YH_LICENSE_FILE'] = dll_path

        print(f"启动子进程执行脚本...")
        process = subprocess.Popen(
            [python_executable, temp_script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        )

        # 等待进程完成或超时
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            return False, "", f"脚本执行超时（超过 {timeout} 秒）"

        print(f"子进程退出码：{process.returncode}")
        print(f"stdout:\n{stdout}")
        if stderr:
            print(f"stderr:\n{stderr}")

        # 尝试解析 JSON 输出
        try:
            result = json.loads(stdout.strip())
            return result.get("success", False), result.get("output", ""), result.get("error", "")
        except json.JSONDecodeError:
            # 原样返回 stdout
            return False, stdout, ""

    except Exception as e:
        return False, "", f"子进程执行失败：{str(e)}\n{traceback.format_exc()}"

    finally:
        if temp_script_path and os.path.exists(temp_script_path):
            try:
                os.unlink(temp_script_path)
            except:
                pass


def test_box_creation():
    """
    测试长方体创建功能的主函数。
    """
    print("=" * 50)
    print("开始测试长方体创建脚本")
    print("=" * 50)

    # 定义草图绘制脚本
    box_script = """
print("正在创建草图...")
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
skt.Open()
print("草图已打开")

# 绘制圆：圆心在原点 (0,0,0)，半径 20
circle = skt.AddCircle(NCTI.Point(0, 0, 0), 20)
print("圆已绘制")

# 关闭草图
skt.Close()
print("草图已关闭")
"""

    need_yh = True
    print(f"在子进程中执行脚本（need_yh={need_yh}）")

    success, output, error = execute_script_in_subprocess(
        script=box_script,
        dll_path=settings.DLL_PATH,
        need_yh=need_yh
    )

    print(f"执行结果：success={success}")
    print(f"输出：{output}")
    if error:
        print(f"错误：{error}")

    if success:
        print("=" * 50)
        print("测试通过！")
        print("=" * 50)
        return True, output, None
    else:
        print("=" * 50)
        print("测试失败！")
        print("=" * 50)
        return False, error or output, None


if __name__ == "__main__":
    # 运行测试
    success, message, data = test_box_creation()

    # 退出码
    sys.exit(0 if success else 1)
