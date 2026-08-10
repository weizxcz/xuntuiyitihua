#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""holdout stage 分析：统计通槽漏检发生在哪一级。
对每个含 seg=9 的文件，判定：
  L1_MISS   = 第一级剪枝就没恢复出通槽（连通分量与 seg9 不重合）
  L2_KILL   = 第一级恢复了但第二级实例分类器杀掉
  OK        = 最终检出
输出按 stage 分桶 + L2_KILL 文件的特征分布。
用法: python -m featurefox._stat_holdout [n_files] [offset]   默认 0 14000 (holdout)
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
TARGET = "20221121_154647_101"  # 重点标注

def load_seg9(name):
    p = os.path.join(LABELS_DIR, name + ".json")
    if not os.path.exists(p): return None
    with open(p, encoding="utf-8") as f: data = json.load(f)
    inner = data[0][1] if isinstance(data[0], list) else data[0]
    seg = {int(k): v for k, v in inner.get("seg", {}).items()}
    return {c for c, v in seg.items() if v == 9}

def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    offset = int(sys.argv[2]) if len(sys.argv) > 2 else 14000
    files = list_step_files(n, offset)
    print("files=%d offset=%d  inst_thr=%.2f" % (len(files), offset, INST_THRESHOLD), flush=True)
    eb, ec = load_models()
    ib, ic = load_instance_models()
    if ib is None: sys.exit("inst model missing")

    t0 = time.time()
    # 分桶
    L1_MISS = 0   # 有 seg9 但第一级任何连通分量都不含 seg9（完全没召回）
    L1_PART = 0   # 第一级恢复部分 seg9
    L2_KILL = 0   # 第一级有完整/部分 seg9 分量但被第二级杀
    L2_KILL_FULL = 0  # 第一级完全恢复 seg9 但被第二级杀（纯第二级责任）
    has_slot = 0
    ok = 0
    kill_details = []  # (name, n_faces_slot, n_edges, edge_prob_mean, inst_p)

    for idx, fn in enumerate(files):
        name = os.path.splitext(fn)[0]
        seg9 = load_seg9(name)
        if not seg9:
            continue
        has_slot += 1
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
            # 每个候选分量的 seg9 cell 交集
            conv_map, _ = _build_edge_convexity_map(parser, fids)
            slot_face_set = {fid for fid, ci in f2c.items() if ci in seg9}
            # 找包含 seg9 面最多的候选分量
            best_overlap = 0
            best_full = False
            best_comp_cells = None
            best_meta = None
            for comp in nx.connected_components(G):
                cf = list(comp)
                if len(cf) < MIN_INSTANCE_FACES: continue
                if sum(1 for fid in cf if ftypes[fid]=="PLANE")/len(cf) < MIN_PLANE_RATIO: continue
                cells = set(f2c.get(fid) for fid in cf)
                ov = len(cells & seg9)
                if ov > best_overlap:
                    best_overlap = ov
                    best_full = (cells & seg9 == seg9) and len(cells - seg9) == 0
                    best_comp_cells = cells
                    # 算实例特征 + 概率
                    feats = extract_instance_features(parser, fa_attrs, conv_map, set(cf), {fid:fid for fid in cf}, ep_lookup)
                    Xi = np.array([feats], dtype=np.float32)
                    ip = float(ic.transform(ib.predict(xgb.DMatrix(Xi, feature_names=INSTANCE_FEATURE_NAMES)))[0])
                    best_meta = (len(cf), feats[INSTANCE_FEATURE_NAMES.index("n_edges_internal")],
                                 feats[INSTANCE_FEATURE_NAMES.index("edge_prob_mean")], ip)
            if best_overlap == 0:
                L1_MISS += 1
                stage = "L1_MISS"
            else:
                # 这个分量是否被第二级保留
                survived = best_meta[3] >= INST_THRESHOLD if best_meta else False
                if best_full and not survived:
                    L2_KILL_FULL += 1
                    stage = "L2_KILL_FULL"
                    if best_meta:
                        kill_details.append((name, best_meta[0], best_meta[1], best_meta[2], best_meta[3]))
                elif not survived:
                    L2_KILL += 1
                    stage = "L2_KILL"
                    if best_meta:
                        kill_details.append((name, best_meta[0], best_meta[1], best_meta[2], best_meta[3]))
                else:
                    if not best_full:
                        L1_PART += 1
                        stage = "L1_PART"
                    else:
                        ok += 1
                        stage = "OK"
            mark = " <<<TARGET" if name == TARGET else ""
            if stage != "OK":
                print("[%d/%d] %s %s (seg9=%d best_ov=%d full=%s meta=%s)%s" % (
                    idx+1, len(files), name, stage, len(seg9), best_overlap, best_full,
                    [round(x,3) for x in (best_meta if best_meta else (0,0,0,0))], mark), flush=True)
        except Exception as ex:
            print("[%d/%d] %s ERR %s" % (idx+1, len(files), name, ex), flush=True)
        if (idx+1) % 200 == 0:
            print("  ...progress %d/%d elapsed %.0fs" % (idx+1, len(files), time.time()-t0), flush=True)

    print("\n" + "="*50)
    print("含通槽文件: %d" % has_slot)
    print("  OK (两级都过)        : %d" % ok)
    print("  L1_PART (部分召回)   : %d" % L1_PART)
    print("  L1_MISS (一级零召回) : %d" % L1_MISS)
    print("  L2_KILL (一级有+二级杀): %d" % L2_KILL)
    print("  L2_KILL_FULL(一级完整+二级杀): %d" % L2_KILL_FULL)
    print("耗时 %.0fs" % (time.time()-t0))
    # L2_KILL 特征分布
    if kill_details:
        ep = np.array([d[3] for d in kill_details])
        ip = np.array([d[4] for d in kill_details])
        nf = np.array([d[1] for d in kill_details])
        print("\nL2_KILL 文件特征分布 (n=%d):" % len(kill_details))
        print("  slot面数 n_faces   : mean=%.1f  (%d面占比=%.0f%%)" % (nf.mean(), (nf==3).sum(), 100*(nf==3).mean()))
        print("  edge_prob_mean : mean=%.3f" % ep.mean())
        print("  inst_P         : mean=%.3f  <0.30:%d  <0.15:%d" % (ip.mean(), (ip<0.30).sum(), (ip<0.15).sum()))
        print("\n被杀通槽明细 (前20):")
        for name,nf,ne,epm,ipp in kill_details[:20]:
            mark = " <<<TARGET" if name==TARGET else ""
            print("  %s nfaces=%d nedges=%d epmean=%.3f instP=%.3f%s" % (name,nf,ne,epm,ipp,mark))

if __name__ == "__main__":
    main()
