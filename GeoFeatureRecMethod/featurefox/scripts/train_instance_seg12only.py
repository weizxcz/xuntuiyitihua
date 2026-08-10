#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""训练实例级分类器 —— 仅含 seg=12 的 STEP 文件版本。

用法（从 YHCADSmartCleaner/ 执行，yhcad_py312 环境）:
    python -m featurefox.scripts.train_instance_seg12only
"""

import os
import sys
import pickle
import json

import numpy as np

# featurefox 包根目录
FEATUREFOX_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if FEATUREFOX_ROOT not in sys.path:
    sys.path.insert(0, FEATUREFOX_ROOT)
from featurefox.lib._env import get_project_root
PROJECT_ROOT = get_project_root()
if PROJECT_ROOT and PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ["NCTI_SEG12_ONLY"] = "1"

import networkx as nx
import xgboost as xgb
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import precision_recall_fscore_support

from featurefox.lib.edge_features import build_face_graph
from featurefox.lib.instance_data import list_step_files, load_label, STEPS_DIR, LABELS_DIR
from featurefox.lib.instance_features import extract_instance_features, INSTANCE_FEATURE_NAMES
from featurefox.lib.ncti_backend import load_part, count_advanced_faces
from featurefox.lib.ncti_faceid_map import init_ncti_safe

# 从 predict 获取阈值常量和模型加载
from featurefox.scripts.predict import (
    load_models, DEFAULT_THRESHOLD, MIN_INSTANCE_FACES, MIN_PLANE_RATIO)

CHUNK_DIR = os.path.join(FEATUREFOX_ROOT, "_chunks")
MODELS_DIR = os.path.join(FEATUREFOX_ROOT, "models")
INST_MODEL_PATH = os.path.join(MODELS_DIR, "inst_clf_seg12only.json")
INST_CALIB_PATH = os.path.join(MODELS_DIR, "inst_calibrator_seg12only.pkl")


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


def collect_instance_dataset(step_files, ncti, verbose=True):
    """收集实例级 (X, y)，子进程隔离。复刻 train_instance.py 逻辑，但：
    - 使用 seg12-only 边分类器做剪枝（如果已训练好）
    """
    import subprocess
    import pickle as pk
    from concurrent.futures import ThreadPoolExecutor, as_completed

    CHUNK = 40
    chunks = [(i, min(i + CHUNK, len(step_files))) for i in range(0, len(step_files), CHUNK)]
    os.makedirs(CHUNK_DIR, exist_ok=True)
    max_workers = int(os.environ.get("NCTI_CHUNK_WORKERS", "32"))

    def run_inst_chunk(cid):
        start, end = chunks[cid]
        pkl = os.path.join(CHUNK_DIR, "_inst_seg12_chunk_{}.pkl".format(cid))
        env = {
            **os.environ,
            "PYTHONPATH": FEATUREFOX_ROOT,
            "PYTHONIOENCODING": "utf-8",
            # 传递 seg12-only 模型路径给子进程
            "FF_EDGE_MODEL": os.path.join(MODELS_DIR, "edge_clf_seg12only.json"),
            "FF_CALIB_MODEL": os.path.join(MODELS_DIR, "calibrator_seg12only.pkl"),
        }
        subprocess.run(
            [sys.executable, "-m", "featurefox.workers._inst_chunk_worker",
             str(start), str(end), pkl],
            env=env)
        if os.path.exists(pkl):
            with open(pkl, "rb") as f:
                X, y, meta = pk.load(f)
            try:
                os.remove(pkl)
            except Exception:
                pass
            return cid, X, y, meta
        return cid, [], [], []

    results = {}
    finished = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(run_inst_chunk, cid): cid for cid in range(len(chunks))}
        for fut in as_completed(futures):
            cid, X, y, meta = fut.result()
            results[cid] = (X, y, meta)
            finished += 1
            if verbose and (finished % 20 == 0 or finished == len(chunks)):
                print("  进度 {}/{} (累计 {} 实例)".format(
                    finished, len(chunks), sum(len(r[0]) for r in results.values())), flush=True)

    all_X, all_y, all_meta = [], [], []
    for cid in range(len(chunks)):
        if cid in results:
            X, y, meta = results[cid]
            all_X.extend(X)
            all_y.extend(y)
            all_meta.extend(meta)
    if not all_X:
        return np.zeros((0, len(INSTANCE_FEATURE_NAMES))), np.zeros(0), []
    if verbose:
        print("  完成: {} 实例".format(len(all_X)))
    return np.array(all_X, dtype=np.float32), np.array(all_y, dtype=np.int32), all_meta


def train(max_files=0):
    print("=" * 60, flush=True)
    print("FeatureFox-NCTI 第二级实例分类器训练 —— 仅 seg=12 文件", flush=True)
    print("=" * 60, flush=True)

    ncti = init_ncti_safe(PROJECT_ROOT)
    if ncti is None:
        sys.exit("NCTI 初始化失败：需 yhcad_py312 环境 + config/ncti_config.json。")

    step_files = list_step_files(max_files, 0)
    print("训练文件数 (仅 seg=12): {}".format(len(step_files)), flush=True)
    X, y, meta = collect_instance_dataset(step_files, ncti)
    n_pos = int(y.sum())
    n_neg = int(len(y) - n_pos)
    print("实例总数: {}  正例(seg12)={} ({:.1%})  负例(其它seg)={}".format(
        len(y), n_pos, n_pos / max(1, len(y)), n_neg), flush=True)

    if len(y) == 0:
        print("无实例数据，无法训练。", flush=True)
        os._exit(0)

    # 按文件名划分 train / calib / test
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
