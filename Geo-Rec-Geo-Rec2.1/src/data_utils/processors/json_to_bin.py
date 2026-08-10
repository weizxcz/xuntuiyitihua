"""
将 MFR 格式的 JSON 图数据转换为 DGL 二进制格式，供 CADSynth 数据集加载。
来源：BrepMFR-main/data/json_to_bin.py
"""
import os
import json
import logging
import numpy as np
import torch
import dgl
from dgl.data.utils import save_graphs

from src.utils.base_functions import load_config_basic


def _convert_single_json_to_bin(json_path, output_bin_path):
    """
    将单个 JSON 文件转换为 DGL 二进制格式。

    Args:
        json_path: JSON 文件路径
        output_bin_path: 输出 bin 文件路径

    Returns:
        bool: 是否成功
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        json_data = json.load(f)

    graph_info = json_data["graph"]
    num_nodes = graph_info["num_nodes"]
    src_nodes = graph_info["src_nodes"]
    dst_nodes = graph_info["dst_nodes"]

    graph = dgl.graph((src_nodes, dst_nodes), num_nodes=num_nodes)

    node_data = json_data.get("node_data", {})
    for key, value in node_data.items():
        np_array = np.array(value)
        if key == "x":
            graph.ndata[key] = torch.tensor(np_array, dtype=torch.float32)
        elif key == "y":
            graph.ndata[key] = torch.tensor(np_array, dtype=torch.float32)
        elif key == "f":
            graph.ndata[key] = torch.tensor(np_array, dtype=torch.int64)
        else:
            graph.ndata[key] = torch.tensor(np_array, dtype=torch.int64)

    edge_data = json_data.get("edge_data", {})
    for key, value in edge_data.items():
        np_array = np.array(value)
        if key == "x":
            graph.edata[key] = torch.tensor(np_array, dtype=torch.float32)
        elif key == "l":
            graph.edata[key] = torch.tensor(np_array, dtype=torch.float32)
        elif key == "a":
            graph.edata[key] = torch.tensor(np_array, dtype=torch.float32)
        else:
            graph.edata[key] = torch.tensor(np_array, dtype=torch.int64)

    graph_labels = json_data.get("graph_labels", {})
    labels_dict = {}
    for key, value in graph_labels.items():
        np_array = np.array(value)
        if key in ["d2_distance", "angle_distance"]:
            labels_dict[key] = torch.tensor(np_array, dtype=torch.float32)
        else:
            labels_dict[key] = torch.tensor(np_array, dtype=torch.int64)

    save_graphs(output_bin_path, [graph], labels_dict)
    return True


def _resolve_mfr_json_bin_paths(config, path_set="default"):
    """按路径集合解析 JSON 输入目录与 bin 输出目录。"""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    use_absolute = config["data_path_infos"]["use_absolute_path"]
    mfr_data_infos = config["data_path_infos"]["mfr_data_infos"]

    if path_set == "adv_unlabeled":
        json_dir = mfr_data_infos.get("adv_unlabeled_graphs_mfr_json", mfr_data_infos["graphs_mfr_json"])
        output_dir = mfr_data_infos.get("adv_unlabeled_bin_data", mfr_data_infos["bin_data"])
    else:
        json_dir = mfr_data_infos["graphs_mfr_json"]
        output_dir = mfr_data_infos["bin_data"]

    if not use_absolute:
        json_dir = os.path.join(base_dir, json_dir)
        output_dir = os.path.join(base_dir, output_dir)
    return json_dir, output_dir


def json_to_bin_batch(path_set="default"):
    """批量将 MFR JSON 图转换为 DGL bin 格式。"""
    config = load_config_basic()
    json_dir, output_dir = _resolve_mfr_json_bin_paths(config, path_set=path_set)

    if not os.path.exists(json_dir):
        logging.error(f"MFR JSON 目录不存在: {json_dir}")
        return

    os.makedirs(output_dir, exist_ok=True)
    success_count = 0
    fail_count = 0

    for filename in os.listdir(json_dir):
        if not filename.endswith('.json'):
            continue
        json_path = os.path.join(json_dir, filename)
        bin_filename = os.path.splitext(filename)[0] + '.bin'
        bin_path = os.path.join(output_dir, bin_filename)
        try:
            _convert_single_json_to_bin(json_path, bin_path)
            success_count += 1
        except Exception as e:
            logging.error(f"转换 {filename} 失败: {e}")
            fail_count += 1

    logging.info(f"JSON→Bin 完成：成功 {success_count}，失败 {fail_count}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Convert MFR JSON graph files to DGL binary format")
    parser.add_argument("--mode", choices=["single", "batch"], default="batch")
    parser.add_argument("--json-file", type=str, help="Input JSON file (single mode)")
    parser.add_argument("--output-bin", type=str, help="Output bin file (single mode)")
    args = parser.parse_args()

    if args.mode == "single":
        if not args.json_file or not args.output_bin:
            parser.error("single 模式需要 --json-file 和 --output-bin")
        _convert_single_json_to_bin(args.json_file, args.output_bin)
    else:
        json_to_bin_batch()
