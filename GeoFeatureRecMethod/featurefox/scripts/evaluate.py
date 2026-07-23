#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""评估 featurefox-NCTI 通槽识别（全量或子集），对比 label seg=9。

featurefox-NCTI 版零映射：predict 输出的 faces 即 cell_id（ai.FaceID 位置索引），
直接与 seg9 对比，无需 STEP→cell 映射（删掉了 STEP 版的 shell_order/几何映射两套逻辑）。

用法（从 utils/through_step/ 执行，yhcad_py312 环境）:
    python -m featurefox_blindhole.evaluate 50            # 前 50 文件
    python -m featurefox_blindhole.evaluate 0             # 全部
    python -m featurefox_blindhole.evaluate 0 0.35 50000  # 训练集外文件（offset 验证泛化）
"""

import os
import sys
import time
import json

import numpy as np

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
    # 解析参数（NCTI 版永远用 NCTI，无 --ncti 标志）
    args = sys.argv[1:]
    max_files = int(args[0]) if len(args) > 0 else 0
    threshold = float(args[1]) if len(args) > 1 else DEFAULT_THRESHOLD
    offset = int(args[2]) if len(args) > 2 else 0

    print("=" * 60, flush=True)
    print("FeatureFox-NCTI 评估 (阈值={}, offset={})".format(threshold, offset), flush=True)
    print("=" * 60, flush=True)

    ncti = init_ncti_safe(PROJECT_ROOT)
    if ncti is None:
        sys.exit("NCTI 初始化失败：需 yhcad_py312 环境 + config/ncti_config.json。")

    booster, calibrator = load_models()
    inst_booster, inst_calib = load_instance_models()
    step_files = list_step_files(max_files, offset)
    print("测试文件数: {} (offset={})".format(len(step_files), offset), flush=True)

    t0 = time.time()
    tp_total = fp_total = fn_total = 0
    file_tp = file_partial = file_miss = file_fp_only = file_ok = 0
    file_error = file_no_label = 0
    results = []

    for i, step_file in enumerate(step_files):
        name = os.path.splitext(step_file)[0]
        stp_path = os.path.join(STEPS_DIR, step_file)
        doc = None
        try:
            part, doc = load_part(stp_path, ncti)
            instances = predict_through_slots(
                stp_path, booster, calibrator, ncti=ncti, part=part, threshold=threshold,
                inst_booster=inst_booster, inst_calibrator=inst_calib)
            # 零映射：instances 的 faces 已是 cell_id（ai.FaceID 位置索引），直接收集
            detected_cells = set()
            for inst in instances:
                detected_cells.update(inst["faces"])
        except Exception as ex:
            file_error += 1
            print("[{}/{}] ERROR {} : {}".format(
                i + 1, len(step_files), name, str(ex)[:60]), flush=True)
            continue
        finally:
            if doc is not None:
                try:
                    doc.Clear()
                except Exception:
                    pass

        seg9, inst_mat, _ = load_label(name)
        if seg9 is None:
            file_no_label += 1
            continue

        tp = detected_cells & seg9
        fp = detected_cells - seg9
        fn = seg9 - detected_cells
        tp_total += len(tp)
        fp_total += len(fp)
        fn_total += len(fn)

        if len(seg9) == 0 and len(detected_cells) == 0:
            file_ok += 1
            status = "OK_NO_SLOT"
        elif detected_cells == seg9:
            file_tp += 1
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
        if status == "EXACT":
            if (i + 1) % 500 == 0:
                print("[{}/{}] ETA:{:.0f}min ...".format(
                    i + 1, len(step_files), eta / 60), flush=True)
        else:
            print("[{}/{}] {:32s}: {}".format(i + 1, len(step_files), name, status), flush=True)

        results.append({
            "name": name, "status": status,
            "detected": sorted(detected_cells), "label": sorted(seg9),
            "tp": sorted(tp), "fp": sorted(fp), "fn": sorted(fn),
        })

    elapsed = time.time() - t0
    total_valid = len([r for r in results if r["status"]])
    print("\n" + "=" * 60, flush=True)
    print("汇总 (FeatureFox-NCTI, 阈={})".format(threshold), flush=True)
    print("=" * 60, flush=True)
    print("有效文件: {} (错误 {}, 无label {})".format(
        total_valid, file_error, file_no_label), flush=True)
    print("耗时: {:.1f}s".format(elapsed), flush=True)

    p = tp_total / (tp_total + fp_total) if (tp_total + fp_total) > 0 else 0
    r = tp_total / (tp_total + fn_total) if (tp_total + fn_total) > 0 else 0
    f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0
    print("\n面级: TP={} FP={} FN={}".format(tp_total, fp_total, fn_total), flush=True)
    print("  Precision = {:.2f}%".format(p * 100), flush=True)
    print("  Recall    = {:.2f}%".format(r * 100), flush=True)
    print("  F1        = {:.2f}%".format(f1 * 100), flush=True)
    print("\n文件级: EXACT={} OK={} PARTIAL={} MISS={} FP_ONLY={}".format(
        file_tp, file_ok, file_partial, file_miss, file_fp_only), flush=True)

    report = {
        "method": "featurefox_blindhole", "threshold": threshold, "mapping": "零映射(cell_id直出)",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_files": len(step_files), "valid_files": total_valid,
        "elapsed": round(elapsed, 1),
        "face_level": {"tp": tp_total, "fp": fp_total, "fn": fn_total,
                       "precision": round(p * 100, 2), "recall": round(r * 100, 2),
                       "f1": round(f1 * 100, 2)},
        "file_level": {"exact": file_tp, "ok": file_ok, "partial": file_partial,
                       "miss": file_miss, "fp_only": file_fp_only},
        "results": results,
    }
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("\n报告: {}".format(REPORT_FILE), flush=True)

    os._exit(0)


if __name__ == "__main__":
    main()
