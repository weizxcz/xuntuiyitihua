#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""边特征提取器（featurefox-NCTI 版核心）。

对每个"面-面"共享边，提取 30 维几何/拓扑特征，用于训练 XGBoost 边分类器。
特征定义与 featurefox(STEP版).edge_features.FEATURE_NAMES 完全一致（顺序/符号约定不变），
仅数据来源从 StepParser 换成 NCTI 原生（NctiPart）：
  - 凸凹性：NCTI EdgeAttr[0/1/2] 直接给（STEP 版靠质心偏移法反推）
  - 面积：FaceAttr[5]；边长：EdgeAttr[3]；边类型：EdgeAttr[9/4]
  - 法向/重心：GetNormalByUV/GetFacePointFromUV at UV(0.5,0.5)

输出边 fa/fb 均为 cell_id（ai.FaceID 位置索引），与 Geo-Rec 训练标签零映射对齐。

特征设计参考:
    - FeatureFox (Fuchs et al., 2026, arXiv:2604.26770): 二面角、凹凸性、面积/周长比、
      归一化长度、面质心距离
    - gAAG/AAGNet (2024): 面类型、边类型、边长度、凸凹性
    - Joshi & Chang (1988): AAG 边凸凹性是特征识别的基础属性
"""

import math
import os
import sys

UTILS_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if UTILS_DIR not in sys.path:
    sys.path.insert(0, UTILS_DIR)

TS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TS_DIR not in sys.path:
    sys.path.insert(0, TS_DIR)

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from geom_helpers import _dot, _vec_len, _angle_between_normals  # noqa: E402
from ncti_backend import NctiFaceAttrs  # noqa: E402

# ── 特征名（固定顺序，与 STEP 版完全一致，与 _edge_feature_vector 输出对齐）──
FEATURE_NAMES = [
    # ── 边凸凹性（连续 + one-hot）──
    "dihedral_sign",          # 连续凸凹符号值（+1=强凹，-1=强凸，0=光滑）
    "abs_dihedral",           # |dihedral_sign|，凹凸强度
    "is_concave",             # one-hot: 凹边
    "is_convex",              # one-hot: 凸边
    "is_smooth",              # one-hot: 光滑边
    "is_conv_unknown",        # one-hot: 未知（无共享边/退化）
    # ── 边几何 ──
    "edge_length",            # 绝对边长度
    "edge_length_norm",       # 归一化（/ 零件总周长）
    "edge_is_line",           # one-hot: 直线边
    "edge_is_circle",         # one-hot: 圆弧边
    "edge_is_other",          # one-hot: 其他类型
    # ── 面面积 ──
    "face_a_area",            # 面 A 面积
    "face_b_area",            # 面 B 面积
    "area_ratio",             # min/max 面积比
    "log_area_ratio",         # log(min/max+eps)
    # ── 面周长 ──
    "face_a_perim",           # 面 A 周长
    "face_b_perim",           # 面 B 周长
    "perim_ratio",            # min/max 周长比
    # ── 面间几何关系 ──
    "centroid_dist",          # 两面重心距离
    "normal_angle_deg",       # 法向量夹角（acute, 0-90）
    "normal_dot",             # 法向量点积（signed, -1~+1，负=反平行）
    # ── 面类型 one-hot + 组合 ──
    "face_a_is_plane",
    "face_a_is_cyl",
    "face_a_is_other",
    "face_b_is_plane",
    "face_b_is_cyl",
    "face_b_is_other",
    "both_plane",             # 交互项：两面都平面
    "plane_cyl",              # 交互项：一平面一圆柱
    "both_cyl",               # 交互项：两面都圆柱
]


# =============================================================================
# 边特征向量构建
# =============================================================================

def _type_flags(ftype):
    """面类型 → one-hot [is_plane, is_cyl, is_other]。"""
    if ftype == "PLANE":
        return (1.0, 0.0, 0.0)
    elif ftype == "CYL":
        return (0.0, 1.0, 0.0)
    return (0.0, 0.0, 1.0)


def build_face_graph(part):
    """构建带属性的面邻接图（NCTI 版）。

    参数:
        part: NctiPart —— 一个零件的 NCTI 数据视图。

    返回:
        edges: list of dict，每个元素描述一条共享边:
            {fa, fb, key, features: [float, ...]}
            fa/fb/key 均为 cell_id（ai.FaceID 位置索引，与 Geo-Rec 训练标签零映射对齐）。
        fa_attrs: NctiFaceAttrs 缓存
    """
    fa_attrs = NctiFaceAttrs(part)

    # 收集所有共享边（每对相邻面一条，key 去重）
    seen_pairs = set()
    edges = []
    for fa in range(part.n_faces):
        for fb in part.adjacency.get(fa, set()):
            key = (min(fa, fb), max(fa, fb))
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            edges.append({"fa": key[0], "fb": key[1], "key": key})

    # 计算每条边的特征
    total_perim = fa_attrs.total_perimeter()
    for e in edges:
        e["features"] = _edge_feature_vector(part, fa_attrs, total_perim, e)

    return edges, fa_attrs


def _edge_feature_vector(part, fa_attrs, total_perim, e):
    """计算单条边的 30 维特征向量（与 FEATURE_NAMES 顺序一致，与 STEP 版同公式）。

    数据来源全部为 NctiPart（凸凹性/边长/类型从 edge_*_map 取；
    面积/重心/法向/类型/周长从 NctiFaceAttrs 取）。
    """
    fa, fb = e["fa"], e["fb"]
    key = e["key"]

    # ── 凸凹性 ──
    conv_label = part.edge_convexity.get(key, "unknown")
    dih_sign = part.edge_dihedral.get(key, 0.0)
    is_concave = 1.0 if conv_label == "concave" else 0.0
    is_convex = 1.0 if conv_label == "convex" else 0.0
    is_smooth = 1.0 if conv_label == "smooth" else 0.0
    is_unknown = 1.0 if conv_label == "unknown" else 0.0

    # ── 边几何 ──
    elen = part.edge_length_map.get(key, 0.0)
    elen_norm = elen / total_perim if total_perim > 0 else 0.0
    ctype = part.edge_type.get(key, "other")
    e_is_line = 1.0 if ctype == "line" else 0.0
    e_is_circle = 1.0 if ctype == "circle" else 0.0
    e_is_other = 1.0 if ctype not in ("line", "circle") else 0.0

    # ── 面面积 ──
    a_area = fa_attrs.area(fa)
    b_area = fa_attrs.area(fb)
    if a_area > 1e-12 and b_area > 1e-12:
        area_ratio = min(a_area, b_area) / max(a_area, b_area)
    else:
        area_ratio = 0.0
    log_area_ratio = math.log(area_ratio + 1e-6) if area_ratio > 0 else math.log(1e-6)

    # ── 面周长 ──
    a_perim = fa_attrs.perimeter(fa)
    b_perim = fa_attrs.perimeter(fb)
    if a_perim > 1e-12 and b_perim > 1e-12:
        perim_ratio = min(a_perim, b_perim) / max(a_perim, b_perim)
    else:
        perim_ratio = 0.0

    # ── 面间几何 ──
    ca = fa_attrs.centroid(fa)
    cb = fa_attrs.centroid(fb)
    if ca is not None and cb is not None:
        centroid_dist = math.sqrt(sum((ca[k] - cb[k]) ** 2 for k in range(3)))
    else:
        centroid_dist = 0.0
    na = fa_attrs.normal(fa)
    nb = fa_attrs.normal(fb)
    if na is not None and nb is not None:
        normal_angle = _angle_between_normals(na, nb)
        normal_dot = _dot(na, nb)
    else:
        normal_angle = 90.0
        normal_dot = 0.0

    # ── 面类型 ──
    a_flags = _type_flags(fa_attrs.ftype(fa))
    b_flags = _type_flags(fa_attrs.ftype(fb))
    fa_type = fa_attrs.ftype(fa)
    fb_type = fa_attrs.ftype(fb)
    both_plane = 1.0 if (fa_type == "PLANE" and fb_type == "PLANE") else 0.0
    plane_cyl = 1.0 if {fa_type, fb_type} == {"PLANE", "CYL"} else 0.0
    both_cyl = 1.0 if (fa_type == "CYL" and fb_type == "CYL") else 0.0

    return [
        dih_sign,
        abs(dih_sign),
        is_concave,
        is_convex,
        is_smooth,
        is_unknown,
        elen,
        elen_norm,
        e_is_line,
        e_is_circle,
        e_is_other,
        a_area,
        b_area,
        area_ratio,
        log_area_ratio,
        a_perim,
        b_perim,
        perim_ratio,
        centroid_dist,
        normal_angle,
        normal_dot,
        a_flags[0], a_flags[1], a_flags[2],
        b_flags[0], b_flags[1], b_flags[2],
        both_plane,
        plane_cyl,
        both_cyl,
    ]
