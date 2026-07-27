import ctypes
import importlib
import io
import json
import os
import sys
import subprocess
import tempfile
import traceback
from config import settings

from params import NewNctiParams, ExecScriptResp, ExecScriptParams, RunScriptContentParams
from webcadscript import ensure_list, notify_go_api_for_input

NCTI = None
YH = None

# 保存原始的异常处理器
_original_excepthook = sys.excepthook

# 默认超时时间（秒）
DEFAULT_SCRIPT_TIMEOUT = 60  # 1 分钟


def initcad():
    dllpath = settings.DLL_PATH
    # 保存当前工作目录
    original_cwd = os.getcwd()

    # 检查是否需要改变工作目录
    if original_cwd != dllpath:
        os.chdir(dllpath)

    global NCTI
    global YH
    # 如果 NCTI 已经缓存，直接返回
    if NCTI is not None and YH is not None:
        return YH, NCTI

    # 检查 dllpath 是否已经在 sys.path 中，避免重复添加
    if dllpath not in sys.path:
        sys.path.insert(0, dllpath)
        print(f"已将路径添加到 sys.path: {dllpath}")
    else:
        print(f"路径已在 sys.path 中，跳过添加：{dllpath}")

    # 清理 sys.path 中的空字符串（当前工作目录的表示）
    if '' in sys.path:
        sys.path.remove('')

    print(f"sys.path:{sys.path}")

    # 一次性加载所有可能的 DLL，避免重复加载
    directories_to_add = ["OCC", "PK", "MeshGems"]
    for directory in directories_to_add:
        try:
            os.add_dll_directory(os.path.join(dllpath, directory))
            print(f"已添加 DLL 目录：{directory}")
        except Exception as e:
            print(f"添加目录{directory}时出错：{e}")

    # 第二步：加载所有 DLL
    dlls_to_load = [
        "ncti_doc_occ.dll",
        "ncti_occ_plugin.dll",
        "ncti_dcm_project.dll",
        "ncti_dcm_plugin.dll",
        "ncti_dcm3_project.dll",
        "ncti_dcm3_plugin.dll",
        "ncti_command.dll",
        "ncti_sketch.dll",
        "yh_command.dll",
        "yh_object.dll"
    ]

    for dll_name in dlls_to_load:
        try:
            ctypes.CDLL(os.path.join(dllpath, dll_name))
            print(f"已加载：{dll_name}")
        except Exception as e:
            print(f"加载{dll_name}时出错：{e}")

    print("所有 DLL 加载完成")

    # 初始化 python 扩展模块
    NCTI = importlib.import_module("ncti_python")
    NCTI.Init(dllpath)

    YH = importlib.import_module("yh_python")
    YH.Init(dllpath)

    return YH, NCTI


def init_yh():
    dllpath = settings.DLL_PATH
    os.chdir(dllpath)
    sys.path.insert(0, dllpath)

    os.add_dll_directory(dllpath + "/OCC")
    ctypes.CDLL(dllpath + "/ncti_doc_occ.dll")
    ctypes.CDLL(dllpath + "/ncti_occ_plugin.dll")
    ctypes.CDLL(dllpath + "/ncti_dcm_plugin.dll")
    ctypes.CDLL(dllpath + "/ncti_dcm3_plugin.dll")

    ctypes.CDLL(dllpath + "/ncti_command.dll")
    ctypes.CDLL(dllpath + "/yh_command.dll")
    ctypes.CDLL(dllpath + "/yh_object.dll")
    ctypes.CDLL(dllpath + "/ncti_sketch.dll")

    YH = importlib.import_module("yh_python")
    YH.Init(dllpath)

    NCTI = importlib.import_module("ncti_python")
    NCTI.Init(dllpath)
    return YH, NCTI


def InputDialog(*arg):
    argsList = list(arg)

    if len(argsList) % 2 != 0:
        return {"errorType": "参数个数必须为偶数"}

    outList = []
    argsArray = []
    argsJson = {
        "WindowTitle": argsList[1],
        "Args": argsArray
    }

    for i in range(2, len(argsList), 2):
        caption = argsList[i]
        value = argsList[i + 1]
        outList.append(value)

        argData = {"title": caption}
        argsArray.append(argData)

        if isinstance(value, (int, float)):
            argData["type"] = "number"
            argData["value"] = value
        elif isinstance(value, str):
            argData["type"] = "string"
            argData["value"] = value
        elif isinstance(value, list):
            argData["type"] = "list"
            argData["value"] = value
        elif type(value).__name__ == "Point":
            argData["type"] = "Point"
            argData["value"] = {"x": value.X, "y": value.Y, "z": value.Z}
        elif type(value).__name__ == "Vector":
            argData["type"] = "Vector"
            argData["value"] = {"x": value.X, "y": value.Y, "z": value.Z}
        else:
            argData["type"] = "Unknown"
            argData["value"] = value

    print("Origin Data", argsJson)

    global global_scope
    task_id = global_scope.get("task_id", "unknown_task")

    if task_id == "unknown_task":
        print("未指定任务 ID")
        return tuple(outList)

    success, output = notify_go_api_for_input(task_id, argsJson, "/api/v1/hubnctis/callback")
    print(f"success:{success},output:{output}")

    if success:
        for i in range(min(len(output), len(outList))):
            current_item = outList[i]
            current_data = output[i] if i < len(output) else None

            if current_data is None:
                continue

            if hasattr(current_item, 'X') and hasattr(current_item, 'Y') and hasattr(current_item, 'Z'):
                if isinstance(current_data, dict):
                    current_item.X = float(current_data.get('x', 0))
                    current_item.Y = float(current_data.get('y', 0))
                    current_item.Z = float(current_data.get('z', 0))
                elif isinstance(current_data, (list, tuple)) and len(current_data) >= 3:
                    current_item.X = float(current_data[0])
                    current_item.Y = float(current_data[1])
                    current_item.Z = float(current_data[2])
                elif isinstance(current_data, (int, float)):
                    current_item.X = float(current_data)
                    current_item.Y = float(current_data)
                    current_item.Z = float(current_data)

            elif isinstance(current_item, (int, float, str)):
                if isinstance(current_data, (int, float)):
                    outList[i] = float(current_data)
                elif isinstance(current_data, str):
                    if current_data.replace('.', '').isdigit():
                        outList[i] = float(current_data)
                    else:
                        outList[i] = current_data

        print(f"finally,outList:{outList}")
        return tuple(outList)

    return ()


def handle_new_sketch_command(params: NewNctiParams):
    try:
        md_type = params.md_type
        cs_type = params.cs_type
        new_ncti_path = params.new_ncti_path
        YH, NCTI = initcad()

        doc = NCTI.Document()
        yh_doc = YH.YHDocument()
        yh_doc.NewPart()

        doc.ID = yh_doc.GetID()
        doc.Save(new_ncti_path)
        doc.Delete()

        return True, None
    except Exception as e:
        print(e)
        return False, str(e)


# 全局作用域
global_scope = {}


def execute_script_in_subprocess(
    script: str,
    dll_path: str,
    timeout: int = DEFAULT_SCRIPT_TIMEOUT,
    ncti_path: str = None,
    new_ncti_path: str = None,
    obj_names: list = None,
    cell_names: list = None,
    task_id: str = None
) -> dict:
    """
    在独立的子进程中执行脚本，防止主进程崩溃。

    Args:
        script: 要执行的脚本内容
        dll_path: CAD DLL 路径
        timeout: 超时时间（秒）
        ncti_path: 输入文件路径
        new_ncti_path: 输出文件路径
        obj_names: 对象名称列表
        cell_names: 单元格 ID 列表
        task_id: 任务 ID

    Returns:
        执行结果字典，包含 success, output, error, result 等字段
    """
    # 构建子进程脚本 - 注意：必须在任何输出之前重定向 stdout/stderr
    temp_script = f"""
import sys
import json
import io
import os
import ctypes
import importlib
import traceback

# 立即重定向 stdout 和 stderr，捕获所有输出（包括 DLL 加载时的输出）
output_buffer = io.StringIO()
sys.stdout = output_buffer
sys.stderr = output_buffer

def run_script():
    try:
        # 添加 DLL 路径
        dll_path = {json.dumps(dll_path)}
        if dll_path not in sys.path:
            sys.path.insert(0, dll_path)

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
            "ncti_command.dll", "ncti_sketch.dll", "yh_command.dll", "yh_object.dll"
        ]
        for dll in dlls:
            try:
                ctypes.CDLL(os.path.join(dll_path, dll))
            except:
                pass

        # 导入模块
        NCTI = importlib.import_module("ncti_python")
        NCTI.Init(dll_path)
        YH = importlib.import_module("yh_python")
        YH.Init(dll_path)

        # 初始化文档
        doc = NCTI.Document()
        yh_doc = YH.YHDocument()

        # 打开或创建文档
        ncti_path = {json.dumps(ncti_path)}
        if ncti_path and os.path.exists(ncti_path):
            yd = yh_doc.Open(ncti_path)
            doc.ID = yd.GetID()
        else:
            yh_doc.NewPart()
            doc.ID = yh_doc.GetID()

        # 设置全局变量
        script = {json.dumps(script)}
        global_scope = {{
            "NCTI": NCTI,
            "YH": YH,
            "doc": doc,
            "yh_doc": yh_doc,
            "print": print,
            "len": len, "str": str, "int": int, "float": float,
            "list": list, "dict": dict, "tuple": tuple, "set": set,
            "range": range, "enumerate": enumerate, "zip": zip,
            "map": map, "filter": filter, "sorted": sorted,
            "sum": sum, "min": min, "max": max, "abs": abs, "round": round,
            "bool": bool, "type": type, "isinstance": isinstance,
            "hasattr": hasattr, "getattr": getattr, "setattr": setattr,
        }}

        exec(script, global_scope)

        # 保存文档
        new_ncti_path = {json.dumps(new_ncti_path)}
        if new_ncti_path and doc.IsModified():
            doc.Save(new_ncti_path)

        # 获取输出
        output = output_buffer.getvalue()

        # 检查是否有 result
        result = None
        if "result" in global_scope:
            result_obj = global_scope["result"]
            if hasattr(result_obj, "State"):
                result = {{
                    "State": result_obj.State,
                    "Information": result_obj.Information
                }}

        return {{
            "success": True,
            "output": output,
            "result": result,
            "error": None
        }}

    except Exception as e:
        output = output_buffer.getvalue()
        tb = traceback.format_exc()
        return {{
            "success": False,
            "output": output,
            "result": None,
            "error": tb
        }}

if __name__ == "__main__":
    # 恢复 stdout 以便打印结果
    sys.stdout = sys.__stdout__
    result = run_script()
    # 只输出 JSON 结果，确保可以被解析
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

        # 设置环境变量，确保子进程使用 UTF-8 编码
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'

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
            # 进程超时，强制终止
            process.kill()
            stdout, stderr = process.communicate()
            return {
                "success": False,
                "error": f"脚本执行超时（超过 {timeout} 秒）",
                "output": stdout,
                "result": None
            }

        # 尝试解析 JSON 输出
        result = None
        # 确保 stdout 和 stderr 不为 None
        if stdout is None:
            stdout = ""
        if stderr:
            print(f"stderr: {stderr}")
        try:
            result = json.loads(stdout.strip())
        except json.JSONDecodeError:
            # 如果解析失败，将 stdout 作为输出内容
            pass

        # 返回结果，stdout 作为 output 字段
        return {
            "success": result.get("success", True) if result else True,
            "output": result.get("output", stdout) if result else stdout,
            "result": result.get("result") if result else None,
            "error": result.get("error") if result else None
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"子进程执行失败：{str(e)}\n{traceback.format_exc()}",
            "output": "",
            "result": None
        }

    finally:
        # 清理临时文件
        if temp_script_path and os.path.exists(temp_script_path):
            try:
                os.unlink(temp_script_path)
            except:
                pass


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


def handle_execute_sketch_command(params: ExecScriptParams, use_subprocess: bool = True):
    """
    执行脚本命令。

    Args:
        params: 执行参数
        use_subprocess: 是否使用子进程执行（推荐 True，防止主进程崩溃）

    Returns:
        (success, message, response_data)
    """
    obj_names = params.obj_names
    cell_names = params.cell_ids
    script = params.script
    ncti_path = params.ncti_path
    new_ncti_path = params.new_ncti_path
    task_id = params.task_id

    dll_path = settings.DLL_PATH

    # 使用子进程执行（推荐）
    if use_subprocess:
        print(f"使用子进程执行脚本，超时时间：{DEFAULT_SCRIPT_TIMEOUT}秒")
        result = execute_script_in_subprocess(
            script=script,
            dll_path=dll_path,
            timeout=DEFAULT_SCRIPT_TIMEOUT,
            ncti_path=ncti_path,
            new_ncti_path=new_ncti_path,
            task_id=task_id
        )

        if result.get("success"):
            # 构建响应
            sub_data = ExecScriptResp(is_update=True)
            output = result.get("output", "")
            msg = output if output else "脚本执行成功"

            return True, msg, sub_data.model_dump()
        else:
            error_msg = result.get("error", "未知错误")
            print(f"脚本执行失败：{error_msg}")
            return False, error_msg, None

    # 使用直接执行（不推荐，仅用于调试）
    YH, NCTI = initcad()
    NCTI.SetPyInputDialogCallback(InputDialog)

    objNames = ensure_list(obj_names)
    cellNames = ensure_list(cell_names)

    export_list = []
    doc = NCTI.Document()
    yh_doc = YH.YHDocument()
    yd = None

    try:
        file_exists = os.path.exists(ncti_path)

        if len(objNames) == 0 and len(cellNames) == 0:
            if file_exists:
                yd = yh_doc.Open(ncti_path)
            else:
                yh_doc.NewPart()
                yd = yh_doc
            doc.ID = yd.GetID()
        else:
            doc.Open(ncti_path, 1)
            sel = NCTI.SelectionManager(doc)
            sel.ObjectNames = objNames
            sel.CellIDs = cellNames
            sel.SetSelected()
            yd = doc
            doc.ID = yd.GetID()

        global global_scope
        global_scope["NCTI"] = NCTI
        global_scope["YH"] = YH
        global_scope["doc"] = doc
        global_scope["yh_doc"] = yd
        global_scope["task_id"] = task_id

        print('开始执行脚本')
        success, output, error = safe_execute_script(script, global_scope)

        if not success:
            try:
                if doc:
                    doc.Delete()
            except:
                pass
            print(error)
            return False, error, None

        print('执行结果')
        captured_output = output
        print(captured_output)

        currsel = NCTI.SelectionManager(doc)

        need_save = doc.IsModified()
        if need_save:
            doc.Save(new_ncti_path)
            print("save success", new_ncti_path)

        download_file = doc.DownloadPath
        if len(download_file) > 0 and os.path.exists(download_file):
            export_list.append(download_file)

        doc.Delete()
        print("delete success")

        sub_data = ExecScriptResp(is_update=need_save)
        if len(currsel.ObjectNames) > 0 or len(currsel.CellIDs) > 0:
            sub_data.has_selected = True
            sub_data.selected_object_Names = currsel.ObjectNames
            sub_data.selected_cell_ids = currsel.CellIDs

        if len(export_list) > 0:
            sub_data.export_files = export_list

        msg = "脚本执行成功"
        if captured_output != "":
            msg = captured_output

        return True, msg, sub_data.model_dump()

    except Exception as e:
        error_msg = f"执行过程中发生错误：{str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        try:
            if doc:
                doc.Delete()
        except:
            pass
        return False, error_msg, None


def handle_run_sketch_case(params: RunScriptContentParams, use_subprocess: bool = True):
    """
    执行脚本内容。

    Args:
        params: 执行参数
        use_subprocess: 是否使用子进程执行（推荐 True）

    Returns:
        (status, message)
    """
    md_type = params.md_type
    cs_type = params.cs_type
    script = params.script_content
    dll_path = settings.DLL_PATH

    # 使用子进程执行（推荐）
    if use_subprocess:
        print(f"使用子进程执行脚本，超时时间：{DEFAULT_SCRIPT_TIMEOUT}秒")
        result = execute_script_in_subprocess(
            script=script,
            dll_path=dll_path,
            timeout=DEFAULT_SCRIPT_TIMEOUT,
        )

        if result.get("success"):
            output = result.get("output", "")
            script_result = result.get("result")

            if script_result:
                status = script_result.get("State") == 0
                msg = script_result.get("Information", output)
            else:
                status = True
                msg = output or "脚本执行成功"

            return status, msg
        else:
            error_msg = result.get("error", "未知错误")
            print(f"脚本执行失败：{error_msg}")
            return False, error_msg

    # 使用直接执行（不推荐，仅用于调试）
    try:
        YH, NCTI = initcad()
        doc = NCTI.Document()
        yh_doc = YH.YHDocument()

        try:
            yh_doc.NewPart(md_type, cs_type)
            doc.ID = yh_doc.GetID()

            global global_scope
            global_scope["NCTI"] = NCTI
            global_scope["YH"] = YH
            global_scope["doc"] = doc
            global_scope["yh_doc"] = yh_doc

            success, output, error = safe_execute_script(script, global_scope)

            status = False
            msg = None

            if success:
                print(f"脚本执行结果：{output}")
                doc.Delete()
                if "result" in global_scope:
                    result_obj = global_scope["result"]
                    print(f"获取到 result: {result_obj}")
                    status = result_obj.State == 0
                    msg = result_obj.Information
                else:
                    status = True
                    msg = output or "脚本执行成功"
            else:
                try:
                    doc.Delete()
                except:
                    pass
                print(error)
                msg = error

            return status, msg

        except Exception as e:
            error_msg = f"执行脚本时出错：{str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            try:
                doc.Delete()
            except:
                pass
            return False, error_msg

    except Exception as e:
        error_msg = f"初始化 CAD 环境时出错：{str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        return False, error_msg
