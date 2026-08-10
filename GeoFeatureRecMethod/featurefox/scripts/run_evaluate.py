#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""评估 featurefox_blindhole 盲孔(seg=12)识别指标 —— Linux 版。
直接运行，不依赖 -m 方式。路径已指向 /data/通槽/。
用法: python3 run_evaluate.py [max_files] [threshold] [offset]
"""

import os
import sys
import time
import json
import numpy as np

# 确保模块可导入
FEATUREFOX_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if FEATUREFOX_ROOT not in sys.path:
    sys.path.insert(0, FEATUREFOX_ROOT)
from featurefox.lib._env import get_project_root
PROJECT_ROOT = get_project_root()
if PROJECT_ROOT and PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from featurefox.lib.edge_features import build_face_graph
from featurefox.scripts.predict import (
    load_models, load_instance_models, predict_through_slots, DEFAULT_THRESHOLD)
from featurefox.lib.instance_data import list_step_files, load_label, STEPS_DIR
from featurefox.lib.ncti_backend import load_part
from featurefox.lib.ncti_faceid_map import init_ncti_safe

REPORT_FILE = os.path.join(FEATUREFOX_ROOT, "featurefox_blindhole_eval_report.json")


def main():
    args = sys.argv[1:]
    max_files = int(args[0]) if len(args) > 0 else 0
    threshold = float(args[1]) if len(args) > 1 else DEFAULT_THRESHOLD
    offset = int(args[2]) if len(args) > 2 else 0

    print("=" * 60, flush=True)
    print("FeatureFox-NCTI 盲孔评估 (seg=12, 阈值={}, offset={})".format(threshold, offset), flush=True)
    print("=" * 60, flush=True)

    ncti = init_ncti_safe(PROJECT_ROOT)
    if ncti is None:
        sys.exit("NCTI 初始化失败。")

    booster, calibrator = load_models()
    inst_booster, inst_calib = load_instance_models()
    step_files = list_step_files(max_files, offset)
    print("测试文件数: {} (offset={})".format(len(step_files), offset), flush=True)

    t0 = time.time()
    tp_total = fp_total = fn_total = 0
    file_exact = file_partial = file_miss = file_fp_only = file_ok = 0
    file_error = file_no_label = 0
    results = []

    # 批量复用 doc（避免每件新建 Document 累积 segfault）
    doc = ncti.Document()

    for i, step_file in enumerate(step_files):
        name = os.path.splitext(step_file)[0]
        stp_path = os.path.join(STEPS_DIR, step_file)

        try:
            part, _doc = load_part(stp_path, ncti, doc=doc)
            instances = predict_through_slots(
                stp_path, booster, calibrator, ncti=ncti, part=part, threshold=threshold,
                inst_booster=inst_booster, inst_calibrator=inst_calib)
            detected_cells = set()
            for inst in instances:
                detected_cells.update(inst["faces"])
        except Exception as ex:
            file_error += 1
            print("[{}/{}] ERROR {} : {}".format(
                i + 1, len(step_files), name, str(ex)[:80]), flush=True)
            continue

        seg12, inst_mat, _ = load_label(name)
        if seg12 is None:
            file_no_label += 1
            continue

        tp = detected_cells & seg12
        fp = detected_cells - seg12
        fn = seg12 - detected_cells
        tp_total += len(tp)
        fp_total += len(fp)
        fn_total += len(fn)

        if len(seg12) == 0 and len(detected_cells) == 0:
            file_ok += 1
            status = "OK_NO_SLOT"
        elif detected_cells == seg12:
            file_exact += 1
            status = "EXACT"
        elif len(tp) > 0 and len(fp) == 0:
            file_partial += 1
            status = "PARTIAL(miss)"
        elif len(tp) > 0 and len(fp) > 0:
            file_partial += 1
            status = "PARTIAL(miss+fp)"
        elif len(tp) == 0 and len(fp) > 0:
            file_fp_only += 1
            status = "FP_ONLY"
        else:
            file_miss += 1
            status = "MISS"

        elapsed = time.time() - t0
        eta = elapsed / (i + 1) * (len(step_files) - i - 1) if i > 0 else 0

        # 只打印非 EXACT 或每 200 件的进度
        if status != "EXACT" or (i + 1) % 200 == 0:
            print("[{}/{}] {:32s}: {}  (TP={} FP={} FN={})  ETA:{:.0f}min".format(
                i + 1, len(step_files), name, status, len(tp), len(fp), len(fn),
                eta / 60), flush=True)

        results.append({
            "name": name, "status": status,
            "detected": sorted(detected_cells), "label": sorted(seg12),
            "tp": sorted(tp), "fp": sorted(fp), "fn": sorted(fn),
        })

    doc.Clear()
    elapsed = time.time() - t0
    total_valid = len(results)

    print("\n" + "=" * 60, flush=True)
    print("汇总 (FeatureFox-NCTI 盲孔 seg=12, 阈={})".format(threshold), flush=True)
    print("=" * 60, flush=True)
    print("有效文件: {} (错误 {}, 无label {})".format(
        total_valid, file_error, file_no_label), flush=True)
    print("耗时: {:.1f}s ({:.1f}min)".format(elapsed, elapsed / 60), flush=True)

    p = tp_total / (tp_total + fp_total) if (tp_total + fp_total) > 0 else 0
    r = tp_total / (tp_total + fn_total) if (tp_total + fn_total) > 0 else 0
    f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0
    print("\n面级: TP={} FP={} FN={}".format(tp_total, fp_total, fn_total), flush=True)
    print("  Precision = {:.2f}%".format(p * 100), flush=True)
    print("  Recall    = {:.2f}%".format(r * 100), flush=True)
    print("  F1        = {:.2f}%".format(f1 * 100), flush=True)
    print("\n文件级: EXACT={} OK={} PARTIAL={} MISS={} FP_ONLY={}".format(
        file_exact, file_ok, file_partial, file_miss, file_fp_only), flush=True)

    report = {
        "method": "featurefox_blindhole",
        "threshold": threshold,
        "mapping": "零映射(cell_id直出)",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_files": len(step_files),
        "valid_files": total_valid,
        "elapsed": round(elapsed, 1),
        "face_level": {
            "tp": tp_total, "fp": fp_total, "fn": fn_total,
            "precision": round(p * 100, 2),
            "recall": round(r * 100, 2),
            "f1": round(f1 * 100, 2)
        },
        "file_level": {
            "exact": file_exact, "ok": file_ok,
            "partial": file_partial, "miss": file_miss,
            "fp_only": file_fp_only
        },
        "results": results,
    }
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("\n报告: {}".format(REPORT_FILE), flush=True)


if __name__ == "__main__":
    main()
