#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""训练实例级分类器（第二级）：真通槽 vs 同类非通槽。

标签来自 inst 矩阵的真实特征实例：
    y=1: 实例 seg == 9（真通槽）
    y=0: 实例 seg != 9 且 seg != 0（其它制造特征，含 seg=22 同类）

用法:
    python -m featurefox.train_instance 0        # 全部 17800
    python -m featurefox.train_instance 14000    # 前 14000（留 holdout）
"""
import os
import sys
import pickle

import numpy as np

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
UTILS_DIR = os.path.dirname(os.path.dirname(THIS_DIR))
TS_DIR = os.path.dirname(THIS_DIR)
for p in (UTILS_DIR, TS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

import networkx as nx
import xgboost as xgb
from sklearn.isotonic import IsotonicRegression

from detect_blind_holes_and_export_stp_v15_22 import StepParser
from detect_through_step import _build_edge_convexity_map
from featurefox.edge_features import build_face_graph
from featurefox.instance_data import list_step_files, shell_face_order, load_label, STEPS_DIR
from featurefox.instance_features import (
    extract_instance_features, INSTANCE_FEATURE_NAMES,
)
from featurefox.predict import (
    load_models, DEFAULT_THRESHOLD, MIN_INSTANCE_FACES, MIN_PLANE_RATIO,
)

INST_MODEL_PATH = os.path.join(THIS_DIR, "inst_clf.json")
INST_CALIB_PATH = os.path.join(THIS_DIR, "inst_calibrator.pkl")


def _seg_by_cell(name):
    """返回 dict cell_id -> seg 值。"""
    import json
    json_path = os.path.join(os.path.dirname(STEPS_DIR), "label", name + ".json")
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


def collect_instance_dataset(step_files, verbose=True):
    """收集实例级 (X, y)，训练样本与推理时完全同源。

    关键：推理时第二级分类器看到的是【边剪枝后的连通分量】，而非标注里的真实
    实例分组。此前用 inst 矩阵分组训练 → 训练分布与推理分布不一致：
    seg=22 的 9 面真实实例被当作负例，但推理时只有它的 3 面子分量 {25,26,28}
    到达分类器（3 面槽形此前几乎只见过正例）→ 被误判为通槽（_344 实测 0.912）。
    这里改用与推理完全一致的边剪枝连通分量训练，让模型见过 {25,26,28} 这类
    低边概率的 3 面非通槽分量作为负例。

    返回:
        X: np.ndarray (n_instances, n_features)
        y: np.ndarray (n_instances,) 0/1
        meta: list[dict] {name, cells, seg_value}
    """
    # 边分类器（第一级）只加载一次，用于给每条边算校准概率 + 剪枝
    edge_booster, edge_calib = load_models()

    X, y, meta = [], [], []
    for i, step_file in enumerate(step_files):
        name = os.path.splitext(step_file)[0]
        try:
            parser = StepParser(os.path.join(STEPS_DIR, step_file))
            parser.parse()
            order = shell_face_order(parser)
            face2cell = {fid: ci for ci, fid in enumerate(order)}
            edges, fa = build_face_graph(parser)
            conv_map, _ = _build_edge_convexity_map(parser, list(parser.advanced_faces.keys()))

            seg9, _, _ = load_label(name)
            if seg9 is None:
                continue
            seg = _seg_by_cell(name)

            # 第一级边分类器：每条边的校准概率 → (min_fid,max_fid) -> p
            edge_probs = {}
            cal_prob = None
            if edges:
                Xe = np.array([e["features"] for e in edges], dtype=np.float32)
                cal_prob = edge_calib.transform(edge_booster.predict(xgb.DMatrix(Xe)))
                for e, p in zip(edges, cal_prob):
                    edge_probs[(min(e["fa"], e["fb"]), max(e["fa"], e["fb"]))] = float(p)

            # 与推理完全一致的剪枝 + 连通分量 + 后过滤
            G = nx.Graph()
            for fid in parser.advanced_faces:
                G.add_node(fid)
            if cal_prob is not None:
                for e, p in zip(edges, cal_prob):
                    if p >= DEFAULT_THRESHOLD:
                        G.add_edge(e["fa"], e["fb"])
            ftype = {fid: parser.face_surface_type(fid) for fid in parser.advanced_faces}

            for comp in nx.connected_components(G):
                cf = list(comp)
                if len(cf) < MIN_INSTANCE_FACES:
                    continue
                if sum(1 for fid in cf if ftype.get(fid) == "PLANE") / len(cf) < MIN_PLANE_RATIO:
                    continue
                # 标签：按分量内各面的 cell seg 构成
                has_seg9 = False
                segs_other = set()
                for fid in cf:
                    sv = seg.get(face2cell.get(fid, -1), 0)
                    if sv == 9:
                        has_seg9 = True
                    elif sv != 0:
                        segs_other.add(sv)
                if has_seg9 and not segs_other:
                    label, sv = 1, 9
                elif segs_other and not has_seg9:
                    label, sv = 0, next(iter(segs_other))
                else:
                    continue  # 混合(seg9+其它)或全无标注，跳过
                # 特征：与推理一致，cells=面id集合，face_id_by_cell=恒等映射
                feats = extract_instance_features(
                    parser, fa, conv_map, set(cf), {fid: fid for fid in cf}, edge_probs)
                X.append(feats)
                y.append(label)
                meta.append({"name": name,
                             "cells": sorted(face2cell.get(fid) for fid in cf if fid in face2cell),
                             "seg": sv})
        except Exception:
            continue
        if verbose and (i + 1) % 1000 == 0:
            pos = sum(y)
            print("  [{}/{}] 实例={} 正例={} ({:.1%})".format(
                i + 1, len(step_files), len(y), pos, pos / max(1, len(y))), flush=True)
    if not X:
        return np.zeros((0, len(INSTANCE_FEATURE_NAMES))), np.zeros(0), []
    return np.array(X, dtype=np.float32), np.array(y, dtype=np.int32), meta


def train(max_files=0):
    # 不再用 TextIOWrapper 重新包装 stdout——它会引入块缓冲，配合 -u 时反而看不到
    # 实时进度（曾因此误判全量训练"挂死"而误杀）。编码由运行时 PYTHONIOENCODING=utf-8 保证。

    step_files = list_step_files(max_files, 0)
    print("训练文件数: {}".format(len(step_files)), flush=True)
    X, y, meta = collect_instance_dataset(step_files)
    n_pos = int(y.sum())
    n_neg = int(len(y) - n_pos)
    print("实例总数: {}  正例(seg9)={} ({:.1%})  负例(其它seg)={}".format(
        len(y), n_pos, n_pos / max(1, len(y)), n_neg))

    # 按文件名划分 train / calib / test（避免泄漏）
    names = sorted(set(m["name"] for m in meta))
    n_total = len(names)
    n_test = max(1, n_total // 10)
    test_names = set(names[-n_test:])
    calib_names = set(names[-2 * n_test:-n_test])
    train_idx = [i for i, m in enumerate(meta)
                 if m["name"] not in test_names and m["name"] not in calib_names]
    calib_idx = [i for i, m in enumerate(meta) if m["name"] in calib_names]
    test_idx = [i for i, m in enumerate(meta) if m["name"] in test_names]

    Xtr, ytr = X[train_idx], y[train_idx]
    Xcal, ycal = X[calib_idx], y[calib_idx]
    Xte, yte = X[test_idx], y[test_idx]
    pos_tr = max(1, int(ytr.sum()))
    neg_tr = max(1, int(len(ytr) - pos_tr))

    print("train={} calib={} test={}  scale_pos_weight={:.2f}".format(
        len(ytr), len(ycal), len(yte), neg_tr / pos_tr))

    # 训练
    dtr = xgb.DMatrix(Xtr, label=ytr, feature_names=INSTANCE_FEATURE_NAMES)
    params = {
        "objective": "binary:logistic",
        "max_depth": 4,
        "learning_rate": 0.1,
        "n_estimators": 200,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "scale_pos_weight": neg_tr / pos_tr,
        "tree_method": "hist",
        "eval_metric": "logloss",
        "verbosity": 0,
    }
    booster = xgb.train(params, dtr, num_boost_round=200)

    # 等渗校准
    raw_cal = booster.predict(xgb.DMatrix(Xcal, feature_names=INSTANCE_FEATURE_NAMES))
    calibrator = IsotonicRegression(out_of_bounds="clip")
    calibrator.fit(raw_cal, ycal)

    # 测试集评估
    raw_te = booster.predict(xgb.DMatrix(Xte, feature_names=INSTANCE_FEATURE_NAMES))
    prob_te = calibrator.transform(raw_te)
    from sklearn.metrics import precision_recall_fscore_support
    pred = (prob_te >= 0.5).astype(int)
    p, r, f1, _ = precision_recall_fscore_support(yte, pred, average="binary", zero_division=0)
    print("\n=== 实例分类器 test 集 (阈值0.5) ===")
    print("Precision={:.2%} Recall={:.2%} F1={:.2%}".format(p, r, f1))

    # 特征重要性
    imp = booster.get_score(importance_type="gain")
    imp_sorted = sorted(imp.items(), key=lambda kv: -kv[1])[:8]
    print("\nTop-8 特征重要性:")
    for fname, gain in imp_sorted:
        print("  {:<28s} {:.1f}".format(fname, gain))

    # 保存
    booster.save_model(INST_MODEL_PATH)
    with open(INST_CALIB_PATH, "wb") as f:
        pickle.dump(calibrator, f)
    print("\n已保存: {} / {}".format(INST_MODEL_PATH, INST_CALIB_PATH))


if __name__ == "__main__":
    max_files = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    train(max_files)
