#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""加载标签 + 生成边训练数据。

边标签设计（直接面向通槽检测）:
    y=1: 该共享边连接的两个面属于同一个通槽实例
         （两面的 cell_id 都在 seg=9 集合中，且 inst[i][j]=1）
    y=0: 其他所有边（非通槽边、通槽边界边、不同通槽间的边）

预测时: 边分类器预测 P(该边在通槽内部) → 保留高概率边 → 连通分量 = 通槽实例。

FeatureFox 原文用 inst[i][j]=1（任意特征实例）做通用边分类 + 语义分类两阶段。
这里为直接面向单类（通槽）目标，合并为一阶段。
"""

import json
import os
import sys

UTILS_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if UTILS_DIR not in sys.path:
    sys.path.insert(0, UTILS_DIR)

from detect_blind_holes_and_export_stp_v15_22 import StepParser  # noqa: E402

STEPS_DIR = r"D:\wyg\data\data\通槽\steps"
LABELS_DIR = r"D:\wyg\data\data\通槽\label"


def shell_face_order(parser):
    """获取 CLOSED_SHELL 内 ADVANCED_FACE 的顺序（cell_id = 位置索引）。"""
    for sid, entity in parser.entities.items():
        if entity.get("type") not in {"CLOSED_SHELL", "OPEN_SHELL"}:
            continue
        refs = [r for r in parser._refs(entity.get("params", ""))
                if r in parser.advanced_faces]
        if refs:
            return refs
    return sorted(parser.advanced_faces.keys())


def load_label(name):
    """加载标签，返回 (seg9_set, inst_matrix, n_faces)。"""
    json_path = os.path.join(LABELS_DIR, name + ".json")
    if not os.path.exists(json_path):
        return None, None, 0
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        seg = data.get("seg", {})
        inst = data.get("inst", None)
    elif isinstance(data, list) and len(data) >= 1:
        inner = data[0][1] if isinstance(data[0], list) else data[0]
        seg = inner.get("seg", {})
        inst = inner.get("inst", None)
    else:
        return None, None, 0

    seg9 = {int(k) for k, v in seg.items() if v == 9}
    return seg9, inst, len(inst) if inst else 0


def list_step_files(limit=0, offset=0):
    """列出 STEP 文件（按名排序）。limit=0 表示全部，offset 跳过前 offset 个。"""
    files = sorted(f for f in os.listdir(STEPS_DIR) if f.endswith(".step"))
    if offset > 0:
        files = files[offset:]
    return files[:limit] if limit > 0 else files


def build_training_sample(parser, edges, seg9, inst_matrix):
    """为一个零件的所有边生成 (X, y)。

    返回:
        X: list[list[float]]，每行是一条边的特征向量
        y: list[int]，0/1 标签
        meta: list[dict]，每条边的元信息 {fa, fb, ec_id}（用于预测时回溯）
    """
    if inst_matrix is None or seg9 is None:
        return [], [], []

    face_order = shell_face_order(parser)
    fid_to_cell = {fid: idx for idx, fid in enumerate(face_order)}

    X, y, meta = [], [], []
    for e in edges:
        fa, fb = e["fa"], e["fb"]
        ca = fid_to_cell.get(fa)
        cb = fid_to_cell.get(fb)
        if ca is None or cb is None:
            continue
        # y=1: 两面都在 seg=9 且属于同一实例（inst[ca][cb]=1）
        in_seg9 = (ca in seg9) and (cb in seg9)
        same_inst = False
        if ca < len(inst_matrix) and cb < len(inst_matrix[0]):
            same_inst = (inst_matrix[ca][cb] == 1) or (inst_matrix[cb][ca] == 1)
        label = 1 if (in_seg9 and same_inst) else 0

        X.append(e["features"])
        y.append(label)
        meta.append({"fa": fa, "fb": fb, "ec_id": e["ec_id"], "cell_a": ca, "cell_b": cb})

    return X, y, meta


def collect_dataset(step_files, build_face_graph_fn, verbose=True):
    """收集多个文件的边训练数据。

    返回:
        all_X: list[list[float]]
        all_y: list[int]
        all_meta: list[dict]（含 name 字段）
    """
    all_X, all_y, all_meta = [], [], []
    n_skip = 0
    for i, step_file in enumerate(step_files):
        name = os.path.splitext(step_file)[0]
        stp_path = os.path.join(STEPS_DIR, step_file)
        try:
            parser = StepParser(stp_path)
            parser.parse()
            seg9, inst, _ = load_label(name)
            if seg9 is None or inst is None:
                n_skip += 1
                continue
            edges, _ = build_face_graph_fn(parser)
            X, y, meta = build_training_sample(parser, edges, seg9, inst)
            all_X.extend(X)
            all_y.extend(y)
            for m in meta:
                m["name"] = name
            all_meta.extend(meta)
        except Exception as ex:
            n_skip += 1
            if verbose:
                print("  skip {}: {}".format(name, str(ex)[:60]))
        if verbose and (i + 1) % 2000 == 0:
            print("  [{}] 已处理 {}/{} 文件, 累计 {} 边样本".format(
                i + 1, i + 1, len(step_files), len(all_X)))
    if verbose:
        print("  完成: {} 文件, {} 边样本, 跳过 {}".format(
            len(step_files) - n_skip, len(all_X), n_skip))
    return all_X, all_y, all_meta
