"""训练子进程 worker，只应由装了 dgl/torch/yaml/torch_ema/torchmetrics 的解释器
（yhcad_env）以 `python -m ai.train_worker <graph|train> <work_dir>` 的方式执行。

<work_dir> 下须有 GUI 侧（function/on_train.py）预先写好的 train_job.json，描述本次
任务的数据来源和参数。本脚本负责：
1. 绕开 dgl.graphbolt 的 DLL 版本坑（与 ai/infer_worker.py 用同一个 stub 手法）。
2. 把 train_job.json 翻译成 ai.AAGNet_train.base_functions.load_config_basic() 期望的
   JSON 结构，写到 work_dir 下，并通过环境变量 AAGNET_TRAIN_CONFIG_PATH 告知训练包
   （该环境变量会被后续 multiprocessing.Pool 子进程继承，无需额外传递）。
3. 生成 graph 阶段用到的 signal.SIGALRM 超时保护（该模块只在 POSIX 上可用）在 Windows
   上由 ai.AAGNet_train.base_functions.initializer() 在每个 multiprocessing.Pool 子进程
   里打桩去掉——Windows 下 Pool 用 spawn，子进程是全新解释器，本进程这里打的补丁不会
   传递过去，必须在子进程自己的 initializer 里做。

训练管线代码已整体移植进本项目自己的 ai/AAGNet_train/ 包（参考 D:\\wyg\\xuntuiyitihua\\Geo-Rec），
不再依赖 Geo-Rec 作为运行期的 sibling 目录——保证本软件能独立分发给最终用户。
"""

import faulthandler  # 子进程 C 层崩溃(段错误等)时把 Python 堆栈 dump 到 stderr，便于定位
faulthandler.enable()

import json
import os
import sys
import traceback
import types
import re

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
sys.modules.setdefault("dgl.graphbolt", types.ModuleType("dgl.graphbolt"))

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MODEL_CONFIG_PATH = os.path.join(_PROJECT_ROOT, "ai", "AAGNet_train", "configs", "round_model_config.yaml")


def _build_train_config(job, work_dir):
    """把 GUI 侧写的 train_job.json 翻译成 ai.AAGNet_train.base_functions.load_config_basic()
    期望的 JSON 结构。

    processed_data 目录名沿用 Geo-Rec 原来的 "0000-00-00_processed_data" 约定：生成 graph
    和训练是两个独立的子进程调用，可能跨天执行，用固定目录名保证同一个 work_dir 下的路径
    在跨天调用之间保持稳定一致（新版 load_config_basic() 本身不做任何日期前缀改写，这里
    只是继续沿用同一目录名以匹配 function/on_train.py 里硬编码的路径约定）。
    """
    processed_data = os.path.join(work_dir, "0000-00-00_processed_data")
    safe_feature_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(job["feature_name"]).strip())
    model_filename = f"{safe_feature_name}_best_model.pth" if safe_feature_name else "best_model.pth"
    return {
        "recognize_task_infos": {
            "name": job["feature_name"],
            "index_num": job["label_index"],
        },
        "data_path_infos": {
            "use_public_data": False,
            "use_real_data": True,
            "real_data_path_infos": {
                "raw_step_data": job["raw_folder"],
                "raw_label_data": job["raw_folder"],
            },
            "processed_data": processed_data,
            "processed_graph_data": os.path.join(processed_data, "graph"),
            "processed_label_data": os.path.join(processed_data, "labels"),
            "divide_data_infos": {
                "random_seed": 42,
                "train_ratio": job.get("train_ratio", 0.8),
                "val_ratio": job.get("val_ratio", 0.1),
                "test_ratio": job.get("test_ratio", 0.1),
                "divide_result_txt_save_dir": os.path.join(processed_data, "splits"),
            },
        },
        "step2graph_infos": {
            "std_eps": 1e-8,
            "use_ncti_tool": True,
            "num_workers": job.get("num_workers", 4),
            "timeout": job.get("timeout", 120),
            "attr_standard_data_path": os.path.join(processed_data, "attr_stat.json"),
        },
        "model_infos": {
            "model_name": "aagnet",
            "model_config_path": _MODEL_CONFIG_PATH,
            "model_save_dir": os.path.join(work_dir, "model_weights"),
            "model_filename": model_filename,
        },
        "logs_infos": {
            "log_dir": os.path.join(work_dir, "logs"),
            "metrics_path": os.path.join(work_dir, "metrics.jsonl"),
        },
    }


def _write_train_config(config_dict, work_dir):
    config_path = os.path.join(work_dir, "aagnet_train_config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config_dict, f, indent=4, ensure_ascii=False)
    os.environ["AAGNET_TRAIN_CONFIG_PATH"] = config_path


def _load_job(work_dir):
    job_path = os.path.join(work_dir, "train_job.json")
    with open(job_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_current_log_path(work_dir):
    """setup_logging() 内部按时间戳生成日志文件名，GUI 侧不方便提前猜到确切路径，
    这里从 logging 模块当前生效的 FileHandler 里取真实路径写出来，供 GUI 轮询定位。
    必须在 setup_logging() 之后、长耗时任务开始之前调用，否则 GUI 没法在运行过程中
    实时定位日志文件来展示进度。"""
    import logging
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.FileHandler):
            with open(os.path.join(work_dir, "current_log_path.txt"), "w", encoding="utf-8") as f:
                f.write(handler.baseFilename)
            return


def _run_graph_mode(work_dir):
    from ai.AAGNet_train.base_functions import setup_logging
    from ai.AAGNet_train.data_workflow import data_processing_workflow
    setup_logging()
    _write_current_log_path(work_dir)
    data_processing_workflow()


def _run_train_mode(work_dir):
    from ai.AAGNet_train.base_functions import setup_logging
    from ai.AAGNet_train.aagnet_train import trainer_module
    setup_logging()
    _write_current_log_path(work_dir)
    trainer_module()


def main(mode, work_dir):
    if mode not in ("graph", "train"):
        raise ValueError(f"未知的 mode: {mode}，应为 'graph' 或 'train'")

    job = _load_job(work_dir)
    config_dict = _build_train_config(job, work_dir)
    _write_train_config(config_dict, work_dir)

    # 用户通过 GUI 弹窗指定的 epochs 优先于 yaml 配置；用环境变量传给训练子进程
    epochs = job.get("epochs")
    if epochs is not None:
        os.environ["AAGNET_TRAIN_EPOCHS"] = str(epochs)

    # Windows 下 multiprocessing 用 spawn：Pool 工作进程是全新解释器，崩溃时异常
    # 会沿调用栈冒泡回主进程。配合下方 `if __name__ == "__main__"` 的
    # `except BaseException` 与顶部 `faulthandler.enable()`，崩溃堆栈会被打印到
    # stderr（即主进程重定向的 _subprocess_{mode}.log），避免出现「退出码 -1 但
    # 日志空白」的情况。
    try:
        import multiprocessing
        multiprocessing.set_start_method("spawn", force=True)
    except (ImportError, ValueError):
        pass

    if mode == "graph":
        _run_graph_mode(work_dir)
    else:
        _run_train_mode(work_dir)


if __name__ == "__main__":
    try:
        main(sys.argv[1], sys.argv[2])
    except BaseException:
        # BaseException 才能覆盖 SystemExit / 信号终止 / 子进程冒泡异常
        traceback.print_exc()
        sys.exit(1)
