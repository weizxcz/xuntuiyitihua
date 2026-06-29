#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""预测通槽实例（边剪枝 + 连通分量）。

流程 (FeatureFox):
    1. 解析 STEP → 构建 AAG → 提取边特征
    2. XGBoost 预测每条边 = P(该边在通槽内部)
    3. 等渗校准
    4. 剪枝: 保留概率 ≥ 阈值的边
    5. 连通分量 = 通槽实例
    6. 后处理: 过滤明显非通槽的实例（面数<3、非平面为主等）
"""

import os
import sys
import pickle

import numpy as np
import networkx as nx

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
UTILS_DIR = os.path.dirname(os.path.dirname(THIS_DIR))
TS_DIR = os.path.dirname(THIS_DIR)
for p in (UTILS_DIR, TS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

import xgboost as xgb

from detect_blind_holes_and_export_stp_v15_22 import StepParser
from featurefox.edge_features import build_face_graph

EDGE_MODEL_PATH = os.path.join(THIS_DIR, "edge_clf.json")
CALIBRATOR_PATH = os.path.join(THIS_DIR, "calibrator.pkl")
INST_MODEL_PATH = os.path.join(THIS_DIR, "inst_clf.json")
INST_CALIB_PATH = os.path.join(THIS_DIR, "inst_calibrator.pkl")

# 默认剪枝阈值（阈值扫描实测 0.35 时 F1 最优，79.46%）
DEFAULT_THRESHOLD = 0.35

# 实例后处理约束
MIN_INSTANCE_FACES = 3   # 通槽至少 3 面（底面 + 2 壁）
MIN_PLANE_RATIO = 0.5    # 通槽实例中平面面占比 ≥ 50%
INST_THRESHOLD = 0.80    # 第二级实例分类器阈值（组件同源模型）：< 0.80 判为非通槽
#   阈值扫描（500 holdout，组件同源模型）：0.50→F1=85.96%(FP=195)；0.80→F1=85.04% P=91.66% FP=136；
#   0.95→F1=81.96%。0.80 取精度优先：_344 误检组{25,26,28} P=0.771<0.80 被拒、真通槽 P=0.997 保留，
#   F1 与最优仅差 0.9pt 但 FP 显著降。偏召回可降到 0.50（_344 误检会保留）。


def load_models():
    """加载 XGBoost 边分类器 + 等渗校准器。"""
    if not os.path.exists(EDGE_MODEL_PATH) or not os.path.exists(CALIBRATOR_PATH):
        raise FileNotFoundError(
            "模型未找到。请先运行 train.py 训练模型。\n"
            "  期望: {} 和 {}".format(EDGE_MODEL_PATH, CALIBRATOR_PATH))
    booster = xgb.Booster()
    booster.load_model(EDGE_MODEL_PATH)
    with open(CALIBRATOR_PATH, "rb") as f:
        calibrator = pickle.load(f)
    return booster, calibrator


def load_instance_models():
    """加载第二级实例分类器（真通槽 vs seg=22 同类）。

    返回 (booster, calibrator)；模型不存在时返回 (None, None)，
    由调用方决定是否启用实例级过滤（向后兼容，未训练时退化为只过滤几何）。
    """
    if not os.path.exists(INST_MODEL_PATH) or not os.path.exists(INST_CALIB_PATH):
        return None, None
    booster = xgb.Booster()
    booster.load_model(INST_MODEL_PATH)
    with open(INST_CALIB_PATH, "rb") as f:
        calibrator = pickle.load(f)
    return booster, calibrator


def predict_through_slots(stp_path, booster, calibrator, threshold=DEFAULT_THRESHOLD,
                          fa_graph=None, parser=None,
                          inst_booster=None, inst_calibrator=None,
                          inst_threshold=INST_THRESHOLD):
    """预测一个 STEP 文件中的通槽实例。

    返回 list[dict]，每个实例:
        {faces: [face_id,...], score: float, n_faces: int, inst_prob: float}

    两级过滤：
        第一级（边分类器）：边剪枝 + 连通分量 + 平面占比。
        第二级（实例分类器，可选）：对每个连通分量用聚合几何判
        P(真通槽) < inst_threshold → 拒绝（剔除 seg=22 等同类误检）。
        传入 inst_booster/inst_calibrator 即启用；None 则跳过。
    """
    if parser is None:
        parser = StepParser(stp_path)
        parser.parse()
    if fa_graph is None:
        edges, fa_attrs = build_face_graph(parser)
    else:
        edges, fa_attrs = fa_graph

    if not edges:
        return []

    # 1. 预测边概率
    X = np.array([e["features"] for e in edges], dtype=np.float32)
    dmat = xgb.DMatrix(X)
    raw_prob = booster.predict(dmat)
    cal_prob = calibrator.transform(raw_prob)

    # 2. 剪枝 + 连通分量
    G = nx.Graph()
    for fid in parser.advanced_faces:
        G.add_node(fid)
    edge_prob_lookup = {}  # (min_fid,max_fid) -> 校准概率，供实例分类器置信度特征用
    for e, p in zip(edges, cal_prob):
        if p >= threshold:
            G.add_edge(e["fa"], e["fb"], prob=float(p))
            edge_prob_lookup[(min(e["fa"], e["fb"]), max(e["fa"], e["fb"]))] = float(p)

    components = list(nx.connected_components(G))

    # 第二级实例分类器需要凸凹性图 + 实例特征
    use_inst_clf = inst_booster is not None and inst_calibrator is not None
    if use_inst_clf:
        from featurefox.instance_features import extract_instance_features, INSTANCE_FEATURE_NAMES
        from detect_through_step import _build_edge_convexity_map
        all_face_ids = list(parser.advanced_faces.keys())
        conv_map, _ = _build_edge_convexity_map(parser, all_face_ids)
        face_id_by_index = {i: fid for i, fid in enumerate(all_face_ids)}

    # 3. 后处理: 过滤非通槽实例
    instances = []
    for comp in components:
        if len(comp) < MIN_INSTANCE_FACES:
            continue
        comp_faces = list(comp)
        # 平面占比检查（通槽以平面为主）
        n_plane = 0
        for fid in comp_faces:
            if parser.face_surface_type(fid) == "PLANE":
                n_plane += 1
        if n_plane / len(comp_faces) < MIN_PLANE_RATIO:
            continue
        # 实例内边的平均概率作为 score
        inst_edges = [(u, v) for u, v in G.edges(comp_faces) if u in comp and v in comp]
        probs = [G[u][v]["prob"] for u, v in inst_edges]
        score = float(np.mean(probs)) if probs else 0.0

        # 第二级实例分类器：拒绝 seg=22 等同类误检
        inst_prob = 1.0
        if use_inst_clf:
            # comp 是 face_id 集合；实例分类器按 cell_id 工作，这里 face_id 即当作索引空间
            # （实例特征只依赖几何，与 id 空间无关）
            cells = set(comp_faces)
            feats = extract_instance_features(
                parser, fa_attrs, conv_map, cells,
                {fid: fid for fid in comp_faces}, edge_prob_lookup)
            Xi = np.array([feats], dtype=np.float32)
            inst_prob = float(inst_calibrator.transform(
                inst_booster.predict(xgb.DMatrix(Xi, feature_names=INSTANCE_FEATURE_NAMES)))[0])
            if inst_prob < inst_threshold:
                continue

        instances.append({
            "faces": sorted(comp_faces),
            "score": score,
            "n_faces": len(comp_faces),
            "inst_prob": inst_prob,
        })

    # 按面数降序、score 降序排列
    instances.sort(key=lambda x: (x["n_faces"], x["score"]), reverse=True)
    return instances


def predict_part(stp_path, threshold=DEFAULT_THRESHOLD, use_instance_filter=True):
    """便捷接口：加载模型 + 预测一个文件。

    use_instance_filter=True 时启用第二级实例分类器（推荐，剔除 seg=22 同类误检）。
    """
    booster, calibrator = load_models()
    inst_booster, inst_calib = (None, None)
    if use_instance_filter:
        inst_booster, inst_calib = load_instance_models()
    return predict_through_slots(
        stp_path, booster, calibrator, threshold,
        inst_booster=inst_booster, inst_calibrator=inst_calib)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python predict.py <step文件> [阈值]")
        sys.exit(1)
    stp_path = sys.argv[1]
    thr = float(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_THRESHOLD
    insts = predict_part(stp_path, thr)
    print("识别实例数: {}".format(len(insts)))
    for i, inst in enumerate(insts, 1):
        print("  #{}: {}面, score={:.3f}, faces={}".format(
            i, inst["n_faces"], inst["score"], inst["faces"]))
