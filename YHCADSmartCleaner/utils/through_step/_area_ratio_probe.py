#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一次性诊断：按 ftype 分桶打印 min(a_s,a_n)/max(a_s,a_n) 比值分布。

目的：决定 sigs_agree 中面积阈值的具体收紧/放宽数字。
  PLANE：鞋带投影只对直边多边形精确，弧边被弦化略偏小 → 阈值从 0.5 收紧还是放宽？
  CYL  ：鞋带 << 真曲面面积，r 可能小到 0.01 → 阈值要再放宽到 0.2？
  OTHER：cone/sphere/torus 同 CYL 严重偏小。
"""
import os, sys, math, glob, pickle, subprocess, tempfile
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))                   # utils/through_step
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))                 # YHCADSmartCleaner
REPO_ROOT = os.path.dirname(PROJECT_ROOT)                             # d:\wyg\xuntuiyitihua
UTILS_DIR = os.path.join(PROJECT_ROOT, "utils")
# 路径顺序很关键：要让 'featurefox' 当包导入（不与同名模块冲突）
for _d in (REPO_ROOT, PROJECT_ROOT, UTILS_DIR, HERE):
    if _d not in sys.path: sys.path.insert(0, _d)

from detect_blind_holes_and_export_stp_v15_22 import StepParser
from featurefox.edge_features import FaceAttrs
from geom_helpers import _dot
from featurefox.ncti_faceid_map import build_step_face_to_ncti_pos_map

PY312 = r"D:/Anaconda3/envs/yhcad_py312/python.exe"
NORM_TH = math.cos(math.radians(25.0))

def init_ncti():
    sdk = os.path.join(PROJECT_ROOT, "SDK")
    if sdk not in sys.path: sys.path.insert(0, sdk)
    try: os.add_dll_directory(sdk); os.add_dll_directory(os.path.join(sdk,"OCC"))
    except: pass
    import ctypes
    for dll in ["ncti_command.dll","ncti_occ_plugin.dll","ncti_doc_occ.dll","ncti_render_vulkan.dll","ncti_window.dll"]:
        p=os.path.join(sdk,dll);
        if os.path.exists(p): ctypes.CDLL(p)
    import ncti_python; ncti_python.Init(sdk); return ncti_python

def _pt(p):
    try: return (float(p.X),float(p.Y),float(p.Z))
    except: return (float(p[0]),float(p[1]),float(p[2]))

def worker(chunk_pkl, out_pkl):
    paths = pickle.load(open(chunk_pkl,"rb"))
    ncti = init_ncti()
    TH_N = NORM_TH
    out = []
    for p in paths:
        try:
            parser = StepParser(p); parser.parse()
            fa = FaceAttrs(parser)
            step_centroids = {}; step_meta = {}
            for k, fid in enumerate(parser.advanced_faces.keys()):
                c = fa.centroid(fid)
                if c is None: continue
                step_centroids[fid] = c
                step_meta[fid] = (fa.ftype(fid), fa.normal(fid), fa.area(fid))
            doc = ncti.Document()
            doc.New("OCC","DCM",0)
            if not doc.RunCommand("cmd_ncti_import_file", str(p), "testbox"):
                out.append({"path":p,"err":"import"}); continue
            ai = ncti.AiModel(doc, "testbox")
            n_ncti = len(ai.FaceID)
            ncti_meta = {}
            for i in range(n_ncti):
                attr = ai.FaceAttr[i] if i<len(ai.FaceAttr) else []
                ftype = "PLANE" if (len(attr)>0 and attr[0]==1.0) else ("CYL" if (len(attr)>1 and attr[1]==1.0) else "OTHER")
                area = float(attr[5]) if len(attr)>5 else 0.0
                try:
                    n = _pt(doc.GetNormalByUV("testbox",i,0.5,0.5)) if True else None
                except: n = None
                ncti_meta[i] = (ftype, n, area)
            pos_map, _ = build_step_face_to_ncti_pos_map(step_centroids, doc, ncti, "testbox", tol=None)
            try: doc.Clear()
            except: pass
            for fid, (ft_s, n_s, a_s) in step_meta.items():
                j = pos_map.get(fid)
                if j is None: continue
                m = ncti_meta.get(j)
                if m is None: continue
                ft_n, n_n, a_n = m
                if ft_s != ft_n: continue
                if not n_s or not n_n: continue
                if abs(_dot(n_s, n_n)) < TH_N: continue
                if a_s < 1e-9 or a_n < 1e-9: continue
                r = min(a_s, a_n) / max(a_s, a_n)
                out.append({"path":p, "ft":ft_s, "r":r, "a_s":a_s, "a_n":a_n})
        except Exception as e:
            out.append({"path":p, "err":repr(e)[:60]})
        tmp = out_pkl+".tmp"; pickle.dump(out,open(tmp,"wb")); os.replace(tmp, out_pkl)
    os._exit(0)

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", nargs=1, metavar=("CHUNK",))
    ap.add_argument("--out", default="_area_probe.pkl")
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--chunk", type=int, default=15)
    args = ap.parse_args()
    if args.worker:
        # 子进程模式：给定 chunk_pkl 和 out_pkl
        # 调用方式：--worker <CHUNK> <OUT>，但为简洁我们固定 from env
        # 实际 main 走的是另一条路，下面兼容旧的 two-arg 调用
        ap2 = argparse.ArgumentParser()
        ap2.add_argument("--worker", nargs=2, metavar=("CHUNK","OUT"))
        ns = ap2.parse_args()
        if ns.worker: worker(ns.worker[0], ns.worker[1])
        return
    files = sorted(glob.glob(r"D:/wyg/data/data/steps/*.step"))[:args.n]
    chunks = [files[i:i+args.chunk] for i in range(0,len(files),args.chunk)]
    R = []
    for ci, ch in enumerate(chunks):
        cf = os.path.join(tempfile.gettempdir(), f"_arp_chunk_{ci}.pkl")
        of = os.path.join(tempfile.gettempdir(), f"_arp_out_{ci}.pkl")
        pickle.dump(ch, open(cf,"wb"))
        if os.path.exists(of): os.remove(of)
        subprocess.run([PY312, os.path.abspath(__file__), "--worker", cf, of], check=False, timeout=900)
        if os.path.exists(of):
            try: R.extend(pickle.load(open(of,"rb")))
            except: pass
        print(f"chunk {ci+1}/{len(chunks)} done, total samples={len(R)}")
    pickle.dump(R, open(args.out,"wb"))
    print(f"wrote {args.out} with {len(R)} samples")
    # 分桶
    bins = [(0.0,0.05),(0.05,0.1),(0.1,0.2),(0.2,0.3),(0.3,0.4),(0.4,0.5),
            (0.5,0.6),(0.6,0.7),(0.7,0.8),(0.8,0.9),(0.9,0.95),(0.95,1.0)]
    by_ft = defaultdict(lambda: [0]*len(bins))
    cnt = defaultdict(int)
    for r in R:
        ft = r.get("ft")
        if not ft: continue
        cnt[ft] += 1
        for bi,(lo,hi) in enumerate(bins):
            if lo <= r["r"] < hi: by_ft[ft][bi] += 1; break
        else:
            if r["r"] >= 1.0 - 1e-9: by_ft[ft][-1] += 1
    print("\n=== 面积比 min/max 分桶分布（仅类型+法向同向对，a_s,a_n>0）===")
    print(f"样本数: PLANE={cnt['PLANE']}  CYL={cnt['CYL']}  OTHER={cnt['OTHER']}")
    print(f"{'bin':>10}  {'PLANE':>8}  {'CYL':>8}  {'OTHER':>8}")
    for bi,(lo,hi) in enumerate(bins):
        print(f"  [{lo:.2f},{hi:.2f})  {by_ft['PLANE'][bi]:>8}  {by_ft['CYL'][bi]:>8}  {by_ft['OTHER'][bi]:>8}")
    # 关键分位
    def pct(ft, p):
        rs = sorted([r["r"] for r in R if r.get("ft")==ft])
        if not rs: return None
        k = max(0, min(len(rs)-1, int(p*len(rs))))
        return rs[k]
    print(f"\n分位数 (1.0=完全相等):")
    for ft in ("PLANE","CYL","OTHER"):
        print(f"  {ft:>5}  p1={pct(ft,0.01):.3f}  p5={pct(ft,0.05):.3f}  p10={pct(ft,0.10):.3f}  p25={pct(ft,0.25):.3f}  p50={pct(ft,0.50):.3f}  p75={pct(ft,0.75):.3f}  p90={pct(ft,0.90):.3f}  p95={pct(ft,0.95):.3f}  p99={pct(ft,0.99):.3f}")
    # 给建议
    print("\n=== 阈值建议（基于分布）===")
    for ft, lo, hi in [("PLANE",0.5,0.7),("CYL",0.05,0.2),("OTHER",0.05,0.2)]:
        below_lo = sum(1 for r in R if r.get("ft")==ft and r["r"]<lo)
        below_hi = sum(1 for r in R if r.get("ft")==ft and r["r"]<hi)
        n = cnt[ft]
        if n:
            print(f"  {ft:>5}  r<{lo} → 拒绝 {below_lo}/{n} ({below_lo/n:.1%})  |  r<{hi} → 拒绝 {below_hi}/{n} ({below_hi/n:.1%})")

if __name__=="__main__":
    # 子进程模式：argv 形式为 ['--worker', '<chunk>', '<out>']
    if len(sys.argv) >= 4 and sys.argv[1] == "--worker":
        worker(sys.argv[2], sys.argv[3])
    else:
        main()
