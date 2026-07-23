
import os
import json
from tqdm import tqdm
import logging
from ..base_functions import load_config_basic


def get_data_paths(data_type):
    """获取数据路径信息

    Args:
        data_type: "public" 或 "real"，对应公开数据集和真实数据集

    Returns:
        (config, source_dir, target_dir)
    """
    config = load_config_basic()

    if data_type == "public":
        raw_key = 'public_data_path_infos'
    elif data_type == "real":
        raw_key = 'real_data_path_infos'
    else:
        raise ValueError(f"未知的 data_type: {data_type}，应为 'public' 或 'real'")

    source_dir = config['data_path_infos'][raw_key]['raw_label_data']
    target_dir = config['data_path_infos']['processed_label_data']
    return config, source_dir, target_dir


def parse_seg_inst(data, data_type):
    """从 JSON 数据中提取 seg、inst、bottom，统一为 (seg_dict, inst_matrix, file_id, bottom_dict) 格式

    支持两种格式：
    - 公开数据: [["file_id", {"seg": {...}, "inst": [[...]], "bottom": {...}}]]
    - 真实数据: [{"part_id": ..., "source_file": "...", "seg": {...}, "inst": [[...]], "bottom": {...}}]

    Args:
        data: 已解析的 JSON 数据
        data_type: "public" 或 "real"

    Returns:
        (seg_dict, inst_matrix, file_id, bottom_dict)
    """
    if isinstance(data, list) and len(data) > 0:
        inner = data[0]
        if isinstance(inner, list):
            # 公开数据格式: [["file_id", {"seg": {...}, ...}]]
            seg_dict = inner[1]["seg"]
            inst_matrix = inner[1]["inst"]
            file_id = inner[0]
            bottom_dict = inner[1].get("bottom", None)
        elif isinstance(inner, dict):
            # 真实数据格式: [{"part_id": ..., "seg": {...}, ...}]
            seg_dict = inner["seg"]
            inst_matrix = inner["inst"]
            source_file = inner.get("source_file", "")
            file_id = os.path.splitext(os.path.basename(source_file))[0] if source_file else str(inner.get("part_id", ""))
            bottom_dict = inner.get("bottom", None)
        else:
            raise ValueError(f"未知的 JSON 内部格式: {type(inner)}")
    elif isinstance(data, dict):
        # 兜底：顶层直接就是 dict
        seg_dict = data["seg"]
        inst_matrix = data["inst"]
        source_file = data.get("source_file", "")
        file_id = os.path.splitext(os.path.basename(source_file))[0] if source_file else ""
        bottom_dict = data.get("bottom", None)
    else:
        raise ValueError(f"未知的 JSON 数据格式: {type(data)}")
    return seg_dict, inst_matrix, file_id, bottom_dict


def filter_and_binarize(seg_dict, inst_matrix, label_index):
    """对 seg/inst 执行过滤和二值化

    - seg: 值为 label_index 的改为 1，其余改为 0
    - inst: 只保留 seg=label_index 对应面的行

    Args:
        seg_dict: {"0": 0, "1": 12, ...} 会被原地修改
        inst_matrix: [[0,...], [0,...], ...]
        label_index: 目标标签索引（如 12）

    Returns:
        (has_label, face_count) — 是否包含目标标签，面总数
    """
    has_label = any(v == label_index for v in seg_dict.values())
    if not has_label:
        return False, 0

    face_count = len(seg_dict)
    inst_rows = len(inst_matrix)
    inst_cols = len(inst_matrix[0]) if inst_rows > 0 else 0

    target_indices = [i for i in range(face_count) if seg_dict[str(i)] == label_index]

    # 过滤 inst
    new_inst = [[0] * inst_cols for _ in range(inst_rows)]
    for face_idx in target_indices:
        if 0 <= face_idx < inst_rows and 0 <= face_idx < inst_cols:
            new_inst[face_idx] = inst_matrix[face_idx]

    # seg 二值化
    for key in seg_dict:
        seg_dict[key] = 1 if seg_dict[key] == label_index else 0

    return True, face_count, new_inst


# ========== 主处理函数 ==========

def process_labels(data_type):
    """通用的标签处理主函数

    Args:
        data_type: "public" 或 "real"

    Returns:
        True/False
    """
    data_label = "开源数据" if data_type == "public" else "真实数据"
    config, source_dir, target_dir = get_data_paths(data_type)
    label_index = config['recognize_task_infos']['index_num']

    logging.info(f"=================={data_label}label信息开始处理==========================")

    if not os.path.exists(source_dir):
        logging.error(f"错误：源文件夹 {source_dir} 不存在，请检查路径！")
        return False
    os.makedirs(target_dir, exist_ok=True)
    logging.info(f"已创建/确认目标文件夹：{target_dir}")

    json_files = [f for f in os.listdir(source_dir) if f.endswith(".json")]
    if not json_files:
        logging.error(f"在 {source_dir} 中没有找到JSON文件")
        return False

    # ========== 处理标签并写出 ==========
    processed_count = 0
    with tqdm(total=len(json_files), desc=f"处理{data_label}标签", unit="file") as pbar:
        for filename in json_files:
            source_path = os.path.join(source_dir, filename)
            target_path = os.path.join(target_dir, filename)
            try:
                with open(source_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # 解析不同格式的 JSON，统一提取 seg/inst/file_id/bottom
                seg_dict, inst_matrix, file_id, bottom_dict = parse_seg_inst(data, data_type)

                # 过滤 + 二值化
                result = filter_and_binarize(seg_dict, inst_matrix, label_index)
                if not result[0]:
                    logging.info(f"跳过 {filename} (无seg={label_index})")
                    pbar.update(1)
                    continue

                _, face_count, new_inst = result

                logging.info(f"{data_label}：{filename}文件包含 {face_count} 个面")

                # bottom 字段：优先用真实标注，缺失时补全0
                if bottom_dict is not None:
                    bottom = bottom_dict
                else:
                    bottom = {str(i): 0 for i in range(face_count)}

                # 统一输出格式: [[file_id, {seg, inst, bottom}]]
                output_data = [[file_id, {"seg": seg_dict, "inst": new_inst, "bottom": bottom}]]

                with open(target_path, "w", encoding="utf-8") as f:
                    json.dump(output_data, f, ensure_ascii=False, indent=2)

                processed_count += 1
                pbar.set_postfix_str(f"处理 {filename}")
                pbar.update(1)

            except Exception as e:
                logging.error(f"处理文件 {filename} 时出错：{str(e)}")
                pbar.update(1)

    logging.info(f"=================={data_label}label信息处理完成，共处理 {processed_count} 个文件==========================")
    return True
