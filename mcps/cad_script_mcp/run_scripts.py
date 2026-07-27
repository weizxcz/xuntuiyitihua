#!/usr/bin/env python3
"""
CAD 脚本执行工具 - 最小化初始化环境

每个脚本执行时注入 NCTI、doc、YH 三个对象。
使用单例模式，只初始化一次。

修改说明：
- ncti 文件路径由调用时传入，格式为 {directory}/{filename}.ncti
- 例如传入 "thread-abc123/thread-abc123.ncti"，实际路径为 "storage/thread-abc123/thread-abc123.ncti"
- 同一次对话传入相同的 ncti_path，确保操作同一个 ncti 文件
"""

import os
import sys
import json
import importlib
from pathlib import Path
from typing import List, Dict, Any, Optional

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 添加父目录到路径以便导入 config 模块
_parent_dir = Path(__file__).parent.parent
if str(_parent_dir) not in sys.path:
    sys.path.insert(0, str(_parent_dir))

# 从 config 模块读取配置（支持环境变量覆盖）
from config import settings

# 日志
logger = __import__('logging').getLogger(__name__)

# 默认存储目录：与 main.py 一致，使用当前脚本所在目录下的 storage
_default_storage_dir = Path(__file__).parent / "storage"

# SDK DLL 路径配置（优先级：环境变量 > 配置文件）
_SDK_DLL_PATH = os.getenv("SDK_DLL_PATH", settings.DLL_PATH)


def get_model_path(ncti_path: str) -> Path:
    """获取模型文件路径。

    传入的 ncti_path 格式为：{uuid}/{filename}.yha
    例如：thread-abc123/thread-abc123.ncti

    Args:
        ncti_path: 会话标识符，格式为 {uuid}/{filename}.yha

    Returns:
        模型文件的完整路径：{storage_dir}/{uuid}/{filename}.yha
    """
    # 将传入的相对路径与 storage 目录拼接
    storage_path = _default_storage_dir / ncti_path
    storage_path.parent.mkdir(parents=True, exist_ok=True)

    return storage_path


class InitEnv:
    """最小化初始化环境 - 单例模式"""

    _instance = None
    _ncti = None
    _yh = None
    _doc = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def init_all(self):
        """一次性初始化 NCTI 和 YH 模块"""
        if self._ncti is not None and self._yh is not None:
            return self._ncti, self._yh

        dll_path = _SDK_DLL_PATH
        if not dll_path or not os.path.exists(dll_path):
            logger.error(f"SDK_DLL_PATH 未设置或不存在：{dll_path}")
            return None, None

        try:
            import ctypes

            # 设置 DLL 加载路径（主目录和 OCC 子目录都需要）
            sys.path.insert(0, dll_path)
            os.add_dll_directory(dll_path)  # 添加主目录
            os.add_dll_directory(os.path.join(dll_path, 'OCC'))  # 添加 OCC 子目录

            # 加载 NCTI 主 DLL
            ctypes.CDLL(os.path.join(dll_path, "ncti_command.dll"))
            ctypes.CDLL(os.path.join(dll_path, "ncti_occ_plugin.dll"))
            ctypes.CDLL(os.path.join(dll_path, "ncti_render_vulkan.dll"))

            # 初始化 NCTI
            self._ncti = importlib.import_module("ncti_python")
            if 1 != self._ncti.Init(dll_path):
                logger.error("NCTI.Init 失败")
                return None, None

            logger.info("NCTI 初始化成功")

            # 初始化 YH（利用已设置好的 DLL 路径）
            py_version = f"{sys.version_info.major}{sys.version_info.minor}"
            py_full_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            logger.info(f"尝试加载 yh_python 模块，Python 版本：{py_full_version}")

            # 先加载 YH 相关的 DLL 依赖
            try:
                ctypes.CDLL(os.path.join(dll_path, "yh_object.dll"))
                ctypes.CDLL(os.path.join(dll_path, "yh_command.dll"))
                logger.info("YH DLL 加载成功")
            except Exception as e:
                logger.error(f"加载 YH DLL 失败：{e}")

            # 优先尝试加载纯 Python 版本 yh_python.py
            yh_python_py = os.path.join(dll_path, "yh_python.py")
            if os.path.exists(yh_python_py):
                try:
                    logger.info(f"尝试加载 yh_python.py...")
                    self._yh = importlib.import_module("yh_python")
                    logger.info(f"YH 初始化成功，使用 yh_python.py")
                except Exception as e:
                    logger.error(f"加载 yh_python.py 失败：{e}")

            # 如果 yh_python.py 不存在或加载失败，尝试加载 .pyd 版本
            if self._yh is None:
                versions_to_try = [f"yh_python{py_version}", "yh_python312", "yh_python311", "yh_python310", "yh_python39", "yh_python38"]

                for module_name in versions_to_try:
                    try:
                        module_path = os.path.join(dll_path, f"{module_name}.pyd")
                        if os.path.exists(module_path):
                            logger.info(f"尝试加载 {module_name}...")
                            self._yh = importlib.import_module(module_name)
                            logger.info(f"YH 初始化成功，使用模块：{module_name}")
                            break
                        else:
                            logger.debug(f"{module_name}.pyd 不存在：{module_path}")
                    except ImportError as e:
                        if "PyInit" in str(e):
                            logger.error(f"加载 {module_name} 失败：Python 版本不兼容（当前 Python {py_full_version}）")
                        else:
                            logger.error(f"加载 {module_name} 失败：{e}")
                        continue
                    except Exception as e:
                        logger.error(f"加载 {module_name} 失败：{e}")
                        import traceback
                        logger.error(f"详细错误：{traceback.format_exc()}")
                        continue

            if self._yh is None:
                logger.error("所有 yh_python 版本都加载失败")
                logger.info(f"当前 Python 版本：{py_full_version}")

            logger.info("NCTI 和 YH 联合初始化完成")
            return self._ncti, self._yh

        except Exception as e:
            logger.error(f"联合初始化失败：{e}")
            import traceback
            logger.error(f"详细错误：{traceback.format_exc()}")
            return None, None

    def init_doc(self, model_path: Optional[Path] = None) -> Optional[Path]:
        """初始化 Document 对象

        Args:
            model_path: 可选的模型文件路径，用于加载现有模型

        Returns:
            模型文件路径（保存后）
        """
        if self._ncti is None:
            self.init_all()
        if self._ncti is None:
            return None

        try:
            # 每次创建新文档
            self._doc = self._ncti.Document()
            self._doc.New("OCC")
            self._doc.SetCreateGeGeom(0)
            logger.info(f"创建新文档，将保存到：{model_path}")
            return model_path
        except Exception as e:
            logger.error(f"初始化 Document 失败：{e}")
            return None

    def release_doc(self):
        """释放 doc 资源"""
        if self._doc is not None:
            try:
                self._doc.Delete()
            except Exception:
                pass
            self._doc = None

    def get_context(self, model_path: Optional[Path] = None) -> Dict[str, Any]:
        """获取执行上下文 {NCTI, doc, YH}

        Args:
            model_path: 可选的模型文件路径

        Returns:
            执行上下文
        """
        # doc 每次执行时重新创建
        self.init_doc(model_path)

        return {
            "NCTI": self._ncti,
            "doc": self._doc,
            "YH": self._yh,
            "_model_path": model_path
        }


# 全局单例
_env = InitEnv()


def execute_script(
    script_content: str,
    model_path: Path,
    object_names: Optional[List[str]] = None,
    cell_ids: Optional[List[str]] = None
) -> Dict[str, Any]:
    """执行脚本 - 调用 run_sketch_script.py 的 handle_execute_sketch_command 函数

    Args:
        script_content: 脚本内容（Python 代码）
        model_path: 模型文件保存路径
        object_names: 选中对象名称列表（可选）
        cell_ids: 选中单元格 ID 列表（可选）

    Returns:
        执行结果
    """
    try:
        from run_sketch_script import handle_execute_sketch_command
        from params import ExecScriptParams

        # 构建 ExecScriptParams 参数
        # model_path 是 Path 对象，需要转换为字符串路径
        model_path_str = str(model_path)
        ncti_path_str = str(model_path.parent / model_path.name)

        params = ExecScriptParams(
            obj_names=object_names or [],
            cell_ids=cell_ids or [],
            script=script_content,
            ncti_path=ncti_path_str,
            new_ncti_path=ncti_path_str,
            task_id="mcp_task"
        )

        # 调用 run_sketch_script.py 中的函数
        success, msg, resp = handle_execute_sketch_command(params)

        if success:
            return {
                "success": True,
                "message": msg or "脚本执行成功"
            }
        else:
            return {
                "success": False,
                "error": msg or "脚本执行失败"
            }

    except Exception as e:
        logger.error(f"调用 run_sketch_script 执行脚本失败：{e}")
        return {
            "success": False,
            "error": f"执行脚本失败：{str(e)}"
        }


def run_scripts(
    scripts: List[Dict[str, Any]],
    ncti_path: str
) -> Dict[str, Any]:
    """
    执行 CAD 脚本

    脚本格式：
    {
        "script_type": "create_box",
        "script_content": "python 代码...",
        "should_execute": true
    }

    Args:
        scripts: 脚本列表
        ncti_path: 会话标识符（必填），用于生成唯一的目录和文件名。
                   格式：{storage_dir}/{ncti_path}/{ncti_path}.ncti
                   同一次对话应传入相同的值，确保操作同一个 ncti 文件。

    Returns:
        执行结果，以 script_type 为键
    """
    model_path = get_model_path(ncti_path)
    logger.info(f"会话模型文件：{model_path}")

    type_counts = {}
    results = {}

    for script in scripts:
        base_type = script.get("script_type", "unknown")

        if base_type in results:
            type_counts[base_type] = type_counts.get(base_type, 0) + 1
            key = f"{base_type}{type_counts[base_type]}"
        else:
            key = base_type

        script_content = script.get("script_content", "")
        should_execute = script.get("should_execute", False)

        if not should_execute:
            results[key] = {"skipped": True, "reason": "should_execute=false"}
            continue

        if not script_content:
            results[key] = {"success": False, "error": "脚本内容为空"}
            continue

        result = execute_script(script_content, model_path)
        results[key] = result

    # 返回目录信息，方便调用方知道文件存储位置
    results["_meta"] = {
        "ncti_path": str(model_path.parent / model_path.name),
        "ncti_dir": str(model_path.parent)
    }

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="执行 CAD 脚本")
    parser.add_argument("--scripts", type=str, required=True, help="脚本 JSON")
    parser.add_argument("--ncti_path", type=str, default=None, help="会话标识符，用于生成唯一的 ncti 文件路径")
    args = parser.parse_args()

    scripts = json.loads(args.scripts)
    result = run_scripts(scripts, args.ncti_path)
    print(json.dumps(result, indent=2, ensure_ascii=False))
