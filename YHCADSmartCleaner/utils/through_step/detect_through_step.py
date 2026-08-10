#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
双侧通槽台阶 (2-sided through step) STEP 几何识别器。

纯 STEP 拓扑/几何识别，不依赖标注标签。
输出识别到的 STEP face_id 列表，供上层高亮使用。

策略：宽松硬过滤 + 多维评分排序，兼顾召回率和精确率。

标签 cell_id 空间（build_training_json / CLI -o）:
  - 默认（且 NCTI 可用）: cell_id = NCTI ai.FaceID 位置索引，与 Geo-Rec 训练图严格对齐。
    识别在 STEP face_id 空间完成后，用 ncti_faceid_map 把 STEP face_id → ai.FaceID 位置
    索引（几何最近邻 + 自适应容差），seg/inst/bottom 按此空间写出。
  - NCTI 不可用（或 --no-ncti）: 退化为 STEP advanced_faces 排序下标。
    ⚠ 该空间【不】与 Geo-Rec 训练标签对齐，仅用于无 NCTI 环境下的调试/高亮，
    切勿直接用于训练。--require-ncti 可强制要求 NCTI（缺失则报错退出，不写错误标签）。
  详见 ncti_faceid_map.py 模块头注释（GetFaceMidPoint 语义、导入「约定 A」、cell_id 定义）。

运行指令：
    python detect_through_step.py STP文件路径 [-o 输出目录] [--seg-id 9]
        [--require-ncti | --no-ncti]
"""

import argparse
import json
import math
import os
import sys
from collections import defaultdict
from itertools import combinations

# 复用项目内的 StepParser
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))                 # .../utils/through_step
UTILS_DIR = os.path.dirname(_THIS_DIR)                                 # .../utils
PROJECT_ROOT = os.path.dirname(UTILS_DIR)                              # YHCADSmartCleaner 根（含 config/）
for _p in (_THIS_DIR, UTILS_DIR, PROJECT_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from detect_blind_holes_and_export_stp_v15_22 import StepParser  # noqa: E402
try:
    from .geom_helpers import _dot, _angle_between_normals, _vec_len, _project_to_plane  # noqa: E402
except ImportError:
    from geom_helpers import _dot, _angle_between_normals, _vec_len, _project_to_plane  # noqa: E402

# NCTI 对齐映射（延迟使用，不在 import 期触发 NCTI 加载）
try:
    from .featurefox.ncti_faceid_map import build_pos_map_for_step  # noqa: E402
except ImportError:
    from featurefox.ncti_faceid_map import build_pos_map_for_step  # noqa: E402


# =============================================================================
# 阈值常量
# =============================================================================
PERP_MIN = 75.0
PERP_MAX = 105.0

MIN_INSTANCE_FACES = 3
MAX_INSTANCE_FACES = 6

# 硬过滤：重心投影参数（排除明显不在侧壁之间的底面）
CENTROID_T_MIN = -0.2
CENTROID_T_MAX = 1.2

# 面积阈值
MIN_FACE_AREA = 0.01
WALL_AREA_RATIO_MAX = 15.0     # 侧壁/底面面积比上限
BOTTOM_WALL_RATIO_MIN = 0.5    # 底面/侧壁平均面积比下限（通槽底面不应太小）
WALL_ANGLE_MAX = 80.0          # 侧壁夹角上限（>80° 为拐角，非通槽）
WALL_AREA_SYMMETRY_MIN = 0.3   # 侧壁面积比下限（min/max，通槽侧壁应大致对称）
BOTTOM_FREE_EDGES_MIN = 1     # 通槽底面至少有 N 条边不与侧壁共享（开放端标志）

# 过渡面（圆角）验证
FILLET_AXIS_ALIGN_MIN = 75.0

# 边凸凹性计算阈值（归一化余弦值）
CONVEXITY_THRESHOLD = 0.02  # |sign| ≤ 此值 → smooth；> → concave；< → convex

# 最低评分阈值（低于此分数的候选直接丢弃）
MIN_SCORE = 45.0
MIN_HYBRID_SCORE = 45.0           # 矩形通槽（trio/extended）评分阈值（与原 MIN_SCORE 一致）
MIN_MIXED_SCORE_STEP = 76.0       # 混合 trio 评分阈值（启用：已有凸凹性过滤）
# 注：底面邻接面过滤（BOTTOM_NEIGHBOR_HARD_MAX）不适用于 STEP 版，
# 因为 STEP 版的 adjacency 只包含候选面之间的邻接，不是全部面。


# =============================================================================
# STEP 专用几何辅助函数
# =============================================================================

def _face_normal(parser, face_id):
    """从 StepParser 提取 PLANE 面的法向量。"""
    sid = parser.face_surface_id(face_id)
    if sid is None:
        return None
    surf = parser.surfaces.get(sid)
    if not surf or surf.get("type") != "PLANE":
        return None
    axis_ref = surf.get("axis_ref")
    if axis_ref is None:
        return None
    axis_info = parser.axis2.get(axis_ref)
    if axis_info is None:
        return None
    if isinstance(axis_info, dict):
        dir_ref = axis_info.get("axis_ref")
    else:
        dir_ref = axis_info
    if dir_ref is None:
        return None
    return parser.directions.get(dir_ref)


def _face_centroid(parser, face_id):
    """计算面的重心（顶点坐标平均值）。"""
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
            if point_ref is not None:
                p = parser.points.get(point_ref)
                if p is not None:
                    pts.append(p)
    if not pts:
        return None
    n = len(pts)
    return (sum(p[0] for p in pts) / n,
            sum(p[1] for p in pts) / n,
            sum(p[2] for p in pts) / n)


def _face_vertices(parser, face_id):
    """收集面的所有顶点坐标。"""
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
            if point_ref is not None:
                p = parser.points.get(point_ref)
                if p is not None:
                    pts.append(p)
    return pts


def _face_area_approx(parser, face_id, normal=None):
    """用顶点投影到面平面后的 2D Shoelace 公式近似 PLANE 面面积。"""
    pts = _face_vertices(parser, face_id)
    if len(pts) < 3:
        return 0.0
    if normal is None:
        normal = _face_normal(parser, face_id)
    if normal is None:
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
    pts_2d = [(sum(p[k] * u[k] for k in range(3)),
               sum(p[k] * v[k] for k in range(3))) for p in pts]
    cx = sum(p[0] for p in pts_2d) / len(pts_2d)
    cy = sum(p[1] for p in pts_2d) / len(pts_2d)
    pts_2d.sort(key=lambda p: math.atan2(p[1] - cy, p[0] - cx))
    area = 0.0
    n_pts = len(pts_2d)
    for i in range(n_pts):
        j = (i + 1) % n_pts
        area += pts_2d[i][0] * pts_2d[j][1]
        area -= pts_2d[j][0] * pts_2d[i][1]
    return abs(area) / 2.0


# =============================================================================
# 边凸凹性计算（从 STEP 几何数据推导）
# =============================================================================

def _face_normal_effective(parser, face_id):
    """返回面有效外法向量（考虑 ADVANCED_FACE 的 same_sense 属性）。

    same_sense=True  → 面法向量 = 表面法向量（不翻转）
    same_sense=False → 面法向量 = -表面法向量（翻转）

    对于 STEP B-rep，有效外法向量指向远离实体材料的方向。
    """
    raw = _face_normal(parser, face_id)
    if raw is None:
        return None
    face_data = parser.advanced_faces.get(face_id)
    if face_data is None:
        return raw
    if not face_data.get("same_sense", True):
        return (-raw[0], -raw[1], -raw[2])
    return raw


def _cyl_surface_normal_at_point(parser, face_id, point):
    """计算圆柱面在指定点的有效外法向量。

    圆柱面法向量 = 从轴线投影点到该点的径向方向，再根据 same_sense 修正。
    """
    sid = parser.face_surface_id(face_id)
    if sid is None:
        return None
    axis_info = parser.axis_info(sid)
    if axis_info is None:
        return None
    axis_point = axis_info.get("point")
    axis_dir = axis_info.get("direction")
    if axis_point is None or axis_dir is None:
        return None

    # 将 point 投影到圆柱轴线上
    dp = tuple(point[k] - axis_point[k] for k in range(3))
    t = _dot(dp, axis_dir)
    proj = tuple(axis_point[k] + t * axis_dir[k] for k in range(3))

    # 径向法向量 = point - 轴线投影点
    n = tuple(point[k] - proj[k] for k in range(3))
    n_len = _vec_len(n)
    if n_len < 1e-12:
        return None
    n = tuple(c / n_len for c in n)

    # same_sense 修正
    face_data = parser.advanced_faces.get(face_id)
    if face_data is not None and not face_data.get("same_sense", True):
        n = (-n[0], -n[1], -n[2])
    return n


def _face_normal_at_edge(parser, face_id, edge_midpoint):
    """返回面在边中点处的有效外法向量（统一 PLANE / CYLINDRICAL 接口）。

    PLANE: 法向量恒定（从 _face_normal_effective 获取）。
    CYLINDRICAL_SURFACE: 法向量随位置变化（径向方向，从 _cyl_surface_normal_at_point 获取）。
    """
    stype = parser.face_surface_type(face_id)
    if stype == "PLANE":
        return _face_normal_effective(parser, face_id)
    elif stype == "CYLINDRICAL_SURFACE":
        return _cyl_surface_normal_at_point(parser, face_id, edge_midpoint)
    return None


def _compute_edge_convexity(parser, face_a, face_b):
    """计算两个面之间共享边的凸凹性（质心偏移法）。

    算法：
    1. 找到两面的共享边曲线，收集顶点
    2. 计算边中点 M 和边方向 d
    3. 获取两面在 M 处的有效外法向量
    4. 计算面 A 重心到 M 的向量，去除边方向分量 → v_perp
    5. sign = dot(v_perp, n_B) / |v_perp|
       - sign > threshold → concave（凹边，槽内角）
       - sign < -threshold → convex（凸边，外角）
       - 其他 → smooth

    不依赖 ORIENTED_EDGE 方向（StepParser 未存储），因为
    去除边方向分量时 d 的正负不影响最终结果。

    Returns: (label, sign_value) — label 为 "concave"/"convex"/"smooth"/"unknown"，
             sign_value 为连续值（+1=强凹，-1=强凸，0=光滑/未知），用于评分。
    """
    _UNKNOWN = ("unknown", 0.0)
    # 共享边曲线
    ecs_a = parser.face_to_edge_curves.get(face_a, set())
    ecs_b = parser.face_to_edge_curves.get(face_b, set())
    shared = ecs_a & ecs_b
    if not shared:
        return _UNKNOWN

    # 收集共享边的所有顶点坐标
    vertices = []
    seen = set()
    for ec_id in shared:
        edge = parser.edge_curves.get(ec_id)
        if not edge:
            continue
        for vid in (edge.get("v1"), edge.get("v2")):
            if vid is None or vid in seen:
                continue
            seen.add(vid)
            pt = parser.vertex_xyz(vid)
            if pt is not None:
                vertices.append(pt)

    if len(vertices) < 2:
        return _UNKNOWN

    # 边中点
    n_v = len(vertices)
    M = tuple(sum(v[k] for v in vertices) / n_v for k in range(3))

    # 边方向（正负无所谓，只用于去除沿边分量）
    d = tuple(vertices[-1][k] - vertices[0][k] for k in range(3))
    d_len = _vec_len(d)
    if d_len < 1e-12:
        return _UNKNOWN
    d = tuple(c / d_len for c in d)

    # 两面在边中点处的有效外法向量
    n_a = _face_normal_at_edge(parser, face_a, M)
    n_b = _face_normal_at_edge(parser, face_b, M)
    if n_a is None or n_b is None:
        return _UNKNOWN

    # 面 A 的重心
    c_a = _face_centroid(parser, face_a)
    if c_a is None:
        return _UNKNOWN

    # "深入面 A" 向量（从边中点到面 A 重心），去除边方向分量
    v_into_a = tuple(c_a[k] - M[k] for k in range(3))
    proj = _dot(v_into_a, d)
    v_perp = tuple(v_into_a[k] - proj * d[k] for k in range(3))
    v_perp_len = _vec_len(v_perp)
    if v_perp_len < 1e-12:
        return "smooth", 0.0  # 重心在边线上 → 无法判定，视为平滑

    # 归一化符号判定
    sign = _dot(v_perp, n_b) / v_perp_len

    if sign > CONVEXITY_THRESHOLD:
        return "concave", sign
    elif sign < -CONVEXITY_THRESHOLD:
        return "convex", sign
    else:
        return "smooth", sign


def _build_edge_convexity_map(parser, face_ids):
    """批量构建边凸凹性映射表。

    遍历所有候选面的共享边，对每对相邻面计算凸凹性。
    返回 (convexity, dihedral):
      convexity: dict (min_fid, max_fid) → "concave"/"convex"/"smooth"/"unknown"
      dihedral:  dict (min_fid, max_fid) → float 连续值（+凹/-凸/0光滑）
    """
    convexity = {}
    dihedral = {}
    face_set = set(face_ids)

    for fid in face_ids:
        for ec_id in parser.face_to_edge_curves.get(fid, set()):
            for other_fid in parser.edge_curve_to_faces.get(ec_id, set()):
                if other_fid == fid or other_fid not in face_set:
                    continue
                key = (min(fid, other_fid), max(fid, other_fid))
                if key in convexity:
                    continue  # 已计算过这对面
                label, sign_val = _compute_edge_convexity(parser, fid, other_fid)
                convexity[key] = label
                dihedral[key] = sign_val

    return convexity, dihedral


def _verify_through_open_ends_step(parser, bottom_face, side_walls, n_bottom, adjacency):
    """验证通槽底面在通槽走向的两端均有开放端面（STEP 版本）。

    核心逻辑：
    1. 计算通槽走向 = 底面法向量 × 侧壁方向（叉积）
    2. 收集底面的自由边对应的邻接面（非侧壁）
    3. 将自由邻接面的重心投影到通槽方向
    4. 检查投影是否跨越正负两侧 → 两端开放

    区分通槽与盲槽/口袋/外凸角的关键验证。
    """
    c_bottom = _face_centroid(parser, bottom_face)
    c_a = _face_centroid(parser, side_walls[0])
    c_b = _face_centroid(parser, side_walls[1])

    if c_bottom is None or c_a is None or c_b is None:
        return False

    # 侧壁方向（从 A 到 B 的单位向量）
    d_wall = tuple(c_b[k] - c_a[k] for k in range(3))
    d_len = _vec_len(d_wall)
    if d_len < 1e-12:
        return False
    d_wall = tuple(c / d_len for c in d_wall)

    # 通槽走向 = 底面法向量 × 侧壁方向（叉积）
    through_dir = (
        n_bottom[1] * d_wall[2] - n_bottom[2] * d_wall[1],
        n_bottom[2] * d_wall[0] - n_bottom[0] * d_wall[2],
        n_bottom[0] * d_wall[1] - n_bottom[1] * d_wall[0],
    )
    td_len = _vec_len(through_dir)
    if td_len < 1e-12:
        return False
    through_dir = tuple(c / td_len for c in through_dir)

    # 收集底面自由边对应的邻接面
    wall_set = set(side_walls)
    bottom_ecs = parser.face_to_edge_curves.get(bottom_face, set())
    wall_a_ecs = parser.face_to_edge_curves.get(side_walls[0], set())
    wall_b_ecs = parser.face_to_edge_curves.get(side_walls[1], set())
    shared_ecs = (bottom_ecs & wall_a_ecs) | (bottom_ecs & wall_b_ecs)
    free_ecs = bottom_ecs - shared_ecs

    if len(free_ecs) < 2:
        return False

    # 收集自由边对应的邻接面重心投影
    projections = []
    for ec_id in free_ecs:
        for other_fid in parser.edge_curve_to_faces.get(ec_id, set()):
            if other_fid == bottom_face or other_fid in wall_set:
                continue
            c_other = _face_centroid(parser, other_fid)
            if c_other is None:
                continue
            d = sum((c_other[k] - c_bottom[k]) * through_dir[k] for k in range(3))
            projections.append(d)

    if len(projections) < 2:
        return False

    # 检查投影是否跨越正负两侧
    has_pos = any(p > 1e-6 for p in projections)
    has_neg = any(p < -1e-6 for p in projections)

    return has_pos and has_neg


# =============================================================================
# 识别器
# =============================================================================

class ThroughStepRecognizer:
    """基于 STEP 拓扑/几何的双侧通槽台阶识别器。

    策略：宽松硬过滤 + 多维评分排序。
    硬过滤只保留最基本的几何约束（垂直、互邻接、面积不为零），
    其余质量信号通过评分系统区分通槽 vs 非通槽。
    """

    def __init__(self, parser):
        self.parser = parser
        self.plane_faces = []           # [(face_id, normal)]
        self.transition_faces = []      # [(face_id, surface_type, axis_dir)]
        self.all_candidate_ids = set()
        self.adjacency = defaultdict(set)
        self._edge_convexity = {}       # (min_fid, max_fid) → "concave"/"convex"/"smooth"
        self._edge_dihedral = {}        # (min_fid, max_fid) → float 连续凹度值

    def recognize(self):
        """返回 list of dict，每个 dict 是一个通槽实例。"""
        self._collect_candidate_faces()
        self._build_adjacency()
        self._edge_convexity, self._edge_dihedral = _build_edge_convexity_map(
            self.parser, self.all_candidate_ids)
        return self._find_instances()

    def _collect_candidate_faces(self):
        """收集 PLANE 面 + CYLINDRICAL_SURFACE 过渡面。"""
        for face_id in self.parser.advanced_faces:
            stype = self.parser.face_surface_type(face_id)
            if stype == "PLANE":
                normal = _face_normal(self.parser, face_id)
                if normal is not None:
                    self.plane_faces.append((face_id, normal))
                    self.all_candidate_ids.add(face_id)
            elif stype == "CYLINDRICAL_SURFACE":
                sid = self.parser.face_surface_id(face_id)
                if sid is not None:
                    axis_info = self.parser.axis_info(sid)
                    axis_dir = axis_info.get("direction") if axis_info else None
                    if axis_dir is not None:
                        self.transition_faces.append((face_id, stype, axis_dir))
                        self.all_candidate_ids.add(face_id)

    def _build_adjacency(self):
        for fid in self.all_candidate_ids:
            for ec_id in self.parser.face_to_edge_curves.get(fid, set()):
                for other_fid in self.parser.edge_curve_to_faces.get(ec_id, set()):
                    if other_fid != fid and other_fid in self.all_candidate_ids:
                        self.adjacency[fid].add(other_fid)

    # =========================================================================
    # 评分系统（核心）
    # =========================================================================

    def _score_candidate(self, bottom_face, side_walls, normal_map):
        """对候选通槽评分（0-100）。多维信号叠加。

        优化后权重分配（总分 100）：
        - 垂直精度（25 分）：底面-侧壁夹角越接近 90° 越高分
        - 重心位置（15 分）：底面重心在侧壁之间（t→0.5）越高分
        - 面积对称性（15 分）：两侧壁面积比越接近 1 越高分
        - 底面/侧壁比（10 分）：底面面积相对侧壁越大越高分
        - 通槽开放度（15 分）：底面自由边占比越高越像通槽
        - 法向量投影（10 分）：侧壁法向量投影后越反平行越像通槽
        - 侧壁边数（3 分）：侧壁边数越少（简单面）越高分
        - 侧壁反平行度（5 分）：法向量点积越接近 -1 越像通槽
        - 质心距离对称性（2 分）：底面到两侧壁距离越对称越高分

        额外加分（在 _validate_core 中叠加）：
        - 贯穿方向验证 +10 分
        - 凹度强度 +最多 5 分
        """
        n_bottom = normal_map[bottom_face]
        n_wa = normal_map[side_walls[0]]
        n_wb = normal_map[side_walls[1]]

        # ── 1. 垂直精度分（25 分）─ 底面-侧壁⊥，通槽核心约束 ──
        a_bottom_wa = _angle_between_normals(n_bottom, n_wa)
        a_bottom_wb = _angle_between_normals(n_bottom, n_wb)
        # 每对越接近 90° 越好
        q1 = max(0.0, 1.0 - abs(a_bottom_wa - 90.0) / 15.0)
        q2 = max(0.0, 1.0 - abs(a_bottom_wb - 90.0) / 15.0)
        s_perp = (q1 + q2) / 2.0 * 25.0

        # ── 2. 重心位置分（15 分）─ 底面重心应在两壁之间 ──
        s_centroid = 0.0
        c_bottom = _face_centroid(self.parser, bottom_face)
        c_a = _face_centroid(self.parser, side_walls[0])
        c_b = _face_centroid(self.parser, side_walls[1])
        centroid_t = None
        if c_bottom is not None and c_a is not None and c_b is not None:
            d = tuple(c_b[k] - c_a[k] for k in range(3))
            d_len_sq = sum(x * x for x in d)
            if d_len_sq > 1e-12:
                centroid_t = sum((c_bottom[k] - c_a[k]) * d[k] for k in range(3)) / d_len_sq
                s_centroid = max(0.0, 1.0 - abs(centroid_t - 0.5) / 0.5) * 15.0

        # ── 3. 面积对称性分（15 分）─ 两侧壁面积应相近 ──
        s_area = 0.0
        area_wa = _face_area_approx(self.parser, side_walls[0], n_wa)
        area_wb = _face_area_approx(self.parser, side_walls[1], n_wb)
        if area_wa > 1e-12 and area_wb > 1e-12:
            ratio = min(area_wa, area_wb) / max(area_wa, area_wb)
            s_area = ratio * 15.0

        # ── 4. 底面/侧壁面积比分（10 分）─ 通槽底面面积应合理 ──
        s_bottom_ratio = 0.0
        area_bottom = _face_area_approx(self.parser, bottom_face, n_bottom)
        avg_wall_area = (area_wa + area_wb) / 2.0
        if avg_wall_area > 1e-12 and area_bottom > 1e-12:
            bw_ratio = area_bottom / avg_wall_area
            s_bottom_ratio = min(1.0, max(0.0, (bw_ratio - 0.3) / 0.7)) * 10.0

        # ── 5. 通槽开放度分（15 分）─ 自由边占比越高越像通槽 ──
        s_open = 0.0
        bottom_ecs = self.parser.face_to_edge_curves.get(bottom_face, set())
        wall_a_ecs = self.parser.face_to_edge_curves.get(side_walls[0], set())
        wall_b_ecs = self.parser.face_to_edge_curves.get(side_walls[1], set())
        shared_ecs = (bottom_ecs & wall_a_ecs) | (bottom_ecs & wall_b_ecs)
        n_bottom_ecs = len(bottom_ecs)
        if n_bottom_ecs > 0:
            free_ratio = (n_bottom_ecs - len(shared_ecs)) / n_bottom_ecs
            s_open = min(1.0, free_ratio * 2.0) * 15.0  # 50%+ 自由边即满分

        # ── 6. 法向量投影分（10 分）─ 投影后越反平行越像 U 型通槽 ──
        # U 型通槽：proj_dot ≈ -1（满分），外凸角/同向面：proj_dot ≈ 1（0 分）
        s_proj = 0.0
        proj_wa = _project_to_plane(n_wa, n_bottom)
        proj_wb = _project_to_plane(n_wb, n_bottom)
        proj_dot = _dot(proj_wa, proj_wb)
        proj_len_sq = _dot(proj_wa, proj_wa) * _dot(proj_wb, proj_wb)
        if proj_len_sq > 1e-12:
            s_proj = max(0.0, (1.0 - proj_dot) / 2.0) * 10.0

        # ── 7. 侧壁边数分（5 分）─ 边数越少越可能是规则侧壁 ──
        ec_wa = len(wall_a_ecs)
        ec_wb = len(wall_b_ecs)
        s_edges = max(0.0, 5.0 - (max(ec_wa, ec_wb) - 4) * 1.0)

        # ── 8. 侧壁平行度分（5 分）─ 结合 abs 角度 + 反平行 dot ──
        wall_angle = _angle_between_normals(n_wa, n_wb)
        s_wall_angle = max(0.0, 1.0 - wall_angle / 90.0)  # 原始：夹角越小越好
        dot_walls = _dot(n_wa, n_wb)
        s_wall_anti = max(0.0, (-dot_walls - 0.3) / 0.7)   # 新增：dot 越负越反平行
        s_wall = s_wall_angle * 3.0 + s_wall_anti * 2.0     # 原始 3 分 + 反平行 2 分

        # ── 9. 质心距离对称性加分（bonus +3）─ FeatureFox 风格 ──
        s_dist = 0.0
        if c_bottom is not None and c_a is not None and c_b is not None:
            d_ba = _vec_len(tuple(c_bottom[k] - c_a[k] for k in range(3)))
            d_bb = _vec_len(tuple(c_bottom[k] - c_b[k] for k in range(3)))
            if max(d_ba, d_bb) > 1e-12:
                dist_ratio = min(d_ba, d_bb) / max(d_ba, d_bb)
                s_dist = dist_ratio * 3.0  # 距离越对称越高分，最多 3

        score = round(s_perp + s_centroid + s_area + s_bottom_ratio + s_open + s_proj + s_edges + s_wall + s_dist, 1)
        return score, centroid_t

    # =========================================================================
    # 搜索 + 验证
    # =========================================================================

    def _find_instances(self):
        """合并 trio + extended + mixed_trio 搜索，评分排序，贪心选面。"""
        trio_results = self._find_trio_instances()
        extended_results = self._find_extended_instances()
        mixed_results = self._find_mixed_trio_instances()

        all_results = trio_results + extended_results + mixed_results

        # 按类型区分阈值过滤
        def _pass_threshold(r):
            s = r.get("score", 0)
            t = r.get("type", "")
            if t == "mixed_trio":
                return s >= MIN_MIXED_SCORE_STEP
            return s >= MIN_HYBRID_SCORE

        all_results = [r for r in all_results if _pass_threshold(r)]

        # 去重（同 face 集合取高分）
        best = {}
        for r in all_results:
            key = tuple(r["faces"])
            if key not in best or r.get("score", 0) > best[key].get("score", 0):
                best[key] = r
        all_results = list(best.values())

        # 评分排序
        all_results.sort(key=lambda r: r.get("score", 0), reverse=True)

        # 贪心选面（高分优先，已被占用的面跳过）
        used_faces = set()
        instances = []
        for result in all_results:
            result_faces = set(result["faces"])
            if result_faces & used_faces:
                continue
            instances.append(result)
            used_faces.update(result_faces)

        return instances

    def _validate_core(self, bottom_face, side_walls, normal_map):
        """核心硬过滤：只保留最基本的几何约束。

        返回 (result_dict | None)。
        """
        n_bottom = normal_map[bottom_face]
        n_wa = normal_map[side_walls[0]]
        n_wb = normal_map[side_walls[1]]

        # ── 垂直性检查：底面与两侧壁都近似垂直 ──
        if not (PERP_MIN <= _angle_between_normals(n_bottom, n_wa) <= PERP_MAX):
            return None
        if not (PERP_MIN <= _angle_between_normals(n_bottom, n_wb) <= PERP_MAX):
            return None

        # ── 互邻接验证 ──
        core = [bottom_face, side_walls[0], side_walls[1]]
        for i in range(3):
            for j in range(i + 1, 3):
                shared = self.parser.face_to_edge_curves.get(core[i], set()) & \
                         self.parser.face_to_edge_curves.get(core[j], set())
                if not shared:
                    return None

        # ── 凸凹性检查（从 NCTI 版移植）──
        # 底面-侧壁的共享边必须是凹边或光滑边，凸边 = 外凸角而非内凹通槽
        for w in side_walls:
            key = (min(bottom_face, w), max(bottom_face, w))
            conv = self._edge_convexity.get(key, "smooth")
            if conv == "convex":
                return None

        # ── 通槽拓扑：底面应有非侧壁共享边（开放端标志） ──
        bottom_ecs = self.parser.face_to_edge_curves.get(bottom_face, set())
        wall_a_ecs = self.parser.face_to_edge_curves.get(side_walls[0], set())
        wall_b_ecs = self.parser.face_to_edge_curves.get(side_walls[1], set())
        shared_with_walls = (bottom_ecs & wall_a_ecs) | (bottom_ecs & wall_b_ecs)
        free_bottom_ecs = bottom_ecs - shared_with_walls
        if len(free_bottom_ecs) < BOTTOM_FREE_EDGES_MIN:
            return None

        # ── 共享边类型检查：底面-侧壁共享边应主要为直线 ──
        shared_ba = bottom_ecs & wall_a_ecs
        shared_bb = bottom_ecs & wall_b_ecs
        for shared_set in (shared_ba, shared_bb):
            if not shared_set:
                continue
            line_count = 0
            for ec_id in shared_set:
                try:
                    ec_type = self.parser.edge_base_curve_type(ec_id)
                except Exception:
                    line_count += 1  # 无法判断时默认按 LINE 处理
                    continue
                if ec_type == "LINE":
                    line_count += 1
            # 至少半数共享边为 LINE，否则拒绝
            if line_count < len(shared_set) * 0.5:
                return None

        # ── 侧壁夹角检查：通槽侧壁应大致平行，垂直=拐角 ──
        wall_angle = _angle_between_normals(n_wa, n_wb)
        if wall_angle > WALL_ANGLE_MAX:
            return None

        # ── 侧壁边数信号：写入评分，不做硬过滤 ──

        # ── 面积硬过滤 ──
        area_bottom = _face_area_approx(self.parser, bottom_face, n_bottom)
        area_wa = _face_area_approx(self.parser, side_walls[0], n_wa)
        area_wb = _face_area_approx(self.parser, side_walls[1], n_wb)
        if area_bottom < MIN_FACE_AREA and area_wa < MIN_FACE_AREA and area_wb < MIN_FACE_AREA:
            return None
        if area_bottom > 1e-12:
            if area_wa / area_bottom > WALL_AREA_RATIO_MAX or area_wb / area_bottom > WALL_AREA_RATIO_MAX:
                return None
        # 底面不应明显小于侧壁（通槽底面是槽底板，面积应 ≥ 侧壁的一半）
        avg_wall_area = (area_wa + area_wb) / 2.0
        if area_bottom > 1e-12 and avg_wall_area > 1e-12:
            if area_bottom / avg_wall_area < BOTTOM_WALL_RATIO_MIN:
                return None
        # 侧壁面积应大致对称（通槽两侧壁高度相近）
        if area_wa > 1e-12 and area_wb > 1e-12:
            if min(area_wa, area_wb) / max(area_wa, area_wb) < WALL_AREA_SYMMETRY_MIN:
                return None

        # ── 重心位置硬过滤 ──
        c_bottom = _face_centroid(self.parser, bottom_face)
        c_a = _face_centroid(self.parser, side_walls[0])
        c_b = _face_centroid(self.parser, side_walls[1])
        centroid_t = None
        if c_bottom is not None and c_a is not None and c_b is not None:
            d = tuple(c_b[k] - c_a[k] for k in range(3))
            d_len_sq = sum(x * x for x in d)
            if d_len_sq > 1e-12:
                centroid_t = sum((c_bottom[k] - c_a[k]) * d[k] for k in range(3)) / d_len_sq
                if centroid_t < CENTROID_T_MIN or centroid_t > CENTROID_T_MAX:
                    return None

        # ── 贯穿方向两端开放验证（改为评分加分项）──
        through_ok = _verify_through_open_ends_step(
            self.parser, bottom_face, side_walls, n_bottom, self.adjacency)

        # ── 评分 ──
        score, _ = self._score_candidate(bottom_face, side_walls, normal_map)

        # ── 贯穿方向加分：验证通过 → +10 分 ──
        if through_ok:
            score = min(100, score + 10)

        # 底面邻接面数（STEP 版仅含候选面间邻接，参考用）
        bottom_neighbor_count = len(self.adjacency.get(bottom_face, set()))

        # 角度信息
        angles = {}
        for i in range(3):
            for j in range(i + 1, 3):
                fi, fj = core[i], core[j]
                key = "{}_{}".format(min(fi, fj), max(fi, fj))
                angles[key] = round(_angle_between_normals(normal_map[fi], normal_map[fj]), 2)

        perp_count = sum(1 for v in angles.values() if PERP_MIN <= v <= PERP_MAX)

        return {
            "bottom_face": bottom_face,
            "side_walls": sorted(side_walls),
            "score": score,
            "angles": angles,
            "n_perpendicular_pairs": perp_count,
            "centroid_t": centroid_t,
            "bottom_neighbor_count": bottom_neighbor_count,
        }

    # =========================================================================
    # 路径 A：3 面 trio
    # =========================================================================

    def _find_trio_instances(self):
        """搜索 3 个 PLANE 面构成的简单通槽。"""
        normal_map = {fid: n for fid, n in self.plane_faces}
        plane_ids = sorted(normal_map.keys())
        results = []

        for fa in plane_ids:
            for fb in sorted(self.adjacency.get(fa, set())):
                if fb <= fa:
                    continue
                if self.parser.face_surface_type(fb) != "PLANE":
                    continue
                common = self.adjacency.get(fa, set()) & self.adjacency.get(fb, set())
                for fc in sorted(common):
                    if fc <= fb:
                        continue
                    if self.parser.face_surface_type(fc) != "PLANE":
                        continue
                    # 枚举哪个是底面
                    for bottom, walls in [(fa, [fb, fc]), (fb, [fa, fc]), (fc, [fa, fb])]:
                        result = self._validate_core(bottom, walls, normal_map)
                        if result is not None:
                            faces = sorted([fa, fb, fc])
                            results.append({
                                "faces": faces,
                                "bottom_face": result["bottom_face"],
                                "side_walls": result["side_walls"],
                                "n_perpendicular_pairs": result["n_perpendicular_pairs"],
                                "angles": result["angles"],
                                "score": result["score"],
                                "type": "simple_3face",
                                "fillets": [],
                            })

        return results

    # =========================================================================
    # 路径 B：4-6 面扩展组（带圆角过渡面）
    # =========================================================================

    def _find_extended_instances(self):
        """搜索带 CYLINDRICAL 过渡面的通槽（4-6 面）。

        约束：
        - 核心 trio 必须互邻接
        - 过渡面必须同时邻接底面和至少一个侧壁
        """
        normal_map = {fid: n for fid, n in self.plane_faces}
        transition_map = {fid: axis_dir for fid, _, axis_dir in self.transition_faces}
        results = []

        for bottom_id, n_bottom in self.plane_faces:
            direct_neighbors = self.adjacency.get(bottom_id, set())

            wall_candidates = []
            for fid in direct_neighbors:
                if fid in normal_map:
                    angle = _angle_between_normals(n_bottom, normal_map[fid])
                    if PERP_MIN <= angle <= PERP_MAX:
                        wall_candidates.append(fid)

            if len(wall_candidates) < 2:
                continue

            for i in range(len(wall_candidates)):
                for j in range(i + 1, len(wall_candidates)):
                    wa = wall_candidates[i]
                    wb = wall_candidates[j]

                    # 核心 trio 互邻接
                    if wb not in self.adjacency.get(wa, set()):
                        continue

                    # 核心验证 + 评分
                    core_result = self._validate_core(bottom_id, [wa, wb], normal_map)
                    if core_result is None:
                        continue

                    # 寻找结构相关的过渡面
                    relevant_fillets = []
                    for tfid, axis_dir in transition_map.items():
                        if tfid not in direct_neighbors:
                            continue
                        adj_to_wa = tfid in self.adjacency.get(wa, set())
                        adj_to_wb = tfid in self.adjacency.get(wb, set())
                        if not (adj_to_wa or adj_to_wb):
                            continue
                        align_angle = _angle_between_normals(axis_dir, n_bottom)
                        if PERP_MIN <= align_angle <= PERP_MAX:
                            relevant_fillets.append(tfid)

                    if not relevant_fillets:
                        continue

                    group = sorted([bottom_id, wa, wb] + relevant_fillets)
                    if len(group) > MAX_INSTANCE_FACES:
                        group = group[:MAX_INSTANCE_FACES]

                    results.append({
                        "faces": group,
                        "bottom_face": core_result["bottom_face"],
                        "side_walls": core_result["side_walls"],
                        "n_perpendicular_pairs": core_result["n_perpendicular_pairs"],
                        "angles": core_result["angles"],
                        "score": core_result["score"],
                        "type": "extended_{}face".format(len(group)),
                        "fillets": sorted(relevant_fillets),
                    })

        return results

    # =========================================================================
    # 路径 C：混合 trio（PLANE 底面 + PLANE 壁 + CYLINDRICAL 壁）
    # =========================================================================

    def _find_mixed_trio_instances(self):
        """搜索包含一个圆柱侧壁的通槽 trio。

        从 NCTI 版移植，适配 STEP 拓扑数据。
        适用场景：通槽的一侧壁为圆柱面（如半圆截面），
        另一侧壁和底面为平面。

        由于 STEP 无边凸凹性数据，通过更严格的评分和
        贯穿方向硬过滤来补偿。
        """
        normal_map = {fid: n for fid, n in self.plane_faces}
        cyl_axis_map = {fid: axis_dir for fid, _, axis_dir in self.transition_faces}
        results = []

        for bottom_id, n_bottom in self.plane_faces:
            bottom_neighbors = self.adjacency.get(bottom_id, set())

            # 找底面的平面壁候选（垂直 + 邻接 + 非凸边）
            plane_wall_candidates = []
            for fid in bottom_neighbors:
                if fid not in normal_map:
                    continue
                n_fid = normal_map[fid]
                angle = _angle_between_normals(n_bottom, n_fid)
                if not (PERP_MIN <= angle <= PERP_MAX):
                    continue
                # 凸凹性预过滤：底面-平面壁边不能是凸边
                key = (min(bottom_id, fid), max(bottom_id, fid))
                conv = self._edge_convexity.get(key, "smooth")
                if conv == "convex":
                    continue
                plane_wall_candidates.append(fid)

            # 找底面的圆柱壁候选（轴线⊥底面法向量 + 邻接 + 非凸边）
            cyl_wall_candidates = []
            for fid in bottom_neighbors:
                if fid not in cyl_axis_map:
                    continue
                axis = cyl_axis_map[fid]
                axis_angle = _angle_between_normals(n_bottom, axis)
                if not (PERP_MIN <= axis_angle <= PERP_MAX):
                    continue
                # 凸凹性预过滤：底面-圆柱壁边不能是凸边
                key = (min(bottom_id, fid), max(bottom_id, fid))
                conv = self._edge_convexity.get(key, "smooth")
                if conv == "convex":
                    continue
                cyl_wall_candidates.append(fid)

            if not plane_wall_candidates or not cyl_wall_candidates:
                continue

            # 组合：1 平面壁 + 1 圆柱壁
            for pw in plane_wall_candidates:
                for cw in cyl_wall_candidates:
                    # 两个壁必须互相邻接
                    if cw not in self.adjacency.get(pw, set()):
                        continue
                    # 壁-壁边不能是凸边
                    key_wc = (min(pw, cw), max(pw, cw))
                    if self._edge_convexity.get(key_wc, "smooth") == "convex":
                        continue

                    # 验证混合 trio
                    result = self._validate_mixed_trio(
                        bottom_id, pw, cw, n_bottom, normal_map, cyl_axis_map
                    )
                    if result is not None:
                        results.append(result)

        return results

    def _validate_mixed_trio(self, bottom, plane_wall, cyl_wall,
                              n_bottom, normal_map, cyl_axis_map):
        """验证 平面底面 + 平面壁 + 圆柱壁 trio。

        从 NCTI 版移植。凸凹性已由 _find_mixed_trio_instances 预过滤，
        贯穿方向验证作为评分加分项（+10 分），与 NCTI 行为对齐。
        """
        n_pw = normal_map.get(plane_wall)
        axis_cw = cyl_axis_map.get(cyl_wall)
        if n_pw is None or axis_cw is None:
            return None

        # ── 平面壁垂直性检查 ──
        angle_b_pw = _angle_between_normals(n_bottom, n_pw)
        if not (PERP_MIN <= angle_b_pw <= PERP_MAX):
            return None

        # ── 圆柱壁轴线⊥底面法向量检查 ──
        angle_b_cw = _angle_between_normals(n_bottom, axis_cw)
        if not (PERP_MIN <= angle_b_cw <= PERP_MAX):
            return None

        # ── 自由边检查（底面应有不与壁共享的边） ──
        wall_set = {plane_wall, cyl_wall}
        bottom_ecs = self.parser.face_to_edge_curves.get(bottom, set())
        pw_ecs = self.parser.face_to_edge_curves.get(plane_wall, set())
        cw_ecs = self.parser.face_to_edge_curves.get(cyl_wall, set())
        shared_ecs = (bottom_ecs & pw_ecs) | (bottom_ecs & cw_ecs)
        free_ecs = bottom_ecs - shared_ecs
        total_ecs = len(bottom_ecs)
        n_shared = len(shared_ecs)
        n_free = len(free_ecs)
        if n_free < BOTTOM_FREE_EDGES_MIN:
            return None

        # ── 面积检查 ──
        area_bottom = _face_area_approx(self.parser, bottom, n_bottom)
        area_pw = _face_area_approx(self.parser, plane_wall, n_pw)
        area_cw = _face_area_approx(self.parser, cyl_wall)
        if area_bottom < MIN_FACE_AREA and area_pw < MIN_FACE_AREA and area_cw < MIN_FACE_AREA:
            return None

        # ── 贯穿方向验证（改为评分加分项，与 NCTI 对齐）──
        through_ok = _verify_through_open_ends_step(
            self.parser, bottom, [plane_wall, cyl_wall], n_bottom, self.adjacency)

        # ── 重心位置：两壁应在底面的不同侧 ──
        c_bottom = _face_centroid(self.parser, bottom)
        c_pw = _face_centroid(self.parser, plane_wall)
        c_cw = _face_centroid(self.parser, cyl_wall)

        # ── 评分 ──
        score = self._score_mixed_trio(
            bottom, plane_wall, cyl_wall,
            n_bottom, n_pw, axis_cw,
            area_bottom, area_pw, area_cw,
            total_ecs, n_shared, n_free,
            c_bottom, c_pw, c_cw
        )

        # 贯穿方向加分
        if through_ok:
            score = min(100, score + 10)

        # 底面邻接面数（STEP 版仅含候选面间邻接，参考用）
        bottom_neighbor_count = len(self.adjacency.get(bottom, set()))

        return {
            "faces": sorted([bottom, plane_wall, cyl_wall]),
            "bottom_face": bottom,
            "side_walls": sorted([plane_wall, cyl_wall]),
            "score": score,
            "angles": {
                "b_pw": round(angle_b_pw, 2),
                "b_cw_axis": round(angle_b_cw, 2),
            },
            "n_perpendicular_pairs": 2,  # 底面-平面壁 + 底面-圆柱壁(轴线)
            "type": "mixed_trio",
            "fillets": [],
            "wall_angle": 0,
            "centroid_t": None,
            "bottom_neighbor_count": bottom_neighbor_count,
        }

    def _score_mixed_trio(self, bottom, pw, cw,
                           n_bottom, n_pw, axis_cw,
                           area_bottom, area_pw, area_cw,
                           total_ecs, shared_ecs, free_ecs,
                           c_bottom, c_pw, c_cw):
        """混合 trio 评分（总分 100）。

        从 NCTI 版移植，6 维评分：
        1. 平面壁垂直精度（30 分）— 平面壁⊥底面
        2. 圆柱壁轴线对齐（20 分）— 圆柱轴线⊥底面法向量
        3. 通槽开放度（15 分）— 自由边占比
        4. 面积合理性（15 分）— 底面/壁面积比
        5. 重心分布（10 分）— 两壁在底面两侧
        6. 边数合理性（10 分）— 壁面邻接面不要太多
        """
        # 1. 平面壁垂直精度（30 分）
        a_b_pw = _angle_between_normals(n_bottom, n_pw)
        q_pw = max(0.0, 1.0 - abs(a_b_pw - 90.0) / 15.0)
        s_perp = q_pw * 30.0

        # 2. 圆柱壁轴线对齐（20 分）
        a_b_cw = _angle_between_normals(n_bottom, axis_cw)
        q_cw = max(0.0, 1.0 - abs(a_b_cw - 90.0) / 15.0)
        s_axis = q_cw * 20.0

        # 3. 通槽开放度（15 分）
        s_open = 0.0
        if total_ecs > 0:
            free_ratio = free_ecs / total_ecs
            s_open = min(1.0, free_ratio * 2.0) * 15.0

        # 4. 面积合理性（15 分）
        s_area = 0.0
        if area_pw > MIN_FACE_AREA and area_cw > MIN_FACE_AREA:
            s_area = 15.0
        elif area_pw > MIN_FACE_AREA or area_cw > MIN_FACE_AREA:
            s_area = 7.5

        # 5. 重心分布（10 分）— 两壁应在底面的不同侧
        s_centroid = 5.0
        if c_bottom is not None and c_pw is not None and c_cw is not None:
            d_pw = tuple(c_pw[k] - c_bottom[k] for k in range(3))
            d_cw = tuple(c_cw[k] - c_bottom[k] for k in range(3))
            dot_pw_cw = _dot(d_pw, d_cw)
            if dot_pw_cw < 0:
                s_centroid = 10.0
            else:
                s_centroid = 2.0

        # 6. 边数合理性（10 分）
        n_pw_neighbors = len(self.adjacency.get(pw, set()))
        n_cw_neighbors = len(self.adjacency.get(cw, set()))
        s_edges = max(0.0, 10.0 - (max(n_pw_neighbors, n_cw_neighbors) - 3) * 1.5)

        return round(s_perp + s_axis + s_open + s_area + s_centroid + s_edges, 1)


# =============================================================================
# 对外接口
# =============================================================================

def recognize_through_steps_from_stp(stp_path):
    """识别 STP 中的双侧通槽台阶，返回识别结果。

    返回 dict:
        step_parser: StepParser 实例
        instances: list of dict（每个通槽实例）
        selected_step_faces: list of int（所有要高亮的 STEP face_id）
    """
    parser = StepParser(stp_path)
    parser.parse()
    recognizer = ThroughStepRecognizer(parser)
    instances = recognizer.recognize()

    selected_step_faces = []
    for inst in instances:
        selected_step_faces.extend(inst["faces"])
    # 去重保序
    seen = set()
    unique = []
    for fid in selected_step_faces:
        if fid not in seen:
            seen.add(fid)
            unique.append(fid)

    return {
        "step_parser": parser,
        "instances": instances,
        "selected_step_faces": unique,
    }


# =============================================================================
# JSON 输出（与 AAGNet 训练标注格式一致）
# =============================================================================

def build_step_face_centroids(parser):
    """{step_face_id: (x, y, z)} —— 供 NCTI 几何最近邻映射使用的面重心。

    与 on_find_blind_hole_stp.py 的 STEP 侧做法一致（都用本文件的 _face_centroid）。
    重心算不出的面被跳过（pos_map 里自然没有它）。
    """
    centroids = {}
    for fid in parser.advanced_faces:
        c = _face_centroid(parser, fid)
        if c is not None:
            centroids[fid] = (float(c[0]), float(c[1]), float(c[2]))
    return centroids


def build_training_json(parser, instances, stp_path, *, feature_seg_id=9,
                        pos_map=None, n_cells=None):
    """构建与 Geo-Rec 训练标注格式一致的标签 JSON。

    cell_id 空间：
      - 传入 pos_map（且 n_cells）→ NCTI ai.FaceID 位置索引，与 Geo-Rec 训练图严格对齐。
        每个 STEP face_id 经 pos_map 映射到位置索引；seg/inst/bottom 维度 = n_cells。
      - 否则 → STEP advanced_faces 排序下标（⚠ 不与训练对齐，仅无 NCTI 时调试/高亮用）。

    NCTI 空间下，若某通槽实例的面未全部映射（pos_map 缺项），记警告但尽量写出已映射部分；
    整个实例一个面都没映射上则跳过该实例（避免写出空 seg / 缺项 inst）。
    """
    part_name = os.path.splitext(os.path.basename(stp_path))[0]

    # ── NCTI ai.FaceID 位置索引空间（与 Geo-Rec 训练标签对齐）──
    if pos_map is not None and n_cells is not None:
        n = n_cells
        seg = {str(i): 0 for i in range(n)}
        bottom = {str(i): 0 for i in range(n)}
        inst_matrix = [[0] * n for _ in range(n)]

        missing_report = []
        n_written = 0
        for inst_info in instances:
            instance_faces = inst_info["faces"]
            cells = sorted({pos_map[f] for f in instance_faces if f in pos_map})
            unmapped = [f for f in instance_faces if f not in pos_map]
            if unmapped:
                missing_report.append((instance_faces, unmapped))
            if not cells:
                continue  # 整个实例未映射上，跳过（不写空标签）
            n_written += 1
            for c in cells:
                seg[str(c)] = feature_seg_id
            bottom_face = inst_info.get("bottom_face")
            if bottom_face is not None and bottom_face in pos_map:
                bottom[str(pos_map[bottom_face])] = 1
            for a in cells:
                for b in cells:
                    inst_matrix[a][b] = 1

        if missing_report:
            sys.stderr.write(
                "警告：{} 个通槽实例有面未映射到 NCTI cell_id（标签可能缺项）: {}\n".format(
                    len(missing_report),
                    ", ".join("#{}".format(f) for _, um in missing_report for f in um)))
        # 纵深防御：pos_map 非空但所有实例零命中 → 输出实为全 0，醒目告警（main 已拦空 pos_map）
        if instances and n_written == 0:
            sys.stderr.write(
                "⚠ 所有 {} 个通槽实例均未映射到 NCTI cell_id，输出的是全 0 标签"
                "（疑似 NCTI 对齐失败），勿用于训练。\n".format(len(instances)))
        return [[part_name, {"seg": seg, "inst": inst_matrix, "bottom": bottom}]]

    # ── STEP advanced_faces 排序下标空间（无 NCTI 回退，不与训练对齐）──
    face_order = sorted(parser.advanced_faces.keys())
    fid_to_idx = {fid: idx for idx, fid in enumerate(face_order)}
    n = len(face_order)

    seg = {str(i): 0 for i in range(n)}
    bottom = {str(i): 0 for i in range(n)}
    inst_matrix = [[0] * n for _ in range(n)]

    for inst_info in instances:
        instance_faces = inst_info["faces"]
        bottom_face = inst_info.get("bottom_face")
        for fid in instance_faces:
            idx = fid_to_idx.get(fid)
            if idx is not None:
                seg[str(idx)] = feature_seg_id
        if bottom_face is not None:
            idx = fid_to_idx.get(bottom_face)
            if idx is not None:
                bottom[str(idx)] = 1
        for fid_a in instance_faces:
            idx_a = fid_to_idx.get(fid_a)
            if idx_a is None:
                continue
            for fid_b in instance_faces:
                idx_b = fid_to_idx.get(fid_b)
                if idx_b is None:
                    continue
                inst_matrix[idx_a][idx_b] = 1

    return [[part_name, {"seg": seg, "inst": inst_matrix, "bottom": bottom}]]


# =============================================================================
# 命令行入口
# =============================================================================

def main():
    ap = argparse.ArgumentParser(description="双侧通槽台阶 STEP 几何识别器。")
    ap.add_argument("input", help="STP/STEP 文件路径")
    ap.add_argument("-o", "--output-dir", default=None, help="JSON 输出目录")
    ap.add_argument("--seg-id", type=int, default=9)
    ncti_grp = ap.add_mutually_exclusive_group()
    ncti_grp.add_argument("--require-ncti", action="store_true",
                          help="强制 NCTI 对齐 cell_id；NCTI 不可用则报错退出，不写未对齐标签")
    ncti_grp.add_argument("--no-ncti", action="store_true",
                          help="跳过 NCTI，标签用 STEP 面下标（不与训练对齐，仅调试用）")
    args = ap.parse_args()

    result = recognize_through_steps_from_stp(args.input)
    parser = result["step_parser"]
    instances = result["instances"]
    print("识别实例数量：{}".format(len(instances)))
    for i, inst in enumerate(instances, 1):
        fillet_str = ""
        if inst.get("fillets"):
            fillet_str = "，圆角 {}".format(", ".join("#{}".format(f) for f in inst["fillets"]))
        print("  实例 #{}：{} [{}] 评分 {:.1f}，面 {}，底面 #{}，侧壁 {}{}".format(
            i,
            inst.get("type", "unknown"),
            inst["n_perpendicular_pairs"],
            inst.get("score", 0),
            ", ".join("#{}".format(f) for f in inst["faces"]),
            inst["bottom_face"],
            ", ".join("#{}".format(f) for f in inst["side_walls"]),
            fillet_str,
        ))

    # ── cell_id 空间：NCTI ai.FaceID 位置索引（默认）或 STEP 面下标（--no-ncti / 对齐失败）──
    # build_pos_map_for_step 三态：NCTI 不可用/导入失败 → (None,None)；
    # NCTI 成功但零匹配 → ({},n)；成功 → ({...},n)。空 dict 与 None 一样视为「未对齐」。
    pos_map = n_cells = None
    if not args.no_ncti:
        step_centroids = build_step_face_centroids(parser)
        pos_map, n_cells = build_pos_map_for_step(
            args.input, step_centroids, project_root=PROJECT_ROOT)

    ncti_engine_used = n_cells is not None   # 是否真建过 NCTI 文档（决定 os._exit）
    aligned = bool(pos_map)                   # 标签是否落在 NCTI 位置索引空间

    # --require-ncti：对齐失败（不可用 或 零匹配）一律报错退出，绝不写未对齐标签
    if args.require_ncti and not aligned:
        if ncti_engine_used:
            sys.exit("错误：--require-ncti 但 NCTI 几何对齐零匹配（pos_map 为空），已跳过写标签。\n"
                     "请排查自适应容差/零件几何，或去掉 --require-ncti 回退到 STEP 面下标。")
        sys.exit("错误：--require-ncti 但 NCTI 不可用，已跳过写标签（避免输出未对齐的训练标签）。\n"
                 "请配置 NCTI（config/ncti_config.json 或 YHCADSmartCleaner 系统 config）后重试。")

    if aligned:
        print("标签 cell_id 空间：NCTI ai.FaceID 位置索引（与 Geo-Rec 训练标签对齐）")
    else:
        sys.stderr.write(
            "⚠ 标签 cell_id 空间：STEP 面下标（不与 Geo-Rec 训练标签对齐，勿用于训练）。\n")
        if ncti_engine_used:
            sys.stderr.write(
                "  ⚠ NCTI 已导入但几何对齐零匹配（pos_map 空），回退到 STEP 面下标。\n"
                "    请排查自适应容差/零件几何；如需强制 NCTI 请用 --require-ncti。\n")
        else:
            sys.stderr.write("  配置 NCTI 或去掉 --no-ncti 以获得对齐标签。\n")

    if args.output_dir and instances:
        os.makedirs(args.output_dir, exist_ok=True)
        json_data = build_training_json(
            parser, instances, args.input,
            feature_seg_id=args.seg_id,
            pos_map=(pos_map if aligned else None),
            n_cells=(n_cells if aligned else None))
        stem = os.path.splitext(os.path.basename(args.input))[0]
        json_path = os.path.join(args.output_dir, "{}.json".format(stem))
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        print("JSON 已保存：{}".format(json_path))

    # NCTI 原生 DLL 析构可能 segfault；建过 NCTI 文档就直接退出（与 annotate/test_ncti 同惯例）
    if ncti_engine_used:
        os._exit(0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
