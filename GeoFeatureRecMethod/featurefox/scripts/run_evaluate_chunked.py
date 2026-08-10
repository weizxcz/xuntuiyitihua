#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""评估 featurefox 盲孔(seg=12)识别指标 —— Linux 版，子进程隔离。
每 chunk 一个子进程，避免 NCTI C++ 累积 segfault。
用法: python3 run_evaluate_chunked.py [max_files] [threshold] [offset]
"""

import os
import sys
import time
import json
import pickle
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

FEATUREFOX_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if FEATUREFOX_ROOT not in sys.path:
    sys.path.insert(0, FEATUREFOX_ROOT)
from featurefox.lib._env import get_project_root
PROJECT_ROOT = get_project_root()
if PROJECT_ROOT and PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from featurefox.lib.instance_data import list_step_files
from featurefox.scripts.predict import DEFAULT_THRESHOLD

REPORT_FILE = os.path.join(FEATUREFOX_ROOT, "featurefox_blindhole_eval_report.json")
REPORT_FILE_TEST = os.path.join(FEATUREFOX_ROOT, "featurefox_blindhole_eval_report_test.json")
CHUNK_DIR = os.path.join(FEATUREFOX_ROOT, "_chunks")
CHUNK_SIZE = 30  # 每 chunk 30 件，子进程隔离 NCTI


def run_chunk_worker(start_idx, end_idx, threshold, offset):
    """子进程：处理 [start_idx, end_idx) 的文件，返回 chunk_results pickle。"""
    import os, sys, time
    # 子进程内重新设置路径
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    _featfox_root = os.path.dirname(_script_dir)
    if _featfox_root not in sys.path:
        sys.path.insert(0, _featfox_root)
    from featurefox.lib._env import get_project_root as _get_pr
    _project_root = _get_pr()
    if _project_root and _project_root not in sys.path:
        sys.path.insert(0, _project_root)

    from featurefox.lib.edge_features import build_face_graph
    from featurefox.scripts.predict import (
        load_models, load_instance_models, predict_through_slots)
    from featurefox.lib.instance_data import list_step_files, load_label, STEPS_DIR
    from featurefox.lib.ncti_backend import load_part
    from featurefox.lib.ncti_faceid_map import init_ncti_safe

    ncti = init_ncti_safe(_PROJECT_ROOT)
    if ncti is None:
        return {"errors": ["NCTI init failed"], "results": [], "tp": 0, "fp": 0, "fn": 0,
                "exact": 0, "ok": 0, "partial": 0, "miss": 0, "fp_only": 0, "error": 1}

    booster, calibrator = load_models()
    inst_booster, inst_calib = load_instance_models()
    step_files = list_step_files(0, offset)
    chunk_files = step_files[start_idx:end_idx]

    tp_total = fp_total = fn_total = 0
    file_exact = file_partial = file_miss = file_fp_only = file_ok = 0
    file_error = file_no_label = 0
    results = []
    errors = []

    # 每件新建 Document（子进程生命周期短，不会累积）
    for i, step_file in enumerate(chunk_files):
        name = os.path.splitext(step_file)[0]
        stp_path = os.path.join(STEPS_DIR, step_file)
        doc = None
        try:
            part, doc = load_part(stp_path, ncti)
            instances = predict_through_slots(
                stp_path, booster, calibrator, ncti=ncti, part=part, threshold=threshold,
                inst_booster=inst_booster, inst_calibrator=inst_calib)
            detected_cells = set()
            for inst in instances:
                detected_cells.update(inst["faces"])
        except Exception as ex:
            file_error += 1
            errors.append(f"{name}: {str(ex)[:80]}")
            if doc is not None:
                try:
                    doc.Clear()
                except Exception:
                    pass
            continue

        seg12, inst_mat, _ = load_label(name)
        if seg12 is None:
            file_no_label += 1
            if doc is not None:
                try:
                    doc.Clear()
                except Exception:
                    pass
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

        if status != "EXACT" and status != "OK_NO_SLOT":
            sys.stderr.write(f"[{start_idx + i + 1}] {name}: {status} TP={len(tp)} FP={len(fp)} FN={len(fn)}\n")

        results.append({
            "name": name, "status": status,
            "detected": sorted(detected_cells), "label": sorted(seg12),
            "tp": sorted(tp), "fp": sorted(fp), "fn": sorted(fn),
        })

        if doc is not None:
            try:
                doc.Clear()
            except Exception:
                pass

    return {
        "results": results, "errors": errors,
        "tp": tp_total, "fp": fp_total, "fn": fn_total,
        "exact": file_exact, "ok": file_ok,
        "partial": file_partial, "miss": file_miss,
        "fp_only": file_fp_only, "error": file_error,
        "no_label": file_no_label,
    }


def main():
    args = sys.argv[1:]
    max_files = int(args[0]) if len(args) > 0 else 0
    threshold = float(args[1]) if len(args) > 1 else DEFAULT_THRESHOLD
    offset = int(args[2]) if len(args) > 2 else 0

    # --test-only: 第4个参数，只评估训练 test 集（复现 train.py random_state=42 的 test 划分）
    test_only = (len(args) >= 4 and args[3] == "--test-only")
    name_filter = None
    filter_file = os.path.join(THIS_DIR, "test_names.json")
    if test_only:
        if os.path.exists(filter_file):
            with open(filter_file) as f:
                name_filter = set(json.load(f))
            print("Test-only 模式: 过滤到 {} 个test文件".format(len(name_filter)), flush=True)
        else:
            print("警告: test_names.json 不存在，先运行 gen_test_split.py", flush=True)

    step_files = list_step_files(max_files, offset, name_filter=name_filter)
    mode_tag = "[Test-Only] " if test_only else ""
    print("=" * 60, flush=True)
    print("{}FeatureFox-NCTI 盲孔评估 (seg=12, 阈={}, offset={})".format(mode_tag, threshold, offset), flush=True)
    print("文件数: {}  chunk_size: {}  chunks: {}".format(
        len(step_files), CHUNK_SIZE, (len(step_files) + CHUNK_SIZE - 1) // CHUNK_SIZE), flush=True)
    print("=" * 60, flush=True)

    os.makedirs(CHUNK_DIR, exist_ok=True)
    max_workers = int(os.environ.get("NCTI_CHUNK_WORKERS", "8"))
    chunks = [(i, min(i + CHUNK_SIZE, len(step_files)))
              for i in range(0, len(step_files), CHUNK_SIZE)]

    t0 = time.time()

    def run(cid):
        s, e = chunks[cid]
        pkl = os.path.join(CHUNK_DIR, f"_eval_{cid}.pkl")
        env = {
            **os.environ,
            "PYTHONPATH": os.pathsep.join([FEATUREFOX_ROOT, PROJECT_ROOT] +
                os.environ.get("PYTHONPATH", "").split(os.pathsep)),
            "PYTHONIOENCODING": "utf-8",
        }
        if test_only:
            env["EVAL_FILTER_FILE"] = filter_file
        # 将 chunk_worker 代码写入临时 .py 文件传给子进程
        worker_script = os.path.join(CHUNK_DIR, f"_eval_worker_{cid}.py")
        with open(worker_script, "w") as f:
            f.write(CHUNK_WORKER_TEMPLATE.format(
                start_idx=s, end_idx=e, threshold=threshold, offset=offset, pkl_path=pkl))
        subprocess.run([sys.executable, worker_script], env=env)
        if os.path.exists(pkl):
            with open(pkl, "rb") as f:
                return pickle.load(f)
        return None

    results_all = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(run, cid): cid for cid in range(len(chunks))}
        done = 0
        for fut in as_completed(futures):
            r = fut.result()
            if r is not None:
                results_all.append(r)
            done += 1
            if done % 10 == 0 or done == len(chunks):
                tp = sum(x["tp"] for x in results_all)
                fp = sum(x["fp"] for x in results_all)
                fn = sum(x["fn"] for x in results_all)
                print("  {}/{} chunks | TP={} FP={} FN={}".format(
                    done, len(chunks), tp, fp, fn), flush=True)

    # 聚合
    tp_total = sum(r["tp"] for r in results_all)
    fp_total = sum(r["fp"] for r in results_all)
    fn_total = sum(r["fn"] for r in results_all)
    file_exact = sum(r["exact"] for r in results_all)
    file_ok = sum(r["ok"] for r in results_all)
    file_partial = sum(r["partial"] for r in results_all)
    file_miss = sum(r["miss"] for r in results_all)
    file_fp_only = sum(r["fp_only"] for r in results_all)
    file_error = sum(r.get("error", 0) for r in results_all)
    file_no_label = sum(r.get("no_label", 0) for r in results_all)

    all_results = []
    all_errors = []
    for r in results_all:
        all_results.extend(r.get("results", []))
        all_errors.extend(r.get("errors", []))

    elapsed = time.time() - t0
    print("\n" + "=" * 60, flush=True)
    print("汇总 (FeatureFox-NCTI 盲孔 seg=12, 阈={})".format(threshold), flush=True)
    print("=" * 60, flush=True)
    print("有效文件: {} (错误 {}, 无label {})".format(
        len(all_results), file_error, file_no_label), flush=True)
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

    if all_errors:
        print("\n错误件 (前20):", flush=True)
        for e in all_errors[:20]:
            print(f"  {e}", flush=True)

    report = {
        "method": "featurefox_blindhole",
        "threshold": threshold,
        "mapping": "零映射(cell_id直出)",
        "test_only": test_only,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_files": len(step_files),
        "valid_files": len(all_results),
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
        "results": all_results,
    }
    out_file = REPORT_FILE_TEST if test_only else REPORT_FILE
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("\n报告: {}".format(out_file), flush=True)

    # 清理
    for fn in os.listdir(CHUNK_DIR):
        if fn.startswith("_eval_"):
            try:
                os.remove(os.path.join(CHUNK_DIR, fn))
            except Exception:
                pass


CHUNK_WORKER_TEMPLATE = r'''#!/usr/bin/env python
"""Chunk worker - auto-generated."""
import os, sys, pickle

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_FEATFOX_ROOT = os.path.dirname(_SCRIPT_DIR)
if _FEATFOX_ROOT not in sys.path:
    sys.path.insert(0, _FEATFOX_ROOT)
from featurefox.lib._env import get_project_root as _get_pr
_PROJECT_ROOT = _get_pr()
if _PROJECT_ROOT and _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from featurefox.lib.edge_features import build_face_graph
from featurefox.scripts.predict import load_models, load_instance_models, predict_through_slots
from featurefox.lib.instance_data import list_step_files, load_label, STEPS_DIR
from featurefox.lib.ncti_backend import load_part
from featurefox.lib.ncti_faceid_map import init_ncti_safe

start_idx = {start_idx}
end_idx = {end_idx}
threshold = {threshold}
offset = {offset}
pkl_path = r"{pkl_path}"

# test-only: 读环境变量中的过滤文件
import json as _json
_name_filter = None
_filter_file = os.environ.get("EVAL_FILTER_FILE", "")
if _filter_file and os.path.exists(_filter_file):
    with open(_filter_file) as _f:
        _name_filter = set(_json.load(_f))

ncti = init_ncti_safe(_PROJECT_ROOT)
if ncti is None:
    with open(pkl_path, "wb") as f:
        pickle.dump({{"errors": ["NCTI init failed"], "results": [], "tp": 0, "fp": 0, "fn": 0,
                       "exact": 0, "ok": 0, "partial": 0, "miss": 0, "fp_only": 0,
                       "error": 1, "no_label": 0}}, f)
    sys.exit(1)

booster, calibrator = load_models()
inst_booster, inst_calib = load_instance_models()
step_files = list_step_files(0, offset, name_filter=_name_filter)
chunk_files = step_files[start_idx:end_idx]

tp_total = fp_total = fn_total = 0
file_exact = file_partial = file_miss = file_fp_only = file_ok = 0
file_error = file_no_label = 0
results = []
errors = []

for i, step_file in enumerate(chunk_files):
    name = os.path.splitext(step_file)[0]
    stp_path = os.path.join(STEPS_DIR, step_file)
    doc = None
    try:
        part, doc = load_part(stp_path, ncti)
        instances = predict_through_slots(
            stp_path, booster, calibrator, ncti=ncti, part=part, threshold=threshold,
            inst_booster=inst_booster, inst_calibrator=inst_calib)
        detected_cells = set()
        for inst in instances:
            detected_cells.update(inst["faces"])
    except Exception as ex:
        file_error += 1
        errors.append(f"{{name}}: {{str(ex)[:80]}}")
        if doc is not None:
            try: doc.Clear()
            except: pass
        continue

    seg12, inst_mat, _ = load_label(name)
    if seg12 is None:
        file_no_label += 1
        if doc is not None:
            try: doc.Clear()
            except: pass
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

    if status not in ("EXACT", "OK_NO_SLOT"):
        sys.stderr.write(f"[{{start_idx + i + 1}}] {{name}}: {{status}} TP={{len(tp)}} FP={{len(fp)}} FN={{len(fn)}}\n")

    results.append({{
        "name": name, "status": status,
        "detected": sorted(detected_cells), "label": sorted(seg12),
        "tp": sorted(tp), "fp": sorted(fp), "fn": sorted(fn),
    }})

    if doc is not None:
        try: doc.Clear()
        except: pass

output = {{
    "results": results, "errors": errors,
    "tp": tp_total, "fp": fp_total, "fn": fn_total,
    "exact": file_exact, "ok": file_ok,
    "partial": file_partial, "miss": file_miss,
    "fp_only": file_fp_only, "error": file_error,
    "no_label": file_no_label,
}}
with open(pkl_path, "wb") as f:
    pickle.dump(output, f)
os._exit(0)
'''


if __name__ == "__main__":
    main()
