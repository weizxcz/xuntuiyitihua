#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""扫描第二级 inst_threshold（一次跑扫所有阈值）。

worker(_eval_scan_worker) 用 inst_threshold=0.0 保留所有候选实例（每个带 inst_prob），
主进程对 SCAN_THRS 每个阈值模拟拒绝，算 P/R/F1，输出对比表找最优。

用法（从 utils/through_step/ 执行，yhcad_py312 环境）:
    python -m featurefox_ncti.evaluate_scan 1000 0.35 50000   # max_files edge_thr offset
"""

import os
import sys
import time
import json
import subprocess

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
UTILS_DIR = os.path.dirname(os.path.dirname(THIS_DIR))
TS_DIR = os.path.dirname(THIS_DIR)
PROJECT_ROOT = os.path.dirname(UTILS_DIR)
for _p in (UTILS_DIR, TS_DIR, PROJECT_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from featurefox_ncti.predict import DEFAULT_THRESHOLD  # noqa: E402
from featurefox_ncti.instance_data import list_step_files  # noqa: E402

REPORT_FILE = os.path.join(THIS_DIR, "featurefox_ncti_inst_threshold_scan.json")
CHUNK = 10           # 平衡 init 开销与卡死件丢邻件；卡死件 60s 杀只丢 9 邻件
CHUNK_TIMEOUT = 60   # 正常 ~1.5s、大件区 ~18s(10 件混大件) <60s 完成；卡死件 NCTI bug >60s 杀跳过
SCAN_THRS = [0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.80]


def main():
    args = sys.argv[1:]
    max_files = int(args[0]) if len(args) > 0 else 0
    edge_threshold = float(args[1]) if len(args) > 1 else DEFAULT_THRESHOLD
    offset = int(args[2]) if len(args) > 2 else 0

    print("=" * 60, flush=True)
    print("FeatureFox-NCTI inst_threshold 扫描 (edge_thr={}, offset={})".format(
        edge_threshold, offset), flush=True)
    print("扫描阈值: {}".format(SCAN_THRS), flush=True)
    print("=" * 60, flush=True)

    step_files = list_step_files(max_files, offset)
    n_total = len(step_files)
    print("测试文件数: {}".format(n_total), flush=True)

    chunks = [(i, min(i + CHUNK, n_total)) for i in range(0, n_total, CHUNK)]

    t0 = time.time()
    results = []
    n_timeout = 0
    for cid, (start, end) in enumerate(chunks):
        jsonl = os.path.join(THIS_DIR, "_eval_scan_chunk_{}.jsonl".format(cid))
        env = {**os.environ, "PYTHONPATH": TS_DIR, "PYTHONIOENCODING": "utf-8"}
        timed_out = False
        try:
            subprocess.run(
                [sys.executable, "-m", "featurefox_ncti._eval_scan_worker",
                 str(start), str(end), str(offset), str(edge_threshold), jsonl],
                env=env, timeout=CHUNK_TIMEOUT)
        except subprocess.TimeoutExpired:
            timed_out = True
            n_timeout += 1
        if os.path.exists(jsonl):
            with open(jsonl, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        results.append(json.loads(line))
                    except Exception:
                        continue
            try:
                os.remove(jsonl)
            except Exception:
                pass
        elapsed = time.time() - t0
        eta = elapsed / (cid + 1) * (len(chunks) - cid - 1)
        flag = " [超时]" if timed_out else ""
        print("chunk {}/{} [{}:{}] (累计 {} 件, ETA {:.0f}min){}".format(
            cid + 1, len(chunks), start, end, len(results), eta / 60, flag), flush=True)

    elapsed = time.time() - t0
    print("\n有效件: {} / {} (超时chunk {})，耗时 {:.0f}s".format(
        len(results), n_total, n_timeout, elapsed), flush=True)

    # ── 扫描多个 inst_threshold ──
    print("\n" + "=" * 60, flush=True)
    print("inst_threshold 扫描结果 (面级)", flush=True)
    print("=" * 60, flush=True)
    print("{:<10} {:<10} {:<10} {:<10} {:<10}".format(
        "inst_thr", "Precision", "Recall", "F1", "FP"), flush=True)
    print("-" * 50, flush=True)

    scan_rows = []
    for thr in SCAN_THRS:
        tp = fp = fn = 0
        for r in results:
            seg9 = set(r["seg9"])
            detected = set()
            for c in r["candidates"]:
                if c["inst_prob"] >= thr:
                    detected.update(c["faces"])
            tp += len(detected & seg9)
            fp += len(detected - seg9)
            fn += len(seg9 - detected)
        p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rr = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * p * rr / (p + rr) if (p + rr) > 0 else 0.0
        print("{:<10.2f} {:<10.2f} {:<10.2f} {:<10.2f} {:<10}".format(
            thr, p * 100, rr * 100, f1 * 100, fp), flush=True)
        scan_rows.append({"inst_thr": thr, "precision": round(p * 100, 2),
                          "recall": round(rr * 100, 2), "f1": round(f1 * 100, 2),
                          "tp": tp, "fp": fp, "fn": fn})

    best = max(scan_rows, key=lambda x: x["f1"])
    print("-" * 50, flush=True)
    print("最优 F1: inst_thr={:.2f} → P={:.2f}% R={:.2f}% F1={:.2f}%".format(
        best["inst_thr"], best["precision"], best["recall"], best["f1"]), flush=True)

    report = {
        "method": "featurefox_ncti_inst_threshold_scan",
        "edge_threshold": edge_threshold, "offset": offset,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "valid_files": len(results), "elapsed": round(elapsed, 1),
        "scan": scan_rows, "best_f1": best,
    }
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("\n报告: {}".format(REPORT_FILE), flush=True)

    os._exit(0)


if __name__ == "__main__":
    main()
