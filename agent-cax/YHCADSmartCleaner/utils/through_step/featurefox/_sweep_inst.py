#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""第二级策略 sweep：在 holdout 上对比几种修复方案的面级 P/R/F1。
策略:
  A. 单级（无第二级）
  B. 第二级 thr=0.50
  C. 第二级 thr=0.80（现状）
  D. 第二级 thr=0.80 + 几何豁免（plane_ratio==1 & concave_ratio==1 & has_split==1 & n_perp_walls>=2）
  E. 第二级 thr=0.80 + 几何豁免（放宽：plane_ratio>=0.66 & concave_ratio>=0.5 & has_split==1）
用法: python -m featurefox._sweep_inst [n] [offset]   默认 0 14000
"""
import os, sys, json, time
import numpy as np
import networkx as nx

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
UTILS_DIR = os.path.dirname(os.path.dirname(THIS_DIR))
TS_DIR = os.path.dirname(THIS_DIR)
for p in (UTILS_DIR, TS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

import xgboost as xgb
from detect_blind_holes_and_export_stp_v15_22 import StepParser
from detect_through_step import _build_edge_convexity_map
from featurefox.edge_features import build_face_graph
from featurefox.predict import (
    load_models, load_instance_models,
    DEFAULT_THRESHOLD, MIN_INSTANCE_FACES, MIN_PLANE_RATIO, INST_THRESHOLD,
)
from featurefox.instance_data import list_step_files, shell_face_order
from featurefox.instance_features import extract_instance_features, INSTANCE_FEATURE_NAMES

STEPS_DIR = r"D:\wyg\data\data\通槽\steps"
LABELS_DIR = r"D:\wyg\data\data\通槽\label"
TARGET = "20221121_154647_101"
FIDX = {n: i for i, n in enumerate(INSTANCE_FEATURE_NAMES)}

def load_seg9(name):
    p = os.path.join(LABELS_DIR, name + ".json")
    if not os.path.exists(p): return None
    with open(p, encoding="utf-8") as f: data = json.load(f)
    inner = data[0][1] if isinstance(data[0], list) else data[0]
    seg = {int(k): v for k, v in inner.get("seg", {}).items()}
    return {c for c, v in seg.items() if v == 9}

def geo_exempt_strict(feats):
    return (feats[FIDX["plane_ratio"]] == 1.0
            and feats[FIDX["concave_edge_ratio"]] == 1.0
            and feats[FIDX["has_bottom_wall_split"]] == 1.0
            and feats[FIDX["n_perp_walls"]] >= 2)

def geo_exempt_loose(feats):
    return (feats[FIDX["plane_ratio"]] >= 0.66
            and feats[FIDX["concave_edge_ratio"]] >= 0.5
            and feats[FIDX["has_bottom_wall_split"]] == 1.0)

def geo_exempt_narrow(feats):
    # 仅"3-4面标准瘦通槽": 纯平面+全凹边+底壁结构+小规模
    return (feats[FIDX["plane_ratio"]] == 1.0
            and feats[FIDX["concave_edge_ratio"]] == 1.0
            and feats[FIDX["has_bottom_wall_split"]] == 1.0
            and feats[FIDX["n_faces"]] <= 4
            and feats[FIDX["n_edges_internal"]] <= 4)

def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    offset = int(sys.argv[2]) if len(sys.argv) > 2 else 14000
    files = list_step_files(n, offset)
    print("files=%d offset=%d" % (len(files), offset), flush=True)
    eb, ec = load_models()
    ib, ic = load_instance_models()
    if ib is None: sys.exit("inst model missing")

    # 每文件预计算候选分量: list of dict{cells:set, inst_p, feats, geo_strict, geo_loose}
    per_file = []  # (seg9, candidates, is_target)
    t0 = time.time()
    for idx, fn in enumerate(files):
        name = os.path.splitext(fn)[0]
        seg9 = load_seg9(name)
        if not seg9:
            continue
        stp = os.path.join(STEPS_DIR, fn)
        try:
            parser = StepParser(stp); parser.parse()
            edges, fa_attrs = build_face_graph(parser)
            order = shell_face_order(parser)
            f2c = {fid: ci for ci, fid in enumerate(order)}
            X = np.array([e["features"] for e in edges], dtype=np.float32)
            cal = ec.transform(eb.predict(xgb.DMatrix(X)))
            fids = list(parser.advanced_faces.keys())
            ftypes = {fid: parser.face_surface_type(fid) for fid in fids}
            G = nx.Graph()
            for fid in fids: G.add_node(fid)
            ep_lookup = {}
            for e, p in zip(edges, cal):
                if p >= DEFAULT_THRESHOLD:
                    G.add_edge(e["fa"], e["fb"], prob=float(p))
                ep_lookup[(min(e["fa"],e["fb"]), max(e["fa"],e["fb"]))] = float(p)
            conv_map, _ = _build_edge_convexity_map(parser, fids)
            cands = []
            for comp in nx.connected_components(G):
                cf = list(comp)
                if len(cf) < MIN_INSTANCE_FACES: continue
                if sum(1 for fid in cf if ftypes[fid]=="PLANE")/len(cf) < MIN_PLANE_RATIO: continue
                feats = extract_instance_features(parser, fa_attrs, conv_map, set(cf), {fid:fid for fid in cf}, ep_lookup)
                Xi = np.array([feats], dtype=np.float32)
                ip = float(ic.transform(ib.predict(xgb.DMatrix(Xi, feature_names=INSTANCE_FEATURE_NAMES)))[0])
                cells = set(f2c.get(fid) for fid in cf)
                cands.append({"cells": cells, "ip": ip,
                              "gs": geo_exempt_strict(feats), "gl": geo_exempt_loose(feats),
                              "gn": geo_exempt_narrow(feats)})
            per_file.append((seg9, cands, name == TARGET))
        except Exception as ex:
            print("ERR %s %s" % (name, ex), flush=True)
        if (idx+1) % 200 == 0:
            print("  preprocess %d/%d %.0fs" % (idx+1, len(files), time.time()-t0), flush=True)

    print("预处理完成: %d 含通槽文件, %.0fs" % (len(per_file), time.time()-t0), flush=True)

    def eval_strategy(alive_fn):
        tp=fp=fn=0; tgt_status=None
        for seg9, cands, is_tgt in per_file:
            detected = set()
            for c in cands:
                if alive_fn(c):
                    detected |= c["cells"]
            tp += len(detected & seg9)
            fp += len(detected - seg9)
            fn += len(seg9 - detected)
            if is_tgt:
                tgt_status = (len(detected & seg9), len(detected - seg9), len(seg9 - detected), sorted(detected))
        p = tp/(tp+fp) if tp+fp else 0
        r = tp/(tp+fn) if tp+fn else 0
        f1 = 2*p*r/(p+r) if p+r else 0
        return p*100, r*100, f1*100, fp, fn, tgt_status

    strategies = {
        "A 单级(无二级)":      lambda c: True,
        "B 二级 thr=0.50":     lambda c: c["ip"] >= 0.50,
        "C 二级 thr=0.80(现)": lambda c: c["ip"] >= 0.80,
        "D 0.80+几何豁免(严)": lambda c: c["ip"] >= 0.80 or c["gs"],
        "E 0.80+几何豁免(宽)": lambda c: c["ip"] >= 0.80 or c["gl"],
        "F 0.80+几何豁免(窄瘦槽)": lambda c: c["ip"] >= 0.80 or c["gn"],
    }
    print("\n" + "="*78)
    print("%-22s %6s %6s %6s %6s %6s" % ("策略", "P%", "R%", "F1%", "FP", "FN"))
    print("-"*78)
    results = {}
    for name, fn in strategies.items():
        p,r,f1,fp,fn_,tgt = eval_strategy(fn)
        results[name] = (p,r,f1,fp,fn_,tgt)
        print("%-22s %6.2f %6.2f %6.2f %6d %6d" % (name, p, r, f1, fp, fn_))
    print("="*78)
    print("\n目标文件 %s 各策略检出:" % TARGET)
    for name, (p,r,f1,fp,fn_,tgt) in results.items():
        if tgt:
            print("  %-22s TP=%d FP=%d FN=%d detected=%s" % (name, tgt[0], tgt[1], tgt[2], tgt[3]))

if __name__ == "__main__":
    main()
