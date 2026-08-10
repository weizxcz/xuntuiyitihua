#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""1-file probe: STEP 顶点集 vs NCTI 面点集匹配验证可行性。

目标：拿 sheng kong_Part191.stp 看：
  1. parser.points 有多少 (x,y,z)
  2. StepParser 是否能解析 .stp
  3. NCTI doc 有没有 GetAllPointsOfFace / GetFaceMidPoint / GetPointFromUV
  4. oracle (重心 NN) 配对后, dump 1-2 对 (STEP 顶点集 vs NCTI 点集), 看重合度
"""
import os, sys, math, glob
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
    p = r"D:\wyg\data\data\真实通槽\通槽\step\sheng kong_Part191.stp"
    print(f"=== file: {os.path.basename(p)}  size={os.path.getsize(p)/1024:.0f}KB ===")
    # 1) StepParser 解析
    try:
        parser = StepParser(p); parser.parse()
    except Exception as e:
        print(f"[FAIL] StepParser 解析失败: {e}")
        return
    pts = [pt for pt in parser.points.values() if pt is not None and len(pt)>=3]
    print(f"[OK] StepParser 解析: parser.points={len(parser.points)} 有效 3D 点 {len(pts)}")
    if pts:
        xs=[p[0] for p in pts]; ys=[p[1] for p in pts]; zs=[p[2] for p in pts]
        print(f"     bbox: x=[{min(xs):.2f},{max(xs):.2f}]  y=[{min(ys):.2f},{max(ys):.2f}]  z=[{min(zs):.2f},{max(zs):.2f}]")
    n_adv = len(parser.advanced_faces)
    print(f"     ADVANCED_FACE 数 = {n_adv}")
    # 2) NCTI 初始化 + import
    ncti = init_ncti()
    print(f"\n=== NCTI Document 接口探测 ===")
    doc = ncti.Document()
    # 列出含 GetPoint/AllPoints/FaceMid 之类的方法
    methods = [m for m in dir(doc) if "oint" in m.lower() or "mid" in m.lower() or "uv" in m.lower() or "vertex" in m.lower()]
    print(f"  命中 ('oint/mid/uv/vertex'): {methods}")
    doc.New("OCC","DCM",0)
    ok = doc.RunCommand("cmd_ncti_import_file", str(p), "testbox")
    print(f"  import: {ok}")
    if not ok:
        print("  import 失败，退出"); return
    ai = ncti.AiModel(doc, "testbox")
    n_ncti = len(ai.FaceID)
    print(f"  ai.FaceID 数量 = {n_ncti}")
    # 3) 试探性调用可能的点集接口
    print(f"\n=== 试探 1 个面的点集接口 ===")
    for j in (0, n_ncti//2, n_ncti-1):
        print(f"  --- face {j} ---")
        # GetFaceMidPoint
        try:
            mid = doc.GetFaceMidPoint("testbox", j)
            print(f"    GetFaceMidPoint = {_pt(mid)}")
        except Exception as e:
            print(f"    GetFaceMidPoint 失败: {e}")
        # GetPointFromUV
        for u, v in ((0.5, 0.5), (0.0, 0.0), (1.0, 0.0)):
            try:
                pp = doc.GetPointFromUV("testbox", j, u, v)
                print(f"    GetPointFromUV({u},{v}) = {_pt(pp)}")
            except Exception as e:
                if u == 0.5:  # 只在第一次失败时打
                    print(f"    GetPointFromUV 失败: {e}")
        # 试探 GetAllPointsOfFace / GetFacePoints
        for fname in ("GetAllPointsOfFace","GetFacePoints","GetFaceAllPoints","GetPointsOfFace"):
            if hasattr(doc, fname):
                try:
                    pts_ncti = getattr(doc, fname)("testbox", j)
                    n = len(pts_ncti)
                    sample = [_pt(pts_ncti[k]) for k in range(min(3, n))]
                    print(f"    {fname} → n={n}  sample={sample}")
                except Exception as e:
                    print(f"    {fname} 调用失败: {e}")
            else:
                pass  # 不存在
    # 4) oracle 配对 + dump 1 对
    print(f"\n=== oracle (重心 NN) 配对 + dump 1 对 ===")
    fa = FaceAttrs(parser)
    step_c = {}; step_meta = {}
    for k, fid in enumerate(parser.advanced_faces.keys()):
        c = fa.centroid(fid)
        if c is None: continue
        step_c[fid] = c
        step_meta[fid] = (fa.ftype(fid), fa.normal(fid), fa.area(fid))
    pos_map, _ = build_step_face_to_ncti_pos_map(step_c, doc, ncti, "testbox", tol=None)
    print(f"  配对成功 {len(pos_map)}/{len(step_meta)}")
    # 选一个 PLANE 配对看
    shown = 0
    for fid, (ft_s, n_s, a_s) in step_meta.items():
        j = pos_map.get(fid)
        if j is None: continue
        if ft_s != "PLANE": continue
        # STEP 顶点
        seen=set(); v_pts=[]
        for ec_id in parser.face_to_edge_curves.get(fid, set()):
            e = parser.edge_curves.get(ec_id)
            if not e: continue
            for vid in (e.get("v1"), e.get("v2")):
                if vid is None or vid in seen: continue
                seen.add(vid)
                pref = parser.vertex_points.get(vid)
                pp = parser.points.get(pref) if pref is not None else None
                if pp is not None and len(pp)>=3: v_pts.append(pp)
        # NCTI 顶点（试探 GetAllPointsOfFace）
        n_ncti_pts = -1
        for fname in ("GetAllPointsOfFace","GetFacePoints"):
            if hasattr(doc, fname):
                try:
                    arr = getattr(doc, fname)("testbox", j)
                    n_ncti_pts = len(arr)
                except: pass
                break
        if shown < 3:
            print(f"  PLANE pair: STEP fid={fid} n_verts={len(v_pts)} | NCTI pos={j} n_pts={n_ncti_pts}")
            if v_pts:
                print(f"    STEP 前 3 点: {v_pts[:3]}")
            shown += 1
        if shown >= 3: break
    try: doc.Clear()
    except: pass
    os._exit(0)

if __name__=="__main__": main()
