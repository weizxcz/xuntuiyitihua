#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""训练 XGBoost 边分类器 + 等渗校准（featurefox-NCTI 版）。

与 featurefox(STEP版).train 的差异：
  - 数据源 NctiPart（NCTI 导入），需 NCTI 环境（yhcad_py312）；
  - collect_dataset 传 ncti；build_training_sample 零映射（edges fa/fb 已是 cell_id）；
  - 训练数据 D:\\wyg\\data\\data\\steps + labels（62495 件）；
  - 删 TextIOWrapper stdout 重包装（吞进度，featurefox §16 教训），用 flush=True；
  - 末尾 os._exit(0) 防 NCTI DLL 析构 segfault。

超参（同 STEP 版，FeatureFox 原文）:
    200 棵树, max_depth=6, learning_rate=0.1, 等渗校准。

用法（从 utils/through_step/ 执行，yhcad_py312 环境）:
    python -m featurefox_ncti.train 2000      # 前 2000 件
    python -m featurefox_ncti.train 0         # 全量 62495 件
"""

import os
import sys
import time
import pickle

import numpy as np

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
UTILS_DIR = os.path.dirname(os.path.dirname(THIS_DIR))
TS_DIR = os.path.dirname(THIS_DIR)
PROJECT_ROOT = os.path.dirname(UTILS_DIR)
for _p in (UTILS_DIR, TS_DIR, PROJECT_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import xgboost as xgb  # noqa: E402
from sklearn.isotonic import IsotonicRegression  # noqa: E402
from sklearn.model_selection import train_test_split  # noqa: E402

from featurefox_ncti.edge_features import build_face_graph, FEATURE_NAMES  # noqa: E402
from featurefox_ncti.instance_data import list_step_files, collect_dataset  # noqa: E402
from YHCADSmartCleaner.utils.through_step.featurefox.ncti_faceid_map import init_ncti_safe  # noqa: E402

MODEL_DIR = THIS_DIR
EDGE_MODEL_PATH = os.path.join(MODEL_DIR, "edge_clf.json")
CALIBRATOR_PATH = os.path.join(MODEL_DIR, "calibrator.pkl")


def train(max_files=0, test_size=0.2):
    print("=" * 60, flush=True)
    print("FeatureFox-NCTI 边分类器训练", flush=True)
    print("=" * 60, flush=True)

    # 0. 初始化 NCTI
    ncti = init_ncti_safe(PROJECT_ROOT)
    if ncti is None:
        sys.exit("NCTI 初始化失败：需 yhcad_py312 环境 + config/ncti_config.json。")

    # 1. 收集数据
    t0 = time.time()
    step_files = list_step_files(max_files)
    print("训练文件数: {}".format(len(step_files)), flush=True)
    print("收集边样本（NCTI 导入，较慢）...", flush=True)
    X, y, meta = collect_dataset(step_files, ncti, build_face_graph, verbose=True)
    X = np.array(X, dtype=np.float32)
    y = np.array(y, dtype=np.int32)
    print("特征矩阵: {}  标签: {}".format(X.shape, y.shape), flush=True)
    pos = int(y.sum())
    neg = int(len(y) - pos)
    print("正样本(通槽内部边): {} ({:.2f}%)".format(pos, 100.0 * pos / len(y)), flush=True)
    print("负样本: {} ({:.2f}%)".format(neg, 100.0 * neg / len(y)), flush=True)
    print("收集耗时: {:.1f}s".format(time.time() - t0), flush=True)

    # 2. 按文件分组划分 train/calib/test（避免泄漏）
    names = np.array([m["name"] for m in meta])
    unique_names = sorted(set(names))
    print("\n唯一零件数: {}".format(len(unique_names)), flush=True)
    train_names, test_names = train_test_split(unique_names, test_size=test_size, random_state=42)
    train_names, calib_names = train_test_split(train_names, test_size=0.2, random_state=42)
    train_set = set(train_names)
    calib_set = set(calib_names)
    test_set = set(test_names)

    train_mask = np.array([m["name"] in train_set for m in meta])
    calib_mask = np.array([m["name"] in calib_set for m in meta])
    test_mask = np.array([m["name"] in test_set for m in meta])

    X_tr, y_tr = X[train_mask], y[train_mask]
    X_cal, y_cal = X[calib_mask], y[calib_mask]
    X_te, y_te = X[test_mask], y[test_mask]
    print("train: {} 边 (pos={}), calib: {} 边 (pos={}), test: {} 边 (pos={})".format(
        len(y_tr), int(y_tr.sum()), len(y_cal), int(y_cal.sum()),
        len(y_te), int(y_te.sum())), flush=True)

    # 3. 训练 XGBoost（FeatureFox 超参 + scale_pos_weight 处理不平衡）
    print("\n训练 XGBoost (200 trees, depth 6, lr 0.1)...", flush=True)
    spw = max(1.0, neg / max(1, pos))
    clf = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        scale_pos_weight=spw,
        objective="binary:logistic",
        tree_method="hist",
        n_jobs=-1,
        random_state=42,
        eval_metric="logloss",
    )
    t1 = time.time()
    clf.fit(X_tr, y_tr)
    print("训练耗时: {:.1f}s".format(time.time() - t1), flush=True)

    # 4. 等渗校准（FeatureFox 用 isotonic + 3-fold；这里 calib 集已独立）
    print("\n等渗校准...", flush=True)
    raw_prob_cal = clf.predict_proba(X_cal)[:, 1]
    calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1)
    calibrator.fit(raw_prob_cal, y_cal)

    # 5. 在 test 集评估边级指标
    raw_prob_te = clf.predict_proba(X_te)[:, 1]
    cal_prob_te = calibrator.transform(raw_prob_te)
    print("\n边级 test 评估:", flush=True)
    _eval_edges(y_te, raw_prob_te, "raw")
    _eval_edges(y_te, cal_prob_te, "calibrated")

    # 6. 保存模型
    clf.get_booster().save_model(EDGE_MODEL_PATH)
    with open(CALIBRATOR_PATH, "wb") as f:
        pickle.dump(calibrator, f)
    print("\n模型已保存:", flush=True)
    print("  边分类器: {}".format(EDGE_MODEL_PATH), flush=True)
    print("  校准器: {}".format(CALIBRATOR_PATH), flush=True)

    # 7. 特征重要性
    print("\n特征重要性 (top 15):", flush=True)
    imp = clf.feature_importances_
    order = np.argsort(imp)[::-1]
    for idx in order[:15]:
        print("  {:22s} {:.4f}".format(FEATURE_NAMES[idx], imp[idx]), flush=True)

    print("\n总耗时: {:.1f}s".format(time.time() - t0), flush=True)


def _eval_edges(y_true, prob, tag):
    """边级 precision/recall/F1（阈值 0.5）。"""
    y_pred = (prob >= 0.5).astype(int)
    tp = int(((y_pred == 1) & (y_true == 1)).sum())
    fp = int(((y_pred == 1) & (y_true == 0)).sum())
    fn = int(((y_pred == 0) & (y_true == 1)).sum())
    p = tp / (tp + fp) if (tp + fp) > 0 else 0
    r = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0
    print("  [{}] P={:.4f} R={:.4f} F1={:.4f}  (TP={} FP={} FN={})".format(
        tag, p, r, f1, tp, fp, fn), flush=True)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    train(max_files=n)
    os._exit(0)
