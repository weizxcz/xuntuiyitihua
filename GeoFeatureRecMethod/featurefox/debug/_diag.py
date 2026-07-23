#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""逐件定位崩件（40-80）。崩件 segfault 杀进程，最后打印的件即崩件。"""
import os
import sys

_FEATFOX_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _FEATFOX_ROOT not in sys.path:
    sys.path.insert(0, _FEATFOX_ROOT)
from featurefox.lib._env import get_project_root
_PROJECT_ROOT = get_project_root()
if _PROJECT_ROOT and _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from featurefox.lib.ncti_backend import load_part
from featurefox.lib.edge_features import build_face_graph
from featurefox.lib.instance_data import list_step_files, STEPS_DIR
from featurefox.lib.ncti_faceid_map import init_ncti_safe

ncti = init_ncti_safe(_PROJECT_ROOT)
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
