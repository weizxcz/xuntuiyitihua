#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""子进程 worker：PQ 评估版——输出每件的 GT 通槽实例 + 候选实例(带 inst_prob)，
供主进程 evaluate_pq 在多个 inst_threshold 下算 Panoptic Quality(论文同口径)。

与 _eval_scan_worker 的差异：除候选外，还输出 GT 通槽实例（标签 inst 矩阵在
seg=9 面上的连通分量，每个=一个真实通槽实例），供实例级 IoU>0.5 匹配算 PQ。
inst_threshold=0.0 保留所有候选(每个带真实 inst_prob)，主进程按阈值模拟拒绝。

用法:
    python -m featurefox_ncti._eval_pq_worker <start> <end> <offset> <edge_threshold> <output_jsonl>
"""
import os
import sys
import json
from collections import defaultdict

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
UTILS_DIR = os.path.dirname(os.path.dirname(THIS_DIR))
TS_DIR = os.path.dirname(THIS_DIR)
PROJECT_ROOT = os.path.dirname(UTILS_DIR)
for _p in (UTILS_DIR, TS_DIR, PROJECT_ROOT, THIS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from featurefox_ncti.predict import (  # noqa: E402
    load_models, load_instance_models, predict_through_slots)
from featurefox_ncti.instance_data import list_step_files, load_label, STEPS_DIR  # noqa: E402
from ncti_backend import load_part  # noqa: E402
from YHCADSmartCleaner.utils.through_step.featurefox.ncti_faceid_map import init_ncti_safe  # noqa: E402


def gt_slot_instances(seg9, inst_matrix):
    """seg=9 面 + inst 矩阵 → GT 通槽实例(连通分量)。

    inst_matrix[ca][cb]==1 表示两面同实例；在 seg9 面集合上做并查集连通分量，
    每个分量 = 一个真实通槽实例。返回 list[set(cell_id)]。
    inst_matrix 缺失/结构异常时退化为整个 seg9 当一个实例。
    """
    if not seg9:
        return []
    if not (isinstance(inst_matrix, list) and inst_matrix
            and isinstance(inst_matrix[0], list)):
        return [set(seg9)]
    seg9_list = sorted(seg9)
    n = len(inst_matrix)
    parent = {f: f for f in seg9_list}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for idx, a in enumerate(seg9_list):
        if a >= n:
            continue
        row = inst_matrix[a]
        for b in seg9_list[idx + 1:]:
            if b < len(row) and row[b] == 1:
                union(a, b)
    groups = defaultdict(list)
    for f in seg9_list:
        groups[find(f)].append(f)
    return [set(g) for g in groups.values()]


def main():
    start = int(sys.argv[1])
    end = int(sys.argv[2])
    offset = int(sys.argv[3])
    edge_threshold = float(sys.argv[4])
    output_jsonl = sys.argv[5]

    ncti = init_ncti_safe(PROJECT_ROOT)
    if ncti is None:
        os._exit(0)

    booster, calibrator = load_models()
    inst_booster, inst_calib = load_instance_models()

    all_files = list_step_files(0, offset)
    chunk_files = all_files[start:end]
    doc = ncti.Document()

    with open(output_jsonl, "w", encoding="utf-8") as out:
        for step_file in chunk_files:
            name = os.path.splitext(step_file)[0]
            stp_path = os.path.join(STEPS_DIR, step_file)
            try:
                part, _ = load_part(stp_path, ncti, doc=doc)
                # inst_threshold=0.0 保留所有候选(每个带真实 inst_prob)
                instances = predict_through_slots(
                    stp_path, booster, calibrator, ncti=ncti, part=part,
                    threshold=edge_threshold, inst_booster=inst_booster,
                    inst_calibrator=inst_calib, inst_threshold=0.0)
                cands = [{"faces": inst["faces"], "inst_prob": inst["inst_prob"]}
                         for inst in instances]
            except Exception:
                continue
            finally:
                try:
                    doc.Clear()
                except Exception:
                    pass

            seg9, inst_matrix, _ = load_label(name)
            if seg9 is None:
                continue

            gts = gt_slot_instances(seg9, inst_matrix)
            rec = {"name": name,
                   "gt": [sorted(g) for g in gts],
                   "candidates": cands}
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()

    os._exit(0)


if __name__ == "__main__":
    main()
