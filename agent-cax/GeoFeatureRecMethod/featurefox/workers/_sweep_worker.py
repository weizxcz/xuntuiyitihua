#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""阈值扫描子进程 worker（featurefox-NCTI 版）。

用法（主进程通过 subprocess 调）:
    python -m featurefox.workers._sweep_worker <start> <end> <pkl_path> <offset>
"""
import os
import sys
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

from featurefox.lib.edge_features import build_face_graph
from featurefox.lib.instance_features import (
    extract_instance_features, INSTANCE_FEATURE_NAMES)
from featurefox.lib.instance_data import list_step_files, load_label, STEPS_DIR
from featurefox.lib.ncti_backend import load_part
from featurefox.lib.ncti_faceid_map import init_ncti_safe

# 从 predict 获取阈值常量和模型加载
from featurefox.scripts.predict import (
    load_models, load_instance_models, MIN_INSTANCE_FACES, MIN_PLANE_RATIO,
    INST_THRESHOLD)

# 扫描阈值（9 点，覆盖超低→高，看 recall 随阈值降的走势）
THRESHOLDS = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50]


def _empty_acc():
    return {t: {"tp": 0, "fp": 0, "fn": 0} for t in THRESHOLDS}


def main():
    start = int(sys.argv[1])
    end = int(sys.argv[2])
    pkl_path = sys.argv[3]
    offset = int(sys.argv[4]) if len(sys.argv) > 4 else 0

    ncti = init_ncti_safe(_PROJECT_ROOT)
    booster, calibrator = load_models()
    inst_booster, inst_calib = load_instance_models()
    use_inst = inst_booster is not None and inst_calib is not None

    step_files = list_step_files(0, offset)
    files = step_files[start:end]

    acc = {"A": _empty_acc(), "B": _empty_acc()}
    n_done = 0
    errors = []

    for idx, step_file in enumerate(files):
        name = os.path.splitext(step_file)[0]
        stp = os.path.join(STEPS_DIR, step_file)
        doc = None
        try:
            part, doc = load_part(stp, ncti)
            edges, fa_attrs = build_face_graph(part)
            seg9, _inst_mat, _n = load_label(name)
            if seg9 is None or not edges:
                continue
            # 建一次图 + 算一次边概率（阈值无关）
            X = np.array([e["features"] for e in edges], dtype=np.float32)
            cal_prob = calibrator.transform(booster.predict(xgb.DMatrix(X)))
            ep = list(zip(edges, cal_prob))
            conv_map = part.edge_convexity

            for t in THRESHOLDS:
                G = nx.Graph()
                G.add_nodes_from(range(part.n_faces))
                elookup = {}
                for e, p in ep:
                    if p >= t:
                        G.add_edge(e["fa"], e["fb"], prob=float(p))
                        key = (min(e["fa"], e["fb"]), max(e["fa"], e["fb"]))
                        elookup[key] = float(p)
                det_A = set()   # 纯第一级
                det_B = set()   # 全流水线
                for comp in nx.connected_components(G):
                    comp = list(comp)
                    if len(comp) < MIN_INSTANCE_FACES:
                        continue
                    n_plane = sum(1 for c in comp if fa_attrs.ftype(c) == "PLANE")
                    if n_plane / len(comp) < MIN_PLANE_RATIO:
                        continue
                    det_A.update(comp)
                    if use_inst:
                        feats = extract_instance_features(
                            part, fa_attrs, conv_map, set(comp), elookup)
                        Xi = np.array([feats], dtype=np.float32)
                        ip = float(inst_calib.transform(
                            inst_booster.predict(xgb.DMatrix(
                                Xi, feature_names=INSTANCE_FEATURE_NAMES)))[0])
                        if ip >= INST_THRESHOLD:
                            det_B.update(comp)
                    else:
                        det_B.update(comp)
                for mode, det in (("A", det_A), ("B", det_B)):
                    acc[mode][t]["tp"] += len(det & seg9)
                    acc[mode][t]["fp"] += len(det - seg9)
                    acc[mode][t]["fn"] += len(seg9 - det)
            n_done += 1
        except Exception as ex:
            errors.append("{}: {}".format(name, str(ex)[:50]))
        finally:
            if doc is not None:
                try:
                    doc.Clear()
                except Exception:
                    pass
        # 增量 pickle（崩件 segfault 前落盘）
        try:
            with open(pkl_path + ".tmp", "wb") as f:
                pickle.dump({"acc": acc, "n_done": n_done,
                             "errors": errors, "thresholds": THRESHOLDS}, f)
            os.replace(pkl_path + ".tmp", pkl_path)
        except Exception:
            pass

    os._exit(0)


if __name__ == "__main__":
    main()
