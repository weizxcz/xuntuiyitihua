
import os
import gc
import logging
from itertools import repeat
from multiprocessing.pool import Pool
from tqdm import tqdm
from pathlib import Path
from src.utils.base_functions import load_config_basic,save_json_data,initializer,init_ncti,load_json
from src.utils.step2graph_tools_ncti import AAGGraphExtraToolNcti,find_standardization,check_zero_std
from src.data_utils.processors.divide_train_val_test import get_train_val_test_info
NCTI = init_ncti()

def _convert_ncti_to_standard_format(agg_data):
    """
    将NCTI的agg_data转换为标准格式
    """
    if isinstance(agg_data, dict) and 'graph' in agg_data:
        standard_data = {
            'graph': agg_data.get('graph', {'edges': ([], []), 'num_nodes': 0}),
            'graph_face_attr': agg_data.get('graph_face_attr', []),
            'graph_face_grid': agg_data.get('graph_face_grid', []),
            'graph_edge_attr': agg_data.get('graph_edge_attr', []),
            'graph_edge_grid': [],
        }
        return standard_data

    # 处理非标准格式的兼容逻辑
    try:
        agg_dict = agg_data.__dict__ if hasattr(agg_data, '__dict__') else agg_data
        standard_data = {
            'graph': {'edges': ([], []), 'num_nodes': 0},
            'graph_face_attr': agg_dict.get('graph_face_attr', []),
            'graph_face_grid': [],
            'graph_edge_attr': agg_dict.get('graph_edge_attr', []),
            'graph_edge_grid': [],
        }
        return standard_data
    except Exception as e:
        logging.error(f"Error converting NCTI data to standard format: {e}")
        return None

def extractor_step2graph_ncti(NCTI,step_path):
    """
    提取step文件并转换为标准graph格式
    """
    try:
        graph_tool = AAGGraphExtraToolNcti(NCTI, step_path)
        graph = graph_tool.get_graph()
        graph_edge_attr = graph_tool.get_graph_edge_attr()
        graph_face_attr = graph_tool.get_graph_face_attr()
        graph_face_grid = graph_tool.get_graph_face_grid()
        agg_data = {
                'graph': graph,
                'graph_face_attr': graph_face_attr,
                'graph_face_grid': graph_face_grid,
                'graph_edge_attr': graph_edge_attr,
                'graph_edge_grid':[]
            }
        return _convert_ncti_to_standard_format(agg_data)
    except Exception as e:
        logging.error(f"Error processing {step_path} with NCTI: {e}")
        return None


def process_one_file(args):
    """
    处理单个step文件：
    1. 检查目标JSON是否已存在（避免覆盖）
    2. 生成graph并保存
    """
    # 第一步：检查JSON是否已存在（核心：避免覆盖
    global NCTI
    step_path,dataset_name = args
    config = load_config_basic()
    output_graphs_dir = config['data_path_infos']['processed_graph_data']
    if not config['data_path_infos']['use_absolute_path']:
        current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        output_graphs_dir = os.path.join(current_dir, output_graphs_dir)
    os.makedirs(output_graphs_dir, exist_ok=True)
    json_filename = f"{step_path.stem}.json"
    json_path = os.path.join(output_graphs_dir,json_filename)
    if os.path.exists(json_path):
        logging.info(f"⚠️  跳过 [{dataset_name}] 的 {json_filename}：{json_path} 已存在（防止覆盖）")
        graph_data = load_json(json_path)
    else:
        graph_data = extractor_step2graph_ncti(NCTI, step_path)
        if graph_data is not None:
            save_json_data(json_path, graph_data)
        else:
            logging.warning(f"❌ 处理 [{dataset_name}] 的 {step_path.stem} 失败：NCTI返回空数据")
            return None
    if dataset_name == "train":
        stat_data = {
            "graph_face_attr": graph_data["graph_face_attr"],
            "graph_edge_attr": graph_data["graph_edge_attr"]
        }
        del graph_data
        gc.collect()
        return [str(step_path.stem), stat_data]
    else:
        del graph_data
        gc.collect()
        return None
    

def load_all_dataset_file_sets(datasets_config, step_path_list):
    """
    加载所有数据集的文件名集合，并过滤出存在的step文件
    Args:
        datasets_config (list): 数据集配置列表（含name和file_list_path）
        step_path_list (list): step文件存放目录列表，可能包含开源数据或真实数据路径
    Returns:
        dataset_file_sets (dict): 键为数据集名，值为该数据集下存在的step文件名集合
        all_filtered_files (dict): 键为数据集名，值为该数据集下的step文件路径列表
    """
    all_filtered_files = {}  # 存储每个数据集的step文件路径
    all_step_filenames = set()
    for step_dir in step_path_list:
        all_step_filenames.update({sf.stem for sf in Path(step_dir).glob("*.st*p")})  # 所有存在的step文件名

    for dataset in datasets_config:
        ds_name = dataset["name"]
        ds_txt_path = dataset["file_list_path"]

        # 加载txt中的文件名
        ds_txt_files = set()
        if os.path.exists(ds_txt_path):
            with open(ds_txt_path, "r", encoding="utf-8") as f:
                for line in f:
                    fn = line.strip()
                    if fn:
                        ds_txt_files.add(fn)
        else:
            logging.warning(f"警告：{ds_name} 的txt文件 {ds_txt_path} 不存在，跳过该数据集")
            continue

        # 过滤：仅保留存在step文件的文件名
        ds_exist_files = ds_txt_files & all_step_filenames

        # 收集该数据集的step文件路径
        ds_step_files = []
        for step_dir in step_path_list:
            ds_step_files.extend([sf for sf in Path(step_dir).glob("*.st*p") if sf.stem in ds_exist_files])
        all_filtered_files[ds_name] = ds_step_files

        logging.info(f"\n{ds_name} 数据集：")
        logging.info(f"  - txt中定义 {len(ds_txt_files)} 个文件")
        logging.info(f"  - 实际存在 {len(ds_exist_files)} 个step文件")

    return all_filtered_files


def profile_step2graph_parallel(all_filtered_files,train_val_test_info_list):
    config = load_config_basic()
    graphs_save_dir = config['data_path_infos']['processed_graph_data']
    num_workers = config['step2graph_infos']['num_workers']
    if not config['data_path_infos']['use_absolute_path']:
        current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        graphs_save_dir = os.path.join(current_dir, graphs_save_dir)
    train_stat_results = []
    for dataset in train_val_test_info_list:
        ds_name = dataset["name"]
        ds_step_files = all_filtered_files.get(ds_name, [])
        if not ds_step_files:
            logging.info(f"\n【{ds_name}】无有效step文件，跳过")
            continue
        logging.info(f"\n【第二步：处理 {ds_name} 数据集】")
        logging.info(f"需处理 {len(ds_step_files)} 个step文件")
        batch_size = min(100, len(ds_step_files))
        total_batches = (len(ds_step_files) - 1) // batch_size + 1
        for batch_idx in range(total_batches):
            start = batch_idx * batch_size
            end = min((batch_idx + 1) * batch_size, len(ds_step_files))
            batch_files = ds_step_files[start:end]
            logging.info(f"\n{ds_name} - 批次 {batch_idx + 1}/{total_batches}：处理 {len(batch_files)} 个文件")
            process_args = zip(
                batch_files,
                repeat(ds_name)
            )
            with Pool(processes=num_workers, initializer=initializer) as pool:
                try:
                    for result in tqdm(
                            pool.imap_unordered(process_one_file, process_args),
                            total=len(batch_files),
                            desc=f"{ds_name} 批次 {batch_idx + 1} 进度"
                    ):
                        if result is not None and ds_name == "train":
                            train_stat_results.append(result)
                except KeyboardInterrupt:
                    logging.error(f"\n用户中断 {ds_name} 批次 {batch_idx + 1} 处理")
                    break
                finally:
                    pool.close()
                    pool.join()
            gc.collect()
    return train_stat_results

def generate_attr_standardization(train_stat_results):
    config = load_config_basic()
    attr_stat_path = config['step2graph_infos']['attr_standard_data_path']
    if not config['data_path_infos']['use_absolute_path']:
        current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        attr_stat_path = os.path.join(current_dir, attr_stat_path)
    attr_stat = find_standardization(train_stat_results)
    check_zero_std(attr_stat)
    save_json_data(attr_stat_path, attr_stat)

def step2graph_batch():
    config = load_config_basic()
    train_val_test_info_list = get_train_val_test_info()
    use_public_data = config['data_path_infos']['use_public_data']
    use_real_data = config['data_path_infos']['use_real_data']
    use_step_dir = []
    if use_public_data:
        step_dir = config['data_path_infos']['public_data_path_infos']['raw_step_data']
        if not config['data_path_infos']['use_absolute_path']:
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            step_dir = os.path.join(current_dir, step_dir)
        use_step_dir.append(step_dir)
    if use_real_data:
        step_dir = config['data_path_infos']['real_data_path_infos']['raw_step_data']
        if not config['data_path_infos']['use_absolute_path']:
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            step_dir = os.path.join(current_dir, step_dir)
        use_step_dir.append(step_dir)
    if len(use_step_dir) == 0:
        logging.error("❌ 未配置任何step数据集路径，无法进行step文件处理")
        return
    
    all_filtered_files = load_all_dataset_file_sets(train_val_test_info_list, use_step_dir)
    train_stat_results = profile_step2graph_parallel(all_filtered_files,train_val_test_info_list)
    generate_attr_standardization(train_stat_results)


    
    
        

