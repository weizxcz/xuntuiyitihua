#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""单文件诊断：dump featurefox 两级管线每一步中间状态（STEP-parser 版本）。
用法: python -m featurefox.debug._debug_one <step路径>
"""
import os, sys, json
import numpy as np
import networkx as nx

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
# debug/ -> featurefox/ -> parent/
FEATFOX_ROOT = os.path.dirname(os.path.dirname(THIS_DIR))
if FEATFOX_ROOT not in sys.path:
    sys.path.insert(0, FEATFOX_ROOT)
from featurefox.lib._env import get_project_root
PROJECT_ROOT = get_project_root()
if PROJECT_ROOT is None:
    PROJECT_ROOT = os.path.join(os.path.dirname(FEATFOX_ROOT), "YHCADSmartCleaner")
UTILS_DIR = os.path.join(PROJECT_ROOT, "utils")
TS_DIR = os.path.join(UTILS_DIR, "through_step")
for p in (PROJECT_ROOT, UTILS_DIR, TS_DIR, FEATFOX_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

import xgboost as xgb
from detect_blind_holes_and_export_stp_v15_22 import StepParser
from detect_through_step import _build_edge_convexity_map
# STEP-parser 版本（非 NCTI）
sys.path.insert(0, os.path.join(TS_DIR, "featurefox"))
from edge_features import build_face_graph
from predict import (
    load_models, load_instance_models,
    DEFAULT_THRESHOLD, MIN_INSTANCE_FACES, MIN_PLANE_RATIO, INST_THRESHOLD,
)
from instance_data import shell_face_order
from instance_features import extract_instance_features, INSTANCE_FEATURE_NAMES
from featurefox.lib._env import get_steps_dir, get_labels_dir

DEFAULT_STP = os.path.join(get_steps_dir(), "20221121_154647_101.step")
STP = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_STP
NAME = os.path.splitext(os.path.basename(STP))[0]
LABEL = os.path.join(get_labels_dir(), NAME + ".json")

sep = lambda t: print("\n" + "="*20 + " " + t + " " + "="*20)

# ---- 标签 ----
seg9, inst_mat, _ = (None, None, None)
with open(LABEL, "r", encoding="utf-8") as f:
    data = json.load(f)
inner = data[0][1] if isinstance(data[0], list) else data[0]
seg = {int(k): v for k, v in inner.get("seg", {}).items()}
seg9 = {c for c, v in seg.items() if v == 9}
print("文件:", NAME)
print("总 cell 数:", len(seg))
print("seg=9 通槽 cell:", sorted(seg9))
# inst 分组
n = len(inner.get("inst", []))
visited = [False]*n
groups = []
for s in range(n):
    if visited[s] or not any(inner["inst"][s]):
        visited[s] = True; continue
    st=[s]; g=set()
    while st:
        i=st.pop()
        if visited[i]: continue
        visited[i]=True; g.add(i)
        for j in range(n):
            if not visited[j] and (inner["inst"][i][j] or inner["inst"][j][i]):
                st.append(j)
    if len(g)>=2: groups.append(g)
print("inst 实例分组:", [sorted(g) for g in groups])
print("通槽实例 cell seg:", {c: seg.get(c) for c in sorted(seg9)})

# ---- 解析 ----
sep("STEP 解析")
parser = StepParser(STP); parser.parse()
faces = list(parser.advanced_faces.keys())
print("解析出面数:", len(faces))
order = shell_face_order(parser)
face2cell = {fid: ci for ci, fid in enumerate(order)}
cell2face = {ci: fid for fid, ci in face2cell.items()}
print("通槽 cell -> face_id:", {c: cell2face.get(c) for c in sorted(seg9)})
# 面类型
ftypes = {fid: parser.face_surface_type(fid) for fid in faces}
print("通槽面类型:", {cell2face.get(c): ftypes.get(cell2face.get(c)) for c in sorted(seg9)})

# ---- 边特征 + 概率 ----
sep("第一级 边分类器")
edges, fa_attrs = build_face_graph(parser)
print("共享边总数:", len(edges))
booster, calib = load_models()
X = np.array([e["features"] for e in edges], dtype=np.float32)
raw = booster.predict(xgb.DMatrix(X))
cal = calib.transform(raw)
probs = np.array(cal)
print("校准概率: min=%.3f max=%.3f mean=%.3f  >=0.35: %d  >=0.50: %d  >=0.80: %d" % (
    probs.min(), probs.max(), probs.mean(), (probs>=0.35).sum(), (probs>=0.50).sum(), (probs>=0.80).sum()))
# 直方图
h, e = np.histogram(probs, bins=[0,0.1,0.2,0.3,0.35,0.4,0.5,0.6,0.7,0.8,0.9,1.01])
print("概率直方图:")
for lo, hi, cnt in zip(e[:-1], e[1:], h):
    print("  [%.2f,%.2f): %d" % (lo,hi,cnt))

# 通槽内部边
slot_faces = {cell2face[c] for c in seg9 if c in cell2face}
print("\n通槽 face_id 集合:", sorted(slot_faces))
slot_edges = []
for e, p in zip(edges, cal):
    if e["fa"] in slot_faces and e["fb"] in slot_faces:
        slot_edges.append((e["fa"], e["fb"], float(p)))
print("通槽内部共享边数:", len(slot_edges))
for fa,fb,p in slot_edges:
    ca, cb = face2cell.get(fa), face2cell.get(fb)
    print("  edge cell(%d-%d) face(%d-%d) P=%.3f %s" % (ca,cb,fa,fb,p, "<-- <0.35 丢弃" if p<DEFAULT_THRESHOLD else ""))

# 通槽面到外部的边（边界边）
bound_edges = []
for e, p in zip(edges, cal):
    inslot = (e["fa"] in slot_faces) + (e["fb"] in slot_faces)
    if inslot == 1:
        bound_edges.append((e["fa"], e["fb"], float(p)))
print("\n通槽边界边数(一面在槽内):", len(bound_edges))
for fa,fb,p in bound_edges:
    print("  boundary face(%d-%d) P=%.3f" % (fa,fb,p))

# ---- 剪枝 + 连通分量 ----
sep("剪枝 + 连通分量 (thr=%.2f)" % DEFAULT_THRESHOLD)
G = nx.Graph()
for fid in faces: G.add_node(fid)
for e, p in zip(edges, cal):
    if p >= DEFAULT_THRESHOLD:
        G.add_edge(e["fa"], e["fb"], prob=float(p))
comps = list(nx.connected_components(G))
big = [c for c in comps if len(c) >= MIN_INSTANCE_FACES]
print("连通分量总数:", len(comps), " 其中 >=%d 面: %d" % (MIN_INSTANCE_FACES, len(big)))
for i, c in enumerate(sorted(comps, key=len, reverse=True)):
    cells = sorted(face2cell.get(f, -99) for f in c)
    overlap = sorted(seg9 & set(cells))
    print("  comp#%d: %d面 cells=%s seg9交集=%s" % (i, len(c), cells, overlap))

# ---- 后处理 ----
sep("后处理 (面数>=%d & 平面占比>=%.2f)" % (MIN_INSTANCE_FACES, MIN_PLANE_RATIO))
for i, c in enumerate(sorted(comps, key=len, reverse=True)):
    cf = list(c)
    npl = sum(1 for fid in cf if ftypes.get(fid)=="PLANE")
    ratio = npl/len(cf)
    cells = sorted(face2cell.get(f,-99) for f in cf)
    keep = len(cf)>=MIN_INSTANCE_FACES and ratio>=MIN_PLANE_RATIO
    print("  comp#%d %d面 平面%d(%.0f%%) cells=%s seg9交集=%s -> %s" % (
        i, len(cf), npl, ratio*100, cells, sorted(seg9 & set(cells)), "保留" if keep else "丢弃"))

# ---- 实例分类器 ----
sep("第二级 实例分类器 (thr=%.2f)" % INST_THRESHOLD)
inst_b, inst_c = load_instance_models()
all_fids = list(parser.advanced_faces.keys())
conv_map, _ = _build_edge_convexity_map(parser, all_fids)
edge_prob_lookup = {}
for e, p in zip(edges, cal):
    edge_prob_lookup[(min(e["fa"],e["fb"]), max(e["fa"],e["fb"]))] = float(p)
for i, c in enumerate(sorted(comps, key=len, reverse=True)):
    cf = list(c)
    if len(cf) < MIN_INSTANCE_FACES: continue
    npl = sum(1 for fid in cf if ftypes.get(fid)=="PLANE")
    if npl/len(cf) < MIN_PLANE_RATIO: continue
    feats = extract_instance_features(parser, fa_attrs, conv_map, set(cf), {fid:fid for fid in cf}, edge_prob_lookup)
    Xi = np.array([feats], dtype=np.float32)
    ip = float(inst_c.transform(inst_b.predict(xgb.DMatrix(Xi, feature_names=INSTANCE_FEATURE_NAMES)))[0])
    cells = sorted(face2cell.get(f,-99) for f in cf)
    print("  comp %d面 cells=%s seg9交集=%s -> inst_P=%.3f %s" % (
        len(cf), cells, sorted(seg9 & set(cells)), ip, "保留" if ip>=INST_THRESHOLD else "拒绝(<%.2f)"%INST_THRESHOLD))
    # 逐特征 dump（含第一级增益归因）
    print("    26维实例特征:")
    for nm, v in zip(INSTANCE_FEATURE_NAMES, feats):
        print("      %-26s = %.4f" % (nm, v))
    imp = inst_b.get_score(importance_type="gain")
    print("    分类器 top-8 gain:", [(k, round(v,1)) for k,v in sorted(imp.items(), key=lambda x:-x[1])[:8]])
