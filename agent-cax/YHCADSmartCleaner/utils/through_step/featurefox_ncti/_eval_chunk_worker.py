#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""子进程 worker：评估一个 chunk 的文件，结果增量写 jsonl。

被 evaluate 通过 subprocess 调用（每 chunk 独立 python 进程，
退出彻底释放 NCTI，解决批量累积 segfault——单进程顺序跑 ~378 件崩）。
不直接运行。

用法:
    python -m featurefox_ncti._eval_chunk_worker <start> <end> <offset> <threshold> <output_jsonl>

崩件容错：每件成功就 flush 一行 json 到 jsonl；segfault 杀进程时，
崩件前已落盘的行保留，主进程读取时跳过半行。
"""
import os
import sys
import json

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
UTILS_DIR = os.path.dirname(os.path.dirname(THIS_DIR))
TS_DIR = os.path.dirname(THIS_DIR)
PROJECT_ROOT = os.path.dirname(UTILS_DIR)
REPO_ROOT = os.path.dirname(PROJECT_ROOT)
for _p in (REPO_ROOT, PROJECT_ROOT, UTILS_DIR, TS_DIR, THIS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from featurefox_ncti.predict import (  # noqa: E402
    load_models, load_instance_models, predict_through_slots)
from featurefox_ncti.instance_data import list_step_files, load_label, STEPS_DIR  # noqa: E402
from ncti_backend import load_part  # noqa: E402
from featurefox.ncti_faceid_map import init_ncti_safe  # noqa: E402


def _status(detected, seg9, tp):
    if len(seg9) == 0 and len(detected) == 0:
        return "OK_NO_SLOT"
    if detected == seg9:
        return "EXACT"
    if len(tp) > 0 and len(detected - seg9) == 0:
        return "PARTIAL(miss)"
    if len(tp) > 0 and len(detected - seg9) > 0:
        return "PARTIAL(miss+fp)"
    if len(tp) == 0 and len(detected) > 0:
        return "FP_ONLY"
    return "MISS"


def main():
    start = int(sys.argv[1])
    end = int(sys.argv[2])
    offset = int(sys.argv[3])
    threshold = float(sys.argv[4])
    output_jsonl = sys.argv[5]

    ncti = init_ncti_safe(PROJECT_ROOT)
    if ncti is None:
        os._exit(0)  # 无输出文件，主进程视为该 chunk 全失败

    booster, calibrator = load_models()
    inst_booster, inst_calib = load_instance_models()

    all_files = list_step_files(0, offset)  # offset 后全部测试集
    chunk_files = all_files[start:end]
    doc = ncti.Document()

    with open(output_jsonl, "w", encoding="utf-8") as out:
        for step_file in chunk_files:
            name = os.path.splitext(step_file)[0]
            stp_path = os.path.join(STEPS_DIR, step_file)
            try:
                part, _ = load_part(stp_path, ncti, doc=doc)
                instances = predict_through_slots(
                    stp_path, booster, calibrator, ncti=ncti, part=part,
                    threshold=threshold, inst_booster=inst_booster,
                    inst_calibrator=inst_calib)
                detected = set()
                for inst in instances:
                    detected.update(inst["faces"])
            except Exception:
                continue  # 导入失败/预测异常跳过；segfault 杀进程时已写的保留
            finally:
                try:
                    doc.Clear()
                except Exception:
                    pass

            seg9, _, _ = load_label(name)
            if seg9 is None:
                continue

            tp = detected & seg9
            fp = detected - seg9
            fn = seg9 - detected
            rec = {
                "name": name,
                "status": _status(detected, seg9, tp),
                "tp": sorted(tp), "fp": sorted(fp), "fn": sorted(fn),
                "seg9": sorted(seg9), "detected": sorted(detected),
            }
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()  # 增量落盘，崩前数据保留

    os._exit(0)


if __name__ == "__main__":
    main()
