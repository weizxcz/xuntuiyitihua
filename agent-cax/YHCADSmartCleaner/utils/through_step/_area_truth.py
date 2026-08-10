#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""用真实 STEP 文件，估算 PLANE 面的真实面积（用边界盒投影估算）vs fa.area vs NCTI attr[5]."""
import os, sys, math, glob, pickle
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

def plane_area_from_vertices(pts, normal):
    """对 pts 投影到 normal 平面后用凸包面积近似（凸包没用，直接用凸多边形对角线）。"""
    if not normal or len(pts) < 3: return 0.0
    n = normal
    ref = (1.0, 0.0, 0.0) if abs(n[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = (ref[1]*n[2]-ref[2]*n[1], ref[2]*n[0]-ref[0]*n[2], ref[0]*n[1]-ref[1]*n[0])
    ulen = math.sqrt(sum(x*x for x in u))
    if ulen < 1e-12: return 0.0
    u = tuple(x/ulen for x in u)
    v = (n[1]*u[2]-n[2]*u[1], n[2]*u[0]-n[0]*u[2], n[0]*u[1]-n[1]*u[0])
    pts2 = [(sum(p[k]*u[k] for k in range(3)), sum(p[k]*v[k] for k in range(3))) for p in pts]
    # 凸包（Andrew's monotone chain）
    pts2 = sorted(set(pts2))
    if len(pts2) < 3: return 0.0
    def cross(o, a, b): return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    lower = []
    for p in pts2:
        while len(lower)>=2 and cross(lower[-2], lower[-1], p) <= 0: lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts2):
        while len(upper)>=2 and cross(upper[-2], upper[-1], p) <= 0: upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    area = 0.0
    n_h = len(hull)
    for i in range(n_h):
        j = (i+1) % n_h
        area += hull[i][0]*hull[j][1] - hull[j][0]*hull[i][1]
    return abs(area)/2.0

def main():
    files = sorted(glob.glob(r"D:/wyg/data/data/steps/*.step"))[:30]
    ncti = init_ncti()
    out = []
    for p in files:
        try:
            parser = StepParser(p); parser.parse()
            fa = FaceAttrs(parser)
            step_c = {}; step_meta = {}; step_pts = {}
            for k, fid in enumerate(parser.advanced_faces.keys()):
                c = fa.centroid(fid)
                if c is None: continue
                step_c[fid] = c
                step_meta[fid] = (fa.ftype(fid), fa.normal(fid), fa.area(fid))
                # 收集顶点
                pts = []
                seen = set()
                for ec_id in parser.face_to_edge_curves.get(fid, set()):
                    e = parser.edge_curves.get(ec_id)
                    if not e: continue
                    for vid in (e.get("v1"), e.get("v2")):
                        if vid is None or vid in seen: continue
                        seen.add(vid)
                        pref = parser.vertex_points.get(vid)
                        pp = parser.points.get(pref) if pref is not None else None
                        if pp is not None and len(pp)>=3: pts.append(pp)
                step_pts[fid] = pts
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
                if ft_s != "PLANE": continue
                j = pos_map.get(fid)
                if j is None: continue
                ft_n, n_n, a_n = ncti_meta[j]
                if ft_n != "PLANE": continue
                ndot = abs(_dot(n_s, n_n)) if (n_s and n_n) else 0
                if ndot < 0.9: continue
                # 用凸包面积作为 PLANE 真实面积估算
                truth_area = plane_area_from_vertices(step_pts.get(fid, []), n_s)
                n_verts = len(step_pts.get(fid, []))
                out.append({
                    "ft": "PLANE", "a_s": a_s, "a_n": a_n, "truth": truth_area,
                    "a_s/truth": a_s/truth_area if truth_area>1e-9 else 0,
                    "a_n/truth": a_n/truth_area if truth_area>1e-9 else 0,
                    "n_verts": n_verts, "ndot": ndot,
                    "file": os.path.basename(p),
                })
        except Exception as e:
            print(f"err {os.path.basename(p)}: {e}")
    pickle.dump(out, open("_area_truth.pkl","wb"))
    print(f"dumped {len(out)} pairs")
    # 统计
    if not out: os._exit(0)
    from collections import defaultdict
    rows = out
    for key in ("a_s/truth","a_n/truth"):
        vals = sorted([r[key] for r in rows if r[key]>0])
        if not vals: continue
        def pct(p): return vals[max(0,min(len(vals)-1,int(p*len(vals))))]
        print(f"\n{key}: p1={pct(0.01):.3f} p10={pct(0.10):.3f} p25={pct(0.25):.3f} p50={pct(0.50):.3f} p75={pct(0.75):.3f} p90={pct(0.90):.3f} p99={pct(0.99):.3f}")
    # 顶点数 vs a_s/truth
    print("\nn_verts vs a_s/truth（如果 a_s 是顶点凸包面积，n_verts=4 时 a_s/truth≈1）")
    by_nv = defaultdict(list)
    for r in rows:
        if r["a_s/truth"]>0:
            by_nv[min(r["n_verts"], 12)].append(r["a_s/truth"])
    for nv in sorted(by_nv.keys()):
        vs = by_nv[nv]
        vs_sorted = sorted(vs)
        def pct(p): return vs_sorted[max(0,min(len(vs_sorted)-1,int(p*len(vs_sorted))))]
        print(f"  n_verts={nv:>2} (n={len(vs):>4})  p25={pct(0.25):.3f} p50={pct(0.50):.3f} p75={pct(0.75):.3f}")
    os._exit(0)

if __name__=="__main__": main()
