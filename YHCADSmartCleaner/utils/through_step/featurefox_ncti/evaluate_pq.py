#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Panoptic Quality(PQ)评估——论文同口径，把账算清楚。

worker(_eval_pq_worker) 用 inst_threshold=0.0 保留所有候选(每个带 inst_prob)，
并输出 GT 通槽实例(inst 矩阵在 seg9 上的连通分量)。主进程对 SCAN_THRS 每阈值
模拟拒绝后做实例级 IoU>0.5 贪心匹配，算:
  - PQ = ΣIoU(TP) / (|TP| + ½|FP| + ½|FN|)   (论文 §IV-C)
  - SQ = mean IoU(匹配对), RQ = |TP|/分母 (PQ = SQ×RQ)
  - R&L 准确率 = GT 实例被完美恢复(IoU=1.0)占比  (论文 Table II "Recognition&Localization Acc")
  - 面级 P/R/F1 (同数据同阈值)               (现有口径，直接对比)

验证"75% 面级 F1 vs 论文 96.87% PQ"差距里有多少是度量幻觉。

用法(从 utils/through_step/ 执行, yhcad_py312 环境):
    python -m featurefox_ncti.evaluate_pq 500 0.35 50000   # max_files edge_thr offset
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

REPORT_FILE = os.path.join(THIS_DIR, "featurefox_ncti_pq_report.json")
CHUNK = 10           # 与 evaluate_scan 一致：毒性件 60s 杀只丢 9 邻件
CHUNK_TIMEOUT = 60
SCAN_THRS = [0.20, 0.30, 0.50, 0.80]   # 0.80=生产阈值；低阈值看 PQ 是否更高
IOU_MATCH = 0.5       # PQ 匹配阈值(论文同)


def _iou(a, b):
    u = a | b
    return len(a & b) / len(u) if u else 0.0


def _match(preds, gts):
    """贪心 IoU>0.5 一对一匹配(按 IoU 降序)。返回 (tp_iou_list, n_fp, n_fn)。"""
    pairs = []
    for pi, p in enumerate(preds):
        for gi, g in enumerate(gts):
            iou = _iou(p, g)
            if iou > IOU_MATCH:
                pairs.append((iou, pi, gi))
    pairs.sort(reverse=True)
    mp, mg = set(), set()
    tp_iou = []
    for iou, pi, gi in pairs:
        if pi in mp or gi in mg:
            continue
        mp.add(pi)
        mg.add(gi)
        tp_iou.append(iou)
    return tp_iou, len(preds) - len(mp), len(gts) - len(mg)


def main():
    args = sys.argv[1:]
    max_files = int(args[0]) if len(args) > 0 else 0
    edge_threshold = float(args[1]) if len(args) > 1 else DEFAULT_THRESHOLD
    offset = int(args[2]) if len(args) > 2 else 0

    print("=" * 60, flush=True)
    print("FeatureFox-NCTI PQ 评估 (edge_thr={}, offset={}, IoU>{} 匹配)".format(
        edge_threshold, offset, IOU_MATCH), flush=True)
    print("扫描 inst_threshold: {}".format(SCAN_THRS), flush=True)
    print("=" * 60, flush=True)

    step_files = list_step_files(max_files, offset)
    n_total = len(step_files)
    print("测试文件数: {}".format(n_total), flush=True)

    chunks = [(i, min(i + CHUNK, n_total)) for i in range(0, n_total, CHUNK)]

    t0 = time.time()
    results = []
    n_timeout = 0
    for cid, (start, end) in enumerate(chunks):
        jsonl = os.path.join(THIS_DIR, "_eval_pq_chunk_{}.jsonl".format(cid))
        env = {**os.environ, "PYTHONPATH": TS_DIR, "PYTHONIOENCODING": "utf-8"}
        timed_out = False
        try:
            subprocess.run(
                [sys.executable, "-m", "featurefox_ncti._eval_pq_worker",
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

    # ── 扫描 inst_threshold，算 PQ + 面级 P/R/F1 ──
    print("\n" + "=" * 60, flush=True)
    print("PQ 扫描 (inst_threshold 变化)", flush=True)
    print("=" * 60, flush=True)
    hdr = "{:<8}{:<7}{:<7}{:<7}{:<8}{:<8}{:<8}{:<8}{:<14}".format(
        "inst_th", "PQ", "SQ", "RQ", "R&L%", "faceP", "faceR", "faceF1", "TP/FP/FN")
    print(hdr, flush=True)
    print("-" * len(hdr), flush=True)

    scan_rows = []
    for thr in SCAN_THRS:
        tp_iou_sum = 0.0
        n_tp = n_fp = n_fn = 0
        n_exact = 0          # GT 实例被完美恢复(IoU=1.0)数
        n_gt_total = 0
        f_tp = f_fp = f_fn = 0   # 面级
        for r in results:
            gts = [set(g) for g in r["gt"]]
            preds = [set(c["faces"]) for c in r["candidates"] if c["inst_prob"] >= thr]
            n_gt_total += len(gts)
            tp_iou, fp, fn = _match(preds, gts)
            tp_iou_sum += sum(tp_iou)
            n_tp += len(tp_iou)
            n_fp += fp
            n_fn += fn
            n_exact += sum(1 for x in tp_iou if x >= 0.999)

            seg9 = set().union(*gts) if gts else set()
            det = set().union(*preds) if preds else set()
            f_tp += len(det & seg9)
            f_fp += len(det - seg9)
            f_fn += len(seg9 - det)

        denom = n_tp + 0.5 * n_fp + 0.5 * n_fn
        sq = (tp_iou_sum / n_tp) if n_tp else 0.0
        rq = (n_tp / denom) if denom else 0.0
        pq = sq * rq
        rl_acc = (n_exact / n_gt_total) if n_gt_total else 0.0
        f_p = f_tp / (f_tp + f_fp) if (f_tp + f_fp) else 0.0
        f_r = f_tp / (f_tp + f_fn) if (f_tp + f_fn) else 0.0
        f_f1 = 2 * f_p * f_r / (f_p + f_r) if (f_p + f_r) else 0.0

        print("{:<8.2f}{:<7.2f}{:<7.2f}{:<7.2f}{:<8.2f}{:<8.2f}{:<8.2f}{:<8.2f}{:<14}".format(
            thr, pq * 100, sq * 100, rq * 100, rl_acc * 100,
            f_p * 100, f_r * 100, f_f1 * 100, "{}/{}/{}".format(n_tp, n_fp, n_fn)), flush=True)
        scan_rows.append({
            "inst_thr": thr, "pq": round(pq * 100, 2), "sq": round(sq * 100, 2),
            "rq": round(rq * 100, 2), "rl_acc": round(rl_acc * 100, 2),
            "face_precision": round(f_p * 100, 2), "face_recall": round(f_r * 100, 2),
            "face_f1": round(f_f1 * 100, 2),
            "inst_tp": n_tp, "inst_fp": n_fp, "inst_fn": n_fn,
            "gt_instances": n_gt_total, "exact": n_exact,
        })

    best = max(scan_rows, key=lambda x: x["pq"])
    print("-" * len(hdr), flush=True)
    print("最优 PQ: inst_thr={:.2f} → PQ={:.2f}% R&L={:.2f}% (面级F1={:.2f}%)".format(
        best["inst_thr"], best["pq"], best["rl_acc"], best["face_f1"]), flush=True)

    report = {
        "method": "featurefox_ncti_pq", "edge_threshold": edge_threshold, "offset": offset,
        "iou_match": IOU_MATCH, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "valid_files": len(results), "elapsed": round(elapsed, 1), "scan": scan_rows,
        "best_pq": best,
    }
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("\n报告: {}".format(REPORT_FILE), flush=True)

    os._exit(0)


if __name__ == "__main__":
    main()
