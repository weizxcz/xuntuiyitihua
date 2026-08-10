#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""实例级特征提取 + 训练数据生成（第二级分类器：真通槽 vs 同类非通槽）。

featurefox-NCTI 版：与 STEP 版的差异仅数据来源 —— extract_instance_features
接收 NctiPart（cell_id 空间），邻接判断用 part.adjacency，凸凹性来自 part.edge_convexity。
26 维 INSTANCE_FEATURE_NAMES 定义与 STEP 版完全一致。

动机：
    边分类器（FeatureFox 第一级）把"看起来像通槽内部"的边连成实例，
    但 seg=22 等其它穿透型特征在边级别几何上与通槽同构，边分类器分不开。
    72% 的 FP 面来自这种整组 seg≠9 的误检实例。

设计：
    标签直接来自 inst 矩阵的真实特征实例分组：
        y=1（正）：该实例的 seg == 9（真通槽）
        y=0（负）：该实例的 seg != 9 且 != 0（其它制造特征，如 seg=22）
    正负样本都是"真实特征实例"，保证模型学的是语义（是不是通槽）而非
    模仿第一级边分类器的错误。
"""

import os
import sys

UTILS_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if UTILS_DIR not in sys.path:
    sys.path.insert(0, UTILS_DIR)
TS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TS_DIR not in sys.path:
    sys.path.insert(0, TS_DIR)

from geom_helpers import _angle_between_normals  # noqa: E402


INSTANCE_FEATURE_NAMES = [
    # ── 规模 ──
    "n_faces",
    "n_edges_internal",       # 实例内部共享边数
    "faces_per_edge",         # n_faces / n_edges
    # ── 面类型构成 ──
    "n_plane", "n_cyl", "n_other",
    "plane_ratio",            # 平面占比
    "has_cyl_wall",           # 是否含圆柱面（混合通槽信号）
    # ── 面积 ──
    "area_total",
    "area_min", "area_max",
    "area_mean", "area_std",
    "area_ratio_minmax",      # min/max 面积比（通槽底面/壁面面积有特定比例）
    "area_bottom_ratio",      # 最小面（疑似底面）/ 总面积
    # ── 周长 ──
    "perim_total",
    "perim_mean",
    "perim_ratio_minmax",
    # ── 凹凸边构成（实例内部边）──
    "concave_edge_ratio",     # 凹边占比（通槽内部以凹边为主）
    "convex_edge_ratio",
    "smooth_edge_ratio",
    # ── 底面/壁面结构 ──
    "n_perp_walls",           # 与某平面近似垂直的其它平面数（通槽≥2）
    "has_bottom_wall_split",  # 存在 1 底 + ≥2 垂直壁 的划分
    "bottom_perp_count_mean", # 底面-壁面垂直对数均值
    # ── 实例平均边概率（第一级模型对该实例的置信度）──
    "edge_prob_mean",
    "edge_prob_min",
]

PERP_MIN, PERP_MAX = 75.0, 105.0


def _instance_groups_from_inst(inst_matrix):
    """从 inst 矩阵提取真实特征实例分组（连通分量）。

    返回 list[set[int]]，每个 set 是同属一个实例的 cell_id 集合。
    """
    if not inst_matrix:
        return []
    n = len(inst_matrix)
    visited = [False] * n
    groups = []
    for start in range(n):
        if visited[start]:
            continue
        # 跳过孤立面（inst[start] 全 0）
        row = inst_matrix[start]
        if not any(row):
            visited[start] = True
            continue
        stack = [start]
        group = set()
        while stack:
            i = stack.pop()
            if visited[i]:
                continue
            visited[i] = True
            group.add(i)
            for j in range(n):
                if not visited[j] and (inst_matrix[i][j] or inst_matrix[j][i]):
                    stack.append(j)
        if len(group) >= 2:
            groups.append(group)
    return groups


def extract_instance_features(part, fa_attrs, convexity_map, cell_ids, edge_probs=None):
    """为一个实例提取 26 维特征向量（NCTI 版，cell_id 空间）。

    参数:
        part: NctiPart
        fa_attrs: NctiFaceAttrs
        convexity_map: dict (min_cell,max_cell) -> concave/convex/smooth（来自 part.edge_convexity）
        cell_ids: set[int]，实例包含的 cell_id（= 面位置索引，零映射）
        edge_probs: 可选，dict (min_cell,max_cell) -> 第一级边概率，用于置信度特征
    """
    faces = [c for c in cell_ids if c is not None]
    if not faces:
        return [0.0] * len(INSTANCE_FEATURE_NAMES)
    face_set = set(faces)

    # 面属性
    areas = [fa_attrs.area(f) or 0.0 for f in faces]
    perims = [fa_attrs.perimeter(f) or 0.0 for f in faces]
    ftypes = [fa_attrs.ftype(f) for f in faces]
    normals = {f: fa_attrs.normal(f) for f in faces}

    n_faces = len(faces)
    n_plane = sum(1 for t in ftypes if t == "PLANE")
    n_cyl = sum(1 for t in ftypes if t == "CYL")
    n_other = n_faces - n_plane - n_cyl
    plane_ratio = n_plane / n_faces

    # 实例内部边（NCTI cell_id 邻接判断）
    internal_pairs = []
    convexity_counts = {"concave": 0, "convex": 0, "smooth": 0, "unknown": 0}
    prob_vals = []
    for i in range(n_faces):
        for j in range(i + 1, n_faces):
            fa, fb = faces[i], faces[j]
            # 是否相邻（NCTI cell_id 邻接，共享边）
            if fb not in part.adjacency.get(fa, set()):
                continue
            internal_pairs.append((fa, fb))
            key = (min(fa, fb), max(fa, fb))
            conv = convexity_map.get(key, "unknown")
            convexity_counts[conv] = convexity_counts.get(conv, 0) + 1
            if edge_probs is not None and key in edge_probs:
                prob_vals.append(edge_probs[key])
    n_edges = len(internal_pairs)
    denom = max(1, n_edges)
    concave_ratio = convexity_counts.get("concave", 0) / denom
    convex_ratio = convexity_counts.get("convex", 0) / denom
    smooth_ratio = convexity_counts.get("smooth", 0) / denom

    # 面积统计
    area_total = sum(areas)
    area_min = min(areas) if areas else 0.0
    area_max = max(areas) if areas else 0.0
    area_mean = area_total / n_faces
    area_std = (sum((a - area_mean) ** 2 for a in areas) / n_faces) ** 0.5
    area_ratio_minmax = (area_min / area_max) if area_max > 1e-12 else 0.0
    area_bottom_ratio = (area_min / area_total) if area_total > 1e-12 else 0.0

    # 周长统计
    perim_total = sum(perims)
    perim_mean = perim_total / n_faces
    perim_min = min(perims) if perims else 0.0
    perim_max = max(perims) if perims else 0.0
    perim_ratio_minmax = (perim_min / perim_max) if perim_max > 1e-12 else 0.0

    # 底面/壁面结构：对每个平面底面，统计与之近似垂直的其它平面
    plane_faces = [f for f in faces if ftypes[faces.index(f)] == "PLANE"]
    best_perp = 0
    has_split = 0
    perp_counts = []
    for bottom in plane_faces:
        nb = normals.get(bottom)
        if nb is None:
            continue
        cnt = 0
        for other in plane_faces:
            if other == bottom:
                continue
            no = normals.get(other)
            if no is None:
                continue
            if PERP_MIN <= _angle_between_normals(nb, no) <= PERP_MAX:
                cnt += 1
        perp_counts.append(cnt)
        if cnt >= 2:
            has_split = 1
        best_perp = max(best_perp, cnt)
    bottom_perp_mean = (sum(perp_counts) / len(perp_counts)) if perp_counts else 0.0

    # 边概率
    prob_mean = (sum(prob_vals) / len(prob_vals)) if prob_vals else 0.0
    prob_min = min(prob_vals) if prob_vals else 0.0

    feats = [
        float(n_faces),
        float(n_edges),
        n_faces / max(1, n_edges),
        float(n_plane), float(n_cyl), float(n_other),
        plane_ratio,
        1.0 if n_cyl > 0 else 0.0,
        area_total, area_min, area_max, area_mean, area_std,
        area_ratio_minmax, area_bottom_ratio,
        perim_total, perim_mean, perim_ratio_minmax,
        concave_ratio, convex_ratio, smooth_ratio,
        float(best_perp),
        float(has_split),
        bottom_perp_mean,
        prob_mean, prob_min,
    ]
    return feats
