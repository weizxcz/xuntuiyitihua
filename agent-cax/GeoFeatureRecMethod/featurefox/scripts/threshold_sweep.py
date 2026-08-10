#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""阈值扫描：在一个 holdout 子集上缓存边概率，快速扫描多个阈值（STEP 文本解析版）。

用法: python -m featurefox.scripts.threshold_sweep 1000 14000
     (评估文件 14000-14999，扫描 6 个阈值)
"""

import os
import sys
import pickle
import numpy as np
import networkx as nx

FEATUREFOX_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if FEATUREFOX_ROOT not in sys.path:
    sys.path.insert(0, FEATUREFOX_ROOT)
from featurefox.lib._env import get_project_root
PROJECT_ROOT = get_project_root()
if PROJECT_ROOT and PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import xgboost as xgb
# 注意：这是 STEP 文本解析版，依赖原版 StepParser
from utils.detect_blind_holes_and_export_stp_v15_22 import StepParser
from featurefox.lib.edge_features import build_face_graph
from featurefox.scripts.predict import load_models, MIN_INSTANCE_FACES, MIN_PLANE_RATIO
from featurefox.instance_data import list_step_files, load_label, shell_face_order
from featurefox.lib._env import get_steps_dir

STEPS_DIR = get_steps_dir()


def main():
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    n_files = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    offset = int(sys.argv[2]) if len(sys.argv) > 2 else 14000
    thresholds = [0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6]

    booster, calibrator = load_models()
    step_files = list_step_files(n_files, offset)
    print("缓存 {} 文件的边概率 (offset={})...".format(len(step_files), offset))

    # 缓存每个文件: (face_order, {edge: prob}, all_face_ids)
    cache = []
    for step_file in step_files:
        name = os.path.splitext(step_file)[0]
        try:
            parser = StepParser(os.path.join(STEPS_DIR, step_file))
            parser.parse()
            face_order = shell_face_order(parser)
            face_map = {fid: idx for idx, fid in enumerate(face_order)}
            edges, _ = build_face_graph(parser)
            X = np.array([e["features"] for e in edges], dtype=np.float32)
            dmat = xgb.DMatrix(X)
            prob = calibrator.transform(booster.predict(dmat)) if edges else np.array([])
            seg9, inst_mat, _ = load_label(name)
            if seg9 is None:
                continue
            cache.append({
                "edges": edges, "prob": prob,
                "face_ids": list(parser.advanced_faces.keys()),
                "face_map": face_map, "seg9": seg9,
                "ftype": {fid: parser.face_surface_type(fid) for fid in parser.advanced_faces},
            })
        except Exception:
            continue

    print("已缓存 {} 文件。扫描阈值: {}".format(len(cache), thresholds))
    print("{:>8s} {:>10s} {:>10s} {:>10s} {:>8s} {:>8s} {:>8s}".format(
        "thresh", "P", "R", "F1", "EXACT", "FP_ONLY", "MISS"))

    for thr in thresholds:
        tp_total = fp_total = fn_total = 0
        exact = miss = fp_only = partial = ok = 0
        for c in cache:
            G = nx.Graph()
            for fid in c["face_ids"]:
                G.add_node(fid)
            for e, p in zip(c["edges"], c["prob"]):
                if p >= thr:
                    G.add_edge(e["fa"], e["fb"], prob=float(p))
            comps = [list(comp) for comp in nx.connected_components(G) if len(comp) >= MIN_INSTANCE_FACES]
            # 平面占比过滤
            det_cells = set()
            for comp in comps:
                n_plane = sum(1 for fid in comp if c["ftype"].get(fid) == "PLANE")
                if n_plane / len(comp) >= MIN_PLANE_RATIO:
                    for fid in comp:
                        cid = c["face_map"].get(fid)
                        if cid is not None:
                            det_cells.add(cid)
            seg9 = c["seg9"]
            tp = det_cells & seg9
            fp = det_cells - seg9
            fn = seg9 - det_cells
            tp_total += len(tp); fp_total += len(fp); fn_total += len(fn)
            if not seg9 and not det_cells:
                ok += 1
            elif det_cells == seg9:
                exact += 1
            elif tp and not fp:
                partial += 1
            elif tp and fp:
                partial += 1
            elif not tp and fp:
                fp_only += 1
            else:
                miss += 1

        p = tp_total / (tp_total + fp_total) if (tp_total + fp_total) else 0
        r = tp_total / (tp_total + fn_total) if (tp_total + fn_total) else 0
        f1 = 2 * p * r / (p + r) if (p + r) else 0
        print("{:>8.2f} {:>9.2f}% {:>9.2f}% {:>9.2f}% {:>8d} {:>8d} {:>8d}".format(
            thr, p * 100, r * 100, f1 * 100, exact, fp_only, miss))


if __name__ == "__main__":
    main()
