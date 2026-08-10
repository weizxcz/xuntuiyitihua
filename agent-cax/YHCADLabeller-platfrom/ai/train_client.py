"""主进程侧的训练子进程调用工具。

本模块只用标准库，不 import torch/dgl，因此可以在缺少 dgl 的主进程环境中安全导入。
真正的图生成/训练逻辑在 `ai/train_worker.py` 里，由装了 dgl/torch 的 conda 环境以子进程
方式执行——具体解释器路径因机器而异，不硬编码，取值顺序与 `ai/infer_client.py` 一致。
训练/生成图耗时可达数分钟到数小时，用 `subprocess.Popen` 非阻塞启动，配合日志文件轮询
展示进度（不像 `infer_client.py` 的 `subprocess.run` 那样阻塞等待）。
"""

import os
import subprocess
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_python_exe(python_exe=None):
    """确定跑 ai/train_worker.py 用的 python 路径，取值顺序同 infer_client._resolve_python_exe。"""
    if python_exe:
        return python_exe
    env_override = os.environ.get("YHCAD_TRAIN_PYTHON") or os.environ.get("YHCAD_AI_PYTHON")
    if env_override:
        return env_override

    from config.config_load import get_system_config_json
    config = get_system_config_json() or {}
    configured = config.get("trainEnvPython") or config.get("aiEnvPython", "")
    if configured:
        return configured

    raise RuntimeError(
        "未配置训练环境的 python 路径：请在 config/system_config.json 中"
        "设置 trainEnvPython（指向本机装了 dgl/torch 的 conda 环境的 python.exe），"
        "或设置环境变量 YHCAD_TRAIN_PYTHON"
    )


def launch_subprocess(mode, work_dir, python_exe=None):
    """以子进程方式启动 ai/train_worker.py，非阻塞，stdout/stderr 重定向到日志文件。

    Args:
        mode: "graph"（生成 graph）或 "train"（训练神经网络）
        work_dir: 本次任务的工作目录（train_job.json 所在目录）

    Returns:
        (Popen对象, 子进程标准输出重定向的日志文件路径)
        主进程不持有日志文件句柄——Popen 后文件副本即关闭，子进程持有自己的
        继承句柄继续写，避免主进程长期占用文件句柄。
    """
    python_exe = resolve_python_exe(python_exe)
    if not os.path.exists(python_exe):
        raise RuntimeError(f"未找到训练环境 python: {python_exe}")

    stdout_log_path = os.path.join(work_dir, f"_subprocess_{mode}.log")
    # 仅用文件句柄把子进程的 stdout 重定向到日志；Popen 会把它继承给子进程
    # （Windows 上子进程得到独立句柄副本），`finally` 中主进程立即关闭自己的
    # 副本，整个训练/生成过程主进程不再持有该文件句柄。
    # `python -u` 强制子进程 stdout/stderr 无缓冲，保证 GUI 轮询能实时读到日志。
    log_fd = open(stdout_log_path, "w", encoding="utf-8")
    try:
        proc = subprocess.Popen(
            [python_exe, "-u", "-m", "ai.train_worker", mode, work_dir],
            cwd=_PROJECT_ROOT,
            stdout=log_fd,
            stderr=subprocess.STDOUT,
        )
    finally:
        log_fd.close()
    return proc, stdout_log_path


def terminate_process_tree(proc):
    """尽力终止整个子进程树（含 multiprocessing.Pool 的 worker 进程）。

    训练主进程通过 spawn 创建 Pool worker，它们是训练主进程的子进程而非兄弟进程；
    仅 `proc.kill()` 只能杀主进程，Pool worker 会残留成孤儿继续占用 GPU/内存。
    Windows 下用 `taskkill /T /F /PID` 按进程树整体强杀；POSIX 下向进程组发 SIGTERM。
    所有失败都静默兜底，退出清理不应因异常而中断。
    """
    if proc is None:
        return
    pid = proc.pid
    if pid is None:
        return
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return
        except OSError:
            pass
    else:
        try:
            import os
            import signal
            os.killpg(os.getpgid(pid), signal.SIGTERM)
            return
        except (OSError, ProcessLookupError):
            pass
    # 兜底：至少尝试直接杀掉主进程
    try:
        proc.kill()
    except Exception:
        pass
