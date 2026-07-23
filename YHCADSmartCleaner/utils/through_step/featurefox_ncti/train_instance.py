#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""训练实例级分类器（第二级）：真通槽 vs 同类非通槽 —— featurefox-NCTI 版。

与 STEP 版差异：NctiPart 数据源、cell_id 零映射、conv_map 取自 part.edge_convexity。
组件同源训练方法论原样保留（用第一级边剪枝连通分量作训练样本，见 featurefox §6.1）。

标签来自 inst 矩阵的真实特征实例：
    y=1: 实例 seg == 9（真通槽）
    y=0: 实例 seg != 9 且 seg != 0（其它制造特征，含 seg=22 同类）

用法（从 utils/through_step/ 执行，yhcad_py312 环境）:
    python -m featurefox_ncti.train_instance 0        # 全量
    python -m featurefox_ncti.train_instance 50000    # 前 50000（留 holdout）
"""
import os
import sys
import pickle
import json

import numpy as np

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
UTILS_DIR = os.path.dirname(os.path.dirname(THIS_DIR))
TS_DIR = os.path.dirname(THIS_DIR)
PROJECT_ROOT = os.path.dirname(UTILS_DIR)
for _p in (UTILS_DIR, TS_DIR, PROJECT_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import networkx as nx  # noqa: E402
import xgboost as xgb  # noqa: E402
from sklearn.isotonic import IsotonicRegression  # noqa: E402

from featurefox_ncti.edge_features import build_face_graph  # noqa: E402
from featurefox_ncti.instance_data import (  # noqa: E402
    list_step_files, load_label, STEPS_DIR, LABELS_DIR)
from featurefox_ncti.instance_features import (  # noqa: E402
    extract_instance_features, INSTANCE_FEATURE_NAMES)
from featurefox_ncti.predict import (  # noqa: E402
    load_models, DEFAULT_THRESHOLD, MIN_INSTANCE_FACES, MIN_PLANE_RATIO)
from ncti_backend import load_part, count_advanced_faces  # noqa: E402
from YHCADSmartCleaner.utils.through_step.featurefox.ncti_faceid_map import init_ncti_safe  # noqa: E402

INST_MODEL_PATH = os.path.join(THIS_DIR, "inst_clf.json")
INST_CALIB_PATH = os.path.join(THIS_DIR, "inst_calibrator.pkl")


def _seg_by_cell(name):
    """返回 dict cell_id -> seg 值。"""
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


def collect_instance_dataset(step_files, ncti, verbose=True):
    """收集实例级 (X, y)，子进程隔离（同 collect_dataset）。

    每 40 件 subprocess 独立进程（_inst_chunk_worker），增量 pickle 容崩。
    组件同源训练方法论在 worker 内（边剪枝连通分量作训练样本，featurefox §6.1）。

    返回:
        X: np.ndarray (n_instances, n_features)
        y: np.ndarray (n_instances,) 0/1
        meta: list[dict] {name, cells, seg}
    """
    import subprocess
    import pickle
    CHUNK = 40
    chunks = [(i, min(i + CHUNK, len(step_files))) for i in range(0, len(step_files), CHUNK)]
    ts_dir = os.path.dirname(THIS_DIR)
    all_X, all_y, all_meta = [], [], []
    for cid, (start, end) in enumerate(chunks):
        pkl = os.path.join(THIS_DIR, "_inst_chunk_{}.pkl".format(cid))
        env = {**os.environ, "PYTHONPATH": ts_dir, "PYTHONIOENCODING": "utf-8"}
        # 不 check：worker exit 127/139 都非0；主进程看 pkl（增量 pickle 容崩）
        subprocess.run(
            [sys.executable, "-m", "featurefox_ncti._inst_chunk_worker",
             str(start), str(end), pkl],
            env=env)
        if os.path.exists(pkl):
            with open(pkl, "rb") as f:
                X, y, meta = pickle.load(f)
            os.remove(pkl)
            all_X.extend(X)
            all_y.extend(y)
            all_meta.extend(meta)
        if verbose:
            print("  chunk {}/{} [{}:{}] (累计 {} 实例)".format(
                cid + 1, len(chunks), start, end, len(all_X)), flush=True)
    if not all_X:
        return np.zeros((0, len(INSTANCE_FEATURE_NAMES))), np.zeros(0), []
    if verbose:
        print("  完成: {} 实例".format(len(all_X)))
    return np.array(all_X, dtype=np.float32), np.array(all_y, dtype=np.int32), all_meta


def train(max_files=0):
    print("=" * 60, flush=True)
    print("FeatureFox-NCTI 第二级实例分类器训练", flush=True)
    print("=" * 60, flush=True)

    ncti = init_ncti_safe(PROJECT_ROOT)
    if ncti is None:
        sys.exit("NCTI 初始化失败：需 yhcad_py312 环境 + config/ncti_config.json。")

    step_files = list_step_files(max_files, 0)
    print("训练文件数: {}".format(len(step_files)), flush=True)
    X, y, meta = collect_instance_dataset(step_files, ncti)
    n_pos = int(y.sum())
    n_neg = int(len(y) - n_pos)
    print("实例总数: {}  正例(seg9)={} ({:.1%})  负例(其它seg)={}".format(
        len(y), n_pos, n_pos / max(1, len(y)), n_neg), flush=True)

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
        len(ytr), len(ycal), len(yte), neg_tr / pos_tr), flush=True)

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
    print("\n=== 实例分类器 test 集 (阈值0.5) ===", flush=True)
    print("Precision={:.2%} Recall={:.2%} F1={:.2%}".format(p, r, f1), flush=True)

    # 特征重要性
    imp = booster.get_score(importance_type="gain")
    imp_sorted = sorted(imp.items(), key=lambda kv: -kv[1])[:8]
    print("\nTop-8 特征重要性:", flush=True)
    for fname, gain in imp_sorted:
        print("  {:<28s} {:.1f}".format(fname, gain), flush=True)

    # 保存
    booster.save_model(INST_MODEL_PATH)
    with open(INST_CALIB_PATH, "wb") as f:
        pickle.dump(calibrator, f)
    print("\n已保存: {} / {}".format(INST_MODEL_PATH, INST_CALIB_PATH), flush=True)


if __name__ == "__main__":
    max_files = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    train(max_files)
    os._exit(0)
