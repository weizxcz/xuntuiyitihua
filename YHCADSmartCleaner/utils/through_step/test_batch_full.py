#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""批量测试通槽识别：全量文件，对比 STEP 检测 vs label seg=9。

用法：
    python test_batch_full.py              # 全部 ~17800 文件
    python test_batch_full.py 500          # 前 500 个文件
    python test_batch_full.py 50           # 前 50 个文件（快速验证）

输出：
    - 控制台实时进度 + 汇总统计
    - JSON 结果文件：batch_full_report.json
"""

import json
import os
import sys
import time
import traceback

UTILS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if UTILS_DIR not in sys.path:
    sys.path.insert(0, UTILS_DIR)

from detect_blind_holes_and_export_stp_v15_22 import StepParser
from detect_through_step import recognize_through_steps_from_stp

STEPS_DIR = r"D:\wyg\data\data\通槽\steps"
LABELS_DIR = r"D:\wyg\data\data\通槽\label"
REPORT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "batch_full_report.json")


def _shell_face_order(parser):
    """获取 CLOSED_SHELL 内 ADVANCED_FACE 的顺序列表，用于映射到 cell_id。"""
    for sid, entity in parser.entities.items():
        if entity.get("type") not in {"CLOSED_SHELL", "OPEN_SHELL"}:
            continue
        refs = [r for r in parser._refs(entity.get("params", ""))
                if r in parser.advanced_faces]
        if refs:
            return refs
    # 无 shell，退回全部面顺序
    return sorted(parser.advanced_faces.keys())


def _step_face_to_cell_id(step_faces_in_order):
    """构建 STEP entity_id → cell_id 映射（与 NCTI 一致）。"""
    return {fid: idx for idx, fid in enumerate(step_faces_in_order)}


def _load_label(name):
    """加载 label JSON，返回 seg=9 的 cell_id 集合。"""
    json_path = os.path.join(LABELS_DIR, name + ".json")
    if not os.path.exists(json_path):
        return None, None

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 新格式：dict
    if isinstance(data, dict):
        seg = data.get("seg", {})
        bottom = data.get("bottom", {})
        seg9 = {int(k) for k, v in seg.items() if v == 9}
        bottom_ids = {int(k) for k, v in bottom.items() if v == 1}
        return seg9, bottom_ids

    # 旧格式：[[name, {seg, inst, bottom}], ...]
    if isinstance(data, list) and len(data) >= 1:
        inner = data[0][1] if isinstance(data[0], list) else data[0]
        seg = inner.get("seg", {})
        bottom = inner.get("bottom", {})
        seg9 = {int(k) for k, v in seg.items() if v == 9}
        bottom_ids = {int(k) for k, v in bottom.items() if v == 1}
        return seg9, bottom_ids

    return None, None


def main():
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    # 参数：测试文件数
    max_files = int(sys.argv[1]) if len(sys.argv) > 1 else 0  # 0 = 全部

    # 收集 STEP 文件
    step_files = sorted(f for f in os.listdir(STEPS_DIR) if f.endswith(".step"))
    print("STEP 文件总数: {}".format(len(step_files)))

    if max_files > 0:
        test_files = step_files[:max_files]
    else:
        test_files = step_files
    print("本次测试: {} 个文件\n".format(len(test_files)))

    t0 = time.time()

    results = []
    tp_total = 0
    fp_total = 0
    fn_total = 0
    file_tp = 0
    file_partial = 0
    file_miss = 0
    file_fp_only = 0
    file_ok = 0
    file_error = 0
    file_no_label = 0
    inst_match = 0
    inst_total = 0

    for i, step_file in enumerate(test_files):
        name = os.path.splitext(step_file)[0]
        stp_path = os.path.join(STEPS_DIR, step_file)
        t_file_start = time.time()

        try:
            # STEP 识别（只解析一次，缓存结果）
            result = recognize_through_steps_from_stp(stp_path)
            instances = result["instances"]
            detected_step_faces = result["selected_step_faces"]
            parser = result["step_parser"]

            # 建立 STEP face_id → cell_id 映射
            face_order = _shell_face_order(parser)
            face_map = _step_face_to_cell_id(face_order)

            # 映射检出面到 cell_id
            detected_cells = set()
            for fid in detected_step_faces:
                cid = face_map.get(fid)
                if cid is not None:
                    detected_cells.add(cid)

            # 每个实例的 cell_id 列表（从缓存的 parser 获取，不重新解析）
            inst_cell_groups = []
            for inst in instances:
                group = set()
                for fid in inst["faces"]:
                    cid = face_map.get(fid)
                    if cid is not None:
                        group.add(cid)
                inst_cell_groups.append(group)

        except Exception as e:
            file_error += 1
            t_file = time.time() - t_file_start
            elapsed = time.time() - t0
            print("[{:5d}/{:5d}] {:40s}: ERROR ({:.2f}s) - {}  [elapsed {:.1f}s]".format(
                i + 1, len(test_files), name, t_file, str(e)[:60], elapsed))
            results.append({"name": name, "error": str(e), "time": round(t_file, 3)})
            continue

        # 加载 label
        seg9, bottom_ids = _load_label(name)
        if seg9 is None:
            file_no_label += 1
            results.append({"name": name, "skip": True})
            continue

        # 对比
        tp = detected_cells & seg9
        fp = detected_cells - seg9
        fn = seg9 - detected_cells

        tp_total += len(tp)
        fp_total += len(fp)
        fn_total += len(fn)

        # 实例级统计（从缓存数据计算，不重新解析）
        for ig in inst_cell_groups:
            inst_total += 1
            if ig and len(ig & seg9) >= len(ig) * 0.5:
                inst_match += 1

        # 文件级判定
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

        t_file = time.time() - t_file_start
        elapsed = time.time() - t0
        eta = elapsed / (i + 1) * (len(test_files) - i - 1) if i > 0 else 0

        # 每个文件一行摘要（关键信息）
        n_inst = len(instances)
        scores = [round(inst['score'], 1) for inst in instances]
        types = [inst.get('type', '?') for inst in instances]

        # 只对非正常文件打印详情
        if status in ("EXACT", "OK_NO_SLOT"):
            print("[{:5d}/{:5d}] {:40s}: {:16s}  {:.2f}s  ETA:{:.0f}m".format(
                i + 1, len(test_files), name, status, t_file, eta / 60))
        else:
            det_str = ",".join(str(c) for c in sorted(detected_cells)) if detected_cells else "-"
            lbl_str = ",".join(str(c) for c in sorted(seg9)) if seg9 else "-"
            fp_str = ",".join(str(c) for c in sorted(fp)) if fp else "-"
            fn_str = ",".join(str(c) for c in sorted(fn)) if fn else "-"
            print("[{:5d}/{:5d}] {:40s}: {:16s} | det({}面/{}inst,scores={},types={}): [{}] label({}面): [{}]".format(
                i + 1, len(test_files), name, status,
                len(detected_cells), n_inst, scores, types,
                det_str[:60], len(seg9), lbl_str[:40]))
            if fp:
                print("         FP: [{}]".format(fp_str[:80]))
            if fn:
                print("         FN: [{}]".format(fn_str[:80]))

        results.append({
            "name": name,
            "status": status,
            "detected_cells": sorted(detected_cells),
            "label_cells": sorted(seg9),
            "tp": sorted(tp),
            "fp": sorted(fp),
            "fn": sorted(fn),
            "n_instances": n_inst,
            "scores": scores,
            "types": types,
            "time": round(t_file, 3),
        })

        # 每 500 个文件保存一次中间结果
        if (i + 1) % 500 == 0:
            _save_report(results, tp_total, fp_total, fn_total,
                         file_tp, file_partial, file_miss, file_fp_only, file_ok,
                         file_error, file_no_label, inst_match, inst_total,
                         elapsed, len(test_files), i + 1, REPORT_FILE)

    elapsed = time.time() - t0

    # 汇总
    total_valid = len([r for r in results if "error" not in r and "skip" not in r])
    print("\n" + "=" * 70)
    print("汇总统计 (v5: 反平行壁面 + 连续二面角 + 质心距离对称)")
    print("=" * 70)
    print("有效文件数: {}  (错误: {}, 无label: {})".format(total_valid, file_error, file_no_label))
    print("总耗时: {:.1f}s ({:.1f}min)".format(elapsed, elapsed / 60))
    print("平均每文件: {:.3f}s".format(elapsed / max(1, total_valid)))

    # 面 级 precision / recall / F1
    precision = tp_total / (tp_total + fp_total) if (tp_total + fp_total) > 0 else 0
    recall = tp_total / (tp_total + fn_total) if (tp_total + fn_total) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    print("\n面级统计:")
    print("  TP={}, FP={}, FN={}".format(tp_total, fp_total, fn_total))
    print("  Precision = {:.2f}%".format(precision * 100))
    print("  Recall    = {:.2f}%".format(recall * 100))
    print("  F1        = {:.2f}%".format(f1 * 100))

    print("\n文件级统计:")
    print("  EXACT (完全正确):     {}".format(file_tp))
    print("  OK_NO_SLOT (无通槽):  {}".format(file_ok))
    print("  PARTIAL (部分正确):   {}".format(file_partial))
    print("  MISS (漏检):          {}".format(file_miss))
    print("  FP_ONLY (纯误检):     {}".format(file_fp_only))

    if inst_total > 0:
        print("\n实例级统计:")
        print("  检出实例: {}".format(inst_total))
        print("  正确实例: {}".format(inst_match))
        print("  实例精度: {:.1f}%".format(inst_match / inst_total * 100))

    # 保存最终结果
    _save_report(results, tp_total, fp_total, fn_total,
                 file_tp, file_partial, file_miss, file_fp_only, file_ok,
                 file_error, file_no_label, inst_match, inst_total,
                 elapsed, len(test_files), len(test_files), REPORT_FILE)
    print("\n结果已保存: {}".format(REPORT_FILE))


def _save_report(results, tp_total, fp_total, fn_total,
                 file_tp, file_partial, file_miss, file_fp_only, file_ok,
                 file_error, file_no_label, inst_match, inst_total,
                 elapsed, total_files, processed, report_path):
    """保存 JSON 报告。"""
    total_valid = len([r for r in results if "error" not in r and "skip" not in r])
    precision = tp_total / (tp_total + fp_total) if (tp_total + fp_total) > 0 else 0
    recall = tp_total / (tp_total + fn_total) if (tp_total + fn_total) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    report = {
        "version": "v5",
        "improvements": ["anti_parallel_wall", "continuous_dihedral", "centroid_distance_symmetry"],
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_files": total_files,
        "processed": processed,
        "valid_files": total_valid,
        "errors": file_error,
        "no_label": file_no_label,
        "elapsed_seconds": round(elapsed, 1),
        "face_level": {
            "tp": tp_total,
            "fp": fp_total,
            "fn": fn_total,
            "precision": round(precision * 100, 2),
            "recall": round(recall * 100, 2),
            "f1": round(f1 * 100, 2),
        },
        "file_level": {
            "exact": file_tp,
            "ok_no_slot": file_ok,
            "partial": file_partial,
            "miss": file_miss,
            "fp_only": file_fp_only,
        },
        "instance_level": {
            "total": inst_total,
            "correct": inst_match,
            "precision": round(inst_match / inst_total * 100, 1) if inst_total > 0 else 0,
        },
        "results": results,
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
