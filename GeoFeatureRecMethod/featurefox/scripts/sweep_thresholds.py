#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""阈值扫描主进程（featurefox-NCTI 版）。

子进程 chunk 隔离（崩件容错）+ ThreadPool 并发，每文件只建一次图、内部扫 9 阈值。
聚合双模式 P/R/F1 曲线：
  Mode A 纯第一级（关实例分类器）——隔离第一级 recall 天花板。
  Mode B 全流水线（开实例分类器）——复现 evaluate 指标。

用法（从 utils/through_step 执行）:
    python -m featurefox_blindhole.sweep_thresholds [n_holdout] [offset]
    # 默认 n_holdout=1500, offset=0→自动取末尾 n_holdout 件
"""
import os
import sys
import pickle
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

FEATUREFOX_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if FEATUREFOX_ROOT not in sys.path:
    sys.path.insert(0, FEATUREFOX_ROOT)
from featurefox.lib._env import get_project_root
PROJECT_ROOT = get_project_root()
if PROJECT_ROOT and PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from featurefox.lib.instance_data import list_step_files

THRESHOLDS = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50]
CHUNK = 40
CHUNK_DIR = os.path.join(FEATUREFOX_ROOT, "_chunks")


def main():
    n_holdout = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
    offset_arg = int(sys.argv[2]) if len(sys.argv) > 2 else 0

    total = len(list_step_files(0, 0))
    offset = offset_arg if offset_arg > 0 else max(0, total - n_holdout)
    holdout = list_step_files(0, offset)[:n_holdout]
    print("=" * 60, flush=True)
    print("阈值扫描: holdout={} (offset={}, 总文件 {})".format(
        len(holdout), offset, total), flush=True)
    print("=" * 60, flush=True)

    chunks = [(i, min(i + CHUNK, len(holdout))) for i in range(0, len(holdout), CHUNK)]
    os.makedirs(CHUNK_DIR, exist_ok=True)
    max_workers = int(os.environ.get("NCTI_CHUNK_WORKERS", "32"))

    def run(cid):
        s, e = chunks[cid]
        pkl = os.path.join(CHUNK_DIR, "_sweep_{}.pkl".format(cid))
        env = {**os.environ, "PYTHONPATH": FEATUREFOX_ROOT, "PYTHONIOENCODING": "utf-8"}
        # 不 check 退出码：worker 崩件 segfault(139)/析构(127) 都非0，看 pkl
        subprocess.run([sys.executable, "-m", "featurefox.workers._sweep_worker",
                        str(s), str(e), pkl, str(offset)], env=env)
        if os.path.exists(pkl):
            with open(pkl, "rb") as f:
                return pickle.load(f)
        return None

    results = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(run, cid): cid for cid in range(len(chunks))}
        done = 0
        for fut in as_completed(futs):
            r = fut.result()
            if r is not None:
                results.append(r)
            done += 1
            if done % 10 == 0 or done == len(chunks):
                print("  {}/{} chunks ...".format(done, len(chunks)), flush=True)

    # 聚合
    agg = {"A": {t: {"tp": 0, "fp": 0, "fn": 0} for t in THRESHOLDS},
           "B": {t: {"tp": 0, "fp": 0, "fn": 0} for t in THRESHOLDS}}
    n_done = 0
    errors = []
    for r in results:
        n_done += r.get("n_done", 0)
        errors.extend(r.get("errors", []))
        for mode in ("A", "B"):
            for t in THRESHOLDS:
                for k in ("tp", "fp", "fn"):
                    agg[mode][t][k] += r["acc"][mode][t][k]

    print("\n完成: {} 件有效, {} 件错误, 耗时 {:.0f}s".format(
        n_done, len(errors), time.time() - t0), flush=True)

    for mode, label in (("A", "Mode A 纯第一级(关实例分类器)"),
                        ("B", "Mode B 全流水线(开实例分类器)")):
        print("\n===== {} =====".format(label), flush=True)
        print("{:<8}{:>8}{:>8}{:>8}   {:>7}{:>7}{:>7}".format(
            "阈值", "P", "R", "F1", "TP", "FP", "FN"), flush=True)
        for t in THRESHOLDS:
            a = agg[mode][t]
            tp, fp, fn = a["tp"], a["fp"], a["fn"]
            p = tp / (tp + fp) if (tp + fp) > 0 else 0
            r = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0
            print("{:<8}{:>7.2f}%{:>7.2f}%{:>7.2f}%   {:>7}{:>7}{:>7}".format(
                t, p * 100, r * 100, f1 * 100, tp, fp, fn), flush=True)

    # 清理 chunk pickle
    for fn in os.listdir(CHUNK_DIR):
        if fn.startswith("_sweep_") and fn.endswith(".pkl"):
            try:
                os.remove(os.path.join(CHUNK_DIR, fn))
            except Exception:
                pass

    if errors:
        print("\n错误件(前10):", flush=True)
        for e in errors[:10]:
            print("  {}".format(e), flush=True)

    os._exit(0)


if __name__ == "__main__":
    main()
