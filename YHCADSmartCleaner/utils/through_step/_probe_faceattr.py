#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""1-file probe: FaceAttr 12 维各项语义探测。

目的：确定 centroid xyz 在 FaceAttr 的哪几个位置（CLAUDE.md 文档写 [6][7][8]，
       但需要实测确认）。

目标：找一个有大量 PLANE 的小件（如 steps/20221121_154647_0.step 之前用过的）。
"""
import os, sys, math
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
PROJ = os.path.dirname(os.path.dirname(HERE))
for _d in (REPO, PROJ, os.path.join(PROJ,"utils"), HERE):
    if _d not in sys.path: sys.path.insert(0, _d)
from detect_blind_holes_and_export_stp_v15_22 import StepParser
from featurefox.edge_features import FaceAttrs
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
    p = r"D:/wyg/data/data/steps/20221121_154647_0.step"
    print(f"=== file: {os.path.basename(p)} ===")
    parser = StepParser(p); parser.parse()
    fa = FaceAttrs(parser)
    ncti = init_ncti()
    doc = ncti.Document(); doc.New("OCC","DCM",0)
    if not doc.RunCommand("cmd_ncti_import_file", str(p), "testbox"):
        print("import 失败"); return
    ai = ncti.AiModel(doc, "testbox")
    n = len(ai.FaceID)
    print(f"  ai.FaceAttr[i] 长度 = {len(ai.FaceAttr[0]) if ai.FaceAttr else 0}")
    print(f"  ai.FaceID 数量 = {n}")
    # 1) 打印前 5 个面的 FaceAttr 全部 12 维
    print(f"\n=== FaceAttr 前 5 个面（每个 12 维）===")
    for i in range(min(5, n)):
        attr = ai.FaceAttr[i]
        print(f"  face {i}: {list(attr)}")
    # 2) oracle 配对
    step_c = {}; step_meta = {}
    for k, fid in enumerate(parser.advanced_faces.keys()):
        c = fa.centroid(fid)
        if c is None: continue
        step_c[fid] = c
        step_meta[fid] = (fa.ftype(fid), fa.normal(fid), fa.area(fid))
    pos_map, _ = build_step_face_to_ncti_pos_map(step_c, doc, ncti, "testbox", tol=None)
    print(f"\n  oracle 配对: {len(pos_map)}/{len(step_meta)}")
    # 3) 对每个 oracle 配对, dump STEP centroid vs NCTI GetFaceMidPoint vs FaceAttr 各列候选
    print(f"\n=== STEP centroid vs NCTI MidPoint vs FaceAttr 各列 ===")
    print(f"  {'k':>3} {'fid':>5} {'ft':>5} {'STEP_centroid':>30}  {'NCTI_MidPoint':>30}  {'FaceAttr[6,7,8]':>30}")
    shown = 0
    for fid, (ft_s, n_s, a_s) in step_meta.items():
        j = pos_map.get(fid)
        if j is None: continue
        if shown >= 8: break
        if ft_s != "PLANE": continue
        sc = step_c[fid]
        try:
            mid = _pt(doc.GetFaceMidPoint("testbox", j))
        except:
            mid = (0,0,0)
        attr = ai.FaceAttr[j]
        # 假设 centroid xyz 在 [6][7][8]
        cand = (attr[6], attr[7], attr[8]) if len(attr) > 8 else (None,None,None)
        # 也试 [7][8][9]
        cand2 = (attr[7], attr[8], attr[9]) if len(attr) > 9 else (None,None,None)
        # [5][6][7]
        cand3 = (attr[5], attr[6], attr[7]) if len(attr) > 7 else (None,None,None)
        print(f"  fid={fid:>5} j={j:>3} ft={ft_s:>5}")
        print(f"    STEP_centroid = {sc}")
        print(f"    NCTI_MidPoint = {mid}")
        print(f"    FaceAttr[5..11] = {list(attr[5:]) if len(attr)>5 else attr}")
        print(f"    cand [6,7,8]   = {cand}")
        print(f"    cand [7,8,9]   = {cand2}")
        print(f"    cand [5,6,7]   = {cand3}")
        # 算距离，看哪个候选最接近
        def dist(a, b):
            return math.sqrt(sum((a[i]-b[i])**2 for i in range(3)))
        print(f"    dist [6,7,8] vs Mid  = {dist(cand, mid):.4f}  vs STEP_centroid = {dist(cand, sc):.4f}")
        print(f"    dist [5,6,7] vs Mid  = {dist(cand3, mid):.4f}  vs STEP_centroid = {dist(cand3, sc):.4f}")
        shown += 1
    try: doc.Clear()
    except: pass
    os._exit(0)

if __name__=="__main__": main()
