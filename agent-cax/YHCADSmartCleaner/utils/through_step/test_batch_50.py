#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""批量测试通槽识别：50 文件，对比 STEP 检测 vs label seg=9。"""

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
    # 收集 STEP 文件
    step_files = sorted(f for f in os.listdir(STEPS_DIR) if f.endswith(".step"))
    print(f"STEP 文件总数: {len(step_files)}")

    # 取前 50 个
    test_files = step_files[:50]
    print(f"本次测试: {len(test_files)} 个文件\n")

    results = []
    tp_total = 0  # true positive faces
    fp_total = 0  # false positive faces
    fn_total = 0  # false negative faces
    file_tp = 0   # 文件级完全正确
    file_partial = 0  # 文件级部分正确
    file_miss = 0  # 文件级漏检
    file_fp_only = 0  # 文件级只有误检
    file_ok = 0    # 无通槽且无检出

    # Windows GBK console: 避免表情符号编码错误
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    for i, step_file in enumerate(test_files):
        name = os.path.splitext(step_file)[0]
        stp_path = os.path.join(STEPS_DIR, step_file)

        try:
            # STEP 识别
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

            # 每个实例的 cell_id 列表
            inst_cell_groups = []
            for inst in instances:
                group = set()
                for fid in inst["faces"]:
                    cid = face_map.get(fid)
                    if cid is not None:
                        group.add(cid)
                inst_cell_groups.append(group)

        except Exception as e:
            print(f"[{i+1:2d}] {name}: ❌ 解析错误 - {e}")
            traceback.print_exc()
            results.append({"name": name, "error": str(e)})
            continue

        # 加载 label
        seg9, bottom_ids = _load_label(name)
        if seg9 is None:
            print(f"[{i+1:2d}] {name}: ⚠️ 无 label 文件，跳过")
            results.append({"name": name, "skip": True})
            continue

        # 对比
        tp = detected_cells & seg9
        fp = detected_cells - seg9
        fn = seg9 - detected_cells

        tp_total += len(tp)
        fp_total += len(fp)
        fn_total += len(fn)

        # 文件级判定
        if len(seg9) == 0 and len(detected_cells) == 0:
            file_ok += 1
            status = "✅ 无通槽"
        elif detected_cells == seg9:
            file_tp += 1
            status = "✅ 完全正确"
        elif len(tp) > 0 and len(fp) == 0:
            file_partial += 1
            status = "🔶 部分正确(漏检)"
        elif len(tp) > 0 and len(fp) > 0:
            file_partial += 1
            status = "🔶 部分正确(漏检+误检)"
        elif len(tp) == 0 and len(fp) > 0:
            file_fp_only += 1
            status = "❌ 纯误检"
        else:
            file_miss += 1
            status = "❌ 漏检"

        # 打印详情
        det_str = ",".join(str(c) for c in sorted(detected_cells)) if detected_cells else "∅"
        lbl_str = ",".join(str(c) for c in sorted(seg9)) if seg9 else "∅"
        tp_str = ",".join(str(c) for c in sorted(tp)) if tp else "∅"
        fp_str = ",".join(str(c) for c in sorted(fp)) if fp else "∅"
        fn_str = ",".join(str(c) for c in sorted(fn)) if fn else "∅"

        n_inst = len(instances)
        scores = [f"{inst['score']:.1f}" for inst in instances]

        print(f"[{i+1:2d}] {name}: {status}")
        print(f"     检出({len(detected_cells)}面/{n_inst}实例,scores={scores}): [{det_str}]")
        print(f"     label({len(seg9)}面): [{lbl_str}]")
        if fp:
            print(f"     误检(FP): [{fp_str}]")
        if fn:
            print(f"     漏检(FN): [{fn_str}]")

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
        })

    # 汇总
    print("\n" + "=" * 70)
    print("汇总统计")
    print("=" * 70)
    total_valid = len([r for r in results if "error" not in r and "skip" not in r])
    print(f"有效文件数: {total_valid}")

    # 面 级 precision / recall / F1
    precision = tp_total / (tp_total + fp_total) if (tp_total + fp_total) > 0 else 0
    recall = tp_total / (tp_total + fn_total) if (tp_total + fn_total) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    print(f"\n面级统计:")
    print(f"  TP={tp_total}, FP={fp_total}, FN={fn_total}")
    print(f"  Precision = {precision*100:.2f}%")
    print(f"  Recall    = {recall*100:.2f}%")
    print(f"  F1        = {f1*100:.2f}%")

    print(f"\n文件级统计:")
    print(f"  ✅ 完全正确: {file_tp}")
    print(f"  ✅ 无通槽(正确): {file_ok}")
    print(f"  🔶 部分正确: {file_partial}")
    print(f"  ❌ 漏检:     {file_miss}")
    print(f"  ❌ 纯误检:   {file_fp_only}")

    # 实例级统计：每个检出的实例是否有足够的 seg=9 面匹配
    inst_match = 0
    inst_total = 0
    for r in results:
        if "error" in r or "skip" in r:
            continue
        label_cells = set(r["label_cells"])
        # 从原始结果获取实例
        name = r["name"]
        stp_path = os.path.join(STEPS_DIR, name + ".step")
        try:
            result = recognize_through_steps_from_stp(stp_path)
            parser = result["step_parser"]
            face_order = _shell_face_order(parser)
            face_map = _step_face_to_cell_id(face_order)
            for inst in result["instances"]:
                inst_cells = set()
                for fid in inst["faces"]:
                    cid = face_map.get(fid)
                    if cid is not None:
                        inst_cells.add(cid)
                inst_total += 1
                # 实例中 >50% 的面在 seg=9 中 → 匹配
                if inst_cells and len(inst_cells & label_cells) >= len(inst_cells) * 0.5:
                    inst_match += 1
        except Exception:
            pass

    if inst_total > 0:
        print(f"\n实例级统计:")
        print(f"  检出实例: {inst_total}")
        print(f"  正确实例: {inst_match}")
        print(f"  实例精度: {inst_match/inst_total*100:.1f}%")


if __name__ == "__main__":
    main()
