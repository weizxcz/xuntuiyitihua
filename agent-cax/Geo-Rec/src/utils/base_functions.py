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

def _replace_path_prefix(obj, old_prefix, new_prefix):
    """递归遍历配置字典，替换所有以 old_prefix 开头的字符串路径值"""
    if isinstance(obj, dict):
        for key in obj:
            if isinstance(obj[key], str) and obj[key].startswith(old_prefix):
                obj[key] = new_prefix + obj[key][len(old_prefix):]
            elif isinstance(obj[key], (dict, list)):
                _replace_path_prefix(obj[key], old_prefix, new_prefix)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, str) and item.startswith(old_prefix):
                obj[i] = new_prefix + item[len(old_prefix):]
            elif isinstance(item, (dict, list)):
                _replace_path_prefix(item, old_prefix, new_prefix)


def _add_date_prefix_to_processed_paths(config):
    """自动为 processed_data 及其相关路径添加日期前缀

    例如：/data/data2/processed_data/true_blind_hole
      →  /data/data2/processed_data/2026-06-04_true_blind_hole
    所有以 processed_data 路径为前缀的配置项（labels、graphs、splits 等）都会同步更新。
    """
    processed_data_path = config.get('data_path_infos', {}).get('processed_data')
    if not processed_data_path:
        return

    parent_dir = os.path.dirname(processed_data_path)
    folder_name = os.path.basename(processed_data_path)
    date_str = datetime.now().strftime("%Y-%m-%d")

    # 如果目录名已经以日期开头（如 2026-06-04_xxx），则不再重复添加
    if folder_name.startswith(date_str) or (len(folder_name) > 10 and folder_name[4] == '-' and folder_name[7] == '-'):
        return

    dated_folder = f"{date_str}_{folder_name}"
    dated_base = os.path.join(parent_dir, dated_folder)

    # 递归替换配置中所有以原路径开头的字符串
    _replace_path_prefix(config, processed_data_path, dated_base)


def load_config_basic() -> Dict[str, Any]:
    """
    基础加载YAML配置，自动为 processed_data 路径添加日期前缀
    """
    current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    config_path = os.path.join(current_dir, 'configs', 'configs.yaml')
    config = load_yaml(config_path)
    _add_date_prefix_to_processed_paths(config)
    return config

def _load_ncti_python_module(dllpath, py_version):
    """加载 NCTI 的 python 绑定模块。

    兼容两种 SDK 命名约定：
    - 新版（2026.2.0+）：文件 libncti_python311.so，导出函数 PyInit_ncti_python
    - 老版：文件 libncti_python.so，导出函数 PyInit_libncti_python

    因为 .so 文件名与 PyInit 函数名可能不一致，普通 import 会失败，
    所以这里按文件路径加载，并枚举可能的模块名匹配其内部导出函数。
    """
    import importlib.util

    # 候选：(库文件名, 对应的模块名/PyInit 后缀)
    candidates = [
        (f"libncti_python{py_version}.so", [f"libncti_python{py_version}", "ncti_python"]),
        ("libncti_python.so", ["libncti_python", "ncti_python"]),
    ]
    last_error = None
    for lib_name, mod_names in candidates:
        lib_path = os.path.join(dllpath, lib_name)
        if not os.path.exists(lib_path):
            continue
        for mod_name in mod_names:
            try:
                spec = importlib.util.spec_from_file_location(mod_name, lib_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module
            except ImportError as e:
                last_error = e
                continue
            except Exception as e:
                last_error = e
                continue
    raise ImportError(f"无法加载 NCTI python 绑定库（{dllpath}），最后错误: {last_error}")


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
            # 将 SDK 目录加入动态库搜索路径，并按依赖顺序加载所有 libncti*.so。
            # 用 RTLD_GLOBAL 让符号全局可见，避免 "undefined symbol" 报错
            # （新版 SDK 的 libncti_python 依赖 libncti_render / libncti_plugin /
            #   libncti_PluginManager / libncti_authorization 等多个库）。
            os.environ['LD_LIBRARY_PATH'] = dllpath + os.pathsep + os.environ.get('LD_LIBRARY_PATH', '')
            # 重要：LD_LIBRARY_PATH 必须在 python 进程启动前就指向正确的 SDK 目录，
            # 否则若环境里残留了其它版本 SDK 的路径，会导致库 ABI 不匹配（undefined symbol）。
            current_ld = os.environ.get('LD_LIBRARY_PATH', '')
            if dllpath not in current_ld.split(os.pathsep):
                print(f"[警告] LD_LIBRARY_PATH 未包含当前 SDK 目录，建议启动前执行：\n"
                      f"  export LD_LIBRARY_PATH={dllpath}:$LD_LIBRARY_PATH")
            # 按 python 版本选择对应的 libncti_python 库
            py_version = f"{sys.version_info.major}{sys.version_info.minor}"
            load_order = [
                "libncti_base.so",
                "libncti.so",
                "libncti_authorization.so",
                "libncti_render.so",
                "libncti_geom_engine.so",
                "libncti_PluginManager.so",
                "libncti_plugin.so",
                "libncti_object.so",
                "libncti_pubfun.so",
                "libncti_occ_plugin.so",
                "libncti_doc_occ.so",
                "libncti_command.so",
            ]
            for lib_name in load_order:
                lib_path = os.path.join(dllpath, lib_name)
                if os.path.exists(lib_path):
                    ctypes.CDLL(lib_path, mode=ctypes.RTLD_GLOBAL)
            # 加载 python 绑定库。新版 SDK 按版本命名（libncti_python311.so），
            # 但其内部导出函数为 PyInit_ncti_python（无 lib 前缀/版本号），
            # 因此不能用普通 import（会因文件名与 PyInit 名不匹配而失败），
            # 需用 importlib 按文件路径加载并指定模块名 "ncti_python"。
            NCTI = _load_ncti_python_module(dllpath, py_version)
        NCTI.Init(dllpath)
        return NCTI
    except Exception as e:
        print(f"初始化NCTI环境时出错: {e}")
        return None


def setup_logging():
    """设置日志记录"""
    config = load_config_basic()
    log_dir_config = config['logs_infos']['log_dir']
    task_name = config['recognize_task_infos']['name']

    # 处理绝对/相对路径
    use_absolute_path = config['data_path_infos'].get('use_absolute_path', True)
    if use_absolute_path:
        log_dir = os.path.join(log_dir_config, task_name)
    else:
        current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        log_dir = os.path.join(current_dir, log_dir_config, task_name)

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