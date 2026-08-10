#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""多文件 dump 真实 PLANE/CYL 配对，看 a_s vs a_n 真实量级与单位。"""
import os, sys, math, glob, pickle, subprocess, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
PROJ = os.path.dirname(os.path.dirname(HERE))
for _d in (REPO, PROJ, os.path.join(PROJ,"utils"), HERE):
    if _d not in sys.path: sys.path.insert(0, _d)
from detect_blind_holes_and_export_stp_v15_22 import StepParser
from featurefox.edge_features import FaceAttrs
from geom_helpers import _dot
from featurefox.ncti_faceid_map import build_step_face_to_ncti_pos_map

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
    files = sorted(glob.glob(r"D:/wyg/data/data/steps/*.step"))[:6]
    ncti = init_ncti()
    out = []
    for p in files:
        parser = StepParser(p); parser.parse()
        # 边界盒 → 估算零件尺度
        all_pts = [pt for pt in parser.points.values() if pt is not None and len(pt)>=3]
        if all_pts:
            xs=[pt[0] for pt in all_pts]; ys=[pt[1] for pt in all_pts]; zs=[pt[2] for pt in all_pts]
            bbox = (max(xs)-min(xs), max(ys)-min(ys), max(zs)-min(zs))
        else: bbox = None
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
            out.append({"file": os.path.basename(p), "ft": ft_s, "a_s": a_s, "a_n": a_n, "bbox": bbox})
    # 分 ftype dump
    for ft in ("PLANE","CYL","OTHER"):
        rows = [r for r in out if r["ft"]==ft]
        if not rows: continue
        # 按 a_s 排序
        rows.sort(key=lambda r: r["a_s"])
        print(f"\n=== {ft}  共 {len(rows)} 对 ===")
        for r in rows[:20]:
            ratio = r["a_s"]/r["a_n"] if r["a_n"]>0 else float("inf")
            print(f"  {r['file']:>35}  a_s={r['a_s']:10.3f}  a_n={r['a_n']:10.4f}  a_s/a_n={ratio:10.3f}  bbox={r['bbox']}")
    os._exit(0)

if __name__=="__main__": main()
