#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""单个零件 dump 全部 PLANE 面的 a_s vs a_n 配对，看真实量级差异。"""
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
    files = sorted(glob.glob(r"D:/wyg/data/data/steps/*.step"))[:3]
    ncti = init_ncti()
    for p in files:
        print(f"\n=== {os.path.basename(p)} ===")
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
        # 只 dump PLANE
        rows = []
        for fid, (ft_s, n_s, a_s) in step_meta.items():
            if ft_s != "PLANE": continue
            j = pos_map.get(fid);
            if j is None: continue
            ft_n, n_n, a_n = ncti_meta[j]
            if ft_n != "PLANE": continue
            ndot = abs(_dot(n_s, n_n)) if (n_s and n_n) else 0
            rows.append((a_s, a_n, a_s/a_n if a_n>0 else 0, ndot))
        # 排序按 a_n 降序
        rows.sort(key=lambda x: -x[1])
        for a_s, a_n, r, ndot in rows[:15]:
            print(f"  a_s={a_s:12.4f}  a_n={a_n:12.4f}  ratio={r:8.4f}  ndot={ndot:.3f}")
        print(f"  ...total {len(rows)} PLANE pairs")
        break
    os._exit(0)

if __name__=="__main__": main()
