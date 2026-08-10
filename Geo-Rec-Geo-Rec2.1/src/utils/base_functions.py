import os
import sys
import ctypes
import importlib
import yaml
import os
import logging
import json
from typing import Dict, Any
from datetime import datetime
import torch
import dgl
import numpy as np


def load_yaml(file_path: str) -> Dict[str, Any]:
    """加载YAML配置文件"""
    with open(file_path, 'r', encoding='utf-8') as file:
        config = yaml.safe_load(file)
    return config

def load_config_basic() -> Dict[str, Any]:
    """
    基础加载YAML配置
    """
    current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    config_path = os.path.join(current_dir, 'configs', 'configs.yaml')
    config = load_yaml(config_path)
    return config

def init_ncti():
    """初始化NCTI环境，支持 Windows 和 Linux"""
    config = load_config_basic()
    try:
        Ncti_api_path = config['ncti_path_config']['Ncti_api_path']
        dllpath = config['ncti_path_config']['dllpath']
        sys.path.insert(0, dllpath)

        if os.name == 'nt':  # Windows
            os.add_dll_directory(Ncti_api_path)
            ctypes.CDLL(os.path.join(dllpath, "ncti_command.dll"))
            ctypes.CDLL(os.path.join(dllpath, "ncti_doc_occ.dll"))
            ctypes.CDLL(os.path.join(dllpath, "ncti_occ_plugin.dll"))
            ctypes.CDLL(os.path.join(dllpath, "ncti_window.dll"))
            NCTI = importlib.import_module("ncti_python")
        else:  # Linux
            ctypes.CDLL(os.path.join(dllpath, "libncti.so"))
            ctypes.CDLL(os.path.join(dllpath, "libncti_base.so"))
            ctypes.CDLL(os.path.join(dllpath, "libncti_object.so"))
            ctypes.CDLL(os.path.join(dllpath, "libncti_pubfun.so"))
            ctypes.CDLL(os.path.join(dllpath, "libncti_command.so"))
            ctypes.CDLL(os.path.join(dllpath, "libncti_occ_plugin.so"))
            NCTI = importlib.import_module("libncti_python")
        NCTI.Init(dllpath)
        return NCTI
    except Exception as e:
        print(f"初始化NCTI环境时出错: {e}")
        return None


def setup_logging():

    """设置日志记录"""
    config = load_config_basic()
    current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    log_dir_config = config['logs_infos']['log_dir']
    task_name = config['recognize_task_infos']['name']
    # 创建log文件夹（如果不存在）
    log_dir = os.path.join(current_dir, log_dir_config,task_name)
    os.makedirs(log_dir, exist_ok=True)

    # 生成带时间戳的日志文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"{log_dir}/run_{timestamp}.log"

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename,encoding='utf-8'),  # 输出到文件
            logging.StreamHandler()  # 同时输出到控制台（可选）
        ]
    )

def save_json_data(pathname, data):
    """保存数据到JSON文件"""
    with open(pathname, 'w', encoding='utf8') as fp:
        json.dump(data, fp, indent=4, ensure_ascii=False, sort_keys=False)

def load_json(pathname):
    with open(pathname, "r") as fp:
        return json.load(fp)
    
def initializer():
    import signal
    """忽略子进程中的CTRL+C信号"""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    global NCTI
    NCTI = init_ncti()

def load_json_or_pkl(pathname):
    # try to load dataset from pickel first
    pkl_path = str(pathname).split('.')[0] + '.pkl'
    if os.path.exists(pkl_path):
        return torch.load(pkl_path)
    else: # if no pkl exists, load from json
        with open(pathname, "r") as fp:
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
        use_absolute_path = config['data_path_infos']['use_absolute_path']
        divide_data_infos_path = config['data_path_infos']['divide_data_infos']['divide_result_txt_save_dir']
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if not use_absolute_path:
            divide_data_infos_path = os.path.join(base_dir, divide_data_infos_path)
        if split == "all":
            with open(os.path.join(divide_data_infos_path, 'train.txt'), 'r') as f:
                train_filelist = f.readlines()
                train_filelist = [x.strip() for x in train_filelist]
            with open(os.path.join(divide_data_infos_path, 'val.txt'), 'r') as f:
                valid_filelist = f.readlines()
                valid_filelist = [x.strip() for x in valid_filelist]
            with open(os.path.join(divide_data_infos_path, 'test.txt'), 'r') as f:
                test_filelist = f.readlines()
                test_filelist = [x.strip() for x in test_filelist]
            assert len(train_filelist) != 0 and len(valid_filelist) != 0 and len(test_filelist) != 0, \
                'have empty partition file'
            split_filelist = train_filelist + valid_filelist + test_filelist
        else:
            with open(os.path.join(divide_data_infos_path, split + '.txt'), 'r') as f:
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

if __name__ == "__main__":
    NCTI = init_ncti()
    if NCTI is None:
        print("NCTI初始化失败，程序终止。")
        sys.exit(1)