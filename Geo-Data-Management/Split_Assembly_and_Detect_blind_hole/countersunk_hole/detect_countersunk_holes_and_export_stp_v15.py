#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STP/STEP 文件中沉头孔（countersink hole）与沉孔（counterbore hole）识别、盲孔倒角规则补充、STP 导出与 JSON 标注脚本。

功能：
1. 输入一个 STP 文件路径或文件夹路径。
2. 遍历 .stp / .step / .stp.txt / .step.txt 文件。
3. 判断每个文件中是否存在：
   - has_countersink_hole：锥形沉头孔
   - has_counterbore_hole：圆柱沉孔 / 平底沉孔
4. 找到 countersink_hole / counterbore_hole 后，导出仅包含相关特征面的 STP 文件，并输出详细日志。

识别规则严格遵循：
- counterbore hole = 同轴大圆柱面 + 同轴小圆柱面 + 中间环形台阶平面 + 小孔贯通
- countersink hole = 同轴圆锥沉头面 + 同轴小圆柱孔 + 外部入口 + 完整圆口；不使用固定半径比例作为强判据

说明：
该脚本采用 STEP 文本拓扑解析方式，不依赖 pythonocc / FreeCAD 等几何内核，
适合批量扫描由 CAD 软件导出的 ISO-10303-21 STEP 文本文件。
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# 支持放在项目子目录中直接运行，例如：
# Geo-Data-Management/fea_recognize/detect_countersunk_holes_and_export_stp_v3_strict.py
# 这样 JSON 输出阶段才能找到 config.config_load。
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
for _p in (SCRIPT_DIR, PROJECT_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

Vec3 = Tuple[float, float, float]


# =========================
# 可调识别阈值
# =========================

# STEP 文件通常以 mm 为单位；这些阈值用于处理导出误差。
ABS_TOL = 1e-4
AXIS_DIST_TOL = 1e-3
ANGLE_TOL = 1e-4
RADIUS_TOL = 1e-3

# countersink 不再使用固定 R_big / R_small 半径比例作为强判据。
# 机械定义通常由大端直径、夹角和配套紧固件尺寸确定，不存在通用固定比例。
# 以下旧阈值仅保留为兼容变量，当前识别函数不再使用它们。
COUNTERSINK_MIN_RADIUS_RATIO = None
COUNTERSINK_MIN_RADIAL_GROWTH = None
COUNTERSINK_MIN_RADIAL_GROWTH_RATIO = None
COUNTERSINK_MIN_DEPTH_RATIO = None

# 沉孔 counterbore 也要求大孔明显大于小孔，避免把微小圆角/倒角过渡误判为沉孔。
COUNTERBORE_MIN_RADIUS_RATIO = 1.15
COUNTERBORE_MIN_RADIAL_GROWTH = 0.2

# counterbore 不是任意同轴大小圆柱的组合。
# 大孔段和小孔段必须在台阶平面两侧相邻，而不能沿同一轴向区间重叠。
# 这可以排除 O-ring 槽、外凸套筒、螺钉头/铆钉状结构等假阳性。
COUNTERBORE_REQUIRE_AXIAL_ADJACENCY = True
COUNTERBORE_REQUIRE_LOCAL_ANNULAR_STEP = True
COUNTERBORE_MAX_INTERVAL_OVERLAP_RATIO = 0.05

# 标准沉头孔/沉孔的入口必须是完整闭合圆口。
# 注意：完整圆在 STEP 中可能是一个 CIRCLE，也可能是多个同心同半径 CIRCLE 圆弧闭合而成。
# 但不能是半圆、缺口圆、LINE+CIRCLE 槽端、B_SPLINE/ELLIPSE 混合边界。
REQUIRE_COMPLETE_CIRCULAR_MOUTH = True
REQUIRE_COMPLETE_STEP_RINGS = True
REQUIRE_COMPLETE_CONE_RINGS = True

# 标准沉头孔/沉孔的沉头空间内部不能再穿过其他同轴圆柱体。
# 如果大圆柱沉台或圆锥沉头内部又存在一个更小/中间半径的同轴圆柱面，
# 通常说明这是 O-ring 槽、套筒、凸台、螺钉头/铆钉状结构，或者其他同轴组合件，
# 而不是用于容纳螺钉头的干净内凹沉头空间。
REJECT_NESTED_COAXIAL_CYLINDERS = True
NESTED_COAXIAL_INTERVAL_OVERLAP_RATIO = 0.08
NESTED_COAXIAL_MIN_OVERLAP_ABS = 1.0e-3

# ADVANCED_FACE 的 .T./.F. 方向只作为辅助信息，不能作为默认硬规则。
# 原因：same_sense 只表示面法向是否跟随基础曲面的自然法向，和“通孔/盲孔/凸台”的关系取决于
# CYLINDRICAL_SURFACE / CONICAL_SURFACE 的参数化方向和 CAD 导出器，不能简单认为所有真孔壁都必须是 .F.。
# 因此默认不强制 .F.；只有命令行加 --strict-inner-sense 时才启用旧版强约束。
REQUIRE_INNER_CAVITY_FACE_ORIENTATION = False

# 但 .T./.F. 可以用于排除“有端盖的实心凸柱/铆钉头/螺钉头”：
# 如果一个候选 countersink/counterbore 的所有曲面都是 .T.，并且小圆柱另一端连接局部圆形端盖，
# 它更像外凸实体柱，而不是空的沉头孔。这个过滤不会影响普通贯通孔，因为贯通孔没有局部端盖。
REJECT_OUTER_SENSE_CAPPED_PROTRUSION = True

# V15-inner-cavity-proof：counterbore 的误检高发于外凸台阶轴。
# 这些结构在拓扑上也可能表现为“大圆柱 + 小圆柱 + 台阶/锥面”，
# 但候选曲面全部为 same_sense=True，缺少任何 .F. 内凹孔壁证据。
# 默认将这种 counterbore 候选按外凸台阶轴排除；
# 可用 --disable-protrusion-sense-filter 关闭该过滤。
REJECT_ALL_OUTER_SENSE_COUNTERBORE = True


# =========================
# 基础数学函数
# =========================

def dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def norm(a: Vec3) -> float:
    return math.sqrt(dot(a, a))


def cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def normalize(v: Vec3) -> Vec3:
    n = norm(v)
    if n <= 0:
        return (0.0, 0.0, 0.0)
    return (v[0] / n, v[1] / n, v[2] / n)


def abs_parallel(a: Vec3, b: Vec3, tol: float = ANGLE_TOL) -> bool:
    a = normalize(a)
    b = normalize(b)
    return abs(abs(dot(a, b)) - 1.0) <= tol


def axis_distance(p1: Vec3, d1: Vec3, p2: Vec3, d2: Vec3) -> float:
    """两条近似平行直线之间的距离。"""
    d1 = normalize(d1)
    d2 = normalize(d2)
    if abs_parallel(d1, d2):
        return norm(cross(sub(p2, p1), d1))
    n = cross(d1, d2)
    nn = norm(n)
    if nn <= 1e-12:
        return norm(cross(sub(p2, p1), d1))
    return abs(dot(sub(p2, p1), n)) / nn


def same_axis(p1: Vec3, d1: Vec3, p2: Vec3, d2: Vec3,
              dist_tol: float = AXIS_DIST_TOL, angle_tol: float = ANGLE_TOL) -> bool:
    return abs_parallel(d1, d2, angle_tol) and axis_distance(p1, d1, p2, d2) <= dist_tol


def project_t(point: Vec3, origin: Vec3, axis: Vec3) -> float:
    return dot(sub(point, origin), normalize(axis))


def close_float(a: float, b: float, tol: float = RADIUS_TOL) -> bool:
    return abs(a - b) <= tol


def close_point(a: Vec3, b: Vec3, tol: float = AXIS_DIST_TOL) -> bool:
    return norm(sub(a, b)) <= tol


def parse_float(s: str) -> float:
    return float(s.replace('D', 'E').replace('d', 'E'))


def parse_float_tuple(s: str) -> Tuple[float, ...]:
    """解析 STEP 里的 (1.,2.,3.) 数值元组。"""
    nums = re.findall(r'[-+]?\d*\.?\d+(?:[EeDd][-+]?\d+)?', s)
    return tuple(parse_float(x) for x in nums)


def extract_refs(s: str) -> List[int]:
    return [int(x) for x in re.findall(r'#(\d+)', s)]


def unique_ints(seq: Iterable[int]) -> List[int]:
    seen = set()
    out = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


# =========================
# STEP 参数拆分
# =========================

def split_top_level_args(arg_text: str) -> List[str]:
    """按顶层逗号拆分 STEP 实体参数，忽略括号和字符串内部的逗号。"""
    args: List[str] = []
    start = 0
    depth = 0
    in_str = False
    i = 0
    while i < len(arg_text):
        c = arg_text[i]
        if c == "'":
            in_str = not in_str
        elif not in_str:
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
            elif c == ',' and depth == 0:
                args.append(arg_text[start:i].strip())
                start = i + 1
        i += 1
    tail = arg_text[start:].strip()
    if tail:
        args.append(tail)
    return args


def strip_outer_parens(s: str) -> str:
    s = s.strip()
    if s.startswith('(') and s.endswith(')'):
        return s[1:-1].strip()
    return s


# =========================
# 数据结构
# =========================

@dataclass
class AxisPlacement3D:
    id: int
    point: Vec3
    axis: Vec3
    ref_dir: Optional[Vec3] = None


@dataclass
class Circle3D:
    id: int
    center: Vec3
    normal: Vec3
    radius: float


@dataclass
class CylinderFace:
    face_id: int
    surface_id: int
    radius: float
    point: Vec3
    axis: Vec3
    circles: List[Circle3D] = field(default_factory=list)


@dataclass
class ConeFace:
    face_id: int
    surface_id: int
    radius_at_placement: float
    semi_angle: float
    point: Vec3
    axis: Vec3
    circles: List[Circle3D] = field(default_factory=list)


@dataclass
class PlaneFace:
    face_id: int
    surface_id: int
    point: Vec3
    normal: Vec3
    circles: List[Circle3D] = field(default_factory=list)


@dataclass
class StepModel:
    path: Path
    raw_entities: Dict[int, Tuple[str, str]] = field(default_factory=dict)
    points: Dict[int, Vec3] = field(default_factory=dict)
    directions: Dict[int, Vec3] = field(default_factory=dict)
    placements3d: Dict[int, AxisPlacement3D] = field(default_factory=dict)
    circles3d: Dict[int, Circle3D] = field(default_factory=dict)
    face_surface: Dict[int, int] = field(default_factory=dict)
    face_same_sense: Dict[int, bool] = field(default_factory=dict)
    face_bound_refs: Dict[int, List[int]] = field(default_factory=dict)
    face_bound_loop: Dict[int, int] = field(default_factory=dict)
    edge_loop_oriented_edges: Dict[int, List[int]] = field(default_factory=dict)
    oriented_edge_edge: Dict[int, int] = field(default_factory=dict)
    edge_curve_curve: Dict[int, int] = field(default_factory=dict)
    surface_curve_3d_curve: Dict[int, int] = field(default_factory=dict)
    cylindrical_surfaces: Dict[int, Tuple[Vec3, Vec3, float]] = field(default_factory=dict)
    conical_surfaces: Dict[int, Tuple[Vec3, Vec3, float, float]] = field(default_factory=dict)
    plane_surfaces: Dict[int, Tuple[Vec3, Vec3]] = field(default_factory=dict)
    cylinder_faces: List[CylinderFace] = field(default_factory=list)
    cone_faces: List[ConeFace] = field(default_factory=list)
    plane_faces: List[PlaneFace] = field(default_factory=list)

    # V13-fast: 拓扑索引缓存。借鉴盲孔脚本 StepParser 的处理方式，
    # 在解析阶段一次性建立 face->edges 与 edge->faces，避免后续每查相邻面
    # 都扫描全部 ADVANCED_FACE。该索引只加速，不改变识别规则。
    face_edge_curve_ids: Dict[int, List[int]] = field(default_factory=dict)
    edge_to_faces: Dict[int, List[int]] = field(default_factory=dict)
    edge_3d_curve_id_cache: Dict[int, Optional[int]] = field(default_factory=dict)
    face_edge_curve_type_cache: Dict[int, List[str]] = field(default_factory=dict)


# =========================
# STEP 文本解析
# =========================

ENTITY_RE = re.compile(r'#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*?)\)\s*;', re.I | re.S)


def read_step_text(path: Path) -> str:
    for enc in ('utf-8', 'utf-8-sig', 'gbk', 'latin-1'):
        try:
            return path.read_text(encoding=enc, errors='strict')
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding='latin-1', errors='ignore')


def parse_step_file(path: Path) -> StepModel:
    text = read_step_text(path)
    model = StepModel(path=path)

    for m in ENTITY_RE.finditer(text):
        eid = int(m.group(1))
        etype = m.group(2).upper()
        args = m.group(3).strip()
        model.raw_entities[eid] = (etype, args)

    # 基础几何实体
    for eid, (etype, args_text) in model.raw_entities.items():
        args = split_top_level_args(args_text)
        if etype == 'CARTESIAN_POINT' and len(args) >= 2:
            vals = parse_float_tuple(args[1])
            if len(vals) >= 3:
                model.points[eid] = (vals[0], vals[1], vals[2])
        elif etype == 'DIRECTION' and len(args) >= 2:
            vals = parse_float_tuple(args[1])
            if len(vals) >= 3:
                model.directions[eid] = normalize((vals[0], vals[1], vals[2]))

    for eid, (etype, args_text) in model.raw_entities.items():
        args = split_top_level_args(args_text)
        if etype == 'AXIS2_PLACEMENT_3D' and len(args) >= 4:
            refs = extract_refs(args_text)
            # 标准形式：AXIS2_PLACEMENT_3D('',#point,#axis,#ref_dir)
            if len(refs) >= 3:
                p = model.points.get(refs[0])
                axis = model.directions.get(refs[1])
                ref_dir = model.directions.get(refs[2])
                if p is not None and axis is not None:
                    model.placements3d[eid] = AxisPlacement3D(eid, p, axis, ref_dir)

    for eid, (etype, args_text) in model.raw_entities.items():
        args = split_top_level_args(args_text)
        if etype == 'CIRCLE' and len(args) >= 3:
            refs = extract_refs(args[1]) if len(args) > 1 else []
            if refs:
                placement = model.placements3d.get(refs[0])
                if placement is not None:
                    try:
                        radius = parse_float(args[2])
                    except Exception:
                        continue
                    model.circles3d[eid] = Circle3D(eid, placement.point, placement.axis, radius)
        elif etype == 'CYLINDRICAL_SURFACE' and len(args) >= 3:
            refs = extract_refs(args[1]) if len(args) > 1 else []
            if refs:
                placement = model.placements3d.get(refs[0])
                if placement is not None:
                    try:
                        radius = parse_float(args[2])
                    except Exception:
                        continue
                    model.cylindrical_surfaces[eid] = (placement.point, placement.axis, radius)
        elif etype == 'CONICAL_SURFACE' and len(args) >= 4:
            refs = extract_refs(args[1]) if len(args) > 1 else []
            if refs:
                placement = model.placements3d.get(refs[0])
                if placement is not None:
                    try:
                        radius = parse_float(args[2])
                        semi_angle = parse_float(args[3])
                    except Exception:
                        continue
                    model.conical_surfaces[eid] = (placement.point, placement.axis, radius, semi_angle)
        elif etype == 'PLANE' and len(args) >= 2:
            refs = extract_refs(args[1]) if len(args) > 1 else extract_refs(args_text)
            if refs:
                placement = model.placements3d.get(refs[0])
                if placement is not None:
                    model.plane_surfaces[eid] = (placement.point, placement.axis)

    # 拓扑实体
    for eid, (etype, args_text) in model.raw_entities.items():
        args = split_top_level_args(args_text)
        if etype == 'ADVANCED_FACE' and len(args) >= 3:
            # ADVANCED_FACE('',(#bound_refs),#surface,.T.)
            refs_in_bounds = extract_refs(args[1]) if len(args) > 1 else []
            surf_refs = extract_refs(args[-2]) if len(args) >= 2 else []
            if surf_refs:
                model.face_surface[eid] = surf_refs[0]
                model.face_bound_refs[eid] = refs_in_bounds
                same_token = args[-1].strip().upper() if args else ".T."
                model.face_same_sense[eid] = (same_token == ".T.")
        elif etype in ('FACE_BOUND', 'FACE_OUTER_BOUND') and len(args) >= 2:
            refs = extract_refs(args[1])
            if refs:
                model.face_bound_loop[eid] = refs[0]
        elif etype == 'EDGE_LOOP' and len(args) >= 2:
            refs = extract_refs(args[1])
            model.edge_loop_oriented_edges[eid] = refs
        elif etype == 'ORIENTED_EDGE' and len(args) >= 4:
            refs = extract_refs(args_text)
            # ORIENTED_EDGE('',*,*,#edge_curve,.T.) 一般只有一个引用
            if refs:
                model.oriented_edge_edge[eid] = refs[-1]
        elif etype == 'EDGE_CURVE' and len(args) >= 4:
            refs = extract_refs(args_text)
            # EDGE_CURVE('',#v1,#v2,#curve,.T.)，第 3 个引用是 curve
            if len(refs) >= 3:
                model.edge_curve_curve[eid] = refs[2]
        elif etype == 'SURFACE_CURVE' and len(args) >= 2:
            refs = extract_refs(args[1])
            if refs:
                model.surface_curve_3d_curve[eid] = refs[0]

    # V14-topology-filter：先构建拓扑索引。后续 get_face_circles / adjacent_faces_for_edge
    # 会直接走缓存，避免重复拆 face->bound->loop->edge。
    build_topology_indexes(model)

    # 构建面信息
    for face_id, surface_id in model.face_surface.items():
        circles = get_face_circles(model, face_id)
        if surface_id in model.cylindrical_surfaces:
            p, axis, radius = model.cylindrical_surfaces[surface_id]
            model.cylinder_faces.append(CylinderFace(face_id, surface_id, radius, p, axis, circles))
        elif surface_id in model.conical_surfaces:
            p, axis, radius, semi_angle = model.conical_surfaces[surface_id]
            model.cone_faces.append(ConeFace(face_id, surface_id, radius, semi_angle, p, axis, circles))
        elif surface_id in model.plane_surfaces:
            p, normal = model.plane_surfaces[surface_id]
            model.plane_faces.append(PlaneFace(face_id, surface_id, p, normal, circles))

    return model



def build_topology_indexes(model: StepModel) -> None:
    """一次性建立常用拓扑索引，功能等价于原来的逐次扫描。\n\n    加速点：\n    - face_edge_curve_ids: ADVANCED_FACE -> EDGE_CURVE 列表；\n    - edge_to_faces: EDGE_CURVE -> 相邻 ADVANCED_FACE 列表；\n    - edge_3d_curve_id_cache: EDGE_CURVE -> CIRCLE/LINE 等真实 3D 曲线；\n    - face_edge_curve_type_cache: ADVANCED_FACE -> 边界曲线类型。\n\n    这些索引借鉴盲孔识别脚本 StepParser 中 face_to_edge_curves、\n    edge_curve_to_faces 的思路，只改变查找方式，不改变识别条件。\n    """
    model.face_edge_curve_ids.clear()
    edge_to_faces_tmp: Dict[int, set] = {}

    for face_id in model.face_surface:
        edge_curve_ids: List[int] = []
        for bound_id in model.face_bound_refs.get(face_id, []):
            loop_id = model.face_bound_loop.get(bound_id)
            if loop_id is None:
                continue
            for oriented_edge_id in model.edge_loop_oriented_edges.get(loop_id, []):
                edge_curve_id = model.oriented_edge_edge.get(oriented_edge_id)
                if edge_curve_id is None:
                    continue
                edge_curve_ids.append(edge_curve_id)

        edge_curve_ids = unique_ints(edge_curve_ids)
        model.face_edge_curve_ids[face_id] = edge_curve_ids
        for edge_curve_id in edge_curve_ids:
            edge_to_faces_tmp.setdefault(edge_curve_id, set()).add(face_id)

    model.edge_to_faces = {edge_id: sorted(face_ids) for edge_id, face_ids in edge_to_faces_tmp.items()}

    model.edge_3d_curve_id_cache.clear()
    for edge_curve_id, curve_id in model.edge_curve_curve.items():
        real_curve_id = curve_id
        etype_args = model.raw_entities.get(curve_id)
        if etype_args is not None:
            etype, _ = etype_args
            if etype.upper() == 'SURFACE_CURVE':
                real_curve_id = model.surface_curve_3d_curve.get(curve_id)
        model.edge_3d_curve_id_cache[edge_curve_id] = real_curve_id

    model.face_edge_curve_type_cache.clear()
    for face_id, edge_ids in model.face_edge_curve_ids.items():
        types: List[str] = []
        for edge_id in edge_ids:
            curve_id = model.edge_3d_curve_id_cache.get(edge_id)
            if curve_id is None:
                types.append("UNKNOWN")
                continue
            ent = model.raw_entities.get(curve_id)
            types.append(ent[0].upper() if ent else "UNKNOWN")
        model.face_edge_curve_type_cache[face_id] = types

def get_face_edge_curve_ids(model: StepModel, face_id: int) -> List[int]:
    cached = model.face_edge_curve_ids.get(face_id)
    if cached is not None:
        return cached

    # 兼容兜底：理论上 parse_step_file() 后缓存一定存在。
    edge_curve_ids: List[int] = []
    for bound_id in model.face_bound_refs.get(face_id, []):
        loop_id = model.face_bound_loop.get(bound_id)
        if loop_id is None:
            continue
        for oriented_edge_id in model.edge_loop_oriented_edges.get(loop_id, []):
            edge_curve_id = model.oriented_edge_edge.get(oriented_edge_id)
            if edge_curve_id is not None:
                edge_curve_ids.append(edge_curve_id)
    edge_curve_ids = unique_ints(edge_curve_ids)
    model.face_edge_curve_ids[face_id] = edge_curve_ids
    return edge_curve_ids


def get_edge_3d_curve_id(model: StepModel, edge_curve_id: int) -> Optional[int]:
    if edge_curve_id in model.edge_3d_curve_id_cache:
        return model.edge_3d_curve_id_cache.get(edge_curve_id)

    curve_id = model.edge_curve_curve.get(edge_curve_id)
    if curve_id is None:
        model.edge_3d_curve_id_cache[edge_curve_id] = None
        return None
    etype_args = model.raw_entities.get(curve_id)
    if etype_args is None:
        model.edge_3d_curve_id_cache[edge_curve_id] = None
        return None
    etype, _ = etype_args
    if etype.upper() == 'SURFACE_CURVE':
        real_curve_id = model.surface_curve_3d_curve.get(curve_id)
    else:
        real_curve_id = curve_id
    model.edge_3d_curve_id_cache[edge_curve_id] = real_curve_id
    return real_curve_id


def get_face_circles(model: StepModel, face_id: int) -> List[Circle3D]:
    circles: List[Circle3D] = []
    for edge_curve_id in get_face_edge_curve_ids(model, face_id):
        c3d = get_edge_3d_curve_id(model, edge_curve_id)
        if c3d is not None and c3d in model.circles3d:
            circles.append(model.circles3d[c3d])
    # 去重
    out: List[Circle3D] = []
    seen = set()
    for c in circles:
        if c.id not in seen:
            seen.add(c.id)
            out.append(c)
    return out


# =========================
# 完整圆口/完整圆环判定辅助函数
# =========================

def _raw_entity(model: StepModel, eid: int) -> Optional[Tuple[str, str]]:
    return model.raw_entities.get(eid)


def _edge_vertex_refs(model: StepModel, edge_curve_id: int) -> List[int]:
    item = _raw_entity(model, edge_curve_id)
    if item is None:
        return []
    etype, args = item
    if etype.upper() != 'EDGE_CURVE':
        return []
    refs = extract_refs(args)
    if len(refs) < 2:
        return []
    return [refs[0], refs[1]]


def _vertex_point_ref(model: StepModel, vertex_id: int) -> Optional[int]:
    item = _raw_entity(model, vertex_id)
    if item is None:
        return None
    etype, args = item
    if etype.upper() != 'VERTEX_POINT':
        return None
    refs = extract_refs(args)
    return refs[0] if refs else None


def _same_vertex_point(model: StepModel, v1: int, v2: int) -> bool:
    if v1 == v2:
        return True
    p1 = _vertex_point_ref(model, v1)
    p2 = _vertex_point_ref(model, v2)
    if p1 is not None and p2 is not None and p1 == p2:
        return True
    xyz1 = model.points.get(p1) if p1 is not None else None
    xyz2 = model.points.get(p2) if p2 is not None else None
    return bool(xyz1 is not None and xyz2 is not None and close_point(xyz1, xyz2, AXIS_DIST_TOL))


def _circle_matches(circle: Circle3D, target: Circle3D, radius_tol: float = RADIUS_TOL) -> bool:
    return (
        close_float(circle.radius, target.radius, radius_tol)
        and close_point(circle.center, target.center, AXIS_DIST_TOL)
        and abs_parallel(circle.normal, target.normal)
    )


def _edge_circle(model: StepModel, edge_curve_id: int) -> Optional[Circle3D]:
    c3d = get_edge_3d_curve_id(model, edge_curve_id)
    if c3d is None:
        return None
    return model.circles3d.get(c3d)


def face_edges_matching_circle(model: StepModel, face_id: int, target: Circle3D, radius_tol: float = RADIUS_TOL) -> List[int]:
    edges = []
    for edge_id in get_face_edge_curve_ids(model, face_id):
        circle = _edge_circle(model, edge_id)
        if circle is None:
            continue
        if _circle_matches(circle, target, radius_tol):
            edges.append(edge_id)
    return unique_ints(edges)


def is_complete_circular_ring_on_face(model: StepModel, face_id: int, target: Circle3D, radius_tol: float = RADIUS_TOL) -> bool:
    """判断 face 上 target 对应的圆边是否构成完整闭合圆环。

    允许两种 STEP 表达：
    1. 单条 EDGE_CURVE 的起点/终点为同一 VERTEX_POINT，表示完整 CIRCLE；
    2. 多条同圆心、同半径、同法向的 CIRCLE 圆弧首尾闭合，顶点图中每个顶点度数为 2。

    只要目标圆被 LINE、ELLIPSE、B_SPLINE 等边界截断，或只是一个未闭合圆弧，就返回 False。
    """
    edges = face_edges_matching_circle(model, face_id, target, radius_tol)
    if not edges:
        return False

    for edge_id in edges:
        verts = _edge_vertex_refs(model, edge_id)
        if len(verts) >= 2 and _same_vertex_point(model, verts[0], verts[1]):
            return True

    # 多圆弧闭合：统计顶点点位的度数。
    degree = {}
    for edge_id in edges:
        verts = _edge_vertex_refs(model, edge_id)
        if len(verts) < 2:
            return False
        v1, v2 = verts[0], verts[1]
        p1 = _vertex_point_ref(model, v1) or v1
        p2 = _vertex_point_ref(model, v2) or v2
        degree[p1] = degree.get(p1, 0) + 1
        degree[p2] = degree.get(p2, 0) + 1

    return bool(degree) and all(v == 2 for v in degree.values())


def _circle_same_station(c1: Circle3D, c2: Circle3D) -> bool:
    return _circle_matches(c1, c2, max(RADIUS_TOL, 1e-5))


def cylinder_other_end_circles(cyl: CylinderFace, connection: Circle3D) -> List[Circle3D]:
    out = []
    for c in cyl.circles:
        if _circle_same_station(c, connection):
            continue
        if close_float(c.radius, cyl.radius, RADIUS_TOL) and same_axis(cyl.point, cyl.axis, c.center, c.normal):
            out.append(c)
    return out


def counterbore_has_complete_circular_mouths(model: StepModel, small_cyl: CylinderFace, big_cyl: CylinderFace, small_circle: Circle3D, big_circle: Circle3D) -> bool:
    """counterbore 的完整圆口/圆环约束。

    必须满足：
    - 台阶小圆和小圆柱连接处是完整圆环；
    - 台阶大圆和大圆柱连接处是完整圆环；
    - 大圆柱沉孔外侧入口还有一个完整大圆口。
    """
    if not REQUIRE_COMPLETE_CIRCULAR_MOUTH:
        return True

    if REQUIRE_COMPLETE_STEP_RINGS:
        if not is_complete_circular_ring_on_face(model, small_cyl.face_id, small_circle):
            return False
        if not is_complete_circular_ring_on_face(model, big_cyl.face_id, big_circle):
            return False
    outer_circles = cylinder_other_end_circles(big_cyl, big_circle)
    if not outer_circles:
        return False
    return any(is_complete_circular_ring_on_face(model, big_cyl.face_id, c) for c in outer_circles)


def plane_face_id_from_circle(model: StepModel, small_circle: Circle3D, big_circle: Circle3D) -> Optional[int]:
    # 仅作为兼容占位；真实台阶完整性在 counterbore_plane_rings_complete 中检查。
    return None


def counterbore_plane_rings_complete(model: StepModel, plane: PlaneFace, small_circle: Circle3D, big_circle: Circle3D) -> bool:
    if not REQUIRE_COMPLETE_STEP_RINGS:
        return True
    return (
        is_complete_circular_ring_on_face(model, plane.face_id, small_circle)
        and is_complete_circular_ring_on_face(model, plane.face_id, big_circle)
    )


def countersink_has_complete_circular_mouths(model: StepModel, cone: ConeFace, cyl: CylinderFace, cone_small: Circle3D, cone_big: Circle3D) -> bool:
    """countersink 的完整圆口/圆环约束。

    必须满足：
    - 圆锥大端入口是完整闭合圆；
    - 圆锥小端连接小圆柱处也是完整圆环；
    - 小圆柱连接处不能只是缺口圆弧。
    """
    if not REQUIRE_COMPLETE_CIRCULAR_MOUTH:
        return True
    if REQUIRE_COMPLETE_CONE_RINGS:
        if not is_complete_circular_ring_on_face(model, cone.face_id, cone_big):
            return False
        if not is_complete_circular_ring_on_face(model, cone.face_id, cone_small):
            return False
    if not is_complete_circular_ring_on_face(model, cyl.face_id, cone_small, max(RADIUS_TOL, 0.02 * cyl.radius)):
        return False
    return True



# =========================
# 特征识别辅助函数
# =========================

def cylinder_has_circle(cyl: CylinderFace, circle: Circle3D,
                        radius_tol: float = RADIUS_TOL) -> bool:
    if not close_float(cyl.radius, circle.radius, radius_tol):
        return False
    if not same_axis(cyl.point, cyl.axis, circle.center, circle.normal):
        return False
    for c in cyl.circles:
        if close_float(c.radius, circle.radius, radius_tol) and close_point(c.center, circle.center, AXIS_DIST_TOL):
            return True
    # 有些 STEP 导出边界不完整；只要圆心落在轴线上且半径匹配，可以作为弱连接。
    return axis_distance(cyl.point, cyl.axis, circle.center, cyl.axis) <= AXIS_DIST_TOL


def cylinder_t_values(cyl: CylinderFace) -> List[float]:
    vals = []
    for c in cyl.circles:
        if close_float(c.radius, cyl.radius, RADIUS_TOL) and same_axis(cyl.point, cyl.axis, c.center, c.normal):
            vals.append(project_t(c.center, cyl.point, cyl.axis))
    vals = sorted(vals)
    # 合并接近值
    merged: List[float] = []
    for v in vals:
        if not merged or abs(v - merged[-1]) > AXIS_DIST_TOL:
            merged.append(v)
    return merged


def cylinder_has_segment(cyl: CylinderFace) -> bool:
    return len(cylinder_t_values(cyl)) >= 2


def has_two_sides_around_step(cyl: CylinderFace, step_center: Vec3) -> bool:
    vals = cylinder_t_values(cyl)
    if len(vals) < 2:
        return True  # 弱化处理：缺少边界时不直接否决
    t0 = project_t(step_center, cyl.point, cyl.axis)
    return min(vals) - AXIS_DIST_TOL <= t0 <= max(vals) + AXIS_DIST_TOL


def cylinder_interval(cyl: CylinderFace) -> Optional[Tuple[float, float]]:
    vals = cylinder_t_values(cyl)
    if len(vals) < 2:
        return None
    return min(vals), max(vals)


def _interval_span(interval: Tuple[float, float]) -> float:
    return max(0.0, float(interval[1]) - float(interval[0]))


def _endpoint_side(interval: Tuple[float, float], t: float, tol: float) -> Optional[int]:
    """
    判断 t 是否位于圆柱轴向区间端点。
    返回 +1 表示该圆柱段从 t 向正轴方向延伸；返回 -1 表示从 t 向负轴方向延伸。
    如果 t 在区间中部或不在端点，返回 None。
    """
    a, b = interval
    if abs(t - a) <= tol:
        return +1
    if abs(t - b) <= tol:
        return -1
    return None


def counterbore_has_axial_adjacency(small_cyl: CylinderFace, big_cyl: CylinderFace, step_center: Vec3) -> bool:
    """
    counterbore 的关键约束：大圆柱沉孔段和小圆柱孔段必须位于台阶平面两侧。

    真正的圆柱沉孔：
        big interval:   [step, outer_opening]
        small interval: [inner_end, step]
    二者只在 step 处相接，不应沿同一轴向范围重叠。

    误检的 O-ring 槽、外凸套筒、螺钉状结构常表现为：
        big interval 与 small interval 基本相同或大面积重叠。
    这类结构虽然有“大圆柱 + 小圆柱 + 环形平面”，但不是给螺钉头嵌入的沉孔。
    """
    s_int = cylinder_interval(small_cyl)
    b_int = cylinder_interval(big_cyl)
    if s_int is None or b_int is None:
        return False

    axis = normalize(small_cyl.axis)
    step_t = project_t(step_center, small_cyl.point, axis)
    tol = max(AXIS_DIST_TOL * 5.0, min(_interval_span(s_int), _interval_span(b_int)) * 1.0e-3, 1.0e-5)

    s_side = _endpoint_side(s_int, step_t, tol)
    b_side = _endpoint_side(b_int, step_t, tol)
    if s_side is None or b_side is None:
        return False

    # 必须分别位于台阶两侧。若两者都从台阶向同一侧延伸，通常是同轴套筒/螺钉状外形。
    if s_side == b_side:
        return False

    overlap = max(0.0, min(s_int[1], b_int[1]) - max(s_int[0], b_int[0]))
    max_allowed = max(tol * 3.0, min(_interval_span(s_int), _interval_span(b_int)) * COUNTERBORE_MAX_INTERVAL_OVERLAP_RATIO)
    if overlap > max_allowed:
        return False

    return True



def _interval_overlap_length(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return max(0.0, min(float(a[1]), float(b[1])) - max(float(a[0]), float(b[0])))


def _combined_interval(*intervals: Optional[Tuple[float, float]]) -> Optional[Tuple[float, float]]:
    vals = [it for it in intervals if it is not None]
    if not vals:
        return None
    return min(it[0] for it in vals), max(it[1] for it in vals)


def _radius_between_for_obstruction(radius: float, inner_radius: float, outer_radius: float, tol: float) -> bool:
    """判断某个同轴圆柱半径是否落在沉头空间内部。

    - 小于 inner_radius：中心柱/更小孔穿过沉头空间，常见于螺钉状凸体或 O-ring 假阳性；
    - 介于 inner_radius 和 outer_radius：沉头空间中出现额外台阶/套筒；
    - 接近 inner_radius 或 outer_radius：可能只是同一孔壁被拆面，不作为阻塞。
    """
    if radius >= outer_radius - tol:
        return False
    if abs(radius - inner_radius) <= tol:
        return False
    if abs(radius - outer_radius) <= tol:
        return False
    return radius < outer_radius - tol


def _has_nested_coaxial_cylinder_obstruction(
    model: StepModel,
    axis_point: Vec3,
    axis_dir: Vec3,
    selected_face_ids: Iterable[int],
    inner_radius: float,
    outer_radius: float,
    feature_interval: Tuple[float, float],
) -> bool:
    """排除沉头空间内部存在其他同轴圆柱体/圆柱孔壁的假阳性。

    真实 countersink/counterbore 应该是一个干净的“外大内小”内凹空间：
    外侧锥面或大圆柱面直接过渡到小圆柱孔。若同一轴线上还有额外圆柱面
    穿过这个轴向范围，并且半径不是当前小孔或外侧沉头半径，就说明中间
    可能有 O-ring 槽、套筒、螺钉头、凸柱或嵌套圆柱结构。
    """
    if not REJECT_NESTED_COAXIAL_CYLINDERS:
        return False

    selected = set(selected_face_ids)
    span = _interval_span(feature_interval)
    if span <= 0:
        return False
    tol_r = max(RADIUS_TOL, abs(float(outer_radius)) * 1.0e-3, 1.0e-5)
    overlap_threshold = max(NESTED_COAXIAL_MIN_OVERLAP_ABS, span * NESTED_COAXIAL_INTERVAL_OVERLAP_RATIO)

    for other in model.cylinder_faces:
        if other.face_id in selected:
            continue
        if not same_axis(axis_point, axis_dir, other.point, other.axis):
            continue
        if not _radius_between_for_obstruction(float(other.radius), float(inner_radius), float(outer_radius), tol_r):
            continue
        other_interval = cylinder_interval(other)
        if other_interval is None:
            continue
        overlap = _interval_overlap_length(other_interval, feature_interval)
        if overlap > overlap_threshold:
            return True
    return False


def countersink_has_no_nested_coaxial_obstruction(model: StepModel, cone: ConeFace, cyl: CylinderFace, cone_small: Circle3D, cone_big: Circle3D) -> bool:
    c_int = cylinder_interval(cyl)
    if c_int is None:
        return False
    axis = normalize(cyl.axis)
    t_small = project_t(cone_small.center, cyl.point, axis)
    t_big = project_t(cone_big.center, cyl.point, axis)
    cone_interval = (min(t_small, t_big), max(t_small, t_big))
    feature_interval = _combined_interval(c_int, cone_interval)
    if feature_interval is None:
        return False
    return not _has_nested_coaxial_cylinder_obstruction(
        model=model,
        axis_point=cyl.point,
        axis_dir=cyl.axis,
        selected_face_ids=[cone.face_id, cyl.face_id],
        inner_radius=cyl.radius,
        outer_radius=cone_big.radius,
        feature_interval=feature_interval,
    )


def counterbore_has_no_nested_coaxial_obstruction(model: StepModel, plane: PlaneFace, small_cyl: CylinderFace, big_cyl: CylinderFace) -> bool:
    s_int = cylinder_interval(small_cyl)
    b_int = cylinder_interval(big_cyl)
    feature_interval = _combined_interval(s_int, b_int)
    if feature_interval is None:
        return False
    return not _has_nested_coaxial_cylinder_obstruction(
        model=model,
        axis_point=small_cyl.point,
        axis_dir=small_cyl.axis,
        selected_face_ids=[plane.face_id, small_cyl.face_id, big_cyl.face_id],
        inner_radius=small_cyl.radius,
        outer_radius=big_cyl.radius,
        feature_interval=feature_interval,
    )


def plane_is_local_annular_step(plane: PlaneFace, small_circle: Circle3D, big_circle: Circle3D) -> bool:
    """
    counterbore 的台阶平面应是局部环形底面，而不是一张包含多孔/槽/轮廓的大共享平面。
    只允许该平面上与当前台阶同心的两个半径环参与判别；若同一平面还包含
    明显不同中心的圆环，通常说明它是 O-ring 槽、端盖面或共享平面，默认排除。
    """
    if not COUNTERBORE_REQUIRE_LOCAL_ANNULAR_STEP:
        return True
    center = small_circle.center
    local = []
    foreign = []
    for c in plane.circles:
        if close_point(c.center, center, AXIS_DIST_TOL) and abs_parallel(c.normal, small_circle.normal):
            local.append(c)
        else:
            foreign.append(c)
    if foreign:
        return False
    radii = sorted({round(float(c.radius), 6) for c in local})
    if len(radii) != 2:
        return False
    if not close_float(radii[0], small_circle.radius, max(RADIUS_TOL, 1e-5)):
        return False
    if not close_float(radii[1], big_circle.radius, max(RADIUS_TOL, 1e-5)):
        return False
    return True


def plane_annular_circle_pairs(plane: PlaneFace) -> List[Tuple[Circle3D, Circle3D]]:
    """返回 plane 上的同心圆对，格式为 (small, big)。"""
    pairs: List[Tuple[Circle3D, Circle3D]] = []
    circles = plane.circles
    for i in range(len(circles)):
        for j in range(i + 1, len(circles)):
            c1, c2 = circles[i], circles[j]
            if not abs_parallel(c1.normal, c2.normal):
                continue
            if not close_point(c1.center, c2.center, AXIS_DIST_TOL):
                continue
            if not abs_parallel(plane.normal, c1.normal):
                continue
            if close_float(c1.radius, c2.radius, RADIUS_TOL):
                continue
            small, big = (c1, c2) if c1.radius < c2.radius else (c2, c1)
            if big.radius / max(small.radius, 1e-12) < COUNTERBORE_MIN_RADIUS_RATIO:
                continue
            if big.radius - small.radius < COUNTERBORE_MIN_RADIAL_GROWTH:
                continue
            pairs.append((small, big))
    return pairs


def find_counterbore_holes(model: StepModel) -> List[Tuple[PlaneFace, CylinderFace, CylinderFace]]:
    """寻找圆柱沉孔：返回 (台阶平面, 小圆柱面, 大圆柱面)。"""
    holes: List[Tuple[PlaneFace, CylinderFace, CylinderFace]] = []
    seen_keys = set()

    for plane in model.plane_faces:
        for small_circle, big_circle in plane_annular_circle_pairs(plane):
            if not plane_is_local_annular_step(plane, small_circle, big_circle):
                continue
            if not counterbore_plane_rings_complete(model, plane, small_circle, big_circle):
                continue
            small_candidates = []
            big_candidates = []

            for cyl in model.cylinder_faces:
                if cylinder_has_circle(cyl, small_circle):
                    small_candidates.append(cyl)
                if cylinder_has_circle(cyl, big_circle):
                    big_candidates.append(cyl)

            for small_cyl in small_candidates:
                for big_cyl in big_candidates:
                    if small_cyl.face_id == big_cyl.face_id:
                        continue
                    if not same_axis(small_cyl.point, small_cyl.axis, big_cyl.point, big_cyl.axis):
                        continue
                    if not same_axis(small_cyl.point, small_cyl.axis, plane.point, plane.normal):
                        # plane.point 不一定在孔轴线上，所以用环形圆心检查更可靠
                        if axis_distance(small_cyl.point, small_cyl.axis, small_circle.center, small_cyl.axis) > AXIS_DIST_TOL:
                            continue
                    if big_cyl.radius <= small_cyl.radius:
                        continue
                    if big_cyl.radius / max(small_cyl.radius, 1e-12) < COUNTERBORE_MIN_RADIUS_RATIO:
                        continue
                    if big_cyl.radius - small_cyl.radius < COUNTERBORE_MIN_RADIAL_GROWTH:
                        continue
                    if not all_curved_faces_are_inner_cavity(model, [small_cyl.face_id, big_cyl.face_id]):
                        continue
                    # 小孔段和大孔段至少应具有圆柱段属性，弱检查即可。
                    if not cylinder_has_segment(small_cyl):
                        continue
                    if not cylinder_has_segment(big_cyl):
                        continue
                    if COUNTERBORE_REQUIRE_AXIAL_ADJACENCY:
                        if not counterbore_has_axial_adjacency(small_cyl, big_cyl, small_circle.center):
                            continue
                    else:
                        if not has_two_sides_around_step(small_cyl, small_circle.center):
                            continue
                        if not has_two_sides_around_step(big_cyl, big_circle.center):
                            continue
                    if not counterbore_has_complete_circular_mouths(model, small_cyl, big_cyl, small_circle, big_circle):
                        continue
                    if not counterbore_has_no_nested_coaxial_obstruction(model, plane, small_cyl, big_cyl):
                        continue

                    # 以轴线位置 + 台阶位置 + 半径组合去重，避免同一孔被多个边界重复计数。
                    axis_origin = small_cyl.point
                    axis_dir = normalize(small_cyl.axis)
                    step_t = project_t(small_circle.center, axis_origin, axis_dir)
                    key = (
                        round(axis_distance((0.0, 0.0, 0.0), axis_dir, axis_origin, axis_dir), 4),
                        round(step_t, 4),
                        round(small_cyl.radius, 4),
                        round(big_cyl.radius, 4),
                        plane.face_id,
                    )
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    holes.append((plane, small_cyl, big_cyl))

    return holes


def cone_boundary_radius_info(cone: ConeFace) -> Optional[Tuple[Circle3D, Circle3D, float]]:
    """返回锥面边界中的小圆、大圆和轴向深度。"""
    valid = []
    for c in cone.circles:
        if same_axis(cone.point, cone.axis, c.center, c.normal):
            valid.append(c)
    if len(valid) < 2:
        return None
    valid = sorted(valid, key=lambda c: c.radius)
    small = valid[0]
    big = valid[-1]
    if big.radius <= small.radius:
        return None
    depth = abs(project_t(big.center, cone.point, cone.axis) - project_t(small.center, cone.point, cone.axis))
    return small, big, depth



def countersink_cone_has_valid_geometry(cone: ConeFace, cone_small: Circle3D, cone_big: Circle3D, depth: float) -> bool:
    """countersink 圆锥面的基础几何合法性检查。

    机械标准通常用“大端直径 + 夹角 + 配合紧固件尺寸”定义 countersink，
    没有一个通用固定的 R_big / R_small 比例。因此这里不再使用半径比例作为强判据。

    本函数只确认它确实是一个外大内小的圆锥段：
    1. 大端半径必须大于小端半径，超过数值容差；
    2. 锥面轴向深度必须大于数值容差；
    3. 大端圆、小端圆与圆锥轴线同轴。

    是否真属于 countersink_hole，继续由外部入口、完整圆口、同轴小圆柱、轴向相邻、
    内凹/非外凸等拓扑规则判断，而不是由半径比例判断。
    """
    small_r = max(float(cone_small.radius), 1e-12)
    big_r = float(cone_big.radius)
    radial_growth = big_r - small_r

    radius_tol = max(RADIUS_TOL * 2.0, small_r * 1.0e-5, 1.0e-6)
    depth_tol = max(AXIS_DIST_TOL * 2.0, small_r * 1.0e-5, 1.0e-6)

    if radial_growth <= radius_tol:
        return False
    if float(depth) <= depth_tol:
        return False
    if not same_axis(cone.point, cone.axis, cone_small.center, cone_small.normal):
        return False
    if not same_axis(cone.point, cone.axis, cone_big.center, cone_big.normal):
        return False
    return True

def is_real_countersink_cone(cone: ConeFace, cone_small: Circle3D, cone_big: Circle3D, depth: float) -> bool:
    """判断圆锥面是否具备 countersink 的基础几何条件。

    这里不再使用固定半径比例作为标准。真正的过滤交给：
    外部入口、完整圆口、同轴小圆柱、轴向相邻、内凹非外凸、无嵌套同轴圆柱等规则。
    """
    return countersink_cone_has_valid_geometry(cone, cone_small, cone_big, depth)


def countersink_has_axial_adjacency(cone: ConeFace, cyl: CylinderFace, cone_small: Circle3D, cone_big: Circle3D) -> bool:
    """
    countersink 的圆锥沉头段和小圆柱孔段也必须轴向相邻。
    小圆柱孔应该从圆锥小端向圆锥大端的相反方向延伸，不能与圆锥段/外凸结构同向重叠。
    """
    c_int = cylinder_interval(cyl)
    if c_int is None:
        return False
    axis = normalize(cyl.axis)
    t_small = project_t(cone_small.center, cyl.point, axis)
    t_big = project_t(cone_big.center, cyl.point, axis)
    if abs(t_big - t_small) <= AXIS_DIST_TOL:
        return False
    tol = max(AXIS_DIST_TOL * 5.0, _interval_span(c_int) * 1.0e-3, 1.0e-5)
    cyl_side = _endpoint_side(c_int, t_small, tol)
    if cyl_side is None:
        return False
    cone_side = +1 if t_big > t_small else -1
    # 小圆柱应从 cone_small 朝 cone_big 的反方向延伸。
    return cyl_side != cone_side


def find_countersink_holes(model: StepModel) -> List[Tuple[ConeFace, CylinderFace]]:
    """寻找锥形沉头孔：返回 (圆锥沉头面, 小圆柱面)。

    重要：这里不再采用“只要 CONICAL_SURFACE + 小圆柱孔就算沉头孔”的宽松规则。
    必须同时满足明显半径放大、足够锥面深度、与小圆柱孔同轴并连接小端圆，
    以排除非孔口结构。
    """
    holes: List[Tuple[ConeFace, CylinderFace]] = []
    seen_keys = set()

    for cone in model.cone_faces:
        info = cone_boundary_radius_info(cone)
        if info is None:
            continue
        cone_small, cone_big, depth = info

        if not is_real_countersink_cone(cone, cone_small, cone_big, depth):
            continue

        for cyl in model.cylinder_faces:
            if not same_axis(cone.point, cone.axis, cyl.point, cyl.axis):
                continue
            if not all_curved_faces_are_inner_cavity(model, [cone.face_id, cyl.face_id]):
                continue
            if not close_float(cyl.radius, cone_small.radius, max(RADIUS_TOL, 0.02 * cyl.radius)):
                continue
            if not cylinder_has_segment(cyl):
                continue
            # 小圆柱应连接锥面的小端圆。
            if not cylinder_has_circle(cyl, cone_small, max(RADIUS_TOL, 0.02 * cyl.radius)):
                continue
            if not countersink_has_axial_adjacency(cone, cyl, cone_small, cone_big):
                continue
            if not countersink_has_complete_circular_mouths(model, cone, cyl, cone_small, cone_big):
                continue
            if not countersink_has_no_nested_coaxial_obstruction(model, cone, cyl, cone_small, cone_big):
                continue
            key = (
                round(cyl.radius, 4),
                round(cone_big.radius, 4),
                round(project_t(cone_small.center, cyl.point, cyl.axis), 4),
                cone.face_id,
                cyl.face_id,
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            holes.append((cone, cyl))

    return holes



# =============================================================================
# 沉头孔 / 沉孔 STP exact-face exporter
# =============================================================================

import os
import datetime as _dt
from collections import Counter


# =============================================================================
# 可选配置区：如果不想从命令行传参，可以直接在这里填写路径。
# 命令行参数优先级更高；留空字符串表示使用默认逻辑。
# =============================================================================
INPUT_STP_PATH = ""
OUTPUT_STP_PATH = ""
OUTPUT_LOG_PATH = ""
OUTPUT_STP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "countersunk_stp_export")
OUTPUT_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "countersunk_log_export")
OUTPUT_JSON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "countersunk_json_export")

# 可选：借鉴盲孔 v15.23 识别标准。
# 该补充用于把“倒角入口盲孔/倒角入口复合底盲孔/多接缝倒角盲孔”等识别为 countersink_hole。
# 为空时默认在脚本同目录查找 detect_blind_holes_and_export_stp_v15_23_inner_wall_orientation.py。
BLIND_V15_SCRIPT_PATH = ""


STEP_SUFFIXES = ('.stp', '.step', '.stp.txt', '.step.txt')


def split_header_data_tail(text: str):
    m1 = re.search(r"\bDATA\s*;", text, re.I)
    if not m1:
        raise ValueError("输入文件不是标准 STEP 文本：未找到 DATA;")
    m2 = re.search(r"\bENDSEC\s*;", text[m1.end():], re.I)
    data_start = m1.end()
    if not m2:
        return text[:data_start], text[data_start:], ""
    data_end = m1.end() + m2.start()
    return text[:data_start], text[data_start:data_end], text[data_end:]


def find_record_end(text: str, start: int) -> int:
    in_string = False
    i = start
    while i < len(text):
        ch = text[i]
        if ch == "'":
            if in_string and i + 1 < len(text) and text[i + 1] == "'":
                i += 2
                continue
            in_string = not in_string
        elif ch == ";" and not in_string:
            return i + 1
        i += 1
    raise ValueError(f"STEP 实体记录未正常结束，起点位置：{start}")


def parse_entity_records_from_data(data: str):
    records = {}
    order = []
    for m in re.finditer(r"#(\d+)\s*=", data):
        eid = int(m.group(1))
        try:
            end = find_record_end(data, m.start())
        except ValueError:
            break
        raw = data[m.start():end].strip()
        rhs = raw.split("=", 1)[1].strip()
        if rhs.startswith("("):
            etype = "COMPLEX"
        else:
            tm = re.match(r"([A-Z0-9_]+)\s*\(", rhs, re.I)
            etype = tm.group(1).upper() if tm else "UNKNOWN"
        refs = [int(x) for x in re.findall(r"#(\d+)", raw)]
        records[eid] = {"id": eid, "type": etype, "raw": raw, "refs": refs}
        order.append(eid)
    return records, order


def dependency_closure(records, seeds):
    seen = set()
    stack = list(seeds)
    while stack:
        eid = stack.pop()
        if eid in seen or eid not in records:
            continue
        seen.add(eid)
        stack.extend(records[eid]["refs"])
    return seen


def unique_keep_order(values):
    seen = set()
    out = []
    for value in values:
        if value is None or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def format_ref_list(refs, per_line=10, indent="    "):
    refs = list(refs)
    if not refs:
        return ""
    tokens = [f"#{x}" for x in refs]
    lines = []
    for i in range(0, len(tokens), per_line):
        chunk = tokens[i:i + per_line]
        line = ", ".join(chunk)
        if i + per_line < len(tokens):
            line += ","
        lines.append(line)
    if len(lines) == 1:
        return lines[0]
    return ("\n" + indent).join(lines)


class ExactFaceStepExporter:
    """把原始 ADVANCED_FACE 原样导出为 OPEN_SHELL 可视化文件。

    该导出方式借鉴盲孔 exact-face 思路：
    不重建几何，不重新拟合圆柱/圆锥，而是保留原 STEP 中的 ADVANCED_FACE
    以及其依赖的 EDGE_LOOP、EDGE_CURVE、CIRCLE、SURFACE 等实体。
    """

    def __init__(self, input_path):
        self.input_path = input_path
        self.text = Path(input_path).read_text(encoding="utf-8", errors="ignore")
        _, self.data, _ = split_header_data_tail(self.text)
        self.records, self.order = parse_entity_records_from_data(self.data)
        self.next_id = max(self.records) + 1 if self.records else 1
        self.new_records = []

    def add(self, rhs):
        eid = self.next_id
        self.next_id += 1
        self.new_records.append(f"#{eid} = {rhs};")
        return eid

    def _num(self, value):
        v = float(value)
        if abs(v) < 1e-14:
            v = 0.0
        return f"{v:.15g}"

    def point(self, xyz):
        return self.add(f"CARTESIAN_POINT( '', ( {self._num(xyz[0])}, {self._num(xyz[1])}, {self._num(xyz[2])} ) )")

    def direction(self, xyz):
        return self.add(f"DIRECTION( '', ( {self._num(xyz[0])}, {self._num(xyz[1])}, {self._num(xyz[2])} ) )")

    def export(self, selected_faces, output_path, label="countersunk_counterbore_features"):
        selected_faces = unique_keep_order(selected_faces)
        missing = [f for f in selected_faces if f not in self.records]
        if missing:
            raise RuntimeError(f"选择的 ADVANCED_FACE 在原 STEP 中不存在：{missing}")

        keep = dependency_closure(self.records, selected_faces)
        kept_records = [self.records[eid]["raw"] for eid in self.order if eid in keep]

        face_refs = format_ref_list(selected_faces, per_line=10, indent="      ")
        shell = self.add(f"OPEN_SHELL( '{label}_faces', ( {face_refs} ) )")
        model = self.add(f"SHELL_BASED_SURFACE_MODEL( '{label}', ( #{shell} ) )")
        origin = self.point((0.0, 0.0, 0.0))
        zdir = self.direction((0.0, 0.0, 1.0))
        xdir = self.direction((1.0, 0.0, 0.0))
        place = self.add(f"AXIS2_PLACEMENT_3D( '', #{origin}, #{zdir}, #{xdir} )")
        length_unit = self.add("( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) )")
        angle_unit = self.add("( NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.) )")
        solid_angle_unit = self.add("( NAMED_UNIT(*) SI_UNIT($,.STERADIAN.) SOLID_ANGLE_UNIT() )")
        uncertainty = self.add(
            f"UNCERTAINTY_MEASURE_WITH_UNIT( LENGTH_MEASURE(1.0E-07), #{length_unit}, "
            "'distance_accuracy_value', 'confusion accuracy' )"
        )
        context = self.add(
            "( GEOMETRIC_REPRESENTATION_CONTEXT(3) "
            f"GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT((#{uncertainty})) "
            f"GLOBAL_UNIT_ASSIGNED_CONTEXT((#{length_unit},#{angle_unit},#{solid_angle_unit})) "
            "REPRESENTATION_CONTEXT('NONE','WORKSPACE') )"
        )
        rep = self.add(f"MANIFOLD_SURFACE_SHAPE_REPRESENTATION( '{label}', ( #{place}, #{model} ), #{context} )")
        app = self.add("APPLICATION_CONTEXT( 'automotive_design' )")
        self.add(f"APPLICATION_PROTOCOL_DEFINITION( 'international standard', 'automotive_design', 2000, #{app} )")
        prod_ctx = self.add(f"PRODUCT_CONTEXT( '', #{app}, 'mechanical' )")
        prod = self.add(f"PRODUCT( '{label}', '{label}', '', ( #{prod_ctx} ) )")
        form = self.add(f"PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE( '1', '', #{prod}, .NOT_KNOWN. )")
        pd_ctx = self.add(f"PRODUCT_DEFINITION_CONTEXT( 'part definition', #{app}, 'design' )")
        pd = self.add(f"PRODUCT_DEFINITION( 'design', '', #{form}, #{pd_ctx} )")
        shape = self.add(f"PRODUCT_DEFINITION_SHAPE( '', '', #{pd} )")
        self.add(f"SHAPE_DEFINITION_REPRESENTATION( #{shape}, #{rep} )")

        now = _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        filename = os.path.basename(output_path).replace("'", "_")
        header = f"""ISO-10303-21;
HEADER;
FILE_DESCRIPTION( ( 'countersunk/counterbore exact-face export' ), '2;1' );
FILE_NAME( '{filename}', '{now}', ( 'countersunk-feature-export' ), ( 'ChatGPT generated script' ), ' ', 'exact-face-countersunk-exporter', ' ' );
FILE_SCHEMA( ( 'AUTOMOTIVE_DESIGN' ) );
ENDSEC;
DATA;
"""
        body = "\n".join(kept_records + self.new_records)
        out = header + body + "\nENDSEC;\nEND-ISO-10303-21;\n"

        out_dir = os.path.dirname(os.path.abspath(output_path))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(output_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(out)

        return {
            "selected_faces": selected_faces,
            "dependency_entity_count": len(kept_records),
            "wrapper_entity_count": len(self.new_records),
            "total_entity_count": len(kept_records) + len(self.new_records),
            "open_shell_id": shell,
            "surface_model_id": model,
        }


def face_type_counter(model: StepModel, face_ids: List[int]) -> Counter:
    counter = Counter()
    for face_id in face_ids:
        surface_id = model.face_surface.get(face_id)
        etype = "UNKNOWN"
        if surface_id in model.cylindrical_surfaces:
            etype = "CYLINDRICAL_SURFACE"
        elif surface_id in model.conical_surfaces:
            etype = "CONICAL_SURFACE"
        elif surface_id in model.plane_surfaces:
            etype = "PLANE"
        counter[etype] += 1
    return counter




def face_is_curved_surface(model: StepModel, face_id: int) -> bool:
    sid = model.face_surface.get(face_id)
    return sid in model.cylindrical_surfaces or sid in model.conical_surfaces


def curved_face_is_inner_cavity(model: StepModel, face_id: int) -> bool:
    """严格方向模式下的曲面方向检查。

    注意：ADVANCED_FACE 的 .T./.F. 不是“孔/凸”的绝对标签。
    它只表示拓扑面方向是否跟随基础曲面的自然参数化方向。
    因此默认不启用这个函数作为硬过滤；只有 --strict-inner-sense 才会要求曲面为 .F.。
    """
    if not face_is_curved_surface(model, face_id):
        return True
    if not REQUIRE_INNER_CAVITY_FACE_ORIENTATION:
        return True
    same = model.face_same_sense.get(face_id)
    if same is None:
        return False
    return same is False


def all_curved_faces_are_inner_cavity(model: StepModel, face_ids: Iterable[int]) -> bool:
    if not REQUIRE_INNER_CAVITY_FACE_ORIENTATION:
        return True
    return all(curved_face_is_inner_cavity(model, fid) for fid in face_ids if face_is_curved_surface(model, fid))


def cylinder_face_is_inner_cavity(model: StepModel, cyl: CylinderFace) -> bool:
    return curved_face_is_inner_cavity(model, cyl.face_id)


def cone_face_is_inner_cavity(model: StepModel, cone: ConeFace) -> bool:
    return curved_face_is_inner_cavity(model, cone.face_id)


def cylinder_group_is_inner_cavity(model: StepModel, group: dict) -> bool:
    return all(cylinder_face_is_inner_cavity(model, cyl) for cyl in group.get("cyls", []))


def curved_face_is_outer_sense(model: StepModel, face_id: int) -> bool:
    """曲面 ADVANCED_FACE 是否为 .T.。

    这里只把 .T. 作为“外凸实体候选”的辅助证据，不能单独据此否定候选孔。
    """
    if not face_is_curved_surface(model, face_id):
        return False
    return model.face_same_sense.get(face_id) is True


def all_curved_faces_are_outer_sense(model: StepModel, face_ids: Iterable[int]) -> bool:
    curved = [fid for fid in face_ids if face_is_curved_surface(model, fid)]
    return bool(curved) and all(curved_face_is_outer_sense(model, fid) for fid in curved)


def local_cap_faces_from_feature_faces(model: StepModel, face_ids: Iterable[int]) -> List[int]:
    """从候选导出面中提取局部圆形端盖面。

    这个函数只识别小圆柱另一端的局部圆形封闭面；大外表面/贯通出口面不会被算作端盖。
    """
    out = []
    for fid in face_ids:
        sid = model.face_surface.get(fid)
        if sid not in model.plane_surfaces:
            continue
        plane = next((p for p in model.plane_faces if p.face_id == fid), None)
        if plane is None:
            continue
        for c in plane.circles:
            if plane_is_local_closed_cap(model, fid, c):
                out.append(fid)
                break
    return unique_keep_order(out)


def is_probable_outer_sense_capped_protrusion(
    model: StepModel,
    curved_face_ids: Iterable[int],
    cap_face_ids: Iterable[int],
) -> bool:
    """排除“实心凸柱/螺钉头/铆钉头”误识别。

    逻辑：
    - 不把 .T. 直接等同于外凸；
    - 只有当候选曲面全部是 .T.，并且存在局部圆形端盖时，才认为它更像实心凸柱；
    - 贯通型沉头孔没有局部端盖，因此不会受这个规则影响；
    - 真实盲型沉头孔如果导出方向异常，也可以通过 --disable-protrusion-sense-filter 关闭该过滤。
    """
    if not REJECT_OUTER_SENSE_CAPPED_PROTRUSION:
        return False
    caps = list(cap_face_ids or [])
    if not caps:
        return False
    return all_curved_faces_are_outer_sense(model, curved_face_ids)




def has_any_inner_sense_curved_face(model: StepModel, face_ids: Iterable[int]) -> bool:
    """候选曲面中是否至少存在一个 .F. 内凹孔壁证据。

    这不是全局硬规则，只用于外凸 counterbore 风险过滤。
    盲孔脚本对标准平底盲孔使用 same_sense=True 外凸过滤；这里借鉴该思想，
    但只作用于 counterbore 这类最容易把台阶轴误识别为沉孔的分支。
    """
    for fid in face_ids or []:
        if face_is_curved_surface(model, fid) and model.face_same_sense.get(fid) is False:
            return True
    return False


def is_probable_outer_sense_counterbore_protrusion(
    model: StepModel,
    curved_face_ids: Iterable[int],
) -> bool:
    """排除外凸台阶轴 / 凸圆柱被误识别为 counterbore_hole。

    当前 counterbore 规则会识别：
        大圆柱 + 小圆柱 + 环形台阶平面，或
        大圆柱 + 锥面过渡 + 小圆柱。
    外凸台阶轴在 STEP 拓扑上也可能满足这些形态条件。

    借鉴盲孔脚本的内凹孔壁证明：
    - 标准内凹孔壁通常至少有 .F. 曲面作为 cavity 证据；
    - 如果一个 counterbore 候选的所有曲面都是 .T.，且没有任何 .F. 曲面，
      说明它更像外凸轴肩/凸圆柱/套筒外表面，而不是从外表面向内凹进去的沉孔。

    该规则只用于 counterbore 分支，不直接作用于全部 countersink，避免误删个别导出方向异常的真实锥形沉头孔。
    """
    if not REJECT_OUTER_SENSE_CAPPED_PROTRUSION:
        return False
    if not REJECT_ALL_OUTER_SENSE_COUNTERBORE:
        return False
    curved = unique_keep_order([fid for fid in (curved_face_ids or []) if face_is_curved_surface(model, fid)])
    if not curved:
        return False
    if has_any_inner_sense_curved_face(model, curved):
        return False
    return all_curved_faces_are_outer_sense(model, curved)

def adjacent_faces_for_edge(model: StepModel, edge_curve_id: int, exclude_face: int) -> List[int]:
    # V13-fast：直接使用 parse_step_file 阶段建立的 EDGE_CURVE -> faces 索引。
    # 原逻辑每次都扫描所有 ADVANCED_FACE，复杂装配体会非常慢。
    faces = model.edge_to_faces.get(edge_curve_id)
    if faces is not None:
        return [face_id for face_id in faces if face_id != exclude_face]

    # 兜底：如果模型不是通过 parse_step_file 创建，仍保持原行为。
    out = []
    for face_id in model.face_surface:
        if face_id == exclude_face:
            continue
        if edge_curve_id in get_face_edge_curve_ids(model, face_id):
            out.append(face_id)
    return unique_keep_order(out)


def face_bound_count_simple(model: StepModel, face_id: int) -> int:
    """返回 ADVANCED_FACE 的 FACE_BOUND / FACE_OUTER_BOUND 数量。"""
    return len(model.face_bound_refs.get(face_id, []) or [])


def face_edge_curve_types(model: StepModel, face_id: int) -> List[str]:
    """返回 face 边界中 EDGE_CURVE 对应的基础曲线类型。"""
    cached = model.face_edge_curve_type_cache.get(face_id)
    if cached is not None:
        return cached
    types = []
    for edge_id in get_face_edge_curve_ids(model, face_id):
        curve_id = get_edge_3d_curve_id(model, edge_id)
        if curve_id is None:
            types.append("UNKNOWN")
            continue
        ent = model.raw_entities.get(curve_id)
        types.append(ent[0].upper() if ent else "UNKNOWN")
    model.face_edge_curve_type_cache[face_id] = types
    return types


def plane_is_local_closed_cap(model: StepModel, face_id: int, terminal_circle: Circle3D) -> bool:
    """判断一个 PLANE 是否是小圆柱末端的局部封闭底面。

    贯穿孔的另一侧通常连接到零件外表面的大 PLANE，这类面往往有多个
    FACE_BOUND，或者包含外轮廓 LINE/B_SPLINE 等复杂边界。它只是出口面，
    不能作为沉头孔/沉孔的“底面”导出。

    真正的封闭底面应是局部圆形盖面：
    1. 只有一个边界环；
    2. 该边界环是完整圆；
    3. 不混入 LINE/ELLIPSE/B_SPLINE 等外轮廓或槽边界。
    """
    sid = model.face_surface.get(face_id)
    if sid not in model.plane_surfaces:
        return False

    if face_bound_count_simple(model, face_id) != 1:
        return False

    edge_types = face_edge_curve_types(model, face_id)
    if not edge_types:
        return False
    if any(t != "CIRCLE" for t in edge_types):
        return False

    if not is_complete_circular_ring_on_face(model, face_id, terminal_circle):
        return False

    # 局部圆形底面的所有圆边都应与 terminal_circle 同心同半径。
    # 如果同一平面还有其他半径/其他中心的圆边，通常是共享平面或结构面。
    for edge_id in get_face_edge_curve_ids(model, face_id):
        circle = _edge_circle(model, edge_id)
        if circle is None:
            continue
        if not _circle_matches(circle, terminal_circle, max(RADIUS_TOL, 1e-5)):
            return False

    return True


def cone_is_local_closed_tip(model: StepModel, face_id: int, terminal_circle: Circle3D, source_cyl_face: int) -> bool:
    """保守判断 CONICAL_SURFACE 是否为封闭型小孔末端。

    该函数只作为导出增强，不影响沉头孔/沉孔判别。为了避免把贯通孔出口倒角
    或外部锥形过渡面当作底面，只在圆锥面没有继续连到外部大平面时才允许导出。
    """
    sid = model.face_surface.get(face_id)
    if sid not in model.conical_surfaces:
        return False
    if not is_complete_circular_ring_on_face(model, face_id, terminal_circle, max(RADIUS_TOL, 1e-5)):
        return False

    # 如果该圆锥面还连接到明显外部平面/复杂平面，通常是贯通孔出口倒角，不导出。
    for edge_id in get_face_edge_curve_ids(model, face_id):
        for adj in adjacent_faces_for_edge(model, edge_id, face_id):
            if adj == source_cyl_face:
                continue
            adj_sid = model.face_surface.get(adj)
            if adj_sid in model.plane_surfaces and not plane_is_local_closed_cap(model, adj, terminal_circle):
                return False
    return True


def cylinder_terminal_faces_for_export(model: StepModel, cyl: CylinderFace, used_edge_centers: List[Vec3]) -> List[int]:
    """为盲型沉头孔/沉孔补充小圆柱的封闭底面。

    关键修正：
    - 如果小圆柱另一端是贯穿出口，不导出出口平面；
    - 只有另一端确认为局部封闭底面时，才额外导出底面；
    - 这样贯通型 counterbore/countersink 只导出沉头结构本身，
      不会把零件外表面的大平面一起选中。
    """
    terminal_faces = []
    used_centers = list(used_edge_centers or [])

    for c in cyl.circles:
        if any(close_point(c.center, uc, max(AXIS_DIST_TOL, 1e-3)) for uc in used_centers):
            continue

        for edge_id in get_face_edge_curve_ids(model, cyl.face_id):
            c3d = get_edge_3d_curve_id(model, edge_id)
            circle = model.circles3d.get(c3d)
            if circle is None:
                continue
            if not close_float(circle.radius, c.radius, RADIUS_TOL):
                continue
            if not close_point(circle.center, c.center, AXIS_DIST_TOL):
                continue

            for adj in adjacent_faces_for_edge(model, edge_id, cyl.face_id):
                sid = model.face_surface.get(adj)
                if sid in model.plane_surfaces:
                    if plane_is_local_closed_cap(model, adj, circle):
                        terminal_faces.append(adj)
                elif sid in model.conical_surfaces:
                    if cone_is_local_closed_tip(model, adj, circle, cyl.face_id):
                        terminal_faces.append(adj)

    return unique_keep_order(terminal_faces)



# =============================================================================
# NCTI Cell ID 映射与 JSON 标注输出
# =============================================================================

def load_ncti_doc(stp_path: Path):
    """
    通过项目全局配置中的 NCTI 对象加载 STP 模型文档。

    该函数采用延迟导入，避免没有 NCTI 环境时影响普通 STP 导出功能。
    需要生成 cell_id JSON 时，必须保证：
    1. config/config_load.py 可正常导入；
    2. global_scope 中已加载 NCTI 和 doc；
    3. 本机/服务器 NCTI SDK/DLL 环境可用。
    """
    from config.config_load import global_scope

    if "NCTI" not in global_scope or "doc" not in global_scope:
        raise RuntimeError("NCTI 未加载成功，请确认 config/system_config.json 与 SDK/DLL 环境。")

    ncti = global_scope["NCTI"]
    doc = ncti.Document()
    doc.New("OCC", "DCM", "GMSH")
    doc.ResetCaseResult()
    doc.SetCreateGeGeom(1)
    doc.SetImportAssemelFile(1)
    doc.RunCommand("cmd_ncti_import_file", str(stp_path))
    return doc


def _step_face_to_cell_id_map(step_face_ids, cell_ids):
    """
    STEP ADVANCED_FACE id 到 NCTI Cell ID 的顺序映射。

    如果 NCTI 返回的是 0..N-1 的连续编号，则直接按 STEP 面顺序映射；
    否则仍按 NCTI 返回 face_ids 的顺序进行一一对应。
    """
    if len(step_face_ids) != len(cell_ids):
        raise ValueError(
            f"STEP面数量({len(step_face_ids)})与NCTI面数量({len(cell_ids)})不一致，无法使用顺序映射。"
        )

    expected_cell_ids = set(range(len(step_face_ids)))
    if set(cell_ids) == expected_cell_ids:
        return {step_face_id: index for index, step_face_id in enumerate(step_face_ids)}

    return {step_face_id: cell_ids[index] for index, step_face_id in enumerate(step_face_ids)}


def _closed_shell_face_groups_from_model(model: StepModel):
    """
    从当前 STEP 文本解析模型中提取 CLOSED_SHELL 分组。

    如果文件没有 CLOSED_SHELL，则回退为把所有 ADVANCED_FACE 当作一个整体。
    """
    groups = []
    for shell_id, item in model.raw_entities.items():
        etype, params = item
        if etype.upper() != "CLOSED_SHELL":
            continue
        face_ids = [ref for ref in extract_refs(params) if ref in model.face_surface]
        if face_ids:
            groups.append({"shell_id": shell_id, "face_ids": face_ids, "count": len(face_ids)})

    if groups:
        return groups

    return [
        {
            "shell_id": None,
            "face_ids": list(model.face_surface.keys()),
            "count": len(model.face_surface),
        }
    ]


def _find_face_objects(doc):
    """提取 NCTI 内核解析后的对象及对应 Cell IDs。"""
    candidates = []
    for name in list(doc.AllNames() or []):
        try:
            face_ids = list(doc.FindAllFaces(name) or [])
        except Exception:
            face_ids = []
        candidates.append({"name": name, "face_ids": face_ids, "count": len(face_ids)})
    return candidates


def _build_step_face_to_cell_id_map(model: StepModel, doc):
    """
    构建 STEP ADVANCED_FACE id -> NCTI Cell ID 的映射字典。
    逻辑参考盲孔 JSON 生成脚本，但适配当前 StepModel 数据结构。
    """
    object_candidates = _find_face_objects(doc)
    shell_groups = _closed_shell_face_groups_from_model(model)

    total_shell_faces = sum(shell["count"] for shell in shell_groups)
    whole_body_matches = [item for item in object_candidates if item["count"] == total_shell_faces]

    if len(whole_body_matches) == 1:
        flat_step_faces = []
        for shell in shell_groups:
            flat_step_faces.extend(shell["face_ids"])
        return _step_face_to_cell_id_map(flat_step_faces, whole_body_matches[0]["face_ids"])

    available = [item for item in object_candidates if item["count"] > 0]
    matches = {}
    used_names = set()

    for shell in shell_groups:
        same_count = [
            item
            for item in available
            if item["count"] == shell["count"] and item["name"] not in used_names
        ]
        if len(same_count) == 1:
            item = same_count[0]
            matches[shell["shell_id"]] = item
            used_names.add(item["name"])

    if not matches and len(shell_groups) == 1:
        shell = shell_groups[0]
        same_count = [item for item in object_candidates if item["count"] == shell["count"]]
        if len(same_count) == 1:
            matches[shell["shell_id"]] = same_count[0]

    if not matches:
        step_counts = ", ".join(f"shell#{item['shell_id']}:{item['count']}" for item in shell_groups)
        obj_counts = ", ".join(f"{item['name']}:{item['count']}" for item in object_candidates) or "无对象"
        raise ValueError(
            "无法将 STEP 的 CLOSED_SHELL 面数量匹配到 NCTI 对象。"
            f" STEP壳面数: {step_counts}; NCTI对象面数: {obj_counts}。"
        )

    step_face_to_cell_id = {}
    for shell in shell_groups:
        item = matches.get(shell["shell_id"])
        if item is None:
            continue
        face_map = _step_face_to_cell_id_map(shell["face_ids"], item["face_ids"])
        step_face_to_cell_id.update(face_map)

    return step_face_to_cell_id


def write_feature_cell_json(
    stp_path: Path,
    model: StepModel,
    selected_step_faces: List[int],
    output_json_path: Path,
    title: str = "countersunk_hole_prediction",
    write_empty: bool = True,
) -> Optional[Path]:
    """
    将识别到的 STEP 面编号转换为 NCTI Cell ID，并输出指定 JSON 文件。

    JSON 格式：
    {
        "title": "countersunk_hole_prediction",
        "content": {
            "feature_1": 5,
            "feature_2": 18
        }
    }

    注意：
    - selected_step_faces 是当前脚本识别/导出的 ADVANCED_FACE id；
    - JSON 中写入的是 NCTI Cell ID；
    - 如果没有识别到面，默认仍输出空 content，便于批量任务保持一文件一 JSON。
    """
    output_json_path.parent.mkdir(parents=True, exist_ok=True)

    if not selected_step_faces:
        if not write_empty:
            return None
        json_data = {"title": title, "content": {}}
        with open(output_json_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=4)
            f.write("\n")
        return output_json_path

    doc = load_ncti_doc(stp_path)
    try:
        face_map = _build_step_face_to_cell_id_map(model, doc)
        ncti_cell_ids = []
        for step_face_id in selected_step_faces:
            cell_id = face_map.get(step_face_id)
            if cell_id is not None:
                ncti_cell_ids.append(cell_id)
    finally:
        doc.Close()

    content_dict = {f"feature_{i + 1}": cid for i, cid in enumerate(ncti_cell_ids)}

    json_data = {
        "title": title,
        "content": content_dict
    }

    with open(output_json_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=4)
        f.write("\n")

    return output_json_path


def default_json_path(src: Path) -> Path:
    stem = main_stem_for_step(src)
    return Path(OUTPUT_JSON_DIR) / f"{stem}.json"


# =============================================================================
# V7 复杂/装配体 counterbore 补充识别：分裂圆柱面 + 多级台阶
# =============================================================================

def _edges_form_complete_circular_ring(model: StepModel, edge_ids: List[int]) -> bool:
    """多个 EDGE_CURVE 是否共同形成完整闭合圆环。"""
    edge_ids = unique_ints(edge_ids)
    if not edge_ids:
        return False
    for edge_id in edge_ids:
        verts = _edge_vertex_refs(model, edge_id)
        if len(verts) >= 2 and _same_vertex_point(model, verts[0], verts[1]):
            return True

    degree = {}
    for edge_id in edge_ids:
        verts = _edge_vertex_refs(model, edge_id)
        if len(verts) < 2:
            return False
        for v in verts[:2]:
            pr = _vertex_point_ref(model, v) or v
            degree[pr] = degree.get(pr, 0) + 1
    return bool(degree) and all(v == 2 for v in degree.values())


def _cylinder_group_ring_complete(model: StepModel, cyls: List[CylinderFace], target: Circle3D) -> bool:
    """允许一个完整圆柱孔壁被拆成多个 ADVANCED_FACE。"""
    edges = []
    for cyl in cyls:
        edges.extend(face_edges_matching_circle(model, cyl.face_id, target))
    return _edges_form_complete_circular_ring(model, edges)


def _make_cylinder_groups(model: StepModel) -> List[dict]:
    """按同轴线 + 同半径合并被 STEP 拆开的圆柱面。"""
    groups = []
    for cyl in model.cylinder_faces:
        placed = False
        for g in groups:
            if close_float(cyl.radius, g["radius"], max(RADIUS_TOL, abs(g["radius"]) * 1e-6)):
                if same_axis(cyl.point, cyl.axis, g["axis_point"], g["axis_dir"]):
                    g["cyls"].append(cyl)
                    placed = True
                    break
        if not placed:
            groups.append({
                "id": len(groups),
                "radius": cyl.radius,
                "axis_point": cyl.point,
                "axis_dir": normalize(cyl.axis),
                "cyls": [cyl],
            })
    return groups


def _group_has_circle(group: dict, circle: Circle3D) -> bool:
    for cyl in group["cyls"]:
        if cylinder_has_circle(cyl, circle):
            return True
    return False


def _cylinder_interval_on_axis(cyl: CylinderFace, origin: Vec3, axis: Vec3) -> Optional[Tuple[float, float]]:
    vals = []
    axis = normalize(axis)
    for c in cyl.circles:
        if close_float(c.radius, cyl.radius, RADIUS_TOL) and same_axis(cyl.point, cyl.axis, c.center, c.normal):
            vals.append(project_t(c.center, origin, axis))
    if not vals:
        return None
    return (min(vals), max(vals))


def _group_interval_on_axis(group: dict, origin: Vec3, axis: Vec3) -> Optional[Tuple[float, float]]:
    vals = []
    for cyl in group["cyls"]:
        interval = _cylinder_interval_on_axis(cyl, origin, axis)
        if interval is not None:
            vals.extend(interval)
    if not vals:
        return None
    return (min(vals), max(vals))


def _interval_has_endpoint(interval: Tuple[float, float], t: float, tol: float) -> bool:
    return abs(interval[0] - t) <= tol or abs(interval[1] - t) <= tol


def _counterbore_connection_relation(
    small_group: dict,
    big_group: dict,
    step_center: Vec3,
) -> Optional[str]:
    """判断两个同轴圆柱组在同一环形平面处的关系。

    返回：
    - axial_step：标准轴向台阶，大孔段和小孔段位于台阶两侧；
    - coterminal：两段在同一外侧端面共端，常见于装配体/多级贯通 counterbore；
    - None：不是可接受的 counterbore 连接。
    """
    origin = small_group["axis_point"]
    axis = normalize(small_group["axis_dir"])
    s_int = _group_interval_on_axis(small_group, origin, axis)
    b_int = _group_interval_on_axis(big_group, origin, axis)
    if s_int is None or b_int is None:
        return None

    step_t = project_t(step_center, origin, axis)
    tol = max(
        AXIS_DIST_TOL * 10.0,
        min(_interval_span(s_int), _interval_span(b_int)) * 1.0e-3,
        1.0e-5,
    )

    s_side = _endpoint_side(s_int, step_t, tol)
    b_side = _endpoint_side(b_int, step_t, tol)
    if s_side is not None and b_side is not None and s_side != b_side:
        return "axial_step"

    # 装配体复杂贯通沉孔常见情况：
    # 两个同轴圆柱组在外侧端面共端，形成一个环形端面/口部层级。
    # 这不是 O-ring 槽的充分条件；后续还要求该组件中至少存在一个 axial_step。
    if _interval_has_endpoint(s_int, step_t, tol) and _interval_has_endpoint(b_int, step_t, tol):
        return "coterminal"

    return None


def _build_grouped_counterbore_connections(model: StepModel) -> List[dict]:
    groups = _make_cylinder_groups(model)
    connections = []
    seen = set()

    for plane in model.plane_faces:
        for small_circle, big_circle in plane_annular_circle_pairs(plane):
            small_groups = [g for g in groups if close_float(g["radius"], small_circle.radius, RADIUS_TOL) and _group_has_circle(g, small_circle)]
            big_groups = [g for g in groups if close_float(g["radius"], big_circle.radius, RADIUS_TOL) and _group_has_circle(g, big_circle)]

            for sg in small_groups:
                for bg in big_groups:
                    if sg["id"] == bg["id"]:
                        continue
                    if bg["radius"] <= sg["radius"]:
                        continue
                    if bg["radius"] / max(sg["radius"], 1e-12) < COUNTERBORE_MIN_RADIUS_RATIO:
                        continue
                    if bg["radius"] - sg["radius"] < COUNTERBORE_MIN_RADIAL_GROWTH:
                        continue
                    if not same_axis(sg["axis_point"], sg["axis_dir"], bg["axis_point"], bg["axis_dir"]):
                        continue
                    if not cylinder_group_is_inner_cavity(model, sg) or not cylinder_group_is_inner_cavity(model, bg):
                        continue

                    # 分裂面补充规则：圆环可以由多个 ADVANCED_FACE 的圆弧合成完整圆。
                    if REQUIRE_COMPLETE_CIRCULAR_MOUTH:
                        if not _cylinder_group_ring_complete(model, sg["cyls"], small_circle):
                            continue
                        if not _cylinder_group_ring_complete(model, bg["cyls"], big_circle):
                            continue

                    relation = _counterbore_connection_relation(sg, bg, small_circle.center)
                    if relation is None:
                        continue

                    key = (plane.face_id, sg["id"], bg["id"], round(small_circle.radius, 5), round(big_circle.radius, 5), relation)
                    if key in seen:
                        continue
                    seen.add(key)

                    connections.append({
                        "plane": plane,
                        "small_group": sg,
                        "big_group": bg,
                        "small_circle": small_circle,
                        "big_circle": big_circle,
                        "relation": relation,
                    })
    return connections


def find_grouped_counterbore_holes(model: StepModel) -> List[dict]:
    """补充识别复杂装配体中的 counterbore。

    解决两类 v6 漏检：
    1. 同一个完整圆柱孔壁被 STEP 拆成多个 ADVANCED_FACE；
    2. 贯通型/多级 counterbore 不是单个“大圆柱 + 小圆柱 + 一个台阶平面”，
       而是多个同轴圆柱级通过多个环形平面连接。

    约束：
    - 必须同轴；
    - 每个参与圆环必须完整闭合；
    - 连通组件中至少有一个真正 axial_step，避免只把同端面的套筒/O-ring 结构识别为沉孔；
    - coterminal 连接只能作为已有 axial_step 组件的外层补充。
    """
    connections = _build_grouped_counterbore_connections(model)
    if not connections:
        return []

    # 构建以 cylinder group 为节点的图。
    by_node = {}
    graph = {}
    for conn in connections:
        s_id = conn["small_group"]["id"]
        b_id = conn["big_group"]["id"]
        by_node[s_id] = conn["small_group"]
        by_node[b_id] = conn["big_group"]
        graph.setdefault(s_id, set()).add(b_id)
        graph.setdefault(b_id, set()).add(s_id)

    visited = set()
    out = []

    for start in list(graph):
        if start in visited:
            continue
        stack = [start]
        component_nodes = set()
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            component_nodes.add(node)
            stack.extend(graph.get(node, set()) - visited)

        comp_conns = [
            conn for conn in connections
            if conn["small_group"]["id"] in component_nodes and conn["big_group"]["id"] in component_nodes
        ]

        if not any(conn["relation"] == "axial_step" for conn in comp_conns):
            continue

        radii = [by_node[n]["radius"] for n in component_nodes]
        if len(set(round(r, 5) for r in radii)) < 2:
            continue
        if max(radii) / max(min(radii), 1e-12) < COUNTERBORE_MIN_RADIUS_RATIO:
            continue

        cyl_faces = []
        for n in component_nodes:
            cyl_faces.extend([c.face_id for c in by_node[n]["cyls"]])

        plane_faces = [conn["plane"].face_id for conn in comp_conns]

        # 最外层和最内层用于日志展示。
        sorted_nodes = sorted(component_nodes, key=lambda n: by_node[n]["radius"])
        small_node = sorted_nodes[0]
        big_node = sorted_nodes[-1]
        small_group = by_node[small_node]
        big_group = by_node[big_node]
        representative_step = next((c for c in comp_conns if c["relation"] == "axial_step"), comp_conns[0])

        face_ids = unique_keep_order(cyl_faces + plane_faces)

        out.append({
            "kind": "counterbore_hole",
            "multi_stage_counterbore": True,
            "faces": face_ids,
            "cylinder_group_faces": unique_keep_order(cyl_faces),
            "step_plane_faces": unique_keep_order(plane_faces),
            "connection_relations": [conn["relation"] for conn in comp_conns],
            "big_cylinder_face": big_group["cyls"][0].face_id,
            "big_cylinder_surface": big_group["cyls"][0].surface_id,
            "big_radius": big_group["radius"],
            "small_cylinder_face": small_group["cyls"][0].face_id,
            "small_cylinder_surface": small_group["cyls"][0].surface_id,
            "small_radius": small_group["radius"],
            "step_plane_face": representative_step["plane"].face_id,
            "step_plane_surface": representative_step["plane"].surface_id,
            "axis_point": small_group["axis_point"],
            "axis_direction": small_group["axis_dir"],
            "reason": "复杂/装配体多级 counterbore：同轴圆柱孔壁被拆成多个 ADVANCED_FACE，多个完整圆环台阶共同构成贯通型圆柱沉孔。"
        })

    # 去重：同一组核心圆柱面只保留一次。
    unique = []
    seen_faces = set()
    for item in sorted(out, key=lambda x: (x["small_radius"], x["big_radius"], min(x["faces"] or [0]))):
        key = tuple(sorted(item["cylinder_group_faces"]))
        if key in seen_faces:
            continue
        seen_faces.add(key)
        unique.append(item)
    return unique

def _counterbore_feature_duplicate(existing_features: List[dict], candidate: dict) -> bool:
    cand_cyl_faces = set(candidate.get("cylinder_group_faces") or [])
    cand_faces = set(candidate.get("faces") or [])
    for feat in existing_features:
        if feat.get("kind") != "counterbore_hole":
            continue
        existing_faces = set(feat.get("faces") or [])
        # 标准三面 counterbore 已覆盖时，不再重复加入 grouped 版本。
        if cand_faces and cand_faces <= existing_faces:
            return True
        if cand_cyl_faces and cand_cyl_faces <= existing_faces:
            return True
        # 同一内外半径、同一轴线的简单重复。
        if (
            close_float(float(feat.get("small_radius") or -1), float(candidate.get("small_radius") or -2), max(RADIUS_TOL, 1e-5))
            and close_float(float(feat.get("big_radius") or -1), float(candidate.get("big_radius") or -2), max(RADIUS_TOL, 1e-5))
            and same_axis(
                feat.get("axis_point") or (0.0, 0.0, 0.0),
                feat.get("axis_direction") or (0.0, 0.0, 1.0),
                candidate.get("axis_point") or (0.0, 0.0, 0.0),
                candidate.get("axis_direction") or (0.0, 0.0, 1.0),
            )
        ):
            return True
    return False




# =============================================================================
# V8.2 补充：带倒角/锥面过渡的 counterbore 识别；只导出连接大小圆柱的最近过渡锥面
# =============================================================================

def _face_bound_stats(model: StepModel, face_id: int) -> Tuple[int, int, int]:
    """返回 (outer_bound_count, total_bound_count, total_edge_count)。"""
    outer = 0
    total = 0
    edge_count = 0
    for bound_id in model.face_bound_refs.get(face_id, []):
        total += 1
        etype, _ = model.raw_entities.get(bound_id, ("", ""))
        if etype.upper() == "FACE_OUTER_BOUND":
            outer += 1
        loop_id = model.face_bound_loop.get(bound_id)
        if loop_id is not None:
            edge_count += len(model.edge_loop_oriented_edges.get(loop_id, []))
    return outer, total, edge_count


def _plane_is_external_like(model: StepModel, face_id: int) -> bool:
    """判断 PLANE 是否更像零件外表面。

    这里只作为“孔口是否通向外部”的辅助证据。
    普通局部台阶平面一般是 1~2 个圆边界；大外表面通常有外轮廓、
    多个孔环、槽边或较复杂的 FACE_BOUND。
    """
    surface_id = model.face_surface.get(face_id)
    if surface_id not in model.plane_surfaces:
        return False
    outer, total, edge_count = _face_bound_stats(model, face_id)
    if total >= 2 and edge_count >= 3:
        return True
    if edge_count >= 4 and outer >= 1:
        return True
    plane = next((p for p in model.plane_faces if p.face_id == face_id), None)
    if plane is not None and len(plane.circles) >= 2:
        return True
    return False


def _edge_circle_for_face(model: StepModel, edge_id: int) -> Optional[Circle3D]:
    c3d = get_edge_3d_curve_id(model, edge_id)
    if c3d is None:
        return None
    return model.circles3d.get(c3d)


def _circle_key(c: Circle3D, ndigits=5):
    return (
        round(float(c.radius), ndigits),
        tuple(round(float(x), ndigits) for x in c.center),
        tuple(round(float(x), ndigits) for x in normalize(c.normal)),
    )


def _circles_same(c1: Circle3D, c2: Circle3D, radius_tol=RADIUS_TOL) -> bool:
    return (
        close_float(c1.radius, c2.radius, radius_tol)
        and close_point(c1.center, c2.center, AXIS_DIST_TOL)
        and abs_parallel(c1.normal, c2.normal)
    )


def _make_cylinder_segment_groups(model: StepModel) -> List[dict]:
    """按同轴、同半径、轴向区间相近/重合合并分裂圆柱面。

    不把同一轴线上前后两个独立沉孔段合并成一个组。
    这比 v7 的同轴同半径全局合并更适合识别 DVI 这类前后两端都有沉台的零件。
    """
    groups = []
    for cyl in model.cylinder_faces:
        interval = cylinder_interval(cyl)
        if interval is None:
            continue
        placed = False
        for g in groups:
            if not close_float(cyl.radius, g["radius"], max(RADIUS_TOL, abs(g["radius"]) * 1e-6)):
                continue
            if not same_axis(cyl.point, cyl.axis, g["axis_point"], g["axis_dir"]):
                continue
            # 把 cyl interval 投影到当前 group 轴坐标系下比较。
            c_vals = []
            for cir in cyl.circles:
                if close_float(cir.radius, cyl.radius, RADIUS_TOL):
                    c_vals.append(project_t(cir.center, g["axis_point"], g["axis_dir"]))
            if len(c_vals) < 2:
                continue
            c_int = (min(c_vals), max(c_vals))
            g_int = g["interval"]
            tol = max(AXIS_DIST_TOL * 10.0, min(_interval_span(g_int), _interval_span(c_int)) * 1e-2, 1e-5)
            # 只合并轴向重合或几乎相同的分裂面；不合并前后两个不同沉孔段。
            if c_int[0] <= g_int[1] + tol and g_int[0] <= c_int[1] + tol:
                g["cyls"].append(cyl)
                g["interval"] = (min(g_int[0], c_int[0]), max(g_int[1], c_int[1]))
                placed = True
                break
        if not placed:
            groups.append({
                "id": len(groups),
                "radius": cyl.radius,
                "axis_point": cyl.point,
                "axis_dir": normalize(cyl.axis),
                "cyls": [cyl],
                "interval": interval,
            })
    return groups


def _segment_group_has_circle(g: dict, target: Circle3D) -> bool:
    for cyl in g.get("cyls", []):
        if cylinder_has_circle(cyl, target):
            return True
    return False


def _segment_group_ring_complete(model: StepModel, g: dict, target: Circle3D) -> bool:
    edges = []
    for cyl in g.get("cyls", []):
        edges.extend(face_edges_matching_circle(model, cyl.face_id, target))
    return _edges_form_complete_circular_ring(model, edges)


def _group_interval_from_stored(g: dict) -> Optional[Tuple[float, float]]:
    return g.get("interval")


def _group_attaches_at_circle_on_opposite_side(g: dict, circle: Circle3D, other_circle: Circle3D) -> bool:
    """检查圆柱组是否以 circle 为端点，且位于过渡面另一侧。"""
    interval = _group_interval_from_stored(g)
    if interval is None:
        return False
    axis = normalize(g["axis_dir"])
    t_circle = project_t(circle.center, g["axis_point"], axis)
    t_other = project_t(other_circle.center, g["axis_point"], axis)
    tol = max(AXIS_DIST_TOL * 10.0, _interval_span(interval) * 1e-3, 1e-5)
    side = _endpoint_side(interval, t_circle, tol)
    if side is None:
        return False
    transition_side = +1 if t_other > t_circle else -1
    # 圆柱段应从连接圆向过渡面反方向延伸。
    return side != transition_side


def _edge_adjacent_faces(model: StepModel, edge_id: int, exclude_face: int) -> List[int]:
    return adjacent_faces_for_edge(model, edge_id, exclude_face)


def _circle_edge_reaches_external_plane(model: StepModel, face_id: int, circle: Circle3D, max_depth: int = 1) -> bool:
    """从某个圆边出发，判断是否能到达外部 PLANE。

    支持：
    - 圆柱边直接接外部平面；
    - 圆柱边接一个 CONICAL_SURFACE，再一跳接外部平面。
    """
    start_edges = face_edges_matching_circle(model, face_id, circle)
    if not start_edges:
        return False

    seen_faces = {face_id}
    frontier = []
    for edge_id in start_edges:
        for adj in _edge_adjacent_faces(model, edge_id, face_id):
            frontier.append((adj, 0))
    while frontier:
        f, depth = frontier.pop(0)
        if f in seen_faces:
            continue
        seen_faces.add(f)
        sid = model.face_surface.get(f)
        if sid in model.plane_surfaces and _plane_is_external_like(model, f):
            return True
        if depth >= max_depth:
            continue
        # 只允许通过圆锥/圆角入口过渡面继续追踪，避免沿着复杂装配体乱跑。
        if sid not in model.conical_surfaces:
            continue
        for e in get_face_edge_curve_ids(model, f):
            for nxt in _edge_adjacent_faces(model, e, f):
                if nxt not in seen_faces:
                    frontier.append((nxt, depth + 1))
    return False


def _group_has_external_opening(model: StepModel, g: dict, exclude_circle: Optional[Circle3D] = None) -> bool:
    for cyl in g.get("cyls", []):
        for c in cyl.circles:
            if not close_float(c.radius, cyl.radius, RADIUS_TOL):
                continue
            if exclude_circle is not None and _circles_same(c, exclude_circle):
                continue
            if not _segment_group_ring_complete(model, g, c):
                continue
            if _circle_edge_reaches_external_plane(model, cyl.face_id, c, max_depth=1):
                return True
    return False


def _cone_between_segment_groups(model: StepModel, cone: ConeFace, small_g: dict, big_g: dict) -> Optional[dict]:
    """判断一个 CONICAL_SURFACE 是否连接了小圆柱组和大圆柱组。

    注意：复杂 STEP 中一个完整圆锥过渡面经常被拆成两个 ADVANCED_FACE，
    因此这里不要求单个 cone face 的圆边本身完整闭合；完整性由两侧
    圆柱组的完整圆环来保证。后续会把同一过渡位置的多个 cone face
    合并到一个 feature 里。
    """
    info = cone_boundary_radius_info(cone)
    if info is None:
        return None
    cone_small, cone_big, depth = info
    if depth is None or depth <= AXIS_DIST_TOL:
        return None
    if not same_axis(small_g["axis_point"], small_g["axis_dir"], big_g["axis_point"], big_g["axis_dir"]):
        return None
    if not same_axis(small_g["axis_point"], small_g["axis_dir"], cone.point, cone.axis):
        if axis_distance(small_g["axis_point"], small_g["axis_dir"], cone_small.center, small_g["axis_dir"]) > AXIS_DIST_TOL:
            return None
    if not close_float(small_g["radius"], cone_small.radius, max(RADIUS_TOL, abs(cone_small.radius) * 1e-5)):
        return None
    if not close_float(big_g["radius"], cone_big.radius, max(RADIUS_TOL, abs(cone_big.radius) * 1e-5)):
        return None
    if not _segment_group_has_circle(small_g, cone_small):
        return None
    if not _segment_group_has_circle(big_g, cone_big):
        return None
    if REQUIRE_COMPLETE_CIRCULAR_MOUTH:
        if not _segment_group_ring_complete(model, small_g, cone_small):
            return None
        if not _segment_group_ring_complete(model, big_g, cone_big):
            return None
    if not _group_attaches_at_circle_on_opposite_side(small_g, cone_small, cone_big):
        return None
    if not _group_attaches_at_circle_on_opposite_side(big_g, cone_big, cone_small):
        return None
    return {"cone": cone, "cone_small": cone_small, "cone_big": cone_big, "depth": depth}


def _group_external_opening_transition_faces(model: StepModel, g: dict, exclude_circle: Optional[Circle3D] = None) -> List[int]:
    """返回大圆柱入口处通向外部平面的过渡锥面 face。

    如果大圆柱直接接外部 PLANE，则返回空列表；
    如果大圆柱通过 CONICAL_SURFACE 再接外部 PLANE，则返回这些 cone face。
    """
    faces = []
    for cyl in g.get("cyls", []):
        for c in cyl.circles:
            if not close_float(c.radius, cyl.radius, RADIUS_TOL):
                continue
            if exclude_circle is not None and _circles_same(c, exclude_circle):
                continue
            if not _segment_group_ring_complete(model, g, c):
                continue
            for edge_id in face_edges_matching_circle(model, cyl.face_id, c):
                for adj in _edge_adjacent_faces(model, edge_id, cyl.face_id):
                    sid = model.face_surface.get(adj)
                    if sid in model.conical_surfaces:
                        # 该 cone 是否一跳通向外部平面
                        for e2 in get_face_edge_curve_ids(model, adj):
                            for nxt in _edge_adjacent_faces(model, e2, adj):
                                nsid = model.face_surface.get(nxt)
                                if nsid in model.plane_surfaces and _plane_is_external_like(model, nxt):
                                    faces.append(adj)
    return unique_keep_order(faces)



def _group_may_lie_on_cone_axis(group: dict, cone: ConeFace, circle: Circle3D) -> bool:
    """用于 chamfered counterbore 的候选预筛选。\n\n    与 _cone_between_segment_groups 中的轴线条件保持一致：\n    group 与 cone 同轴，或者目标圆心落在 group 轴线上。\n    """
    if same_axis(group["axis_point"], group["axis_dir"], cone.point, cone.axis):
        return True
    return axis_distance(group["axis_point"], group["axis_dir"], circle.center, group["axis_dir"]) <= AXIS_DIST_TOL


def _circle_lookup_key_for_index(circle: Circle3D, ndigits: int = 5):
    """用于候选检索的圆截面 key。

    这里只按圆心和半径建索引，不把法向作为强 key。
    原因是同一个物理圆边在 STEP 中法向可能正反相反；真正判定仍由
    _segment_group_has_circle / same_axis / _circles_same 等函数完成。
    """
    return (
        round(float(circle.radius), ndigits),
        tuple(round(float(x), ndigits) for x in circle.center),
    )


def _add_group_unique(out: List[dict], group: Optional[dict], seen: set) -> None:
    if not group:
        return
    gid = group.get("id")
    if gid in seen:
        return
    seen.add(gid)
    out.append(group)


def _build_segment_group_connection_indexes(model: StepModel, groups: List[dict]):
    """为圆柱组建立“圆截面 -> 圆柱组”和“face -> 圆柱组”索引。

    这一步对应盲孔脚本里的 edge_curve_to_faces / face_to_edge_curves 思路：
    先把拓扑关系建好，再从候选圆锥面的端部圆边直接筛相邻圆柱组。
    这样后续不再需要 cone × group × group 的全局暴力组合。
    """
    circle_to_groups: Dict[tuple, List[dict]] = {}
    face_to_group: Dict[int, dict] = {}

    for g in groups:
        group_seen_by_key = set()
        for cyl in g.get("cyls", []):
            face_to_group[cyl.face_id] = g
            for c in cyl.circles:
                if not close_float(c.radius, g["radius"], max(RADIUS_TOL, abs(float(g["radius"])) * 1.0e-5)):
                    continue
                key = _circle_lookup_key_for_index(c)
                if key in group_seen_by_key:
                    continue
                group_seen_by_key.add(key)
                circle_to_groups.setdefault(key, []).append(g)

    return circle_to_groups, face_to_group


def _groups_adjacent_to_face_circle(model: StepModel, source_face: int, circle: Circle3D, face_to_group: Dict[int, dict]) -> List[dict]:
    """从 source_face 的目标圆边直接追踪相邻圆柱组。"""
    out: List[dict] = []
    seen = set()
    for edge_id in face_edges_matching_circle(model, source_face, circle, max(RADIUS_TOL, 1e-5)):
        for adj in _edge_adjacent_faces(model, edge_id, source_face):
            _add_group_unique(out, face_to_group.get(adj), seen)
    return out


def _candidate_segment_groups_for_cone_circle(
    model: StepModel,
    groups: List[dict],
    cone: ConeFace,
    circle: Circle3D,
    circle_to_groups: Optional[Dict[tuple, List[dict]]] = None,
    face_to_group: Optional[Dict[int, dict]] = None,
) -> List[dict]:
    """按拓扑相邻关系 + 圆截面索引筛选圆柱组。

    原版做法需要对所有 groups 扫描；这一版的优先级是：
    1. cone 端部圆边直接相邻的 CYLINDRICAL_SURFACE 组；
    2. 与 cone 端部圆同圆心/同半径的圆柱组索引；
    3. 只有上述都没有命中时，才退回全量扫描，保证异常 STEP 不被漏掉。

    最后的几何/拓扑条件仍然保持不变。
    """
    face_to_group = face_to_group or {}
    circle_to_groups = circle_to_groups or {}

    raw: List[dict] = []
    seen = set()

    for g in _groups_adjacent_to_face_circle(model, cone.face_id, circle, face_to_group):
        _add_group_unique(raw, g, seen)

    for g in circle_to_groups.get(_circle_lookup_key_for_index(circle), []):
        _add_group_unique(raw, g, seen)

    # 兜底：极少数 STEP 端部边界不规范，直接邻接和圆 key 都取不到时再扫描。
    if not raw:
        for g in groups:
            _add_group_unique(raw, g, seen)

    out = []
    tol_r = max(RADIUS_TOL, abs(float(circle.radius)) * 1.0e-5)
    for g in raw:
        if not close_float(g["radius"], circle.radius, tol_r):
            continue
        if not _group_may_lie_on_cone_axis(g, cone, circle):
            continue
        if not cylinder_group_is_inner_cavity(model, g):
            continue
        if not _segment_group_has_circle(g, circle):
            continue
        out.append(g)
    return out


def _candidate_segment_groups_for_split_cone_group(
    model: StepModel,
    cyl_groups: List[dict],
    cg: dict,
    small: Circle3D,
    big: Circle3D,
    circle_to_groups: Optional[Dict[tuple, List[dict]]] = None,
    face_to_group: Optional[Dict[int, dict]] = None,
) -> List[dict]:
    """为 split countersink 的小端圆筛选小圆柱组。

    v11 版本这里会让每个 split cone group 扫描所有 cyl_groups。
    现在先从多片 cone face 的小端圆边追踪相邻圆柱组，再用圆截面索引补充。
    """
    face_to_group = face_to_group or {}
    circle_to_groups = circle_to_groups or {}
    raw: List[dict] = []
    seen = set()

    for cone in cg.get("cones", []):
        for g in _groups_adjacent_to_face_circle(model, cone.face_id, small, face_to_group):
            _add_group_unique(raw, g, seen)

    for g in circle_to_groups.get(_circle_lookup_key_for_index(small), []):
        _add_group_unique(raw, g, seen)

    if not raw:
        for g in cyl_groups:
            _add_group_unique(raw, g, seen)

    out = []
    for cyl_g in raw:
        if not same_axis(cg["axis_point"], cg["axis_dir"], cyl_g["axis_point"], cyl_g["axis_dir"]):
            continue
        if not cylinder_group_is_inner_cavity(model, cyl_g):
            continue
        if not close_float(cyl_g["radius"], small.radius, max(RADIUS_TOL, 0.02 * small.radius)):
            continue
        if not _segment_group_has_circle(cyl_g, small):
            continue
        if REQUIRE_COMPLETE_CIRCULAR_MOUTH and not _segment_group_ring_complete(model, cyl_g, small):
            continue
        if not _group_attaches_at_circle_on_opposite_side(cyl_g, small, big):
            continue
        interval = _group_interval_from_stored(cyl_g)
        if interval is None or _interval_span(interval) < max(0.05, 0.01 * small.radius):
            continue
        out.append(cyl_g)
    return out

def find_chamfered_counterbore_holes(model: StepModel) -> List[dict]:
    """识别没有明显环形 PLANE、而由锥面/倒角连接大小圆柱的 counterbore。

    V14-topology-filter 优化：原版是 cone × group × group 三重暴力组合。
    这里先沿 cone 的小端圆/大端圆追踪相邻圆柱组，并用圆截面索引补充，再做原有规则判断。
    后面的 _cone_between_segment_groups 仍然保留，因此识别条件不变。
    """
    groups = _make_cylinder_segment_groups(model)
    circle_to_groups, face_to_group = _build_segment_group_connection_indexes(model, groups)
    pending = {}

    for cone in model.cone_faces:
        if not cone_face_is_inner_cavity(model, cone):
            continue
        info = cone_boundary_radius_info(cone)
        if info is None:
            continue
        cone_small, cone_big, _ = info

        small_groups = _candidate_segment_groups_for_cone_circle(
            model, groups, cone, cone_small,
            circle_to_groups=circle_to_groups,
            face_to_group=face_to_group,
        )
        big_groups = _candidate_segment_groups_for_cone_circle(
            model, groups, cone, cone_big,
            circle_to_groups=circle_to_groups,
            face_to_group=face_to_group,
        )
        if not small_groups or not big_groups:
            continue

        for sg in small_groups:
            for bg in big_groups:
                if sg["id"] == bg["id"]:
                    continue
                if bg["radius"] <= sg["radius"]:
                    continue
                ratio = bg["radius"] / max(sg["radius"], 1e-12)
                if ratio < 1.22:
                    continue
                if bg["radius"] - sg["radius"] < max(0.08, sg["radius"] * 0.08):
                    continue
                if not same_axis(sg["axis_point"], sg["axis_dir"], bg["axis_point"], bg["axis_dir"]):
                    continue

                conn = _cone_between_segment_groups(model, cone, sg, bg)
                if conn is None:
                    continue

                # 大圆柱另一侧必须是外部入口；否则可能只是内部套筒/过渡结构。
                if not _group_has_external_opening(model, bg, exclude_circle=conn["cone_big"]):
                    continue

                s_int = _group_interval_from_stored(sg)
                b_int = _group_interval_from_stored(bg)
                if s_int is None or b_int is None:
                    continue
                small_len = _interval_span(s_int)
                big_len = _interval_span(b_int)
                if small_len < max(0.5, sg["radius"] * 0.6):
                    continue
                if big_len < max(0.08, bg["radius"] * 0.05):
                    continue
                if (bg["radius"] - sg["radius"]) / max(sg["radius"], 1e-12) < 0.18:
                    continue

                # 同一完整锥面可能被 STEP 拆成两个 ADVANCED_FACE。
                # 用大小端圆心/半径和圆柱组 id 合并。
                key = (
                    sg["id"],
                    bg["id"],
                    _circle_key(conn["cone_small"]),
                    _circle_key(conn["cone_big"]),
                )
                item = pending.setdefault(key, {
                    "small_group": sg,
                    "big_group": bg,
                    "cone_faces": [],
                    "cone_small": conn["cone_small"],
                    "cone_big": conn["cone_big"],
                    "depths": [],
                })
                item["cone_faces"].append(cone.face_id)
                item["depths"].append(conn["depth"])

    out = []
    seen = set()
    for _, item in pending.items():
        sg = item["small_group"]
        bg = item["big_group"]
        cone_faces = unique_keep_order(item["cone_faces"])
        entry_cones = _group_external_opening_transition_faces(model, bg, exclude_circle=item["cone_big"])

        faces = []
        for c in bg["cyls"]:
            faces.append(c.face_id)
        # v8.2 修正：外侧入口倒角/圆锥面只作为“入口外表面”的证据，
        # 不作为沉头孔/沉孔主体导出。真正属于该 counterbore 的圆锥面
        # 是连接大圆柱沉台与小圆柱孔、离小圆柱壁最近的 transition_cone_faces。
        faces.extend(cone_faces)
        for c in sg["cyls"]:
            faces.append(c.face_id)
        faces = unique_keep_order(faces)

        key = tuple(sorted(faces))
        if key in seen:
            continue
        seen.add(key)

        out.append({
            "kind": "counterbore_hole",
            "chamfered_counterbore": True,
            "faces": faces,
            "cylinder_group_faces": unique_keep_order([c.face_id for c in bg["cyls"]] + [c.face_id for c in sg["cyls"]]),
            "entry_transition_cone_faces": entry_cones,
            "transition_cone_faces": cone_faces,
            "transition_cone_small_circle_key": _circle_key(item["cone_small"]),
            "transition_cone_big_circle_key": _circle_key(item["cone_big"]),
            "big_cylinder_face": bg["cyls"][0].face_id,
            "big_cylinder_surface": bg["cyls"][0].surface_id,
            "big_radius": bg["radius"],
            "small_cylinder_face": sg["cyls"][0].face_id,
            "small_cylinder_surface": sg["cyls"][0].surface_id,
            "small_radius": sg["radius"],
            "step_plane_face": None,
            "step_plane_surface": None,
            "axis_point": sg["axis_point"],
            "axis_direction": sg["axis_dir"],
            "reason": "带倒角/锥面过渡的 counterbore：同轴大圆柱沉台与小圆柱孔通过最近的完整圆锥过渡连接；外侧入口倒角仅作为开口证据，不作为主体导出面。"
        })

    # 去重：同一轴线、同一半径组合、同一大/小圆柱组只保留一次。
    unique = []
    used = set()
    for item in sorted(out, key=lambda x: (round(x["small_radius"], 5), round(x["big_radius"], 5), min(x["faces"] or [0]))):
        key = (
            round(item["small_radius"], 5),
            round(item["big_radius"], 5),
            tuple(sorted(item.get("cylinder_group_faces") or [])),
            item.get("transition_cone_small_circle_key"),
            item.get("transition_cone_big_circle_key"),
        )
        if key in used:
            continue
        used.add(key)
        unique.append(item)
    return unique




# =============================================================================
# V12 补充：单片圆锥面 + 小圆柱孔的弱沉头 countersink 识别
# =============================================================================

# 这类孔在电气件、铝型材、滑台零件中很常见：
# - 圆锥面可能只有一个 ADVANCED_FACE，不需要 split 规则；
# - 不能用固定半径比例判断是否为 countersink；
# - 只要满足“外侧完整圆口 + 圆锥小端完整连接小圆柱孔 + 同轴 + 轴向相邻”，
#   就应作为 countersink_hole 候选。
# 以下旧阈值仅保留为兼容变量，当前识别函数不再使用它们。
RELAXED_COUNTERSINK_MIN_RADIUS_RATIO = None
RELAXED_COUNTERSINK_MIN_RADIAL_GROWTH = None
RELAXED_COUNTERSINK_MIN_RADIAL_GROWTH_RATIO = None
RELAXED_COUNTERSINK_MIN_DEPTH_ABS = None
RELAXED_COUNTERSINK_MIN_DEPTH_RATIO = None


def is_relaxed_mounting_countersink_cone(cone: ConeFace, cone_small: Circle3D, cone_big: Circle3D, depth: float) -> bool:
    """弱沉头圆锥面判断。

    不再使用 R_big / R_small 固定比例；只做外大内小、非零深度、同轴的基础检查。
    是否成立继续由外部入口、完整圆口、小圆柱连接、轴向相邻和凸柱过滤决定。
    """
    return countersink_cone_has_valid_geometry(cone, cone_small, cone_big, depth)


def _relaxed_countersink_duplicate(existing_features: List[dict], candidate: dict) -> bool:
    """弱沉头 countersink 去重。

    注意：同一个小圆柱通孔两端可能各有一个 countersink，二者会共享同一个
    CYLINDRICAL_SURFACE，但圆锥入口不同，应计为两个独立沉头孔。
    因此这里不能用“面重叠 50%”这种宽松规则去重，只在圆锥面和小圆柱面都相同
    或完整 face 集完全相同时才视为重复。
    """
    cand_faces = set(candidate.get("faces") or [])
    cand_cone = candidate.get("cone_face")
    cand_cyl = candidate.get("small_cylinder_face")
    for feat in existing_features:
        if feat.get("kind") != "countersink_hole":
            continue
        faces = set(feat.get("faces") or [])
        if cand_faces and faces and cand_faces == faces:
            return True
        if cand_cone is not None and cand_cyl is not None:
            if feat.get("cone_face") == cand_cone and feat.get("small_cylinder_face") == cand_cyl:
                return True
    return False


def find_relaxed_mounting_countersink_holes(model: StepModel, include_terminal_faces: bool = True) -> List[dict]:
    """补充识别单片圆锥面 + 小圆柱孔的 countersink_hole。

    适用场景：
    - 圆锥面没有被拆分，旧 split 规则不会进入；
    - 圆锥半径放大只有约 1.15~1.35，旧强阈值会排除；
    - 该结构仍是完整外侧圆口、同轴小圆柱孔、外大内小的沉头孔。

    排除场景：
    - 大端没有通向外部平面；
    - 小端没有完整连接小圆柱孔；
    - 小圆柱另一端形成局部端盖且候选曲面全为 .T.，更像实心凸柱；
    - 沉头空间中有嵌套同轴圆柱阻塞。
    """
    out = []
    seen = set()

    for cone in model.cone_faces:
        if not cone_face_is_inner_cavity(model, cone):
            continue
        info = cone_boundary_radius_info(cone)
        if info is None:
            continue
        cone_small, cone_big, depth = info
        if not is_relaxed_mounting_countersink_cone(cone, cone_small, cone_big, depth):
            continue

        # 大端必须是外侧完整入口。这里比旧规则更关键：
        # 只有外大内小、通向外表面的锥面才算 countersink；内部过渡锥面不能算。
        if not _cone_group_has_external_opening(model, [cone], cone_big):
            continue

        for cyl in model.cylinder_faces:
            if not same_axis(cone.point, cone.axis, cyl.point, cyl.axis):
                continue
            if not cylinder_face_is_inner_cavity(model, cyl):
                continue
            if not close_float(cyl.radius, cone_small.radius, max(RADIUS_TOL, 0.02 * cone_small.radius)):
                continue
            if not cylinder_has_segment(cyl):
                continue
            if not cylinder_has_circle(cyl, cone_small, max(RADIUS_TOL, 0.02 * cyl.radius)):
                continue
            if not countersink_has_axial_adjacency(cone, cyl, cone_small, cone_big):
                continue
            if REQUIRE_COMPLETE_CIRCULAR_MOUTH:
                if not countersink_has_complete_circular_mouths(model, cone, cyl, cone_small, cone_big):
                    continue
            if not countersink_has_no_nested_coaxial_obstruction(model, cone, cyl, cone_small, cone_big):
                continue

            terminal_faces = []
            if include_terminal_faces:
                terminal_faces = cylinder_terminal_faces_for_export(model, cyl, [cone_small.center])
            face_ids = unique_keep_order([cone.face_id, cyl.face_id] + terminal_faces)

            if is_probable_outer_sense_capped_protrusion(
                model,
                curved_face_ids=[cone.face_id, cyl.face_id],
                cap_face_ids=terminal_faces,
            ):
                continue

            key = (
                cone.face_id,
                cyl.face_id,
                _circle_key(cone_small),
                _circle_key(cone_big),
            )
            if key in seen:
                continue
            seen.add(key)

            out.append({
                "kind": "countersink_hole",
                "relaxed_single_cone_countersink": True,
                "faces": face_ids,
                "cone_face": cone.face_id,
                "cone_surface": cone.surface_id,
                "cone_small_radius": cone_small.radius,
                "cone_big_radius": cone_big.radius,
                "cone_depth": depth,
                "cone_semi_angle_rad": cone.semi_angle,
                "cone_included_angle_deg": math.degrees(cone.semi_angle * 2.0) if cone.semi_angle is not None else None,
                "small_cylinder_face": cyl.face_id,
                "small_cylinder_surface": cyl.surface_id,
                "small_radius": cyl.radius,
                "axis_point": cyl.point,
                "axis_direction": cyl.axis,
                "reason": "补充 countersink：单片圆锥沉头面 + 同轴小圆柱孔；允许较浅但完整的安装沉头，要求外侧完整圆口、小端完整连接小圆柱孔、轴向相邻，并排除外凸实心柱和嵌套同轴圆柱。"
            })

    return out


# =============================================================================
# V10.1 补充：分裂圆锥面 + 分裂小圆柱面的 countersink 识别
# =============================================================================

# 这类结构在 STEP 里常见表现：
# - 一个完整锥形沉头面被拆成两个或多个 CONICAL_SURFACE / ADVANCED_FACE；
# - 小圆柱孔壁也被拆成两个或多个 CYLINDRICAL_SURFACE / ADVANCED_FACE；
# - 单个 cone face 看起来只是半个圆锥环，因此旧规则的“单面完整圆口”会失败。
#
# 为避免把普通微小倒角全部放开，这里只作为补充规则：
# - 必须有多个 cone face 拼成完整大端圆和小端圆；
# - 必须连接到外部平面；
# - 必须有完整小圆柱孔壁组；
# - 允许 45°/90°类浅锥形沉头，适配小型电气/塑料件中的沉头安装孔。
# split countersink 同样不再使用固定半径比例/经验深度阈值。
# 只要求多个面片合并后构成外大内小、有非零深度、同轴的圆锥段。
SPLIT_COUNTERSINK_MIN_RADIUS_RATIO = None
SPLIT_COUNTERSINK_MIN_RADIAL_GROWTH = None
SPLIT_COUNTERSINK_MIN_DEPTH_ABS = None
SPLIT_COUNTERSINK_MIN_DEPTH_RATIO = None
SPLIT_COUNTERSINK_REQUIRE_SPLIT_FACE = True


def _cone_group_ring_complete(model: StepModel, cone_faces: List[ConeFace], target: Circle3D) -> bool:
    """多个 CONICAL_SURFACE 面片是否在 target 圆上共同形成完整闭合圆环。"""
    edges = []
    for cone in cone_faces:
        edges.extend(face_edges_matching_circle(model, cone.face_id, target, max(RADIUS_TOL, 1e-5)))
    return _edges_form_complete_circular_ring(model, edges)


def _cone_group_has_external_opening(model: StepModel, cone_faces: List[ConeFace], big_circle: Circle3D) -> bool:
    """锥面大端是否直接连接到外部平面。"""
    for cone in cone_faces:
        for edge_id in face_edges_matching_circle(model, cone.face_id, big_circle, max(RADIUS_TOL, 1e-5)):
            for adj in adjacent_faces_for_edge(model, edge_id, cone.face_id):
                sid = model.face_surface.get(adj)
                if sid in model.plane_surfaces and _plane_is_external_like(model, adj):
                    return True
    return False


def _make_split_cone_groups(model: StepModel) -> List[dict]:
    """按同轴、同大小端圆，把被 STEP 拆开的 countersink 锥面合并。"""
    groups: List[dict] = []

    for cone in model.cone_faces:
        if not cone_face_is_inner_cavity(model, cone):
            continue
        info = cone_boundary_radius_info(cone)
        if info is None:
            continue
        small, big, depth = info
        # 不再用固定半径比例/经验尺寸作为 countersink 的强判据。
        # 这里只确认多个圆锥面片合并后确实构成外大内小、有非零深度的圆锥段。
        if not countersink_cone_has_valid_geometry(cone, small, big, depth):
            continue

        placed = False
        for g in groups:
            if not same_axis(g["axis_point"], g["axis_dir"], cone.point, cone.axis):
                continue
            if not _circles_same(g["small_circle"], small, max(RADIUS_TOL, 1e-5)):
                continue
            if not _circles_same(g["big_circle"], big, max(RADIUS_TOL, 1e-5)):
                continue
            g["cones"].append(cone)
            g["depth"] = max(g["depth"], depth)
            placed = True
            break

        if not placed:
            groups.append({
                "id": len(groups),
                "axis_point": cone.point,
                "axis_dir": normalize(cone.axis),
                "small_circle": small,
                "big_circle": big,
                "depth": depth,
                "cones": [cone],
            })

    return groups


def _split_countersink_feature_duplicate(existing_features: List[dict], candidate: dict) -> bool:
    cand_faces = set(candidate.get("faces") or [])
    if not cand_faces:
        return False
    for feat in existing_features:
        if feat.get("kind") != "countersink_hole":
            continue
        faces = set(feat.get("faces") or [])
        if not faces:
            continue
        if cand_faces <= faces or faces <= cand_faces:
            return True
        if len(cand_faces & faces) >= max(1, int(min(len(cand_faces), len(faces)) * 0.5)):
            return True
    return False


def find_split_countersink_holes(model: StepModel, include_terminal_faces: bool = True) -> List[dict]:
    """补充识别“圆锥面和小圆柱面均被拆成多片”的 countersink_hole。

    该规则专门解决类似四个安装孔这种情况：
    单个 cone face / cylinder face 都不是完整 360°，但多个面片合并后是完整沉头孔。
    """
    cone_groups = _make_split_cone_groups(model)
    cyl_groups = _make_cylinder_segment_groups(model)
    circle_to_groups, face_to_group = _build_segment_group_connection_indexes(model, cyl_groups)
    out = []
    seen = set()

    for cg in cone_groups:
        cones = cg["cones"]
        small = cg["small_circle"]
        big = cg["big_circle"]

        if SPLIT_COUNTERSINK_REQUIRE_SPLIT_FACE and len(cones) < 2:
            continue

        if REQUIRE_COMPLETE_CIRCULAR_MOUTH:
            if not _cone_group_ring_complete(model, cones, small):
                continue
            if not _cone_group_ring_complete(model, cones, big):
                continue

        if not _cone_group_has_external_opening(model, cones, big):
            continue

        matched_cyl_groups = _candidate_segment_groups_for_split_cone_group(
            model,
            cyl_groups,
            cg,
            small,
            big,
            circle_to_groups=circle_to_groups,
            face_to_group=face_to_group,
        )

        for cyl_g in matched_cyl_groups:
            cone_faces = unique_keep_order([c.face_id for c in cones])
            cyl_faces = unique_keep_order([c.face_id for c in cyl_g.get("cyls", [])])
            face_ids = unique_keep_order(cone_faces + cyl_faces)

            if include_terminal_faces and cyl_g.get("cyls"):
                # 贯通型不会额外导出出口大平面；只有局部封闭底面才会被 cylinder_terminal_faces_for_export 加入。
                face_ids.extend(cylinder_terminal_faces_for_export(model, cyl_g["cyls"][0], [small.center]))
                face_ids = unique_keep_order(face_ids)

            cyl_interval = _group_interval_from_stored(cyl_g)
            axis = normalize(cyl_g["axis_dir"])
            t_small = project_t(small.center, cyl_g["axis_point"], axis)
            t_big = project_t(big.center, cyl_g["axis_point"], axis)
            cone_interval = (min(t_small, t_big), max(t_small, t_big))
            feature_interval = _combined_interval(cyl_interval, cone_interval)
            if feature_interval is not None:
                if _has_nested_coaxial_cylinder_obstruction(
                    model=model,
                    axis_point=cyl_g["axis_point"],
                    axis_dir=cyl_g["axis_dir"],
                    selected_face_ids=face_ids,
                    inner_radius=float(small.radius),
                    outer_radius=float(big.radius),
                    feature_interval=feature_interval,
                ):
                    continue

            key = (
                _circle_key(small),
                _circle_key(big),
                tuple(sorted(cone_faces)),
                tuple(sorted(cyl_faces)),
            )
            if key in seen:
                continue
            seen.add(key)

            out.append({
                "kind": "countersink_hole",
                "split_countersink": True,
                "faces": face_ids,
                "cone_faces": cone_faces,
                "cylinder_faces": cyl_faces,
                "cone_small_radius": small.radius,
                "cone_big_radius": big.radius,
                "cone_depth": cg["depth"],
                "small_cylinder_face": cyl_faces[0] if cyl_faces else None,
                "small_cylinder_surface": cyl_g["cyls"][0].surface_id if cyl_g.get("cyls") else None,
                "small_radius": cyl_g["radius"],
                "axis_point": cyl_g["axis_point"],
                "axis_direction": cyl_g["axis_dir"],
                "reason": "分裂面 countersink：圆锥沉头面和小圆柱孔壁均被 STEP 拆成多片；多片圆锥面共同形成完整大端/小端圆环，并与完整小圆柱孔壁同轴相邻。"
            })

    return out


# =============================================================================
# 借鉴盲孔 V15.23 的倒角入口/分裂圆柱壁识别逻辑
# =============================================================================

_BLIND_V15_MODULE_CACHE = None


def _resolve_blind_v15_script_path(cli_path: Optional[str] = None) -> Optional[Path]:
    """查找盲孔 V15.23 脚本，用于补充识别倒角入口型 countersink_hole。"""
    candidates = []
    if cli_path:
        candidates.append(Path(cli_path).expanduser())
    if BLIND_V15_SCRIPT_PATH:
        candidates.append(Path(BLIND_V15_SCRIPT_PATH).expanduser())
    candidates.extend([
        SCRIPT_DIR / "detect_blind_holes_and_export_stp_v15_23_inner_wall_orientation.py",
        Path(__file__).resolve().with_name("detect_blind_holes_and_export_stp_v15_23_inner_wall_orientation.py"),
        Path.cwd() / "detect_blind_holes_and_export_stp_v15_23_inner_wall_orientation.py",
        Path("/mnt/data/detect_blind_holes_and_export_stp_v15_23_inner_wall_orientation.py"),
    ])
    for p in candidates:
        try:
            p = p.resolve()
        except Exception:
            pass
        if p.is_file():
            return p
    return None


def _load_blind_v15_module(cli_path: Optional[str] = None):
    """延迟加载盲孔 V15.23 脚本。加载失败时返回 None，不影响主规则运行。"""
    global _BLIND_V15_MODULE_CACHE
    if _BLIND_V15_MODULE_CACHE is not None:
        return _BLIND_V15_MODULE_CACHE
    path = _resolve_blind_v15_script_path(cli_path)
    if path is None:
        return None
    spec = importlib.util.spec_from_file_location("blind_v15_23_for_countersunk", str(path))
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _BLIND_V15_MODULE_CACHE = mod
    return mod


def _blind_v15_feature_key(faces: List[int]) -> Tuple[int, ...]:
    return tuple(sorted(int(x) for x in faces if x is not None))


def _is_blind_v15_chamfered_countersink_group(group: dict) -> bool:
    """把盲孔中的倒角入口型结构解释为 countersink_hole。"""
    hole_type = str(group.get("type") or "")
    chamfer_faces = group.get("chamfer_faces") or []
    compound_faces = group.get("compound_bottom_faces") or []
    # 1) 明确的倒角入口盲孔：倒角入口本身就是 countersink/入口沉头结构。
    if "倒角入口" in hole_type and chamfer_faces:
        return True
    # 2) 切缝倒角型、双倒角型：v15 中这类依赖入口倒角/相对外平面判断。
    if "倒角" in hole_type and chamfer_faces:
        return True
    # 3) 多接缝/分裂圆柱壁 + 入口过渡面：这种是我们前面漏掉的圆柱壁/倒角面拼接情况。
    if chamfer_faces and ("分裂圆柱壁" in hole_type or group.get("replacement_cyl_faces") or group.get("source_faces")):
        return True
    # 4) 复合底但无入口倒角，不一定是 countersink，先不归入。
    return False


def collect_blind_v15_chamfer_countersinks(
    step_path: Path,
    blind_v15_script: Optional[str] = None,
    include_chamfer: bool = True,
) -> List[dict]:
    """运行盲孔 V15.23，并把倒角入口盲孔转换为 countersink_hole 特征。"""
    mod = _load_blind_v15_module(blind_v15_script)
    if mod is None:
        return []
    step = mod.StepParser(str(step_path))
    step.parse()
    recognizer = mod.BlindHoleRecognizer(
        step,
        min_radius=0.0,
        min_depth_ratio=1.2,
        min_depth_abs=2.0,
        require_circular_mouth=True,
        allow_shared_plane_bottom_mouth_exception=True,
    )
    raw_holes = recognizer.recognize()
    post = mod.apply_corrected_v13_postprocess(
        step,
        recognizer,
        raw_holes,
        shared_plane_selection="inner",
        enable_broad_partial=False,
        enable_variable_depth=False,
    )
    holes = post[0] if isinstance(post, tuple) else post
    selected, per_hole = mod.select_exact_faces_from_holes(step, recognizer, holes, include_chamfer=include_chamfer)

    features = []
    seen = set()
    for group in per_hole:
        if not _is_blind_v15_chamfered_countersink_group(group):
            continue
        faces = list(group.get("export_faces") or group.get("source_faces") or [])
        faces = unique_keep_order([int(x) for x in faces if x is not None])
        if not faces:
            continue
        key = _blind_v15_feature_key(faces)
        if key in seen:
            continue
        seen.add(key)
        features.append({
            "kind": "countersink_hole",
            "source_rule": "blind_v15_chamfered_blind_hole",
            "blind_v15_type": group.get("type"),
            "faces": faces,
            "chamfer_faces": unique_keep_order(group.get("chamfer_faces") or []),
            "bottom_faces": unique_keep_order(group.get("bottom_faces") or []),
            "compound_bottom_faces": unique_keep_order(group.get("compound_bottom_faces") or []),
            "cylinder_faces": unique_keep_order(group.get("replacement_cyl_faces") or ([group.get("cyl_face")] if group.get("cyl_face") is not None else [])),
            "cyl_face": group.get("cyl_face"),
            "cyl_surface": group.get("cyl_surface"),
            "radius": group.get("radius"),
            "axis_point": group.get("axis_point"),
            "axis_direction": group.get("axis_direction"),
            "reason": "借鉴盲孔 V15.23：倒角入口盲孔属于 countersink_hole；使用 V15 的完整圆口、入口过渡面、分裂圆柱壁/多接缝拼接和内凹封闭过滤规则。",
        })
    return features


def _feature_faces_overlap(existing: List[dict], candidate_faces: List[int], min_overlap_ratio: float = 0.5) -> bool:
    cset = set(candidate_faces or [])
    if not cset:
        return False
    for feat in existing:
        fset = set(feat.get("faces") or [])
        if not fset:
            continue
        inter = len(cset & fset)
        if inter >= max(1, int(min(len(cset), len(fset)) * min_overlap_ratio)):
            return True
    return False

def collect_feature_results(model: StepModel, mode: str = "both", include_terminal_faces: bool = True, enable_blind_v15_countersink: bool = True, blind_v15_script: Optional[str] = None):
    """返回特征列表和要导出的 ADVANCED_FACE 编号。"""
    mode = (mode or "both").lower()
    features = []
    selected_faces = []

    if mode in {"both", "counterbore", "counterbore_hole"}:
        # 1) 严格标准 counterbore：大圆柱 + 小圆柱 + 局部环形台阶平面。
        for index, (plane, small_cyl, big_cyl) in enumerate(find_counterbore_holes(model), 1):
            terminal_faces = []
            if include_terminal_faces:
                terminal_faces = cylinder_terminal_faces_for_export(model, small_cyl, [plane.circles[0].center] if plane.circles else [])
            counterbore_curved_faces = [big_cyl.face_id, small_cyl.face_id]
            if is_probable_outer_sense_capped_protrusion(
                model,
                curved_face_ids=counterbore_curved_faces,
                cap_face_ids=terminal_faces,
            ):
                continue
            if is_probable_outer_sense_counterbore_protrusion(model, counterbore_curved_faces):
                continue
            face_ids = unique_keep_order([big_cyl.face_id, small_cyl.face_id, plane.face_id] + terminal_faces)
            features.append({
                "kind": "counterbore_hole",
                "index": len(features) + 1,
                "faces": face_ids,
                "big_cylinder_face": big_cyl.face_id,
                "big_cylinder_surface": big_cyl.surface_id,
                "big_radius": big_cyl.radius,
                "small_cylinder_face": small_cyl.face_id,
                "small_cylinder_surface": small_cyl.surface_id,
                "small_radius": small_cyl.radius,
                "step_plane_face": plane.face_id,
                "step_plane_surface": plane.surface_id,
                "axis_point": small_cyl.point,
                "axis_direction": small_cyl.axis,
                "reason": "同轴大圆柱面 + 同轴小圆柱面 + 中间环形台阶平面。"
            })
            selected_faces.extend(face_ids)

        # 2) 复杂/装配体多级 counterbore：允许同一圆柱孔壁被拆成多个面，
        #    允许 R25->R20->R14 这类多级贯通沉孔。
        for candidate in find_grouped_counterbore_holes(model):
            if _counterbore_feature_duplicate(features, candidate):
                continue
            candidate = dict(candidate)
            curved_faces = candidate.get("cylinder_group_faces") or [
                x for x in (candidate.get("faces") or []) if face_is_curved_surface(model, x)
            ]
            cap_faces = local_cap_faces_from_feature_faces(model, candidate.get("faces") or [])
            if is_probable_outer_sense_capped_protrusion(model, curved_faces, cap_faces):
                continue
            if is_probable_outer_sense_counterbore_protrusion(model, curved_faces):
                continue
            candidate["index"] = len(features) + 1
            features.append(candidate)
            selected_faces.extend(candidate.get("faces") or [])

        # 3) 带倒角/锥面过渡的 counterbore：用于 DVI/RJ45 安装耳孔这类
        #    没有标准平面台阶、但确实有大圆柱沉台和小圆柱孔的结构。
        for candidate in find_chamfered_counterbore_holes(model):
            if _counterbore_feature_duplicate(features, candidate):
                continue
            candidate = dict(candidate)
            curved_faces = candidate.get("cylinder_group_faces") or [
                x for x in (candidate.get("faces") or []) if face_is_curved_surface(model, x)
            ]
            cap_faces = local_cap_faces_from_feature_faces(model, candidate.get("faces") or [])
            if is_probable_outer_sense_capped_protrusion(model, curved_faces, cap_faces):
                continue
            if is_probable_outer_sense_counterbore_protrusion(model, curved_faces):
                continue
            candidate["index"] = len(features) + 1
            features.append(candidate)
            selected_faces.extend(candidate.get("faces") or [])

    if mode in {"both", "countersink", "countersink_hole"}:
        for index, (cone, cyl) in enumerate(find_countersink_holes(model), 1):
            info = cone_boundary_radius_info(cone)
            cone_small, cone_big, depth = info if info is not None else (None, None, None)
            terminal_faces = []
            if include_terminal_faces and cone_small is not None:
                terminal_faces = cylinder_terminal_faces_for_export(model, cyl, [cone_small.center])
            if is_probable_outer_sense_capped_protrusion(
                model,
                curved_face_ids=[cone.face_id, cyl.face_id],
                cap_face_ids=terminal_faces,
            ):
                continue
            face_ids = unique_keep_order([cone.face_id, cyl.face_id] + terminal_faces)
            features.append({
                "kind": "countersink_hole",
                "index": len(features) + 1,
                "faces": face_ids,
                "cone_face": cone.face_id,
                "cone_surface": cone.surface_id,
                "cone_small_radius": cone_small.radius if cone_small else None,
                "cone_big_radius": cone_big.radius if cone_big else None,
                "cone_depth": depth,
                "cone_semi_angle_rad": cone.semi_angle,
                "cone_included_angle_deg": math.degrees(cone.semi_angle * 2.0) if cone.semi_angle is not None else None,
                "small_cylinder_face": cyl.face_id,
                "small_cylinder_surface": cyl.surface_id,
                "small_radius": cyl.radius,
                "axis_point": cyl.point,
                "axis_direction": cyl.axis,
                "reason": "同轴圆锥沉头面 + 同轴小圆柱孔 + 外部入口 + 完整圆口；不使用固定半径比例作为强判据。"
            })
            selected_faces.extend(face_ids)

        # 4) 单片圆锥面 + 小圆柱孔的弱沉头 countersink 补充：
        #    旧强阈值会把 R1.23->R1.50、R1.62->R2.00 这类真实安装沉头排除；
        #    这里通过“外侧完整圆口 + 同轴完整小圆柱 + 轴向相邻 + 非凸柱”来补回。
        for candidate in find_relaxed_mounting_countersink_holes(model, include_terminal_faces=include_terminal_faces):
            if _relaxed_countersink_duplicate(features, candidate):
                continue
            # 不能用通用 overlap 过滤：同一小圆柱通孔两端的 countersink 会共享 cylinder face，
            # 但它们是两个不同入口，应同时保留。
            candidate = dict(candidate)
            candidate["index"] = len(features) + 1
            features.append(candidate)
            selected_faces.extend(candidate.get("faces") or [])

        # 5) 分裂面 countersink 补充：
        #    当圆锥沉头面和小圆柱孔壁都被 STEP 拆成多片时，单个 face 不是完整圆环；
        #    这里按同轴同大小端圆进行分组后再判断完整圆口。
        for candidate in find_split_countersink_holes(model, include_terminal_faces=include_terminal_faces):
            if _split_countersink_feature_duplicate(features, candidate):
                continue
            if _feature_faces_overlap(features, candidate.get("faces") or []):
                continue
            candidate = dict(candidate)
            curved_faces = (candidate.get("cone_faces") or []) + (candidate.get("cylinder_faces") or [])
            cap_faces = local_cap_faces_from_feature_faces(model, candidate.get("faces") or [])
            if is_probable_outer_sense_capped_protrusion(model, curved_faces, cap_faces):
                continue
            candidate["index"] = len(features) + 1
            features.append(candidate)
            selected_faces.extend(candidate.get("faces") or [])

        # 盲孔 V15.23 补充：倒角型盲孔直接作为 countersink_hole。
        # 该路径用于补充“倒角面拼接、圆柱壁被多接缝拆分、入口过渡面不是单个完整 CONICAL_SURFACE”的情况。
        if enable_blind_v15_countersink:
            try:
                for bf in collect_blind_v15_chamfer_countersinks(model.path, blind_v15_script=blind_v15_script, include_chamfer=True):
                    if _feature_faces_overlap(features, bf.get("faces") or []):
                        continue
                    bf = dict(bf)
                    bf["index"] = len(features) + 1
                    features.append(bf)
                    selected_faces.extend(bf.get("faces") or [])
            except Exception as e:
                # 补充规则失败不应影响主规则。详细错误写入日志特征，方便定位。
                features.append({
                    "kind": "diagnostic",
                    "faces": [],
                    "reason": f"盲孔 V15.23 countersink 补充规则执行失败：{e}",
                })

    features = [f for f in features if f.get("kind") != "diagnostic" or f.get("faces")]
    if REQUIRE_INNER_CAVITY_FACE_ORIENTATION:
        filtered_features = []
        filtered_selected = []
        for feat in features:
            faces = list(feat.get("faces") or [])
            if faces and not all_curved_faces_are_inner_cavity(model, faces):
                continue
            filtered_features.append(feat)
            filtered_selected.extend(faces)
        features = filtered_features
        selected_faces = unique_keep_order(filtered_selected)
    return features, unique_keep_order(selected_faces)


def main_stem_for_step(path: Path) -> str:
    name = path.name
    low = name.lower()
    if low.endswith('.stp.txt'):
        return name[:-8]
    if low.endswith('.step.txt'):
        return name[:-9]
    if low.endswith('.stp'):
        return name[:-4]
    if low.endswith('.step'):
        return name[:-5]
    return path.stem


def is_step_file(path: Path) -> bool:
    name = path.name.lower()
    return path.is_file() and any(name.endswith(suf) for suf in STEP_SUFFIXES)


def iter_step_files(input_path: Path, recursive: bool = False) -> List[Path]:
    if input_path.is_file():
        return [input_path] if is_step_file(input_path) else []
    if not input_path.is_dir():
        return []
    it = input_path.rglob("*") if recursive else input_path.iterdir()
    return sorted([p for p in it if is_step_file(p)])


def default_output_paths(src: Path):
    stem = main_stem_for_step(src)
    out_stp = Path(OUTPUT_STP_DIR) / f"{stem}_countersunk_features.stp"
    out_log = Path(OUTPUT_LOG_DIR) / f"{stem}_countersunk_features_log.txt"
    return out_stp, out_log


def build_log(src: Path, features, selected_faces, export_info=None) -> str:
    lines = []
    lines.append("沉头孔/沉孔识别与导出日志")
    lines.append(f"输入文件：{src}")
    lines.append(f"识别时间：{_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("识别定义：")
    lines.append("1. countersink_hole：锥形沉头孔，核心结构为同轴 CONICAL_SURFACE + 小 CYLINDRICAL_SURFACE；不使用固定半径比例；核心是同轴圆锥面 + 小圆柱孔 + 外部入口 + 完整圆口 + 内凹空间。O-ring 槽、套筒/螺钉状嵌套同轴结构不计入。")
    lines.append("2. counterbore_hole：圆柱沉孔/平底沉孔，标准结构为同轴大 CYLINDRICAL_SURFACE + 小 CYLINDRICAL_SURFACE + 局部环形台阶 PLANE；同时补充识别多级贯通沉孔和带倒角/锥面过渡的沉台孔。")
    lines.append("3. 本脚本不强制要求小孔贯通；贯通型不额外选择出口面，封闭型才额外选择局部底面。")
    lines.append("4. 必须是内凹沉头空间，不把 O-ring 槽、外凸套筒、螺钉头/铆钉状结构、普通矩形槽/散热片/接口外壳结构计入。")
    lines.append("5. V15 增加 counterbore 内凹孔壁证明：若 counterbore 候选的所有曲面均为 .T. 且没有任何 .F. 内凹孔壁证据，则按外凸台阶轴/凸圆柱排除。")
    lines.append("5. 借鉴盲孔 V15.23：倒角入口盲孔、倒角入口复合底盲孔，以及圆柱壁/入口倒角被 STEP 拆成多片但能闭合成完整圆口的结构，补充识别为 countersink_hole。")
    lines.append("6. ADVANCED_FACE 的 .T./.F. 默认仅作辅助信息；不会直接把 .T. 判为外凸，只有 .T.曲面 + 局部端盖等拓扑证据同时成立时，才过滤实心凸柱/铆钉头类误检。")
    lines.append("")
    countersink_count = sum(1 for f in features if f["kind"] == "countersink_hole")
    counterbore_count = sum(1 for f in features if f["kind"] == "counterbore_hole")
    lines.append(f"countersink_hole 数量：{countersink_count}")
    lines.append(f"counterbore_hole 数量：{counterbore_count}")
    lines.append(f"导出 ADVANCED_FACE 数量：{len(selected_faces)}")
    lines.append("")

    for i, feat in enumerate(features, 1):
        lines.append(f"特征 #{i}：{feat['kind']}")
        lines.append(f"  判定依据：{feat.get('reason')}")
        if feat["kind"] == "counterbore_hole":
            lines.append(f"  大圆柱面：ADVANCED_FACE #{feat.get('big_cylinder_face')} / CYLINDRICAL_SURFACE #{feat.get('big_cylinder_surface')} / R={feat.get('big_radius')}")
            lines.append(f"  小圆柱面：ADVANCED_FACE #{feat.get('small_cylinder_face')} / CYLINDRICAL_SURFACE #{feat.get('small_cylinder_surface')} / R={feat.get('small_radius')}")
            if feat.get("multi_stage_counterbore"):
                lines.append(f"  类型补充：多级/装配体 counterbore")
                lines.append(f"  台阶平面组：{', '.join('#' + str(x) for x in feat.get('step_plane_faces', []))}")
                lines.append(f"  圆柱面组：{', '.join('#' + str(x) for x in feat.get('cylinder_group_faces', []))}")
            elif feat.get("chamfered_counterbore"):
                lines.append(f"  类型补充：带倒角/锥面过渡 counterbore")
                lines.append(f"  入口过渡锥面：{', '.join('#' + str(x) for x in feat.get('entry_transition_cone_faces', []))}")
                lines.append(f"  内部过渡锥面：{', '.join('#' + str(x) for x in feat.get('transition_cone_faces', []))}")
            else:
                lines.append(f"  台阶平面：ADVANCED_FACE #{feat.get('step_plane_face')} / PLANE #{feat.get('step_plane_surface')}")
        elif feat["kind"] == "countersink_hole":
            if feat.get("relaxed_single_cone_countersink"):
                lines.append("  类型补充：单片圆锥面 countersink")
                lines.append(f"  圆锥沉头面：ADVANCED_FACE #{feat.get('cone_face')} / CONICAL_SURFACE #{feat.get('cone_surface')}")
                lines.append(f"  小圆柱面：ADVANCED_FACE #{feat.get('small_cylinder_face')} / CYLINDRICAL_SURFACE #{feat.get('small_cylinder_surface')} / R={feat.get('small_radius')}")
                lines.append(f"  锥面小端半径：{feat.get('cone_small_radius')}")
                lines.append(f"  锥面大端半径：{feat.get('cone_big_radius')}")
                lines.append(f"  锥面深度：{feat.get('cone_depth')}")
                lines.append(f"  锥面总角度：{feat.get('cone_included_angle_deg')}")
            elif feat.get("split_countersink"):
                lines.append("  类型补充：分裂面 countersink")
                lines.append(f"  圆锥面组：{', '.join('#' + str(x) for x in feat.get('cone_faces', [])) or '-'}")
                lines.append(f"  小圆柱面组：{', '.join('#' + str(x) for x in feat.get('cylinder_faces', [])) or '-'}")
                lines.append(f"  锥面小端半径：{feat.get('cone_small_radius')}")
                lines.append(f"  锥面大端半径：{feat.get('cone_big_radius')}")
                lines.append(f"  锥面深度：{feat.get('cone_depth')}")
            elif feat.get("source_rule") == "blind_v15_chamfered_blind_hole":
                lines.append("  类型补充：借鉴盲孔 V15.23 的倒角入口/分裂圆柱壁规则")
                lines.append(f"  V15 盲孔类型：{feat.get('blind_v15_type')}")
                lines.append(f"  圆柱壁面：{', '.join('#' + str(x) for x in feat.get('cylinder_faces', [])) or '-'}")
                lines.append(f"  入口倒角/圆角/锥面：{', '.join('#' + str(x) for x in feat.get('chamfer_faces', [])) or '-'}")
                lines.append(f"  底面/封闭面：{', '.join('#' + str(x) for x in (feat.get('bottom_faces', []) + feat.get('compound_bottom_faces', []))) or '-'}")
                lines.append(f"  半径：{feat.get('radius')}")
            else:
                lines.append(f"  圆锥沉头面：ADVANCED_FACE #{feat.get('cone_face')} / CONICAL_SURFACE #{feat.get('cone_surface')}")
                lines.append(f"  小圆柱面：ADVANCED_FACE #{feat.get('small_cylinder_face')} / CYLINDRICAL_SURFACE #{feat.get('small_cylinder_surface')} / R={feat.get('small_radius')}")
                lines.append(f"  锥面小端半径：{feat.get('cone_small_radius')}")
                lines.append(f"  锥面大端半径：{feat.get('cone_big_radius')}")
                lines.append(f"  锥面深度：{feat.get('cone_depth')}")
                lines.append(f"  锥面总角度：{feat.get('cone_included_angle_deg')}")
        else:
            lines.append(f"  诊断信息：{feat.get('reason')}")
        lines.append(f"  轴线定位点：{feat.get('axis_point')}")
        lines.append(f"  轴线方向：{feat.get('axis_direction')}")
        lines.append(f"  导出面：{', '.join('#' + str(x) for x in feat['faces'])}")
        lines.append("")

    if export_info:
        lines.append("导出信息：")
        for k, v in export_info.items():
            lines.append(f"  {k}: {v}")
    return "\n".join(lines)


def process_one_file(src: Path, output_stp: Optional[Path], output_log: Optional[Path], output_json: Optional[Path], mode: str, include_terminal_faces: bool, export_json: bool, json_title: str, write_empty_json: bool, enable_blind_v15_countersink: bool = True, blind_v15_script: Optional[str] = None, json_only: bool = False, detect_only: bool = False):
    model = parse_step_file(src)
    features, selected_faces = collect_feature_results(
        model,
        mode=mode,
        include_terminal_faces=include_terminal_faces,
        enable_blind_v15_countersink=enable_blind_v15_countersink,
        blind_v15_script=blind_v15_script,
    )

    if detect_only:
        countersink_count = sum(1 for f in features if f.get("kind") == "countersink_hole")
        counterbore_count = sum(1 for f in features if f.get("kind") == "counterbore_hole")
        print(
            f"[DETECT_ONLY] {src.name}: "
            f"countersink={countersink_count}, "
            f"counterbore={counterbore_count}, "
            f"step_faces={len(selected_faces)}"
        )
        return {
            "file": str(src),
            "features": features,
            "selected_faces": selected_faces,
            "output_stp": None,
            "output_log": None,
            "output_json": None,
            "json_error": None,
        }

    # json_only=True 时只生成 JSON，不导出 STP，也不写 TXT 日志。
    if not json_only and (output_stp is None or output_log is None):
        default_stp, default_log = default_output_paths(src)
        output_stp = output_stp or default_stp
        output_log = output_log or default_log
    if output_json is None:
        output_json = default_json_path(src)

    export_info = None
    if selected_faces and not json_only:
        exporter = ExactFaceStepExporter(src)
        label = f"{main_stem_for_step(src)}_{mode}_countersunk_features"
        export_info = exporter.export(selected_faces, str(output_stp), label=label)

    json_path = None
    json_error = None
    if export_json:
        try:
            json_path = write_feature_cell_json(
                src,
                model,
                selected_faces,
                output_json,
                title=json_title,
                write_empty=write_empty_json,
            )
        except Exception as e:
            json_error = str(e)

    if json_only:
        countersink_count = sum(1 for f in features if f.get("kind") == "countersink_hole")
        counterbore_count = sum(1 for f in features if f.get("kind") == "counterbore_hole")
        print(
            f"[JSON_ONLY] {src.name}: "
            f"countersink={countersink_count}, "
            f"counterbore={counterbore_count}, "
            f"step_faces={len(selected_faces)}"
        )
        if export_json:
            if json_path is not None:
                print(f"JSON 已保存：{json_path}")
            elif json_error:
                print(f"JSON 生成失败：{json_error}")
            else:
                print("未生成 JSON。")
        return {
            "file": str(src),
            "features": features,
            "selected_faces": selected_faces,
            "output_stp": None,
            "output_log": None,
            "output_json": str(json_path) if json_path is not None else None,
            "json_error": json_error,
        }

    os.makedirs(os.path.dirname(os.path.abspath(output_log)) or ".", exist_ok=True)
    log = build_log(src, features, selected_faces, export_info)
    if export_json:
        log += "\n\nJSON 标注输出："
        if json_path is not None:
            log += f"\n  JSON 已保存：{json_path}"
        elif json_error:
            log += f"\n  JSON 生成失败：{json_error}"
        else:
            log += "\n  未生成 JSON。"

    with open(output_log, "w", encoding="utf-8", newline="\n") as f:
        f.write(log)

    print(log)
    if selected_faces:
        print(f"\nSTP 已导出：{output_stp}")
    else:
        print("\n未识别到目标特征，未导出 STP。")
    if export_json:
        if json_path is not None:
            print(f"JSON 已保存：{json_path}")
        elif json_error:
            print(f"JSON 生成失败：{json_error}")
    print(f"日志已保存：{output_log}")

    return {
        "file": str(src),
        "features": features,
        "selected_faces": selected_faces,
        "output_stp": str(output_stp) if selected_faces else None,
        "output_log": str(output_log),
        "output_json": str(json_path) if json_path is not None else None,
        "json_error": json_error,
    }


def build_arg_parser():
    parser = argparse.ArgumentParser(description="识别 STP/STEP 中 countersink_hole / counterbore_hole，并导出对应特征面 STP。")
    parser.add_argument("input", nargs="?", default=None, help="STP/STEP 文件路径，或文件夹路径。未提供时使用脚本顶部 INPUT_STP_PATH。")
    parser.add_argument("--input", dest="input_opt", default=None, help="兼容参数：STP/STEP 文件路径，或文件夹路径。优先级高于位置参数 input。")
    parser.add_argument("--output", dest="output_opt", default=None, help="兼容参数：--json-only 时作为 JSON 输出目录；否则作为 STP 输出目录。")
    parser.add_argument("--mode", choices=["both", "countersink", "counterbore"], default="both", help="识别/导出类型，默认 both。")
    parser.add_argument("--output-stp", default=None, help="单文件模式下指定输出 STP 路径。")
    parser.add_argument("--output-log", default=None, help="单文件模式下指定输出日志路径。")
    parser.add_argument("--output-stp-dir", default=None, help="批量模式下指定输出 STP 文件夹。")
    parser.add_argument("--output-log-dir", default=None, help="批量模式下指定输出日志文件夹。")
    parser.add_argument("--output-json", default=None, help="单文件模式下指定输出 JSON 路径。")
    parser.add_argument("--output-json-dir", default=None, help="批量模式下指定输出 JSON 文件夹。")
    parser.add_argument("--no-json", action="store_true", help="不生成 NCTI Cell ID JSON，只导出 STP 和日志。")
    parser.add_argument("--json-only", action="store_true", help="只生成 JSON，不导出 STP，也不写 TXT 日志。")
    parser.add_argument("--detect-only", action="store_true", help="只做文本拓扑识别，不导出 STP、不写日志、不生成 JSON、不调用 NCTI；用于快速测试识别耗时。")
    parser.add_argument("--json-title", default="countersunk_hole_prediction", help="JSON 中 title 字段，默认 countersunk_hole_prediction。")
    parser.add_argument("--skip-empty-json", action="store_true", help="未识别到特征时不生成空 JSON。默认会生成空 content JSON。")
    parser.add_argument("-r", "--recursive", action="store_true", help="当输入为文件夹时递归扫描。")
    parser.add_argument("--no-terminal-faces", action="store_true", help="不额外导出小圆柱另一端的封闭/终止面。")
    parser.add_argument("--no-blind-v15-countersink", action="store_true", help="关闭借鉴盲孔 V15.23 的倒角型 countersink 补充规则。")
    parser.add_argument("--blind-v15-script", default=None, help="盲孔 V15.23 脚本路径；默认在当前脚本同目录查找。")
    parser.add_argument("--strict-inner-sense", action="store_true", help="启用旧版严格 .F. 孔壁方向约束；默认关闭，不建议批量使用。")
    parser.add_argument("--allow-outer-sense-curved-faces", action="store_true", help="兼容旧参数：等价于不启用 --strict-inner-sense。")
    parser.add_argument("--disable-protrusion-sense-filter", action="store_true", help="关闭外凸实心柱过滤，包括“.T.曲面 + 局部端盖”和 counterbore 全 .T. 外凸台阶轴过滤。")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.json_only and args.no_json:
        parser.error("--json-only 与 --no-json 不能同时使用。")
    if args.detect_only and args.json_only:
        parser.error("--detect-only 与 --json-only 不能同时使用。")
    if args.detect_only and args.no_json:
        # detect-only 本来就不生成 JSON；允许用户保留 --no-json 不报错。
        pass

    input_value = args.input_opt or args.input or INPUT_STP_PATH
    if not input_value:
        parser.error("请传入 STP/STEP 文件或文件夹路径，或填写脚本顶部 INPUT_STP_PATH。")

    input_path = Path(input_value).expanduser().resolve()

    global OUTPUT_STP_DIR, OUTPUT_LOG_DIR, OUTPUT_JSON_DIR, REQUIRE_INNER_CAVITY_FACE_ORIENTATION, REJECT_OUTER_SENSE_CAPPED_PROTRUSION
    # 兼容用户原来的 --output 参数：
    # - --json-only 时，--output 表示 JSON 输出目录；
    # - 非 json-only 时，--output 表示 STP 输出目录。
    if args.output_opt:
        if args.json_only and not args.output_json_dir:
            OUTPUT_JSON_DIR = args.output_opt
        elif not args.json_only and not args.output_stp_dir:
            OUTPUT_STP_DIR = args.output_opt

    if args.output_stp_dir:
        OUTPUT_STP_DIR = args.output_stp_dir
    if args.output_log_dir:
        OUTPUT_LOG_DIR = args.output_log_dir
    if args.output_json_dir:
        OUTPUT_JSON_DIR = args.output_json_dir
    if args.strict_inner_sense:
        REQUIRE_INNER_CAVITY_FACE_ORIENTATION = True
    if args.allow_outer_sense_curved_faces:
        REQUIRE_INNER_CAVITY_FACE_ORIENTATION = False
    if args.disable_protrusion_sense_filter:
        REJECT_OUTER_SENSE_CAPPED_PROTRUSION = False

    files = iter_step_files(input_path, recursive=args.recursive)
    if not files:
        print(f"未找到可分析的 STP/STEP 文件：{input_path}", file=sys.stderr)
        return 1

    ok = 0
    failed = 0
    for src in files:
        try:
            out_stp = None if args.json_only else (Path(args.output_stp).expanduser().resolve() if args.output_stp and len(files) == 1 else None)
            out_log = None if args.json_only else (Path(args.output_log).expanduser().resolve() if args.output_log and len(files) == 1 else None)
            out_json = Path(args.output_json).expanduser().resolve() if args.output_json and len(files) == 1 else None
            process_one_file(
                src,
                output_stp=out_stp,
                output_log=out_log,
                output_json=out_json,
                mode=args.mode,
                include_terminal_faces=not args.no_terminal_faces,
                export_json=False if args.detect_only else (True if args.json_only else (not args.no_json)),
                json_title=args.json_title,
                write_empty_json=not args.skip_empty_json,
                enable_blind_v15_countersink=not args.no_blind_v15_countersink,
                blind_v15_script=args.blind_v15_script,
                json_only=args.json_only,
                detect_only=args.detect_only,
            )
            ok += 1
        except Exception as e:
            failed += 1
            print(f"[ERROR] {src}: {e}", file=sys.stderr)

    print(f"\n完成：成功 {ok} 个，失败 {failed} 个。")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
