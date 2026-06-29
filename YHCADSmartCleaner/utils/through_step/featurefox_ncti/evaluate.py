#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""评估 featurefox-NCTI 通槽识别（全量或子集），对比 label seg=9。

featurefox-NCTI 版零映射：predict 输出的 faces 即 cell_id（ai.FaceID 位置索引），
直接与 seg9 对比，无需 STEP→cell 映射。

工程：subprocess 隔离（每 40 件一个子进程 `_eval_chunk_worker`），解决 NCTI 批量
累积 segfault（单进程顺序跑 ~378 件崩，与训练同因）。子进程超时 CHUNK_TIMEOUT 防
"毒性文件"（NCTI 导入卡死级慢，实测 68min/件）拖垮整体：超时杀 worker，读已落盘
jsonl（毒性文件前件保留，毒性件及同 chunk 后续丢失）。崩件容错同理。

用法（从 utils/through_step/ 执行，yhcad_py312 环境）:
    python -m featurefox_ncti.evaluate 50            # 前 50 文件
    python -m featurefox_ncti.evaluate 0             # 全部
    python -m featurefox_ncti.evaluate 0 0.35 50000  # 训练集外文件（offset 验证泛化）
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
REPO_ROOT = os.path.dirname(PROJECT_ROOT)
for _p in (REPO_ROOT, PROJECT_ROOT, UTILS_DIR, TS_DIR, THIS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from featurefox_ncti.predict import DEFAULT_THRESHOLD  # noqa: E402
from featurefox_ncti.instance_data import list_step_files  # noqa: E402

REPORT_FILE = os.path.join(THIS_DIR, "featurefox_ncti_eval_report.json")
CHUNK = 40           # 每子进程处理件数（须 < NCTI 累积崩点 ~378；小则毒性文件隔离细）
CHUNK_TIMEOUT = 180  # 子进程超时秒数（毒性文件卡死级慢，超时杀掉跳过）


def main():
    args = sys.argv[1:]
    max_files = int(args[0]) if len(args) > 0 else 0
    threshold = float(args[1]) if len(args) > 1 else DEFAULT_THRESHOLD
    offset = int(args[2]) if len(args) > 2 else 0

    print("=" * 60, flush=True)
    print("FeatureFox-NCTI 评估 (阈={}, offset={}, chunk={}, 超时={}s)".format(
        threshold, offset, CHUNK, CHUNK_TIMEOUT), flush=True)
    print("=" * 60, flush=True)

    step_files = list_step_files(max_files, offset)
    n_total = len(step_files)
    print("测试文件数: {} (offset={})".format(n_total, offset), flush=True)

    chunks = [(i, min(i + CHUNK, n_total)) for i in range(0, n_total, CHUNK)]

    t0 = time.time()
    results = []
    n_timeout = 0
    for cid, (start, end) in enumerate(chunks):
        jsonl = os.path.join(THIS_DIR, "_eval_chunk_{}.jsonl".format(cid))
        env = {**os.environ, "PYTHONPATH": TS_DIR, "PYTHONIOENCODING": "utf-8"}
        # 不 check 退出码：worker exit 127（NCTI 析构）/139（崩件 segfault）都非0；
        # timeout 防毒性文件拖垮：超时杀 worker，读已落盘 jsonl。
        timed_out = False
        try:
            subprocess.run(
                [sys.executable, "-m", "featurefox_ncti._eval_chunk_worker",
                 str(start), str(end), str(offset), str(threshold), jsonl],
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
                        continue  # 跳过崩件半行
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

    # ── 汇总 ──
    tp_total = sum(len(r["tp"]) for r in results)
    fp_total = sum(len(r["fp"]) for r in results)
    fn_total = sum(len(r["fn"]) for r in results)
    file_tp = file_partial = file_miss = file_fp_only = file_ok = 0
    for r in results:
        s = r["status"]
        if s == "OK_NO_SLOT":
            file_ok += 1
        elif s == "EXACT":
            file_tp += 1
        elif s.startswith("PARTIAL"):
            file_partial += 1
        elif s == "FP_ONLY":
            file_fp_only += 1
        else:
            file_miss += 1

    lost = n_total - len(results)
    print("\n" + "=" * 60, flush=True)
    print("汇总 (FeatureFox-NCTI, 阈={})".format(threshold), flush=True)
    print("=" * 60, flush=True)
    print("有效文件: {} / {} (丢失 {}，含超时/崩件/无标签；超时chunk {})".format(
        len(results), n_total, lost, n_timeout), flush=True)
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
        "method": "featurefox_ncti", "threshold": threshold, "mapping": "零映射(cell_id直出)",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_files": n_total, "valid_files": len(results), "lost": lost, "timeout_chunks": n_timeout,
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
