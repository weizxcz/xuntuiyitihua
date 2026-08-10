#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""边特征提取器（FeatureFox 路线的核心）。

对每个"面-面"共享边，提取一组几何/拓扑特征，用于训练 XGBoost 边分类器。

特征设计参考:
    - FeatureFox (2025): 二面角、凹凸性、面积/周长比、归一化长度、面质心距离
    - gAAG/AAGNet (2024): 面类型、边类型、边长度、凸凹性
    - Joshi & Chang (1988): AAG 边凸凹性是特征识别的基础属性

实现复用 detect_through_step.py 的几何辅助函数（法向量、重心、面积、凸凹性），
新增：边长度计算（LINE / CIRCLE）、面周长、面类型组合特征。
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

from detect_blind_holes_and_export_stp_v15_22 import StepParser  # noqa: E402
from geom_helpers import _dot, _vec_len, _angle_between_normals  # noqa: E402
import detect_through_step as dts  # noqa: E402

# ── 特征名（固定顺序，与 build_edge_dataset 输出对齐）──
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
# 边长度计算（StepParser 不直接提供，需从几何实体推导）
# =============================================================================

def _unwrap_curve_entity(parser, ec_id):
    """解开 SURFACE_CURVE 包装，返回底层几何实体 id（LINE/CIRCLE/...）。"""
    edge = parser.edge_curves.get(ec_id)
    if not edge:
        return None
    curve_ref = edge.get("curve")
    ent = parser.entities.get(curve_ref, {})
    if ent.get("type") == "SURFACE_CURVE":
        refs = parser._refs(ent.get("params", ""))
        return refs[0] if refs else curve_ref
    return curve_ref


def _circle_radius_center(parser, ec_id):
    """返回 CIRCLE 边的 (radius, center_xyz)，非 CIRCLE 返回 (None, None)。"""
    cid = _unwrap_curve_entity(parser, ec_id)
    if cid is None:
        return None, None
    ent = parser.entities.get(cid, {})
    if ent.get("type") != "CIRCLE":
        return None, None
    refs = parser._refs(ent.get("params", ""))
    if not refs:
        return None, None
    parts = parser._split_top_level(ent.get("params", ""))
    radius = parser._to_float(parts[2]) if len(parts) >= 3 else None
    axis = parser.axis2.get(refs[0], {})
    center = parser.points.get(axis.get("point_ref"))
    return radius, center


def edge_length(parser, ec_id):
    """计算边的长度。LINE: 端点距离；CIRCLE: 弧长；其他: 端点距离近似。"""
    ctype = parser.edge_base_curve_type(ec_id)
    pts = parser.edge_vertices_xyz(ec_id)
    if len(pts) < 2:
        return 0.0

    if ctype == "CIRCLE":
        radius, _ = _circle_radius_center(parser, ec_id)
        if radius is not None and radius > 1e-12:
            a, b = pts[0], pts[1]
            chord = math.sqrt(sum((a[k] - b[k]) ** 2 for k in range(3)))
            if chord < 1e-9:
                return 2.0 * math.pi * radius  # 闭合整圆（圆柱接缝边）
            s = max(-1.0, min(1.0, chord / (2.0 * radius)))
            theta = 2.0 * math.asin(s)
            return radius * theta  # 小弧长（StepParser 无 TRIMMED_CURVE 范围，取小弧）

    # LINE 或其他：端点直线距离
    a, b = pts[0], pts[1]
    return math.sqrt(sum((a[k] - b[k]) ** 2 for k in range(3)))


# =============================================================================
# 面属性缓存（每个 parser 计算一次）
# =============================================================================

class FaceAttrs:
    """缓存一个零件所有面的几何属性，避免重复计算。"""

    def __init__(self, parser):
        self.parser = parser
        self._area = {}
        self._perim = {}
        self._centroid = {}
        self._normal = {}
        self._ftype = {}
        self._total_perim = None

    def area(self, fid):
        if fid not in self._area:
            n = self.normal(fid)
            self._area[fid] = dts._face_area_approx(self.parser, fid, n)
        return self._area[fid]

    def centroid(self, fid):
        if fid not in self._centroid:
            self._centroid[fid] = dts._face_centroid(self.parser, fid)
        return self._centroid[fid]

    def normal(self, fid):
        if fid not in self._normal:
            stype = self.parser.face_surface_type(fid)
            if stype == "PLANE":
                self._normal[fid] = dts._face_normal_effective(self.parser, fid)
            elif stype == "CYLINDRICAL_SURFACE":
                # 圆柱面法向量位置相关，这里用重心处法向量作为代表
                c = self.centroid(fid)
                if c is not None:
                    self._normal[fid] = dts._cyl_surface_normal_at_point(self.parser, fid, c)
                else:
                    self._normal[fid] = None
            else:
                self._normal[fid] = dts._face_normal_effective(self.parser, fid)
        return self._normal[fid]

    def ftype(self, fid):
        """面类型简化为 3 类: PLANE / CYL / OTHER。"""
        if fid not in self._ftype:
            stype = self.parser.face_surface_type(fid)
            if stype == "PLANE":
                self._ftype[fid] = "PLANE"
            elif stype == "CYLINDRICAL_SURFACE":
                self._ftype[fid] = "CYL"
            else:
                self._ftype[fid] = "OTHER"
        return self._ftype[fid]

    def perimeter(self, fid):
        if fid not in self._perim:
            total = 0.0
            for ec_id in self.parser.face_to_edge_curves.get(fid, set()):
                total += edge_length(self.parser, ec_id)
            self._perim[fid] = total
        return self._perim[fid]

    def total_perimeter(self):
        if self._total_perim is None:
            seen_ec = set()
            total = 0.0
            for fid in self.parser.advanced_faces:
                for ec_id in self.parser.face_to_edge_curves.get(fid, set()):
                    if ec_id not in seen_ec:
                        seen_ec.add(ec_id)
                        total += edge_length(self.parser, ec_id)
            self._total_perim = total if total > 1e-12 else 1.0
        return self._total_perim


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


def build_face_graph(parser):
    """构建带属性的面邻接图。

    返回:
        edges: list of dict, 每个元素描述一条共享边:
            {fa, fb, ec_id, features: [float, ...]}
        fa_attrs: FaceAttrs 缓存
        edge_convexity: dict (min_fid,max_fid) -> (label, sign)
    """
    fa_attrs = FaceAttrs(parser)
    # 用 detect_through_step 的凸凹性函数（已含 same_sense 修正）
    all_face_ids = list(parser.advanced_faces.keys())
    convexity_map, dihedral_map = dts._build_edge_convexity_map(parser, all_face_ids)

    # 收集所有共享边（每对相邻面）
    seen_pairs = set()
    edges = []
    for fid in all_face_ids:
        for ec_id in parser.face_to_edge_curves.get(fid, set()):
            for other_fid in parser.edge_curve_to_faces.get(ec_id, set()):
                if other_fid == fid:
                    continue
                key = (min(fid, other_fid), max(fid, other_fid))
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                edges.append({
                    "fa": key[0],
                    "fb": key[1],
                    "ec_id": ec_id,
                })

    # 计算每条边的特征
    total_perim = fa_attrs.total_perimeter()
    for e in edges:
        e["features"] = _edge_feature_vector(
            parser, fa_attrs, convexity_map, dihedral_map, total_perim, e)

    return edges, fa_attrs


def _edge_feature_vector(parser, fa_attrs, convexity_map, dihedral_map,
                         total_perim, e):
    """计算单条边的特征向量（与 FEATURE_NAMES 顺序一致）。"""
    fa, fb = e["fa"], e["fb"]
    ec_id = e["ec_id"]
    key = (min(fa, fb), max(fa, fb))

    # ── 凸凹性 ──
    conv_label = convexity_map.get(key, "unknown")
    dih_sign = dihedral_map.get(key, 0.0)
    is_concave = 1.0 if conv_label == "concave" else 0.0
    is_convex = 1.0 if conv_label == "convex" else 0.0
    is_smooth = 1.0 if conv_label == "smooth" else 0.0
    is_unknown = 1.0 if conv_label == "unknown" else 0.0

    # ── 边几何 ──
    elen = edge_length(parser, ec_id)
    elen_norm = elen / total_perim if total_perim > 0 else 0.0
    ctype = parser.edge_base_curve_type(ec_id)
    e_is_line = 1.0 if ctype == "LINE" else 0.0
    e_is_circle = 1.0 if ctype == "CIRCLE" else 0.0
    e_is_other = 1.0 if ctype not in ("LINE", "CIRCLE") else 0.0

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
