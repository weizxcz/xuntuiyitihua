"""训练管线的公用工具函数（从 Geo-Rec 的 src/utils/base_functions.py 移植）。

与 Geo-Rec 原版的主要差异：
1. 不再有 configs.yaml：load_config_basic() 直接从环境变量
   AAGNET_TRAIN_CONFIG_PATH 指向的 JSON 文件读取本次任务配置，该文件由
   ai/train_worker.py 在启动时写入 work_dir 并通过环境变量传给自身及后续
   fork/spawn 出的多进程 worker（多进程 Pool 子进程会继承父进程环境变量）。
2. 配置里的路径全部由 train_worker.py 提前拼成绝对路径，因此这里去掉了
   Geo-Rec 原版里到处都有的 use_absolute_path 分支判断。
3. NCTI 初始化复用本项目自己的 config.config_load.init_ncti_config()
   （5 DLL 加载顺序，读取 config/system_config.json），而不是 Geo-Rec 自带的
   面向 Linux/configs.yaml 的 init_ncti()。
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any

import torch
import dgl
import numpy as np
import yaml


def load_yaml(file_path: str) -> Dict[str, Any]:
    """加载YAML配置文件"""
    with open(file_path, 'r', encoding='utf-8') as file:
        config = yaml.safe_load(file)
    return config


def load_config_basic() -> Dict[str, Any]:
    """读取本次训练任务的配置（JSON），路径来自环境变量 AAGNET_TRAIN_CONFIG_PATH。"""
    config_path = os.environ["AAGNET_TRAIN_CONFIG_PATH"]
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def init_ncti():
    """复用本项目自己的 NCTI 初始化逻辑（config.config_load 模块级已完成一次初始化）。"""
    from config import config_load
    return config_load.NCTI


def setup_logging():
    """设置日志记录"""
    config = load_config_basic()
    log_dir_config = config['logs_infos']['log_dir']
    task_name = config['recognize_task_infos']['name']

    log_dir = os.path.join(log_dir_config, task_name)
    os.makedirs(log_dir, exist_ok=True)

    # 生成带时间戳的日志文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"{log_dir}/run_{timestamp}.log"

    # 配置日志（force=True 确保覆盖已有配置，解决日志文件为空的问题）
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename, encoding='utf-8'),
            logging.StreamHandler()
        ],
        force=True
    )
    logging.info(f"日志文件已创建: {log_filename}")


def save_json_data(pathname, data):
    """保存数据到JSON文件。

    编码必须与读端 load_json / load_json_or_pkl 保持一致（utf-8），否则在 Windows
    上含非 ASCII 字符（如中文 step 名）的 graph json 会出现 'gbk' 解码失败。
    ensure_ascii=False 让中文原样落盘，配合 utf-8 读写两端闭环。
    """
    with open(pathname, 'w', encoding='utf-8') as fp:
        json.dump(data, fp, indent=4, ensure_ascii=False, sort_keys=False)


def load_json(pathname):
    with open(pathname, "r", encoding="utf-8") as fp:
        return json.load(fp)


def append_metrics(record: Dict[str, Any]):
    """把一个 epoch 的 loss/指标追加写一行 JSON，供 GUI"训练实时监测"窗口轮询画图。"""
    config = load_config_basic()
    metrics_path = config['logs_infos']['metrics_path']
    os.makedirs(os.path.dirname(metrics_path), exist_ok=True)
    with open(metrics_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')


def initializer():
    import signal
    """忽略子进程中的CTRL+C信号"""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    # Windows 的 multiprocessing 用 spawn，子进程重新 import signal 模块，
    # 不会继承父进程运行期打的 SIGALRM 补丁（train_worker._neutralize_sigalrm
    # 只作用于父进程自身），所以这里在子进程里再打一次。
    neutralize_sigalrm()
    global NCTI
    NCTI = init_ncti()


def neutralize_sigalrm():
    """Windows 没有 signal.SIGALRM/signal.alarm，step2graph_ncti.process_one_file
    用它们做单文件超时保护。这里打桩成空操作（signal.signal 校验参数必须是真实信号，
    不能像 SIGINT 那样直接赋一个任意整数给 SIGALRM，所以用哨兵对象 + 包装函数，只在
    遇到这个哨兵时短路，其他信号仍走原始 signal.signal），让该模块在 Windows 上能
    正常跑（代价是失去单文件解析卡死时的强制超时保护，桌面规模数据集下可接受）。"""
    import signal
    if hasattr(signal, "SIGALRM"):
        return
    sentinel = object()
    signal.SIGALRM = sentinel
    original_signal = signal.signal

    def _signal_stub(signalnum, handler):
        if signalnum is sentinel:
            return None
        return original_signal(signalnum, handler)

    signal.signal = _signal_stub
    signal.alarm = lambda seconds: 0


def load_json_or_pkl(pathname):
    # try to load dataset from pickel first
    pkl_path = str(pathname).split('.')[0] + '.pkl'
    if os.path.exists(pkl_path):
        return torch.load(pkl_path)
    else:  # if no pkl exists, load from json
        with open(pathname, "r", encoding="utf-8") as fp:
            return json.load(fp)


def load_one_graph(fn, data):
    # Create the graph using the edges and number of nodes
    edges = tuple(data['graph']['edges'])
    num_nodes = data['graph']['num_nodes']
    dgl_graph = dgl.graph(edges, num_nodes=num_nodes)

    # Convert node attributes to PyTorch tensors and add them to the graph
    node_attributes = data['graph_face_attr']
    node_attributes = np.array(node_attributes)
    node_attributes = torch.from_numpy(node_attributes).type(torch.float32)
    dgl_graph.ndata["x"] = node_attributes

    # Convert and add node grid attributes if they are present
    node_grid_attributes = data['graph_face_grid']
    if len(node_grid_attributes) > 0:
        node_grid_attributes = np.array(node_grid_attributes)
        node_grid_attributes = torch.from_numpy(node_grid_attributes).type(torch.float32)
        dgl_graph.ndata["grid"] = node_grid_attributes

    # Convert edge attributes to PyTorch tensors and add them to the graph
    edge_attributes = data['graph_edge_attr']
    edge_attributes = np.array(edge_attributes)
    edge_attributes = torch.from_numpy(edge_attributes).type(torch.float32)
    dgl_graph.edata["x"] = edge_attributes

    # Convert and add edge grid attributes if they are present
    edge_grid_attributes = data['graph_edge_grid']
    if len(edge_grid_attributes) > 0:
        edge_grid_attributes = np.array(edge_grid_attributes)
        edge_grid_attributes = torch.from_numpy(edge_grid_attributes).type(torch.float32)
        dgl_graph.edata["grid"] = edge_grid_attributes

    sample = {"graph": dgl_graph, "filename": fn}
    return sample


def load_split_filelist(split):
    """
    加载指定数据分割的文件名列表

    参数:
        split (str): 数据分割名称（"train"、"val"、"test" 或 "all"）

    返回:
        List[str]: 文件名列表
    """
    config = load_config_basic()
    divide_data_infos_path = config['data_path_infos']['divide_data_infos']['divide_result_txt_save_dir']
    if split == "all":
        with open(os.path.join(divide_data_infos_path, 'train.txt'), 'r', encoding='utf-8') as f:
            train_filelist = f.readlines()
            train_filelist = [x.strip() for x in train_filelist]
        with open(os.path.join(divide_data_infos_path, 'val.txt'), 'r', encoding='utf-8') as f:
            valid_filelist = f.readlines()
            valid_filelist = [x.strip() for x in valid_filelist]
        with open(os.path.join(divide_data_infos_path, 'test.txt'), 'r', encoding='utf-8') as f:
            test_filelist = f.readlines()
            test_filelist = [x.strip() for x in test_filelist]
        assert len(train_filelist) != 0 and len(valid_filelist) != 0 and len(test_filelist) != 0, \
            'have empty partition file'
        split_filelist = train_filelist + valid_filelist + test_filelist
    else:
        with open(os.path.join(divide_data_infos_path, split + '.txt'), 'r', encoding='utf-8') as f:
            split_filelist = f.readlines()
        assert len(split_filelist) != 0, 'have empty partition file'
    split_filelist = [x.strip() for x in split_filelist]
    return split_filelist


def load_statistics(stat_path):
    stat = load_json_or_pkl(stat_path)
    mean_face_attr = np.array(stat['mean_face_attr'])
    std_face_attr = np.array(stat['std_face_attr'])
    mean_edge_attr = np.array(stat['mean_edge_attr'])
    std_edge_attr = np.array(stat['std_edge_attr'])
    stat['mean_face_attr'] = torch.from_numpy(mean_face_attr)
    stat['std_face_attr'] = torch.from_numpy(std_face_attr)
    stat['mean_edge_attr'] = torch.from_numpy(mean_edge_attr)
    stat['std_edge_attr'] = torch.from_numpy(std_edge_attr)
    # if the std is 0, we set the std to 1
    eps = 1e-8
    stat['std_face_attr'][stat['std_face_attr'] < eps] = 1.
    stat['std_edge_attr'][stat['std_edge_attr'] < eps] = 1.
    return stat
