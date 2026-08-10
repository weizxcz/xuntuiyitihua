#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""评估 FeatureFox 通槽识别（全量或子集），对比 label seg=9。

用法:
    python evaluate.py 50            # 前 50 文件（旧映射，不需 NCTI）
    python evaluate.py 0 --ncti       # 全部文件（NCTI 几何映射，需 yhcad_py312）
    python evaluate.py 0 0.35 14000 --ncti  # 训练集外文件 + NCTI 几何映射
"""

import os
import sys
import time
import json
import io

import numpy as np

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
UTILS_DIR = os.path.dirname(os.path.dirname(THIS_DIR))
TS_DIR = os.path.dirname(THIS_DIR)
for p in (UTILS_DIR, TS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from detect_blind_holes_and_export_stp_v15_22 import StepParser
from featurefox.edge_features import build_face_graph
from featurefox.predict import (
    load_models, load_instance_models, predict_through_slots, DEFAULT_THRESHOLD,
)
from featurefox.instance_data import list_step_files, load_label, shell_face_order

STEPS_DIR = r"D:\wyg\data\data\通槽\steps"
REPORT_FILE = os.path.join(THIS_DIR, "featurefox_eval_report.json")


# ---- 旧映射（shell_face_order，基于 STEP entity 顺序）----

def _detected_cells_shell_order(instances, face_map):
    cells = set()
    for inst in instances:
        for fid in inst["faces"]:
            cid = face_map.get(fid)
            if cid is not None:
                cells.add(cid)
    return cells


# ---- 新几何映射（GetFaceMidPoint(cell_index) + ai.FaceID 位置）----

def _ncti_point_to_tuple(pt):
    """NCTI 点 → (x,y,z)。兼容 Point(.X/.Y/.Z) 与序列。"""
    try:
        return (float(pt.X), float(pt.Y), float(pt.Z))
    except (AttributeError, TypeError):
        return (float(pt[0]), float(pt[1]), float(pt[2]))


def _build_face_centroids(parser, fa_attrs):
    centroids = {}
    for fid in parser.advanced_faces:
        c = fa_attrs.centroid(fid)
        if c is not None:
            centroids[fid] = (float(c[0]), float(c[1]), float(c[2]))
    return centroids


def _geometric_pos_map(parser, fa_attrs, doc, ncti, obj_name, tol=None):
    """STEP entity ID → ai.FaceID 位置索引（几何最近邻，GetFaceMidPoint 用 cell_index）。"""
    ai = ncti.AiModel(doc, obj_name)
    face_ids = ai.FaceID
    n_faces = len(face_ids)

    # GetFaceMidPoint(obj_name, cell_index) → cell_index 位置面的中点
    ncti_mids = {}
    for i in range(n_faces):
        try:
            pt = doc.GetFaceMidPoint(obj_name, i)
            ncti_mids[i] = _ncti_point_to_tuple(pt)
        except Exception:
            continue
    if not ncti_mids:
        return {}, n_faces

    step_centroids = _build_face_centroids(parser, fa_attrs)
    if not step_centroids:
        return {}, n_faces

    if tol is None:
        all_pts = list(step_centroids.values())
        xs = [p[0] for p in all_pts]
        ys = [p[1] for p in all_pts]
        zs = [p[2] for p in all_pts]
        diag = ((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2
                + (max(zs) - min(zs)) ** 2) ** 0.5
        tol = diag * 0.15

    entity_to_cell = {}
    for eid, sc in step_centroids.items():
        best_cell, best_d = None, None
        for cell_idx, npt in ncti_mids.items():
            d = (sc[0] - npt[0]) ** 2 + (sc[1] - npt[1]) ** 2 + (sc[2] - npt[2]) ** 2
            if best_d is None or d < best_d:
                best_d, best_cell = d, cell_idx
        if best_cell is not None and best_d <= tol * tol:
            entity_to_cell[eid] = (best_cell, best_d)

    cell_to_entity = {}
    for eid, (cid, _) in entity_to_cell.items():
        cell_to_entity.setdefault(cid, []).append(eid)
    pos_map = {}
    for eid, (cid, d2) in entity_to_cell.items():
        cands = cell_to_entity.get(cid, [])
        if len(cands) > 1:
            best_eid = min(cands, key=lambda e: entity_to_cell[e][1])
            if eid != best_eid:
                continue
        pos_map[eid] = cid
    return pos_map, n_faces


def _detected_cells_geometric(instances, pos_map):
    """用几何映射将 entity ID 映射为 cell_id。"""
    cells = set()
    for inst in instances:
        for fid in inst["faces"]:
            cid = pos_map.get(fid)
            if cid is not None:
                cells.add(cid)
    return cells


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    # 解析参数
    use_ncti = "--ncti" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--ncti"]
    max_files = int(args[0]) if len(args) > 0 else 0
    threshold = float(args[1]) if len(args) > 1 else DEFAULT_THRESHOLD
    offset = int(args[2]) if len(args) > 2 else 0

    mode = "NCTI 几何映射" if use_ncti else "shell_order 旧映射"
    print("=" * 60)
    print("FeatureFox 评估 (阈值={}, offset={}, 模式={})".format(
        threshold, offset, mode))
    print("=" * 60)

    booster, calibrator = load_models()
    inst_booster, inst_calib = load_instance_models()
    step_files = list_step_files(max_files, offset)
    print("测试文件数: {} (offset={})".format(len(step_files), offset))

    # NCTI 初始化（仅几何映射模式）
    ncti = None
    if use_ncti:
        try:
            sys.path.insert(0, os.path.dirname(os.path.dirname(UTILS_DIR)))
            from config.config_load import init_ncti_config
            ncti = init_ncti_config()
            if ncti is None:
                sys.exit("NCTI 初始化失败（需 yhcad_py312 环境）")
            print("NCTI 已初始化")
        except Exception as e:
            sys.exit("NCTI 不可用: {}（需 yhcad_py312 环境）".format(e))

    t0 = time.time()
    tp_total = fp_total = fn_total = 0
    file_tp = file_partial = file_miss = file_fp_only = file_ok = 0
    file_error = file_no_label = 0
    results = []

    for i, step_file in enumerate(step_files):
        name = os.path.splitext(step_file)[0]
        stp_path = os.path.join(STEPS_DIR, step_file)
        try:
            parser = StepParser(stp_path)
            parser.parse()
            fa_graph = build_face_graph(parser)
            _, fa_attrs = fa_graph
            instances = predict_through_slots(
                stp_path, booster, calibrator, threshold, fa_graph=fa_graph, parser=parser,
                inst_booster=inst_booster, inst_calibrator=inst_calib)

            if use_ncti and ncti is not None:
                # NCTI 几何映射
                doc = ncti.Document()
                doc.New("OCC", "DCM", 0)
                doc.RunCommand("cmd_ncti_import_file", str(stp_path), "testbox")
                ai = ncti.AiModel(doc, "testbox")
                obj_name = "testbox"
                pos_map, _ = _geometric_pos_map(parser, fa_attrs, doc, ncti, obj_name)
                detected_cells = _detected_cells_geometric(instances, pos_map)
                try:
                    doc.Clear()
                except Exception:
                    pass
            else:
                # 旧映射：shell_face_order（基于 STEP entity 顺序）
                face_order = shell_face_order(parser)
                face_map = {fid: idx for idx, fid in enumerate(face_order)}
                detected_cells = _detected_cells_shell_order(instances, face_map)
        except Exception as ex:
            file_error += 1
            print("[{}/{}] ERROR {} : {}".format(i + 1, len(step_files), name, ex))
            continue

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
                print("[{}/{}] ETA:{:.0f}min ...".format(i + 1, len(step_files), eta / 60))
        else:
            print("[{}/{}] {:32s}: {}".format(i + 1, len(step_files), name, status))

        results.append({
            "name": name, "status": status,
            "detected": sorted(detected_cells), "label": sorted(seg9),
            "tp": sorted(tp), "fp": sorted(fp), "fn": sorted(fn),
        })

    elapsed = time.time() - t0
    total_valid = len([r for r in results if r["status"]])
    print("\n" + "=" * 60)
    print("汇总 (FeatureFox, 阈={}, {})".format(threshold, mode))
    print("=" * 60)
    print("有效文件: {} (错误 {}, 无label {})".format(total_valid, file_error, file_no_label))
    print("耗时: {:.1f}s".format(elapsed))

    p = tp_total / (tp_total + fp_total) if (tp_total + fp_total) > 0 else 0
    r = tp_total / (tp_total + fn_total) if (tp_total + fn_total) > 0 else 0
    f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0
    print("\n面级: TP={} FP={} FN={}".format(tp_total, fp_total, fn_total))
    print("  Precision = {:.2f}%".format(p * 100))
    print("  Recall    = {:.2f}%".format(r * 100))
    print("  F1        = {:.2f}%".format(f1 * 100))
    print("\n文件级: EXACT={} OK={} PARTIAL={} MISS={} FP_ONLY={}".format(
        file_tp, file_ok, file_partial, file_miss, file_fp_only))

    report = {
        "method": "featurefox", "threshold": threshold, "mapping": mode,
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
    print("\n报告: {}".format(REPORT_FILE))

    if use_ncti:
        # NCTI DLL 析构 segfault，直接退出
        os._exit(0)


if __name__ == "__main__":
    main()