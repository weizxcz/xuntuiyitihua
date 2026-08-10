#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""预测通槽实例（边剪枝 + 连通分量）—— featurefox-NCTI 版。

与 featurefox(STEP版).predict 的差异：
  - 数据源 NctiPart（NCTI 导入），删 StepParser；
  - 图节点 = cell_id（ai.FaceID 位置索引），输出 faces 即 cell_id
    （零映射，直接喂 Geo-Rec 训练图节点下标）；
  - 第二级凸凹性取自 part.edge_convexity（NCTI EdgeAttr，不需质心偏移反推）；
  - 平面检查用 fa_attrs.ftype(cell)。

流程 (FeatureFox):
    1. NCTI 导入 STEP → NctiPart → 构建 AAG → 提取边特征
    2. XGBoost 预测每条边 = P(该边在通槽内部)
    3. 等渗校准 → 剪枝(>=阈值) → 连通分量 = 通槽实例
    4. 后处理: 面数>=3、平面占比>=50%
    5. 第二级实例分类器(可选): P(真通槽) < inst_threshold → 拒绝
"""

import os
import sys
import pickle

import numpy as np
import networkx as nx

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
UTILS_DIR = os.path.dirname(os.path.dirname(THIS_DIR))
TS_DIR = os.path.dirname(THIS_DIR)
PROJECT_ROOT = os.path.dirname(UTILS_DIR)
REPO_ROOT = os.path.dirname(PROJECT_ROOT)
for _p in (REPO_ROOT, PROJECT_ROOT, UTILS_DIR, TS_DIR, THIS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import xgboost as xgb  # noqa: E402

from featurefox_ncti.edge_features import build_face_graph  # noqa: E402
from ncti_backend import load_part  # noqa: E402
from featurefox.ncti_faceid_map import init_ncti_safe  # noqa: E402

EDGE_MODEL_PATH = os.path.join(THIS_DIR, "edge_clf.json")
CALIBRATOR_PATH = os.path.join(THIS_DIR, "calibrator.pkl")
INST_MODEL_PATH = os.path.join(THIS_DIR, "inst_clf.json")
INST_CALIB_PATH = os.path.join(THIS_DIR, "inst_calibrator.pkl")

# 默认剪枝阈值（与 STEP 版一致；NCTI 版重训后可重新扫描）
DEFAULT_THRESHOLD = 0.35
MIN_INSTANCE_FACES = 3   # 通槽至少 3 面（底面 + 2 壁）
MIN_PLANE_RATIO = 0.5    # 通槽实例中平面面占比 ≥ 50%
INST_THRESHOLD = 0.80    # 第二级实例分类器阈值：< 0.80 判为非通槽


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

    返回 (booster, calibrator)；模型不存在返回 (None, None)（退化为仅几何过滤）。
    """
    if not os.path.exists(INST_MODEL_PATH) or not os.path.exists(INST_CALIB_PATH):
        return None, None
    booster = xgb.Booster()
    booster.load_model(INST_MODEL_PATH)
    with open(INST_CALIB_PATH, "rb") as f:
        calibrator = pickle.load(f)
    return booster, calibrator


def predict_through_slots(stp_path, booster, calibrator, ncti=None, part=None,
                          threshold=DEFAULT_THRESHOLD,
                          inst_booster=None, inst_calibrator=None,
                          inst_threshold=INST_THRESHOLD):
    """预测一个 STEP 文件中的通槽实例（NCTI 版）。

    参数:
        stp_path: STEP 文件路径
        booster/calibrator: 第一级边分类器 + 校准器
        ncti: NCTI 模块（part 为 None 时用于内部 load_part）
        part: 已加载的 NctiPart（可选，批量复用；提供则不重新导入）
        threshold: 边剪枝阈值
        inst_booster/inst_calibrator: 第二级实例分类器（可选）
        inst_threshold: 第二级拒绝阈值

    返回 list[dict]，每个实例:
        {faces: [cell_id,...], score: float, n_faces: int, inst_prob: float}
    faces 为 cell_id（ai.FaceID 位置索引），与 Geo-Rec 训练图零映射对齐。
    """
    _owned_doc = None
    try:
        if part is None:
            if ncti is None:
                raise ValueError("part 和 ncti 至少提供一个（part=None 时需 ncti 内部导入）")
            part, _owned_doc = load_part(stp_path, ncti)

        edges, fa_attrs = build_face_graph(part)
        if not edges:
            return []

        # 1. 预测边概率
        X = np.array([e["features"] for e in edges], dtype=np.float32)
        dmat = xgb.DMatrix(X)
        raw_prob = booster.predict(dmat)
        cal_prob = calibrator.transform(raw_prob)

        # 2. 剪枝 + 连通分量（节点 = cell_id 位置索引）
        G = nx.Graph()
        for cell in range(part.n_faces):
            G.add_node(cell)
        edge_prob_lookup = {}  # (min,max) -> 校准概率，供实例分类器置信度特征用
        for e, p in zip(edges, cal_prob):
            if p >= threshold:
                G.add_edge(e["fa"], e["fb"], prob=float(p))
                edge_prob_lookup[(min(e["fa"], e["fb"]), max(e["fa"], e["fb"]))] = float(p)

        components = list(nx.connected_components(G))

        # 第二级实例分类器需要凸凹性图 + 实例特征
        use_inst_clf = inst_booster is not None and inst_calibrator is not None
        if use_inst_clf:
            from featurefox_ncti.instance_features import (
                extract_instance_features, INSTANCE_FEATURE_NAMES)
            conv_map = part.edge_convexity  # NCTI 原生凸凹性，cell_id 空间

        # 3. 后处理: 过滤非通槽实例
        instances = []
        for comp in components:
            if len(comp) < MIN_INSTANCE_FACES:
                continue
            comp_cells = list(comp)
            # 平面占比检查（通槽以平面为主）
            n_plane = sum(1 for c in comp_cells if fa_attrs.ftype(c) == "PLANE")
            if n_plane / len(comp_cells) < MIN_PLANE_RATIO:
                continue
            # 实例内边的平均概率作为 score
            inst_edges = [(u, v) for u, v in G.edges(comp_cells) if u in comp and v in comp]
            probs = [G[u][v]["prob"] for u, v in inst_edges]
            score = float(np.mean(probs)) if probs else 0.0

            # 第二级实例分类器：拒绝 seg=22 等同类误检
            inst_prob = 1.0
            if use_inst_clf:
                cells = set(comp_cells)
                feats = extract_instance_features(
                    part, fa_attrs, conv_map, cells, edge_prob_lookup)
                Xi = np.array([feats], dtype=np.float32)
                inst_prob = float(inst_calibrator.transform(
                    inst_booster.predict(xgb.DMatrix(Xi, feature_names=INSTANCE_FEATURE_NAMES)))[0])
                if inst_prob < inst_threshold:
                    continue

            instances.append({
                "faces": sorted(comp_cells),
                "score": score,
                "n_faces": len(comp_cells),
                "inst_prob": inst_prob,
            })

        # 按面数降序、score 降序排列
        instances.sort(key=lambda x: (x["n_faces"], x["score"]), reverse=True)
        return instances
    finally:
        if _owned_doc is not None:
            try:
                _owned_doc.Clear()
            except Exception:
                pass


def predict_part(stp_path, threshold=DEFAULT_THRESHOLD, use_instance_filter=True, ncti=None):
    """便捷接口：加载模型 + 预测一个文件。

    use_instance_filter=True 启用第二级实例分类器（推荐，剔除 seg=22 同类误检）。
    ncti 为 None 时内部 init_ncti_safe。
    """
    if ncti is None:
        ncti = init_ncti_safe(PROJECT_ROOT)
    booster, calibrator = load_models()
    inst_booster, inst_calib = (None, None)
    if use_instance_filter:
        inst_booster, inst_calib = load_instance_models()
    return predict_through_slots(
        stp_path, booster, calibrator, ncti=ncti, threshold=threshold,
        inst_booster=inst_booster, inst_calibrator=inst_calib)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python -m featurefox_ncti.predict <step文件> [阈值]")
        sys.exit(1)
    stp_path = sys.argv[1]
    thr = float(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_THRESHOLD
    insts = predict_part(stp_path, thr)
    print("识别实例数: {}".format(len(insts)))
    for i, inst in enumerate(insts, 1):
        print("  #{}: {}面, score={:.3f}, faces={}".format(
            i, inst["n_faces"], inst["score"], inst["faces"]))
    os._exit(0)
