#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
NCTI-native 通槽批量测试（50 文件）。

用法:
    python test_batch_50_ncti.py [N]

    N: 测试文件数（默认 50）

需要 NCTI SDK 环境和 yhcad_py312 Python 3.12。
"""

import json
import os
import sys
import time
import traceback

# ── 路径 ──
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, "..", "..")
SDK = os.path.abspath(os.path.join(PROJECT_ROOT, "SDK"))

STEPS_DIR = r"D:\wyg\data\data\通槽\steps"
LABELS_DIR = r"D:\wyg\data\data\labels"

sys.path.insert(0, SDK)
sys.path.insert(0, os.path.abspath(PROJECT_ROOT))

# ── NCTI 初始化 ──
os.add_dll_directory(SDK)
os.add_dll_directory(os.path.join(SDK, "OCC"))
import ctypes
for dll in [
    "ncti_command.dll",
    "ncti_occ_plugin.dll",
    "ncti_doc_occ.dll",
    "ncti_render_vulkan.dll",
    "ncti_window.dll",
]:
    ctypes.CDLL(os.path.join(SDK, dll))

import ncti_python
ncti_python.Init(SDK)

from utils.through_step.detect_through_step_ncti import recognize_through_steps_ncti


# ── Label 加载 ──
def _load_label(name):
    """加载 label JSON，返回 seg=9 的 cell_id 集合。"""
    json_path = os.path.join(LABELS_DIR, name + ".json")
    if not os.path.exists(json_path):
        return None

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    seg = {}
    if isinstance(data, dict):
        seg = data.get("seg", {})
    elif isinstance(data, list) and len(data) >= 1:
        inner = data[0]
        if isinstance(inner, list) and len(inner) >= 2:
            seg = inner[1].get("seg", {})

    return {int(k) for k, v in seg.items() if v == 9}


def _import_step(doc, step_path):
    """导入 STEP 文件到文档。每个文件用新文档避免冲突。"""
    doc.New("OCC", "DCM", "GMSH")
    doc.ResetCaseResult()
    doc.SetCreateGeGeom(1)
    doc.SetImportAssemelFile(1)
    doc.RunCommand("cmd_ncti_import_file", step_path)
    names = list(doc.AllNames() or [])
    return names


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 50

    # 收集 STEP 文件
    step_files = sorted(f for f in os.listdir(STEPS_DIR) if f.endswith((".step", ".stp")))
    total = len(step_files)
    test_files = step_files[:N]
    print(f"STEP 文件总数: {total}, 本次测试: {len(test_files)} 个\n")

    doc = ncti_python.Document()

    # 统计
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
    file_skip = 0

    t0 = time.time()

    # 输出到文件，避免 NCTI 内部日志混入
    report_path = os.path.join(SCRIPT_DIR, "batch_ncti_report.txt")
    with open(report_path, "w", encoding="utf-8") as rpt:

        for i, step_file in enumerate(test_files):
            name = os.path.splitext(step_file)[0]
            step_path = os.path.join(STEPS_DIR, step_file)

            # ── 导入 & 识别 ──
            try:
                names = _import_step(doc, step_path)
                if not names:
                    rpt.write(f"[{i+1:3d}] {name}: 导入失败(names为空)\n")
                    rpt.flush()
                    file_error += 1
                    results.append({"name": name, "error": "import_empty"})
                    continue

                obj = names[0]
                result = recognize_through_steps_ncti(ncti_python, doc, obj)
                instances = result["instances"]
                detected_cells = set(result["selected_cells"])

            except Exception as e:
                rpt.write(f"[{i+1:3d}] {name}: 错误 - {e}\n")
                traceback.print_exc(file=rpt)
                rpt.flush()
                file_error += 1
                results.append({"name": name, "error": str(e)})
                continue

            # ── 加载 label ──
            seg9 = _load_label(name)
            if seg9 is None:
                rpt.write(f"[{i+1:3d}] {name}: 无 label, 跳过\n")
                rpt.flush()
                file_skip += 1
                results.append({"name": name, "skip": True})
                continue

            # ── 对比 ──
            tp = detected_cells & seg9
            fp = detected_cells - seg9
            fn = seg9 - detected_cells

            tp_total += len(tp)
            fp_total += len(fp)
            fn_total += len(fn)

            # 文件级判定
            if len(seg9) == 0 and len(detected_cells) == 0:
                file_ok += 1
                status = "OK"
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

            # 打印
            n_inst = len(instances)
            scores = [f"{inst['score']:.1f}" for inst in instances]
            types = [inst.get("type", "?") for inst in instances]

            det_str = ",".join(str(c) for c in sorted(detected_cells)) or "-"
            lbl_str = ",".join(str(c) for c in sorted(seg9)) or "-"
            fp_str = ",".join(str(c) for c in sorted(fp)) or "-"
            fn_str = ",".join(str(c) for c in sorted(fn)) or "-"

            rpt.write(f"[{i+1:3d}] {name}: {status} | "
                      f"det({len(detected_cells)}面/{n_inst}实例,scores={scores},types={types}): [{det_str}] "
                      f"label({len(seg9)}面): [{lbl_str}]\n")
            if fp:
                rpt.write(f"       FP: [{fp_str}]\n")
            if fn:
                rpt.write(f"       FN: [{fn_str}]\n")
            rpt.flush()

            results.append({
                "name": name,
                "status": status,
                "detected": sorted(detected_cells),
                "label": sorted(seg9),
                "tp": sorted(tp),
                "fp": sorted(fp),
                "fn": sorted(fn),
                "n_inst": n_inst,
                "scores": scores,
                "types": types,
            })

    elapsed = time.time() - t0

    # ── 汇总（同时写到报告和控制台） ──
    def log(msg=""):
        rpt.write(msg + "\n")
        print(msg)

    log("\n" + "=" * 70)
    log(f"汇总统计  (耗时 {elapsed:.1f}s, {len(test_files)} 文件)")
    log("=" * 70)

    valid = len([r for r in results if "error" not in r and "skip" not in r])
    log(f"有效文件: {valid}   错误: {file_error}   无label: {file_skip}")

    precision = tp_total / (tp_total + fp_total) if (tp_total + fp_total) > 0 else 0
    recall = tp_total / (tp_total + fn_total) if (tp_total + fn_total) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    log(f"\n面级统计:")
    log(f"  TP={tp_total}, FP={fp_total}, FN={fn_total}")
    log(f"  Precision = {precision*100:.2f}%")
    log(f"  Recall    = {recall*100:.2f}%")
    log(f"  F1        = {f1*100:.2f}%")

    log(f"\n文件级统计:")
    log(f"  EXACT(完全正确): {file_tp}")
    log(f"  OK(无通槽):      {file_ok}")
    log(f"  PARTIAL(部分):   {file_partial}")
    log(f"  MISS(漏检):      {file_miss}")
    log(f"  FP_ONLY(纯误检): {file_fp_only}")
    log(f"  ERROR:           {file_error}")

    if valid > 0:
        log(f"\n文件级准确率: {(file_tp+file_ok)/valid*100:.1f}% ({file_tp+file_ok}/{valid})")
        log(f"文件级召回率: {(file_tp+file_partial)/valid*100:.1f}% ({file_tp+file_partial}/{valid})")

    rpt.flush()
    print(f"\n报告已写入: {report_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
    finally:
        os._exit(0)
