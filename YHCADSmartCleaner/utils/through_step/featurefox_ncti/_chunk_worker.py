#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""子进程 worker：收集一个 chunk 的训练数据，pickle dump。

被 collect_dataset 通过 subprocess 调用（每 chunk 独立 python 进程，
退出彻底释放 NCTI，解决批量累积 segfault）。不直接运行。

用法:
    python -m featurefox_ncti._chunk_worker <start> <end> <output_pkl>
"""
import os
import sys
import pickle

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
UTILS_DIR = os.path.dirname(os.path.dirname(THIS_DIR))
TS_DIR = os.path.dirname(THIS_DIR)
PROJECT_ROOT = os.path.dirname(UTILS_DIR)
for _p in (UTILS_DIR, TS_DIR, PROJECT_ROOT, THIS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from ncti_backend import load_part, count_advanced_faces  # noqa: E402
from featurefox_ncti.edge_features import build_face_graph  # noqa: E402
from featurefox_ncti.instance_data import (  # noqa: E402
    list_step_files, load_label, build_training_sample, STEPS_DIR)
from YHCADSmartCleaner.utils.through_step.featurefox.ncti_faceid_map import init_ncti_safe  # noqa: E402


def main():
    start = int(sys.argv[1])
    end = int(sys.argv[2])
    output_pkl = sys.argv[3]

    ncti = init_ncti_safe(PROJECT_ROOT)
    if ncti is None:
        with open(output_pkl, "wb") as f:
            pickle.dump(([], [], []), f)
        os._exit(0)

    all_files = list_step_files(0, 0)
    chunk_files = all_files[start:end]
    doc = ncti.Document()
    X, y, meta = [], [], []
    for step_file in chunk_files:
        name = os.path.splitext(step_file)[0]
        stp_path = os.path.join(STEPS_DIR, step_file)
        try:
            part, _ = load_part(stp_path, ncti, doc=doc)
            expected = count_advanced_faces(stp_path)
            if expected is not None and expected != part.n_faces:
                continue
            seg9, inst, _ = load_label(name)
            if seg9 is None or inst is None:
                continue
            edges, _ = build_face_graph(part)
            Xc, yc, mc = build_training_sample(edges, seg9, inst)
            X.extend(Xc)
            y.extend(yc)
            for m in mc:
                m["name"] = name
            meta.extend(mc)
            # 增量 pickle（原子写）：崩件 segfault 杀进程时，保留崩件前已处理数据
            tmp = output_pkl + ".tmp"
            with open(tmp, "wb") as f:
                pickle.dump((X, y, meta), f)
            os.replace(tmp, output_pkl)
        except Exception:
            continue
    os._exit(0)


if __name__ == "__main__":
    main()
