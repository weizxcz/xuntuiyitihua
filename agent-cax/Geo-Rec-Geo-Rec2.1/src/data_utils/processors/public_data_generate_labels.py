import os
import json
import numpy as np
from tqdm import tqdm
import logging
from src.utils.base_functions import load_config_basic



def get_data_path_infos():
    """获取数据路径信息"""
    config = load_config_basic()
    use_absolute_path = config['data_path_infos']['use_absolute_path']
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    if use_absolute_path:
        source_dir = config['data_path_infos']['public_data_path_infos']['raw_label_data']
        target_dir = config['data_path_infos']['processed_label_data']
    else:
        source_dir = os.path.join(base_dir, config['data_path_infos']['public_data_path_infos']['raw_label_data'])
        target_dir = os.path.join(base_dir, config['data_path_infos']['processed_label_data'])
    return config,source_dir, target_dir



def process_round_json_files():
    """处理JSON文件，提取seg值为label_index的部分并保存到新文件夹"""
    config,source_dir, target_dir = get_data_path_infos()
    label_index_raw = config['recognize_task_infos']['index_num']
    label_index_list = label_index_raw if isinstance(label_index_raw, list) else [label_index_raw]
    logging.info("==================开源数据label信息开始处理==========================")
    if not os.path.exists(source_dir):
        logging.error(f"错误：源文件夹 {source_dir} 不存在，请检查路径！")
        return False
    os.makedirs(target_dir, exist_ok=True)
    logging.info(f"已创建/确认目标文件夹：{target_dir}")

    # 获取所有JSON文件列表
    json_files = [f for f in os.listdir(source_dir) if f.endswith(".json")]
    if not json_files:
        logging.error(f"在 {source_dir} 中没有找到JSON文件")
        return False

    # 使用tqdm创建进度条
    processed_count = 0
    with tqdm(total=len(json_files), desc="处理JSON文件", unit="file") as pbar:
        for filename in json_files:
            source_path = os.path.join(source_dir, filename)
            target_path = os.path.join(target_dir, filename)
            try:
                # 读取原始 JSON 文件
                with open(source_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # 定位到 "seg" 对应的字典
                seg_dict = data[0][1]["seg"]

                # 检查是否存在值为 label_index_list 中任一值的 seg
                has_label_index = any(value in label_index_list for value in seg_dict.values())
                if not has_label_index:
                    logging.info(f"跳过 {filename} (无seg={label_index_list})")
                    pbar.update(1)
                    continue

                # 定位到 "inst" 对应的矩阵，获取其维度（与面数一致）
                inst_matrix = data[0][1]["inst"]
                inst_rows = len(inst_matrix)
                inst_cols = len(inst_matrix[0]) if inst_rows > 0 else 0

                # 将 seg 字典转换为列表，便于索引操作（确保顺序与面索引一致）
                seg_list = [seg_dict[str(i)] for i in range(len(seg_dict))]
                face_count = len(seg_list)
                logging.info(f"开源数据：{filename}文件包含 {face_count} 个面")

                # 找出 seg 中值在 label_index_list 中的索引位置（这些面最终会被标记为1）
                target_indices = [i for i, val in enumerate(seg_list) if val in label_index_list]

                new_inst = [[0] * inst_cols for _ in range(inst_rows)]
                for face_idx in target_indices:
                    if 0 <= face_idx < inst_rows and 0 <= face_idx < inst_cols:
                        new_inst[face_idx][face_idx] = 1

                data[0][1]["inst"] = new_inst

                # 遍历 seg 字典，将值在 label_index_list 中的改为 1，其他改为 0
                for key in seg_dict:
                    seg_dict[key] = 1 if seg_dict[key] in label_index_list else 0

                with open(target_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)

                processed_count += 1
                pbar.set_postfix_str(f"处理 {filename}")
                pbar.update(1)

            except Exception as e:
                logging.error(f"\n处理文件 {filename} 时出错：{str(e)}")
                pbar.update(1)
    logging.info("==================开源数据label信息处理完成==========================")
    return True



if __name__ == "__main__":
    process_round_json_files()