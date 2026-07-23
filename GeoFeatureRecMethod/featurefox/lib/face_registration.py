#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""通用面配准工具：建 STEP-文本-cell_id ↔ NCTI-ai.FaceID 的面双射（特征无关）。

解决的问题：标注 cell_id 是 STEP 文本 ADVANCED_FACE 出现顺序，NCTI ai.FaceID 是另一
套顺序，真实件两者面数相等但顺序不同 → 位置映射破裂。本工具按**几何签名值匹配**
（不靠位置），建一张面排列，任意特征(seg=9/12/22…)标注都走同一排列重映射。

签名（两边化归到同形，按面类型）：
  PLANE : (单位法向 canonical, 离原点距离 offset)
  CYL   : (轴向 canonical, 半径, 轴向位置)   ← NCTI 用 2 点+2 法向闭式拟合
  OTHER : (类型标记, NCTI 质心) 兜底（锥/环/自由面，机械件少数）

NCTI 侧用 doc.GetNormalByUV / GetFacePointFromUV（featurefox_ncti 同款 UV 采样）。
"""
import os
import re
import sys
import math

import numpy as np

from .ncti_backend import load_part
from .ncti_faceid_map import init_ncti_safe

# ---- 匹配容差（量纲 mm）----
TOL_DIR = 0.02        # 法向/轴向分量容差（cos≈0.02）
TOL_OFF = 0.5         # 平面偏移容差 mm
TOL_RAD = 0.05        # 半径容差 mm
TOL_AXIAL = 0.5       # 同轴圆柱轴向位置容差 mm
TOL_CEN = 0.5         # OTHER 质心容差 mm
TOL_CEN_GLOB = 3.0    # 跨类型兜底质心容差 mm（救类型分歧面，比组内宽）


def _canon(vec):
    """单位化 + 符号规范化（首个非零分量为正），消除法向/轴向朝向歧义。"""
    v = np.array(vec, dtype=np.float64)
    n = np.linalg.norm(v)
    if n < 1e-9:
        return v
    v = v / n
    for c in v:
        if abs(c) > 1e-6:
            if c < 0:
                v = -v
            break
    return v


def _round_vec(v, dec=2):
    return tuple(round(float(x), dec) for x in v)


# ============================================================
# STEP 文本侧：解析每张 ADVANCED_FACE（出现顺序）的曲面参数
# ============================================================
def parse_step_face_signatures(stp_path):
    """返回 list[dict]，按 ADVANCED_FACE 在文本中的出现顺序：
       {"type": "PLANE"/"CYL"/"CONE"/"OTHER", "normal":.., "axis":.., "radius":..,
        "point": (x,y,z)  # 面上一个点（平面=面上点，圆柱=轴上点）}
    """
    with open(stp_path, "r", encoding="utf-8", errors="ignore") as f:
        txt = f.read()
    m = re.search(r"DATA;\s*(.*?)\s*ENDSEC;", txt, re.S | re.I)
    data = m.group(1) if m else txt

    pts = {}      # eid -> (x,y,z)
    dirs = {}     # eid -> (x,y,z)
    axis2 = {}    # eid -> (loc_ref, axis_ref)
    surfs = {}    # eid -> (type, loc_ref, axis_ref, radius_or_None)

    for line in data.splitlines():
        ml = re.match(r"#(\d+)\s*=\s*([A-Z_0-9]+)\s*\((.*)\)\s*;", line)
        if not ml:
            continue
        eid, etype, body = ml.group(1), ml.group(2), ml.group(3)
        if etype == "CARTESIAN_POINT":
            inner = re.search(r"\(([^)]*)\)\s*$", body)
            if inner:
                nums = [float(x) for x in inner.group(1).split(",")]
                pts[eid] = tuple(nums)
        elif etype == "DIRECTION":
            inner = re.search(r"\(([^)]*)\)\s*$", body)
            if inner:
                try:
                    nums = [float(x) for x in inner.group(1).split(",")]
                    dirs[eid] = tuple(nums)
                except ValueError:
                    pass
        elif etype == "AXIS2_PLACEMENT_3D":
            refs = re.findall(r"#(\d+)", body)
            if len(refs) >= 2:
                axis2[eid] = (refs[0], refs[1])  # loc, axis
        elif etype in ("PLANE", "CYLINDRICAL_SURFACE", "CONICAL_SURFACE",
                       "TOROIDAL_SURFACE", "SPHERICAL_SURFACE"):
            refs = re.findall(r"#(\d+)", body)
            nums = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", body)
            radius = None
            if etype == "CYLINDRICAL_SURFACE" and nums:
                radius = float(nums[0])
            elif etype == "TOROIDAL_SURFACE" and len(nums) >= 1:
                radius = float(nums[0])  # major radius 近似
            if refs:
                surfs[eid] = (etype, refs[0], (refs[1] if len(refs) > 1 else None), radius)

    def axis2_xyz(aid):
        if aid not in axis2:
            return None, None
        loc_ref, axis_ref = axis2[aid]
        loc = pts.get(loc_ref)
        ax = dirs.get(axis_ref)
        return loc, ax

    sigs = []
    for line in data.splitlines():
        mf = re.search(r"ADVANCED_FACE\s*\(\s*'[^']*'\s*,\s*\([^)]*\)\s*,\s*#(\d+)", line)
        if not mf:
            continue
        sid = mf.group(1)
        if sid not in surfs:
            sigs.append({"type": "OTHER", "point": None})
            continue
        etype, axis2_ref, axis_ref, radius = surfs[sid]
        # axis2_ref 指向 AXIS2_PLACEMENT_3D（含位置点 + 轴向），穿透解析
        loc, ax = axis2_xyz(axis2_ref)
        if etype == "PLANE":
            sigs.append({"type": "PLANE", "normal": ax, "point": loc})
        elif etype == "CYLINDRICAL_SURFACE":
            sigs.append({"type": "CYL", "axis": ax, "radius": radius, "point": loc})
        elif etype == "CONICAL_SURFACE":
            sigs.append({"type": "CONE", "axis": ax, "point": loc})
        else:
            sigs.append({"type": "OTHER", "point": loc})
    return sigs


# ============================================================
# NCTI 侧：每张 ai.FaceID 的曲面参数（AiModel 5×5 UV 网格 + SVD 鲁棒拟合）
# ============================================================
def ncti_face_signatures(part, doc):
    """返回 list[dict]，按 ai.FaceID 顺序，同 STEP 侧 dict 形状。

    用 AiModel.FacePoints/FaceNormals 5×5 网格（25 点+25 法向）鲁棒拟合：
      - 法向方差≈0 → 平面
      - 法向 SVD 最小奇异值远小（法向共垂于轴）→ 圆柱（轴=最小奇异向量，
        半径=点到轴均距）
      - 否则 OTHER
    """
    ai = part.ncti.AiModel(doc, part.obj_name)
    has_mask = hasattr(ai, "FaceMask")
    sigs = []
    for cell in range(part.n_faces):
        sigs.append(_grid_sig(ai, cell, part, has_mask))
    return sigs


def _grid_sig(ai, cell, part, has_mask):
    try:
        pts = np.array(ai.FacePoints[cell], dtype=np.float64).reshape(-1, 3)
        nrm = np.array(ai.FaceNormals[cell], dtype=np.float64).reshape(-1, 3)
        if has_mask:
            mask = np.array(ai.FaceMask[cell], dtype=np.float64).reshape(-1)
            valid = mask > 0
        else:
            valid = np.ones(len(pts), dtype=bool)
    except Exception:
        return {"type": "OTHER", "point": None}
    P = pts[valid]
    Nn = nrm[valid]
    if len(P) < 3:
        try:
            cen = part.face_centroid(cell)
        except Exception:
            cen = None
        return {"type": "OTHER", "point": cen}
    cen = P.mean(axis=0)
    # 平面：法向方差小
    nvar = float(np.linalg.norm(Nn - Nn.mean(axis=0)))
    if nvar < 0.5:
        n = Nn.mean(axis=0)
        n = n / np.linalg.norm(n)
        return {"type": "PLANE", "normal": tuple(n), "point": tuple(cen)}
    # 圆柱：法向 SVD 最小奇异值远小于最大
    try:
        _, S, Vt = np.linalg.svd(Nn - Nn.mean(axis=0), full_matrices=False)
    except Exception:
        return {"type": "OTHER", "point": tuple(cen)}
    if len(S) >= 3 and S[0] > 1e-6 and S[-1] < 0.3 * S[0]:
        axis = Vt[-1]
        axis = axis / np.linalg.norm(axis)
        proj = P - np.outer(P @ axis, axis)          # 投影到 ⊥轴 平面
        center = proj.mean(axis=0)                    # 圆心（在轴上）
        r = float(np.mean(np.linalg.norm(proj - center, axis=1)))
        return {"type": "CYL", "axis": tuple(axis), "radius": r, "point": tuple(center)}
    return {"type": "OTHER", "point": tuple(cen)}


def _uv_point(doc, obj, cell, u, v):
    pt = doc.GetFacePointFromUV(obj, cell, u, v)
    return (pt.X, pt.Y, pt.Z)


def _uv_vec(doc, obj, cell, u, v):
    v = doc.GetNormalByUV(obj, cell, u, v)
    return (v.X, v.Y, v.Z)


# ============================================================
# 匹配：按类型分组，组内按签名值匹配，验证双射
# ============================================================
def register(step_sigs, ncti_sigs):
    """返回 (mapping, diag): mapping dict step_idx -> ncti_idx（干净双射）或 None。
       diag: {'n_step','n_ncti','matched','unmatched_step','unmatched_ncti','by_type'}"""
    if len(step_sigs) != len(ncti_sigs):
        return None, {"err": "面数不等 ({} vs {})".format(len(step_sigs), len(ncti_sigs))}

    def key_of(sig):
        t = sig["type"]
        if t == "PLANE" and sig.get("normal"):
            n = _canon(sig["normal"])
            d = float(np.dot(n, np.array(sig["point"], dtype=np.float64)))
            return ("PLANE", _round_vec(n, 2), round(d, 1))
        if t == "CYL" and sig.get("axis") and sig.get("radius") is not None:
            a = _canon(sig["axis"])
            # 只按 (轴, 半径) 配；共轴同半径碰撞（罕见）交给组内质心（两侧轴向顺序一致）
            return ("CYL", _round_vec(a, 2), round(float(sig["radius"]), 1))
        # OTHER：用质心
        pt = sig.get("point")
        if pt:
            return ("OTHER", _round_vec(pt, 1))
        return ("UNPARSED",)

    # 按 key 分组（两侧）
    sk = {}
    for i, s in enumerate(step_sigs):
        sk.setdefault(key_of(s), []).append(i)
    nk = {}
    for j, s in enumerate(ncti_sigs):
        nk.setdefault(key_of(s), []).append(j)

    mapping = {}
    used_n = set()
    unmatched_s, unmatched_n = [], []
    by_type = {}
    for key, s_ids in sk.items():
        n_ids = nk.get(key, [])
        by_type.setdefault(key[0], [0, 0])
        by_type[key[0]][0] += len(s_ids)
        by_type[key[0]][1] += len(n_ids)
        if len(s_ids) == 1 and len(n_ids) == 1:
            mapping[s_ids[0]] = n_ids[0]
            used_n.add(n_ids[0])
        elif len(s_ids) >= 1 and len(n_ids) >= 1:
            # 同 key 多面（共面/共轴碰撞）：组内按质心就近贪心配
            _match_by_centroid(s_ids, n_ids, step_sigs, ncti_sigs,
                               mapping, used_n, unmatched_s, unmatched_n)
        else:
            unmatched_s.extend(s_ids)
            unmatched_n.extend(n_ids)

    # 跨类型兜底：主签名没配上的（类型分歧面），全局按质心就近贪心配
    rem_s = [i for i in range(len(step_sigs)) if i not in mapping]
    rem_n = [j for j in range(len(ncti_sigs)) if j not in used_n]
    _match_by_centroid(rem_s, rem_n, step_sigs, ncti_sigs,
                       mapping, used_n, unmatched_s, unmatched_n)

    diag = {
        "n_step": len(step_sigs), "n_ncti": len(ncti_sigs),
        "matched": len(mapping),
        "unmatched_step": len([i for i in range(len(step_sigs)) if i not in mapping]),
        "by_type": by_type,
    }
    if len(mapping) == len(step_sigs):
        return mapping, diag
    return None, diag


def _match_by_centroid(s_ids, n_ids, step_sigs, ncti_sigs,
                       mapping, used_n, unmatched_s, unmatched_n):
    """组内/兜底：按面质心就近贪心 1:1 配对（写回 mapping/used_n）。"""
    sp = [_centroid(step_sigs[i]) for i in s_ids]
    np_ = [_centroid(ncti_sigs[j]) for j in n_ids]
    avail = list(range(len(n_ids)))
    for si, i in enumerate(s_ids):
        if not avail:
            unmatched_s.append(i)
            continue
        # 找最近可用 NCTI 面
        best_k = min(avail, key=lambda k: _dist(sp[si], np_[k]))
        if _dist(sp[si], np_[best_k]) <= TOL_CEN_GLOB:
            mapping[i] = n_ids[best_k]
            used_n.add(n_ids[best_k])
            avail.remove(best_k)
        else:
            unmatched_s.append(i)
    for k in avail:
        unmatched_n.append(n_ids[k])


def _centroid(sig):
    p = sig.get("point")
    return np.array(p, dtype=np.float64) if p is not None else np.zeros(3)


def _dist(a, b):
    return float(np.linalg.norm(a - b))


# ============================================================
# 测试入口：田一冰多特征测双射成功率
# ============================================================
def main():
    # PROJECT_ROOT 需要是含 config/config_load.py 的项目根
    from ._env import get_project_root
    _project_root = get_project_root()
    if _project_root is None:
        _project_root = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "YHCADSmartCleaner")
    S = sys.argv[1] if len(sys.argv) > 1 else \
        "/mnt/data/geometry_data/steps/step_files_tyb/田一冰_countersunk_v18"
    nmax = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    ncti = init_ncti_safe(_project_root)
    import glob
    files = sorted(glob.glob(os.path.join(S, "*.stp")))[:nmax]
    n_clean = 0
    n_face_clean = 0
    n_face_tot = 0
    type_counts = {}
    fails = []
    for fp in files:
        name = os.path.splitext(os.path.basename(fp))[0]
        try:
            step_sigs = parse_step_face_signatures(fp)
            part, doc = load_part(fp, ncti)
            ncti_sigs = ncti_face_signatures(part, doc)
            doc.Clear()
            mapping, diag = register(step_sigs, ncti_sigs)
        except Exception as ex:
            fails.append((name, "EXC:" + str(ex)[:40]))
            continue
        n_face_tot += len(step_sigs)
        for t, (s, n) in diag.get("by_type", {}).items():
            type_counts.setdefault(t, [0, 0])
            type_counts[t][0] += s
            type_counts[t][1] += n
        if mapping is not None:
            n_clean += 1
            n_face_clean += len(mapping)
        else:
            fails.append((name, "match {}/{}".format(diag.get("matched", 0), diag.get("n_step", 0))))
    n = len(files)
    print("=" * 60)
    print("面配准双射成功率（田一冰）: {}/{} 文件 = {:.1%}".format(
        n_clean, n, n_clean / max(1, n)))
    print("面级干净双射: {}/{} = {:.1%}".format(
        n_face_clean, n_face_tot, n_face_clean / max(1, n_face_tot)))
    print("\n按面类型（STEP侧 / NCTI侧 计数）：")
    for t in sorted(type_counts):
        s, c = type_counts[t]
        print("  {:<8} STEP侧 {:>7}  NCTI侧 {:>7}".format(t, s, c))
    if fails:
        print("\n失败/部分文件（前15）：")
        for nm, why in fails[:15]:
            print("  {} : {}".format(nm, why))
    print("=" * 60)


if __name__ == "__main__":
    main()
