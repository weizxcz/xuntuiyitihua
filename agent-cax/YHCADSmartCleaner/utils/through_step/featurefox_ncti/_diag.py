#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""逐件定位崩件（40-80）。崩件 segfault 杀进程，最后打印的件即崩件。"""
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
UTILS_DIR = os.path.dirname(os.path.dirname(THIS_DIR))
TS_DIR = os.path.dirname(THIS_DIR)
PROJECT_ROOT = os.path.dirname(UTILS_DIR)
for _p in (UTILS_DIR, TS_DIR, PROJECT_ROOT, THIS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from ncti_backend import load_part  # noqa: E402
from featurefox_ncti.edge_features import build_face_graph  # noqa: E402
from featurefox_ncti.instance_data import list_step_files, STEPS_DIR  # noqa: E402
from YHCADSmartCleaner.utils.through_step.featurefox.ncti_faceid_map import init_ncti_safe  # noqa: E402

ncti = init_ncti_safe(PROJECT_ROOT)
if ncti is None:
    sys.exit("NCTI init failed")
files = list_step_files(0, 0)[40:80]
print("逐件 40-80 ({}件)".format(len(files)), flush=True)
doc = ncti.Document()
for i, f in enumerate(files):
    idx = 40 + i
    print("[{}] {} loading...".format(idx, f), flush=True)
    part, _ = load_part(os.path.join(STEPS_DIR, f), ncti, doc=doc)
    edges, _ = build_face_graph(part)
    print("[{}] {} OK {}面 {}边".format(idx, f, part.n_faces, len(edges)), flush=True)
print("=== 全部 OK ===", flush=True)
os._exit(0)
