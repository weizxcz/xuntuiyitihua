#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""修：先把全部面积配对 dump 到 pkl，再 python 直接读分析。"""
import os, sys, math, glob
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
PROJ = os.path.dirname(os.path.dirname(HERE))
for _d in (REPO, PROJ, os.path.join(PROJ,"utils"), HERE):
    if _d not in sys.path: sys.path.insert(0, _d)
from detect_blind_holes_and_export_stp_v15_22 import StepParser
from featurefox.edge_features import FaceAttrs
from geom_helpers import _dot
from featurefox.ncti_faceid_map import build_step_face_to_ncti_pos_map
import pickle

def init_ncti():
    sdk = os.path.join(PROJ, "SDK")
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

def main():
    files = sorted(glob.glob(r"D:/wyg/data/data/steps/*.step"))[:30]
    ncti = init_ncti()
    out = []
    for p in files:
        parser = StepParser(p); parser.parse()
        fa = FaceAttrs(parser)
        step_c = {}; step_meta = {}
        for k, fid in enumerate(parser.advanced_faces.keys()):
            c = fa.centroid(fid)
            if c is None: continue
            step_c[fid] = c
            step_meta[fid] = (fa.ftype(fid), fa.normal(fid), fa.area(fid))
        doc = ncti.Document(); doc.New("OCC","DCM",0)
        if not doc.RunCommand("cmd_ncti_import_file", str(p), "testbox"): continue
        ai = ncti.AiModel(doc, "testbox")
        ncti_meta = {}
        for i in range(len(ai.FaceID)):
            attr = ai.FaceAttr[i]
            ftype = "PLANE" if attr[0]==1.0 else ("CYL" if attr[1]==1.0 else "OTHER")
            area = float(attr[5])
            n = _pt(doc.GetNormalByUV("testbox",i,0.5,0.5))
            ncti_meta[i] = (ftype, n, area)
        pos_map, _ = build_step_face_to_ncti_pos_map(step_c, doc, ncti, "testbox", tol=None)
        try: doc.Clear()
        except: pass
        for fid, (ft_s, n_s, a_s) in step_meta.items():
            j = pos_map.get(fid)
            if j is None: continue
            ft_n, n_n, a_n = ncti_meta[j]
            if ft_s != ft_n: continue
            ndot = abs(_dot(n_s, n_n)) if (n_s and n_n) else 0
            if ndot < 0.9: continue
            out.append({"ft": ft_s, "a_s": a_s, "a_n": a_n, "ndot": ndot})
    pickle.dump(out, open("_area_pairs.pkl","wb"))
    print(f"dumped {len(out)} pairs")
    # 全部分 ftype
    from collections import defaultdict
    by_ft = defaultdict(list)
    for r in out: by_ft[r["ft"]].append(r)
    for ft, rows in by_ft.items():
        print(f"\n=== {ft}  共 {len(rows)} 对 ===")
        if not rows: continue
        ratios = sorted([(r["a_s"]/r["a_n"] if r["a_n"]>0 else 0) for r in rows])
        def pct(p): return ratios[max(0,min(len(ratios)-1,int(p*len(ratios))))]
        print(f"  ratio (a_s/a_n): p1={pct(0.01):.3f} p10={pct(0.10):.3f} p25={pct(0.25):.3f} p50={pct(0.50):.3f} p75={pct(0.75):.3f} p90={pct(0.90):.3f} p99={pct(0.99):.3f}")
        # 反向：r = a_n/a_s
        ratios_inv = sorted([(r["a_n"]/r["a_s"] if r["a_s"]>0 else 0) for r in rows])
        def pcti(p): return ratios_inv[max(0,min(len(ratios_inv)-1,int(p*len(ratios_inv))))]
        print(f"  ratio (a_n/a_s): p1={pcti(0.01):.3f} p10={pcti(0.10):.3f} p25={pcti(0.25):.3f} p50={pcti(0.50):.3f} p75={pcti(0.75):.3f} p90={pcti(0.90):.3f} p99={pcti(0.99):.3f}")
        # 直方图（log10 a_s/a_n）
        bins = [-3,-2,-1,-0.5,-0.2,0,0.2,0.5,1,2,3]
        hist = [0]*len(bins)
        for r in rows:
            if r["a_n"]<1e-9: continue
            x = math.log10(max(r["a_s"],1e-12)/max(r["a_n"],1e-12))
            for i in range(len(bins)-1):
                if bins[i]<=x<bins[i+1]: hist[i]+=1; break
            else:
                if x>=bins[-1]: hist[-1]+=1
        print("  log10(a_s/a_n) 直方图：")
        for i in range(len(bins)-1):
            print(f"    [{bins[i]:+5.1f}, {bins[i+1]:+5.1f})  {hist[i]:>4}  {'#'*min(50,hist[i])}")
        print(f"    [{bins[-1]:+5.1f}, +inf)  {hist[-1]:>4}  {'#'*min(50,hist[-1])}")
    os._exit(0)

if __name__=="__main__": main()
