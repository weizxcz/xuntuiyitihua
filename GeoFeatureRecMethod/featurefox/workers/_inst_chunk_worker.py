#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""子进程 worker：收集一个 chunk 的实例训练数据（组件同源），pickle dump。

用法:
    python -m featurefox.workers._inst_chunk_worker <start> <end> <output_pkl>
"""
import os
import sys
import json
import pickle

import numpy as np
import networkx as nx
import xgboost as xgb

_FEATFOX_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _FEATFOX_ROOT not in sys.path:
    sys.path.insert(0, _FEATFOX_ROOT)
from featurefox.lib._env import get_project_root
_PROJECT_ROOT = get_project_root()
if _PROJECT_ROOT and _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from featurefox.lib.ncti_backend import load_part, count_advanced_faces
from featurefox.lib.edge_features import build_face_graph
from featurefox.lib.instance_data import (
    list_step_files, load_label, STEPS_DIR, LABELS_DIR)
from featurefox.lib.instance_features import (
    extract_instance_features, INSTANCE_FEATURE_NAMES)
from featurefox.lib.ncti_faceid_map import init_ncti_safe

# 从 predict 获取阈值常量和模型加载
from featurefox.scripts.predict import (
    load_models, DEFAULT_THRESHOLD, MIN_INSTANCE_FACES, MIN_PLANE_RATIO)


def _seg_by_cell(name):
    json_path = os.path.join(LABELS_DIR, name + ".json")
    if not os.path.exists(json_path):
        return {}
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list) and len(data) >= 1:
        inner = data[0][1] if isinstance(data[0], list) else data[0]
    else:
        inner = data
    seg = inner.get("seg", {})
    return {int(k): v for k, v in seg.items()}


def main():
    start = int(sys.argv[1])
    end = int(sys.argv[2])
    output_pkl = sys.argv[3]

    ncti = init_ncti_safe(_PROJECT_ROOT)
    if ncti is None:
        with open(output_pkl, "wb") as f:
            pickle.dump(([], [], []), f)
        os._exit(0)

    edge_booster, edge_calib = load_models()
    all_files = list_step_files(0, 0)
    chunk_files = all_files[start:end]
    doc = ncti.Document()
    X, y, meta = [], [], []
    for step_file in chunk_files:
        name = os.path.splitext(step_file)[0]
        stp_path = os.path.join(STEPS_DIR, step_file)
        try:
            part, _ = load_part(stp_path, ncti, doc=doc)
            expected = count_advanced_faces(stp_path)
            if expected is not None and expected != part.n_faces:
                continue
            edges, fa = build_face_graph(part)
            conv_map = part.edge_convexity
            seg9, _, _ = load_label(name)
            if seg9 is None:
                continue
            seg = _seg_by_cell(name)

            edge_probs = {}
            cal_prob = None
            if edges:
                Xe = np.array([e["features"] for e in edges], dtype=np.float32)
                cal_prob = edge_calib.transform(edge_booster.predict(xgb.DMatrix(Xe)))
                for e, p in zip(edges, cal_prob):
                    edge_probs[(min(e["fa"], e["fb"]), max(e["fa"], e["fb"]))] = float(p)

            G = nx.Graph()
            for cell in range(part.n_faces):
                G.add_node(cell)
            if cal_prob is not None:
                for e, p in zip(edges, cal_prob):
                    if p >= DEFAULT_THRESHOLD:
                        G.add_edge(e["fa"], e["fb"])
            ftype = {cell: fa.ftype(cell) for cell in range(part.n_faces)}

            for comp in nx.connected_components(G):
                cf = list(comp)
                if len(cf) < MIN_INSTANCE_FACES:
                    continue
                if sum(1 for c in cf if ftype.get(c) == "PLANE") / len(cf) < MIN_PLANE_RATIO:
                    continue
                has_seg9 = False
                segs_other = set()
                for c in cf:
                    sv = seg.get(c, 0)
                    if sv == 12:
                        has_seg9 = True
                    elif sv != 0:
                        segs_other.add(sv)
                if has_seg9 and not segs_other:
                    label, sv = 1, 12
                elif segs_other and not has_seg9:
                    label, sv = 0, next(iter(segs_other))
                else:
                    continue
                feats = extract_instance_features(part, fa, conv_map, set(cf), edge_probs)
                X.append(feats)
                y.append(label)
                meta.append({"name": name, "cells": sorted(cf), "seg": sv})

            # 增量 pickle（原子写）：崩件 segfault 杀进程时保留崩件前数据
            tmp = output_pkl + ".tmp"
            with open(tmp, "wb") as f:
                pickle.dump((X, y, meta), f)
            os.replace(tmp, output_pkl)
        except Exception:
            continue
    os._exit(0)


if __name__ == "__main__":
    main()
