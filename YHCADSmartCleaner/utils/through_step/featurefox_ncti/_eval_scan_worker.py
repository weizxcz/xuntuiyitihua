#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""子进程 worker：评估"扫描版"——输出每件的候选实例 + inst_prob + seg9，
供主进程 evaluate_scan 扫描多个第二级 inst_threshold（一次跑扫所有阈值）。

与 _eval_chunk_worker 的差异：不在此做最终拒绝，用 inst_threshold=0.0 让
predict_through_slots 保留所有通过后处理的候选（每个带 inst_prob），主进程
再按不同阈值模拟拒绝。这样跑一遍即可得任意多阈值的 P/R/F1。

用法:
    python -m featurefox_ncti._eval_scan_worker <start> <end> <offset> <edge_threshold> <output_jsonl>
"""
import os
import sys
import json

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
UTILS_DIR = os.path.dirname(os.path.dirname(THIS_DIR))
TS_DIR = os.path.dirname(THIS_DIR)
PROJECT_ROOT = os.path.dirname(UTILS_DIR)
for _p in (UTILS_DIR, TS_DIR, PROJECT_ROOT, THIS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from featurefox_ncti.predict import (  # noqa: E402
    load_models, load_instance_models, predict_through_slots)
from featurefox_ncti.instance_data import list_step_files, load_label, STEPS_DIR  # noqa: E402
from ncti_backend import load_part  # noqa: E402
from ncti_faceid_map import init_ncti_safe  # noqa: E402


def main():
    start = int(sys.argv[1])
    end = int(sys.argv[2])
    offset = int(sys.argv[3])
    edge_threshold = float(sys.argv[4])
    output_jsonl = sys.argv[5]

    ncti = init_ncti_safe(PROJECT_ROOT)
    if ncti is None:
        os._exit(0)

    booster, calibrator = load_models()
    inst_booster, inst_calib = load_instance_models()

    all_files = list_step_files(0, offset)
    chunk_files = all_files[start:end]
    doc = ncti.Document()

    with open(output_jsonl, "w", encoding="utf-8") as out:
        for step_file in chunk_files:
            name = os.path.splitext(step_file)[0]
            stp_path = os.path.join(STEPS_DIR, step_file)
            try:
                part, _ = load_part(stp_path, ncti, doc=doc)
                # inst_threshold=0.0 保留所有候选（每个带真实 inst_prob）
                instances = predict_through_slots(
                    stp_path, booster, calibrator, ncti=ncti, part=part,
                    threshold=edge_threshold, inst_booster=inst_booster,
                    inst_calibrator=inst_calib, inst_threshold=0.0)
                cands = [{"faces": inst["faces"], "inst_prob": inst["inst_prob"]}
                         for inst in instances]
            except Exception:
                continue
            finally:
                try:
                    doc.Clear()
                except Exception:
                    pass

            seg9, _, _ = load_label(name)
            if seg9 is None:
                continue

            rec = {"name": name, "seg9": sorted(seg9), "candidates": cands}
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()

    os._exit(0)


if __name__ == "__main__":
    main()
