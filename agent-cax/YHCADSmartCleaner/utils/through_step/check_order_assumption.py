#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测量「shell ADVANCED_FACE 声明顺序 == ai.FaceID 位置索引」假设的违反率。

这是零映射（featurefox_ncti）的地基假设：NCTI 导入 STEP 后，第 k 个声明的
ADVANCED_FACE 是否对应 ai.FaceID 的位置 k。count_advanced_faces 只验【面数】，
本脚本验【顺序】+【拓扑】+【labels 真值】——三路独立评估映射逻辑是否正确。

方法（不循环依赖被测假设）：
  1. STEP 侧：StepParser 按声明顺序取每个面的 (类型/法向/面积/重心)。
  2. NCTI 侧：ai.FaceAttr + GetFaceMidPoint + GetNormalByUV 取每个位置 i 的签名。
  3. 独立 oracle：复用 ncti_faceid_map.build_step_face_to_ncti_pos_map（重心↔面中点
     最近邻，【不假设顺序】）给出 step_face_id → ncti 位置 的几何真值对应。
  4. 顺序判定：声明位置 k 的 STEP 面，oracle 说它对应位置 j。j==k → 顺序保持；否则违反。
  5. 高可信过滤：仅当两侧类型+法向(+面积)也一致才算「可信锚点」，排除重心歧义。
  6. 拓扑同构：每个位置 k 的「邻居类型+共享边凸凹性」多重集，两侧比对——与 oracle 解耦。
  7. Labels 真值：用 shell_face_order 解析 CLOSED_SHELL 顺序得 STEP fid→cell_id 真值，
     对比 oracle 给出 pos_map[fid] 与真值 cell_id 的吻合率（F1 风格）。

用法（yhcad_py312 环境，从 utils/through_step 目录执行，PYTHONIOENCODING=utf-8）：
  # 单件验证（确认 convention A 流程打通）
  python check_order_assumption.py --n 1
  # 批量 200 件，convention A（Geo-Rec 训练口径，零映射地基）
  python check_order_assumption.py --n 200 --conv A
  # 子进程 worker 模式（main 自动调用，勿手敲）
  python check_order_assumption.py --worker <chunk.pkl> <out.pkl> A
"""

import os
import sys
import math
import glob
import json
import pickle

# ── 路径设置（与 featurefox/edge_features.py 一致，保证 StepParser/dts/FaceAttrs 可导入）──
HERE = os.path.dirname(os.path.abspath(__file__))                  # utils/through_step
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))              # YHCADSmartCleaner
UTILS_DIR = os.path.join(PROJECT_ROOT, "utils")
for _d in (PROJECT_ROOT, UTILS_DIR, HERE):
    if _d not in sys.path:
        sys.path.insert(0, _d)

from detect_blind_holes_and_export_stp_v15_22 import StepParser  # noqa: E402
from featurefox.edge_features import FaceAttrs                   # noqa: E402
from geom_helpers import _dot                                     # noqa: E402
from featurefox.ncti_faceid_map import build_step_face_to_ncti_pos_map       # noqa: E402

STEP_DATA = r"D:/wyg/data/data/steps"
PY312 = r"D:/Anaconda3/envs/yhcad_py312/python.exe"


# =============================================================================
# NCTI 初始化（直接模式，参照 test_ncti_init.py，不依赖 GUI/config_load）
# =============================================================================

def init_ncti(project_root=PROJECT_ROOT):
    sdk = os.path.join(project_root, "SDK")
    if sdk not in sys.path:
        sys.path.insert(0, sdk)
    try:
        os.add_dll_directory(sdk)
        os.add_dll_directory(os.path.join(sdk, "OCC"))
    except Exception:
        pass
    import ctypes
    for dll in ["ncti_command.dll", "ncti_occ_plugin.dll", "ncti_doc_occ.dll",
                "ncti_render_vulkan.dll", "ncti_window.dll"]:
        p = os.path.join(sdk, dll)
        if os.path.exists(p):
            ctypes.CDLL(p)
    import ncti_python
    ncti_python.Init(sdk)
    return ncti_python


def _pt(p):
    try:
        return (float(p.X), float(p.Y), float(p.Z))
    except (AttributeError, TypeError):
        return (float(p[0]), float(p[1]), float(p[2]))


def get_mid(doc, obj, i):
    try:
        return _pt(doc.GetFaceMidPoint(obj, i))
    except Exception:
        return None


def get_normal(doc, obj, i):
    try:
        v = doc.GetNormalByUV(obj, i, 0.5, 0.5)
        return _pt(v) if v is not None else None
    except Exception:
        return None


# =============================================================================
# PLANE 真面积（凸包投影）— 用于 sigs_agree 的 a_s/truth 判据
# =============================================================================

def _face_vertices(parser, face_id):
    """收集面所有顶点坐标（与 detect_through_step._face_vertices 逻辑一致）。"""
    pts = []
    seen = set()
    for ec_id in parser.face_to_edge_curves.get(face_id, set()):
        edge = parser.edge_curves.get(ec_id)
        if not edge:
            continue
        for vid in (edge.get("v1"), edge.get("v2")):
            if vid is None or vid in seen:
                continue
            seen.add(vid)
            point_ref = parser.vertex_points.get(vid)
            p = parser.points.get(point_ref) if point_ref is not None else None
            if p is not None and len(p) >= 3:
                pts.append(p)
    return pts


def _convex_hull_area_2d(pts, normal):
    """点集投影到 normal 平面后用 Andrew 单调链凸包算面积。无 normal/点<3 → 0。"""
    if not normal or len(pts) < 3:
        return 0.0
    n = normal
    ref = (1.0, 0.0, 0.0) if abs(n[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = (ref[1] * n[2] - ref[2] * n[1],
         ref[2] * n[0] - ref[0] * n[2],
         ref[0] * n[1] - ref[1] * n[0])
    u_len = math.sqrt(sum(x * x for x in u))
    if u_len < 1e-12:
        return 0.0
    u = tuple(x / u_len for x in u)
    v = (n[1] * u[2] - n[2] * u[1],
         n[2] * u[0] - n[0] * u[2],
         n[0] * u[1] - n[1] * u[0])
    pts2 = sorted({(sum(p[k] * u[k] for k in range(3)),
                    sum(p[k] * v[k] for k in range(3))) for p in pts})
    if len(pts2) < 3:
        return 0.0

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower = []
    for p in pts2:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts2):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    area = 0.0
    n_h = len(hull)
    for i in range(n_h):
        j = (i + 1) % n_h
        area += hull[i][0] * hull[j][1] - hull[j][0] * hull[i][1]
    return abs(area) / 2.0


# =============================================================================
# 签名一致性（高可信锚点过滤）
# =============================================================================

def sigs_agree(ft_s, n_s, a_s, ft_n, n_n, a_n, n_verts_s=None, truth_area_s=None):
    """两侧签名是否一致（类型硬等 + 法向同向 + 面积量级合理）。

    法向用 abs(dot) 容 same_sense 翻转；面积按类型分支：
      - PLANE:  STEP 鞋带 ≈ 真面积（p50=1.0, n_verts=4 时几乎完美）；
                NCTI attr[5] 对 PLANE 不可信（p50=0.001 偏差 1000 倍），不参与判据。
                用 a_s / truth_area 比值：
                  n_verts ≤ 6  → r ≥ 0.7
                  n_verts > 6  → r ≥ 0.55（含弧边被弦化略偏小）
      - CYL/OTHER:  STEP 鞋带 ≪ 真曲面面积（差 10~3000 倍）；
                    NCTI attr[5] 是真面积。
                    改用 a_n/a_s 反向（避免分母太小）：
                  r = a_n / a_s；r ≥ 0.2 视为量级合理
                    （CYL p50≈0.001 但 p99≈0.37；0.2 留出余量）
    """
    if ft_n is None or ft_s != ft_n:
        return False
    if n_s and n_n:
        if abs(_dot(n_s, n_n)) < math.cos(math.radians(25.0)):
            return False
    if ft_s == "PLANE":
        # 优先用 a_s/truth（真面积归一化），fallback 到 a_s/a_n（保留旧判据）
        if truth_area_s is not None and truth_area_s > 1e-9 and a_s and a_s > 1e-9:
            r = a_s / truth_area_s
            thr = 0.7 if (n_verts_s is None or n_verts_s <= 6) else 0.55
            if r < thr:
                return False
        elif a_s and a_n and a_s > 1e-9 and a_n > 1e-9:
            # 旧判据（fallback）：min/max
            r = min(a_s, a_n) / max(a_s, a_n)
            if r < 0.5:
                return False
    else:
        # CYL/OTHER：用 a_n/a_s 反向（a_s ≪ a_n，避免取倒数被噪声吞）
        if a_s and a_n and a_s > 1e-9 and a_n > 1e-9:
            r = a_n / a_s
            if r < 0.2:
                return False
    return True


# ── 唯一签名（消除 oracle 歧义：曲面上重心 NN 不可靠）──
_NORM_BUCKETS = 12  # 球面经纬格：方位 12 × 仰角 6

def _normal_bucket(n, buckets=_NORM_BUCKETS):
    """法向量化到球面格 key（方位 buckets × 仰角 6），容 same_sense 翻转。

    把 n 和 -n 规约到同一格（取首非零分量为正的半球），故同向/反向同格。
    """
    if not n:
        return None
    x, y, z = float(n[0]), float(n[1]), float(n[2])
    L = math.sqrt(x * x + y * y + z * z)
    if L < 1e-12:
        return None
    x, y, z = x / L, y / L, z / L
    # 规约到固定半球（首非零分量为正）→ n 与 -n 同格
    for c in (x, y, z):
        if abs(c) > 1e-9:
            if c < 0:
                x, y, z = -x, -y, -z
            break
    az = int(((math.atan2(y, x) / (2 * math.pi)) % 1.0) * buckets)
    el = int((math.asin(max(-1.0, min(1.0, z))) / math.pi + 0.5) * 6)
    return (round(az, 0), round(el, 0))


def _sig_key(ftype, normal):
    """面的强签名 key = (类型, 法向球面格)。用于判全局唯一性。"""
    return (ftype, _normal_bucket(normal))


def _unique_keys(sig_list):
    """sig_list: [(fid/pos, ftype, normal, ...)] → set of 全局唯一的 sig_key。"""
    from collections import Counter
    cnt = Counter(_sig_key(ft, n) for _, ft, n, *_ in sig_list)
    return {k for k, c in cnt.items() if c == 1}



# =============================================================================
# 单件检测
# =============================================================================

def check_one(stp_path, ncti, conv="A", obj="testbox"):
    parser = StepParser(stp_path)
    parser.parse()
    step_order = list(parser.advanced_faces.keys())   # 声明顺序（dict 保插入序）
    fa = FaceAttrs(parser)

    step_centroids = {}
    step_meta = {}                                     # fid -> (k, ftype, normal, area, n_verts, truth_area)
    for k, fid in enumerate(step_order):
        c = fa.centroid(fid)
        if c is None:
            continue
        step_centroids[fid] = c
        n_v = None; truth_a = None
        if fa.ftype(fid) == "PLANE":
            # 计算顶点数 + 凸包面积（=PLANE 真面积）
            pts = _face_vertices(parser, fid)
            n_v = len(pts)
            truth_a = _convex_hull_area_2d(pts, fa.normal(fid))
        step_meta[fid] = (k, fa.ftype(fid), fa.normal(fid), fa.area(fid), n_v, truth_a)
    n_step = len(step_order)

    # NCTI 导入
    doc = ncti.Document()
    if conv == "A":                                    # Geo-Rec 训练口径
        doc.New("OCC", "DCM", 0)
    else:                                              # convention B（test_batch_50_ncti）
        doc.New("OCC", "DCM", "GMSH")
        try:
            doc.ResetCaseResult()
        except Exception:
            pass
        try:
            doc.SetCreateGeGeom(1)
        except Exception:
            pass
        try:
            doc.SetImportAssemelFile(1)
        except Exception:
            pass
    ok = doc.RunCommand("cmd_ncti_import_file", str(stp_path), obj)
    if not ok:
        return {"path": stp_path, "error": "import_failed"}

    ai = ncti.AiModel(doc, obj)
    n_ncti = len(ai.FaceID)
    ncti_meta = {}                                     # 位置 i -> (ftype, normal, area, mid)
    for i in range(n_ncti):
        attr = ai.FaceAttr[i] if i < len(ai.FaceAttr) else []
        if len(attr) > 0 and attr[0] == 1.0:
            ftype = "PLANE"
        elif len(attr) > 1 and attr[1] == 1.0:
            ftype = "CYL"
        else:
            ftype = "OTHER"
        area = float(attr[5]) if len(attr) > 5 else 0.0
        ncti_meta[i] = (ftype, get_normal(doc, obj, i), area, get_mid(doc, obj, i))

    # 独立 oracle：重心↔面中点最近邻（不假设顺序），给 step fid -> ncti 位置
    pos_map, _ = build_step_face_to_ncti_pos_map(step_centroids, doc, ncti, obj, tol=None)
    try:
        doc.Clear()
    except Exception:
        pass

    # 四层计数：loose / type / strict / uniq
    # 另加 plane-only：仅 PLANE 面（两侧采样精确无曲面歧义，最干净的判据）
    lp = lv = tp = tv = sp = sv = up = uv = pp = pv = 0
    examples = []
    # 全局唯一签名（同签名只出现一次 → 该面在对应侧无歧义）
    from collections import Counter
    uniq_step = {k for k, c in Counter(_sig_key(ft, n) for (_, ft, n, _) in step_meta.values()).items() if c == 1}
    uniq_ncti = {k for k, c in Counter(_sig_key(m[0], m[1]) for m in ncti_meta.values()).items() if c == 1}
    for fid, (k, ft_s, n_s, a_s, n_v_s, truth_s) in step_meta.items():
        if fid not in pos_map:
            continue
        j = pos_map[fid]
        m = ncti_meta.get(j)
        if m is None:
            continue
        ft_n, n_n, a_n, _ = m
        order_ok = (j == k)
        if order_ok:
            lp += 1
        else:
            lv += 1
        type_ok = (ft_s == ft_n)
        if type_ok:
            if order_ok:
                tp += 1
            else:
                tv += 1
        if type_ok and sigs_agree(ft_s, n_s, a_s, ft_n, n_n, a_n,
                                   n_verts_s=n_v_s, truth_area_s=truth_s):
            if order_ok:
                sp += 1
            else:
                sv += 1
                if len(examples) < 5:
                    examples.append({"k": k, "j": j, "ft": ft_s})
        # uniq：签名在两侧都唯一 → oracle 不可能把别的面当成它，判定可信
        key_s = _sig_key(ft_s, n_s)
        if key_s in uniq_step and key_s in uniq_ncti:
            if order_ok:
                up += 1
            else:
                uv += 1
                if len(examples) < 10:
                    examples.append({"k": k, "j": j, "ft": ft_s, "uniq": True})
        # plane-only：PLANE 面两侧采样精确，最干净判据
        if ft_s == "PLANE" and ft_n == "PLANE":
            if order_ok:
                pp += 1
            else:
                pv += 1
                if len(examples) < 12:
                    examples.append({"k": k, "j": j, "ft": "PLANE", "plane": True})

    # ── 拓扑同构（per-position local topology signature，不依赖 oracle）──
    topo = _eval_topo_isomorphism(parser, fa, ai, ncti_meta)

    # ── Labels 真值评估（shell_face_order 即金标准 STEP→cell 映射）──
    lab = _eval_against_labels(stp_path, parser, pos_map)

    return {
        "path": stp_path, "conv": conv,
        "n_step": n_step, "n_ncti": n_ncti,
        "count_match": n_step == n_ncti,
        "n_matched": len(pos_map),
        "lp": lp, "lv": lv, "tp": tp, "tv": tv, "sp": sp, "sv": sv,
        "up": up, "uv": uv, "pp": pp, "pv": pv,
        "topo": topo, "lab": lab,
        "examples": examples,
    }


# =============================================================================
# 评估 1：拓扑同构（per-position local topology signature，对 oracle 解耦）
# =============================================================================

def _eval_topo_isomorphism(parser, fa, ai, ncti_meta):
    """每个位置 k 的「邻居类型+共享边凸凹性」多重集，两侧比对。

    签名构造：
      STEP 侧：face_to_edge_curves → edge_curve_to_faces 找邻居，凸凹取
        _build_edge_convexity_map（质心偏移法反推）。
      NCTI 侧：FaceEID/FaceID 找邻居，凸凹取 EdgeAttr[0/1/2]（引擎直接给）。
    比较：相同位置 k 的签名若相等 → 该位置局部拓扑两侧一致。
    """
    import detect_through_step as dts
    conv_map, _ = dts._build_edge_convexity_map(parser, list(parser.advanced_faces.keys()))

    step_sigs = {}
    for k, fid in enumerate(list(parser.advanced_faces.keys())):
        sig = []
        for ec_id in parser.face_to_edge_curves.get(fid, set()):
            for other_fid in parser.edge_curve_to_faces.get(ec_id, set()):
                if other_fid == fid:
                    continue
                other_ft = fa.ftype(other_fid)
                key = (min(fid, other_fid), max(fid, other_fid))
                conv = conv_map.get(key, "smooth")
                # STEP "unknown"（凸凹性算法退化）归一为 smooth，与 NCTI 3 类对齐
                if conv == "unknown":
                    conv = "smooth"
                sig.append((other_ft, conv))
        step_sigs[k] = tuple(sorted(sig))

    ncti_sigs = {}
    n = len(ai.FaceID) if ai else 0
    n_e = min(len(ai.FaceEID), len(ai.FaceFID), len(ai.EdgeAttr))
    for i in range(n):
        # 同一对面（min, max）可有多条共享边（几何上拆段）；先聚合一对面一签名
        pair_convs = {}                       # pair_key -> list of conv labels
        for e_idx in range(n_e):
            eid = ai.FaceEID[e_idx]
            fid = ai.FaceFID[e_idx]
            if eid == i and fid is not None and fid >= 0:
                other = fid
            elif fid == i and eid is not None and eid >= 0:
                other = eid
            else:
                continue
            other_meta = ncti_meta.get(other)
            if other_meta is None:
                continue
            other_ft = other_meta[0]
            ea = ai.EdgeAttr[e_idx] if e_idx < len(ai.EdgeAttr) else []
            if len(ea) > 1 and ea[1]:
                conv = "convex"
            elif len(ea) > 0 and ea[0]:
                conv = "concave"
            else:
                conv = "smooth"
            pair_key = (min(i, other), max(i, other))
            pair_convs.setdefault(pair_key, []).append((other_ft, conv))
        # 一对面一签名：凸凹性取首条非 smooth（与 NctiPart.edge_convexity 一致）
        sig = []
        for k, lst in pair_convs.items():
            ft = lst[0][0]                    # 该邻面类型
            convs = [c for _, c in lst]
            conv = next((c for c in convs if c != "smooth"), "smooth")
            sig.append((ft, conv))
        ncti_sigs[i] = tuple(sorted(sig))

    n_pos = min(len(step_sigs), len(ncti_sigs))
    match = mismatch = 0
    for k in range(n_pos):
        if step_sigs.get(k) == ncti_sigs.get(k):
            match += 1
        else:
            mismatch += 1
    return {"match": match, "mismatch": mismatch, "n_pos": n_pos}


# =============================================================================
# 评估 2：Labels 金标准（oracle vs shell_face_order 真值）
# =============================================================================

LABELS_DIRS = [r"D:/wyg/data/data/labels", r"D:/wyg/data/data/通槽/label"]


def _eval_against_labels(stp_path, parser, pos_map):
    """用 labels 评估 oracle 映射 vs shell_face_order 真值。

    shell_face_order(parser) 给出 STEP 面在 CLOSED_SHELL 引用顺序中的位置 =
    zero-mapping / labels 隐含的真值 cell_id。比较 oracle 预测 pos_map[fid] 与
    真值 cell_id 的吻合率。额外统计 seg=9（通槽）面的吻合率。
    """
    name = os.path.splitext(os.path.basename(stp_path))[0]
    label_data = None
    for d in LABELS_DIRS:
        p = os.path.join(d, name + ".json")
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    label_data = json.load(f)
                break
            except Exception:
                continue
    if label_data is None:
        return {"have_label": False}

    if isinstance(label_data, list) and len(label_data) >= 1:
        inner = label_data[0][1] if isinstance(label_data[0], list) else label_data[0]
        seg = inner.get("seg", {})
    elif isinstance(label_data, dict):
        seg = label_data.get("seg", {})
    else:
        return {"have_label": True, "error": "unknown format"}

    try:
        from featurefox.instance_data import shell_face_order
        face_order = shell_face_order(parser)
    except Exception as e:
        return {"have_label": True, "error": "shell_face_order: " + str(e)[:60]}

    fid_to_cell = {fid: idx for idx, fid in enumerate(face_order)}
    seg_int = {int(k): v for k, v in seg.items()}

    correct = wrong = unmatched = 0
    s9c = s9w = s9u = 0
    for fid, true_cell in fid_to_cell.items():
        true_seg = seg_int.get(true_cell)
        if fid not in pos_map:
            unmatched += 1
            if true_seg == 9:
                s9u += 1
        elif pos_map[fid] == true_cell:
            correct += 1
            if true_seg == 9:
                s9c += 1
        else:
            wrong += 1
            if true_seg == 9:
                s9w += 1

    return {
        "have_label": True,
        "n_faces": len(fid_to_cell),
        "correct": correct, "wrong": wrong, "unmatched": unmatched,
        "s9c": s9c, "s9w": s9w, "s9u": s9u,
        "s9_total": s9c + s9w + s9u,
    }


# =============================================================================
# 子进程 worker（每 chunk 一个进程，规避 NCTI 批量 segfault；增量 pickle 容崩件）
# =============================================================================

def run_worker(chunk_pkl, out_pkl, conv):
    paths = pickle.load(open(chunk_pkl, "rb"))
    ncti = init_ncti(PROJECT_ROOT)
    results = []
    for p in paths:
        try:
            r = check_one(p, ncti, conv)
        except Exception as e:                         # 单件异常不杀进程
            r = {"path": p, "error": repr(e)}
        results.append(r)
        try:                                           # 增量落盘：崩件前数据保留
            tmp = out_pkl + ".tmp"
            with open(tmp, "wb") as fh:
                pickle.dump(results, fh)
            os.replace(tmp, out_pkl)
        except Exception:
            pass
    os._exit(0)                                        # 防 NCTI DLL 析构 segfault（退出码 127 正常）


# =============================================================================
# 主流程 + 报告
# =============================================================================

def report(results, out_path, conv):
    ok = [r for r in results if "error" not in r]
    err = [r for r in results if "error" in r]
    count_match = [r for r in ok if r["count_match"]]
    cm_rate = (len(count_match) / len(ok)) if ok else 0.0

    lp = sum(r["lp"] for r in ok)
    lv = sum(r["lv"] for r in ok)
    tp = sum(r["tp"] for r in ok)
    tv = sum(r["tv"] for r in ok)
    sp = sum(r["sp"] for r in ok)
    sv = sum(r["sv"] for r in ok)
    up = sum(r["up"] for r in ok)
    uv = sum(r["uv"] for r in ok)
    pp = sum(r["pp"] for r in ok)
    pv = sum(r["pv"] for r in ok)
    loose_viol = (lv / (lp + lv)) if (lp + lv) else 0.0
    type_viol = (tv / (tp + tv)) if (tp + tv) else 0.0
    strict_viol = (sv / (sp + sv)) if (sp + sv) else 0.0
    uniq_viol = (uv / (up + uv)) if (up + uv) else 0.0
    plane_viol = (pv / (pp + pv)) if (pp + pv) else 0.0

    # 拓扑同构聚合
    topo_match = sum(r["topo"]["match"] for r in ok if "topo" in r)
    topo_mis = sum(r["topo"]["mismatch"] for r in ok if "topo" in r)
    topo_total = topo_match + topo_mis
    topo_rate = (topo_match / topo_total) if topo_total else 0.0

    # Labels 真值聚合
    lab_files = [r for r in ok if r.get("lab", {}).get("have_label")]
    if lab_files:
        l_total = sum(r["lab"]["n_faces"] for r in lab_files)
        l_corr = sum(r["lab"]["correct"] for r in lab_files)
        l_wrong = sum(r["lab"]["wrong"] for r in lab_files)
        l_unm = sum(r["lab"]["unmatched"] for r in lab_files)
        s9_total = sum(r["lab"]["s9_total"] for r in lab_files)
        s9_corr = sum(r["lab"]["s9c"] for r in lab_files)
        s9_wrong = sum(r["lab"]["s9w"] for r in lab_files)
        s9_unm = sum(r["lab"]["s9u"] for r in lab_files)
        l_rate = (l_corr / l_total) if l_total else 0.0
        s9_rate = (s9_corr / s9_total) if s9_total else 0.0
    else:
        l_total = l_corr = l_wrong = l_unm = s9_total = s9_corr = s9_wrong = s9_unm = 0
        l_rate = s9_rate = 0.0

    clean_files = [r for r in count_match if r["lv"] == 0 and r["lp"] > 0]
    viol_files = [r for r in count_match if r["lv"] > 0]

    L = []
    L.append("=" * 64)
    L.append("顺序假设违反率报告   convention={}   (零映射地基检验)".format(conv))
    L.append("=" * 64)
    L.append("总文件: {}   (成功 {}   失败/崩 {})".format(len(results), len(ok), len(err)))
    L.append("面数匹配 (n_step==n_ncti) 率: {}/{} = {:.1%}".format(
        len(count_match), len(ok), cm_rate))
    L.append("")
    L.append("【核心】声明顺序==位置顺序 的违反率（仅面数匹配件）:")
    L.append("  loose  (oracle 匹配即算)         : preserved={}  violated={}   违反率 = {:.2%}".format(
        lp, lv, loose_viol))
    L.append("  type   (+类型一致，主指标)        : preserved={}  violated={}   违反率 = {:.2%}".format(
        tp, tv, type_viol))
    L.append("  strict (+类型+法向+面积，最严)    : preserved={}  violated={}   违反率 = {:.2%}".format(
        sp, sv, strict_viol))
    L.append("  uniq   (签名全局唯一，oracle无歧义): preserved={}  violated={}   违反率 = {:.2%}  ★最可信".format(
        up, uv, uniq_viol))
    L.append("  plane  (仅 PLANE 面，两侧采样精确)  : preserved={}  violated={}   违反率 = {:.2%}  ★最干净".format(
        pp, pv, plane_viol))
    if count_match:
        L.append("  完全干净文件 (loose 无违反): {}/{} = {:.1%}".format(
            len(clean_files), len(count_match), len(clean_files) / len(count_match)))
        L.append("  含 >=1 违反文件 (loose): {}/{} = {:.1%}".format(
            len(viol_files), len(count_match), len(viol_files) / len(count_match)))
    L.append("")
    L.append("【独立评估 1】拓扑同构（per-position (neighbor_ftype, conv) 多重集比对）:")
    L.append("  match={}  mismatch={}  局部拓扑一致率 = {:.3%}  (位置对 {})".format(
        topo_match, topo_mis, topo_rate, topo_total))
    L.append("  （与 oracle 解耦；若 order 真乱而非签名噪声，此处会显著低于 100%）")
    L.append("")
    L.append("【独立评估 2】Labels 金标准（oracle vs shell_face_order 真值）:")
    L.append("  有 label 的件: {}/{}".format(len(lab_files), len(ok)))
    if l_total:
        L.append("  全 face:    correct={}  wrong={}  unmatched={}  总={}   准确率 = {:.3%}".format(
            l_corr, l_wrong, l_unm, l_total, l_rate))
        L.append("  seg=9(通槽): correct={}  wrong={}  unmatched={}  总={}   准确率 = {:.3%}  ★映射对识别最关键的面".format(
            s9_corr, s9_wrong, s9_unm, s9_total, s9_rate))
        L.append("  完全干净文件 (loose 无违反): {}/{} = {:.1%}".format(
            len(clean_files), len(count_match), len(clean_files) / len(count_match)))
        L.append("  含 >=1 违反文件 (loose): {}/{} = {:.1%}".format(
            len(viol_files), len(count_match), len(viol_files) / len(count_match)))
    L.append("")
    L.append("解读:")
    L.append("  - 面数匹配率高 + 违反率低  => 地基稳，零映射/位置索引可信。")
    L.append("  - 面数匹配率低            => NCTI 合并/拆分面，cell_id 空间与 STEP 错位（更严重）。")
    L.append("  - 面数匹配但违反率高      => 纯重排，位置索引≠声明顺序，零映射会整体错位。")
    L.append("")
    L.append("违反示例 (STEP 声明位 k -> oracle 指认位 j, 类型):")
    shown = 0
    for r in viol_files:
        for ex in r["examples"]:
            L.append("  {}   k={} -> j={}   {}".format(
                os.path.basename(r["path"]), ex["k"], ex["j"], ex["ft"]))
            shown += 1
            if shown >= 25:
                break
        if shown >= 25:
            break

    txt = "\n".join(L)
    print(txt)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(txt)
    print("\n报告写入: {}".format(out_path))


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", nargs=2, metavar=("CHUNK", "OUT"))
    ap.add_argument("--conv", default="A", choices=["A", "B"])
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--chunk", type=int, default=15)
    ap.add_argument("--data", default=STEP_DATA)
    ap.add_argument("--out", default="order_violation_report.txt")
    args = ap.parse_args()

    if args.worker:
        run_worker(args.worker[0], args.worker[1], args.conv)
        return

    files = sorted(glob.glob(os.path.join(args.data, "*.step")) +
                   glob.glob(os.path.join(args.data, "*.stp")))[:args.n]
    print("sampled {} files, conv={}, chunk={}".format(len(files), args.conv, args.chunk))

    all_results = []
    if args.n <= args.chunk:
        # 单进程（小批量，低于 segfault 阈值）
        ncti = init_ncti(PROJECT_ROOT)
        for p in files:
            try:
                r = check_one(p, ncti, args.conv)
            except Exception as e:
                r = {"path": p, "error": repr(e)}
            all_results.append(r)
            tag = "ERR:" + str(r.get("error", ""))[:40] if "error" in r else \
                "n_step={} n_ncti={} match={} lp={} lv={} tp={} tv={}".format(
                    r["n_step"], r["n_ncti"], r["count_match"],
                    r["lp"], r["lv"], r["tp"], r["tv"])
            print("  {} -> {}".format(os.path.basename(p), tag))
    else:
        import subprocess
        import tempfile
        chunks = [files[i:i + args.chunk] for i in range(0, len(files), args.chunk)]
        for ci, chunk in enumerate(chunks):
            cf = os.path.join(tempfile.gettempdir(), "_ovc_chunk_{}.pkl".format(ci))
            of = os.path.join(tempfile.gettempdir(), "_ovc_out_{}.pkl".format(ci))
            with open(cf, "wb") as fh:
                pickle.dump(chunk, fh)
            if os.path.exists(of):
                os.remove(of)
            cmd = [PY312, os.path.abspath(__file__), "--worker", cf, of, "--conv", args.conv]
            print("chunk {}/{} ({} files) ...".format(ci + 1, len(chunks), len(chunk)))
            try:
                subprocess.run(cmd, check=False, timeout=900)
            except Exception as e:
                print("  chunk run failed: {}".format(e))
            if os.path.exists(of):
                try:
                    all_results.extend(pickle.load(open(of, "rb")))
                except Exception as e:
                    print("  load out failed: {}".format(e))
            else:
                print("  no output (worker crashed, lost {} files)".format(len(chunk)))

    report(all_results, args.out, args.conv)


if __name__ == "__main__":
    main()
