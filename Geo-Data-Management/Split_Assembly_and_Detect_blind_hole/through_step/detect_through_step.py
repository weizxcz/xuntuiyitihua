#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
双侧通槽台阶 (2-sided through step) 几何识别器。

基于 1000 个标注样本的统计规则：
- 100% PLANE 面（所有 seg=9 面均为平面）
- 典型 3 面组合：2 侧壁 + 1 底面
- 侧壁法线互相平行或呈任意角度，底面法线与两侧壁都垂直（75°-105°）
- 边类型 >99% LINE
- 88% 所有通槽面形成连通子图

运行指令：
    python detect_through_step.py STP文件路径
    python detect_through_step.py D:/wyg/data/data/通槽/steps/20221121_154647_1.step

也可以直接填写脚本顶部的 INPUT_STP_PATH，然后运行：
    python detect_through_step.py

输出 JSON 格式与 AAGNet 训练标注一致：
    [[ "part_name", { "seg": {...}, "inst": [[...]], "bottom": {...} } ]]
"""

import argparse
import json
import math
import os
import re
import sys
from collections import defaultdict, deque
from pathlib import Path

# 尝试复用 blind_hole 的 StepParser
BLIND_HOLE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "blind_hole")
if os.path.isdir(BLIND_HOLE_DIR) and BLIND_HOLE_DIR not in sys.path:
    sys.path.insert(0, os.path.dirname(BLIND_HOLE_DIR))

try:
    from blind_hole.detect_blind_holes_and_export_stp_v15_23 import StepParser
except ImportError:
    # fallback: 如果 blind_hole 模块不可用，直接内联 StepParser 核心逻辑
    StepParser = None

# canonical NCTI 对齐映射（位置索引语义）。与 annotate_through_step.py 同源，
# 指向 YHCADSmartCleaner/utils/through_step/ncti_faceid_map.py。
FEATUREFOX_ROOT = r"D:/wyg/xuntuiyitihua/YHCADSmartCleaner/utils/through_step"
if FEATUREFOX_ROOT not in sys.path:
    sys.path.insert(0, FEATUREFOX_ROOT)
# 本项目根（Split_Assembly_and_Detect_blind_hole，含 config/config_load.py）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:
    from ncti_faceid_map import build_pos_map_for_step, init_ncti_safe  # noqa: E402
except Exception as _e:
    sys.stderr.write("ncti_faceid_map 导入失败（NCTI 对齐将不可用）: {}\n".format(_e))
    build_pos_map_for_step = None
    init_ncti_safe = None

_NCTI_CACHE = {"ncti": None, "tried": False}


def _get_ncti():
    """惰性、一次性初始化 NCTI（用本项目 config/config_load.init_ncti_config）。
    失败/不可用返回 None。批处理时只初始化一次，避免逐文件重载。"""
    if init_ncti_safe is None:
        return None
    if not _NCTI_CACHE["tried"]:
        _NCTI_CACHE["tried"] = True
        _NCTI_CACHE["ncti"] = init_ncti_safe(PROJECT_ROOT)
    return _NCTI_CACHE["ncti"]

# =============================================================================
# 可选配置区
# =============================================================================
INPUT_STP_PATH = ""
FEATURE_SEG_ID = 9  # 2-sided_through_step 在标注中的 seg index
FEATURE_NAME = "2-sided_through_step"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# 角度阈值（度）
PERP_MIN = 75.0
PERP_MAX = 105.0
PARALLEL_DOT = 0.95  # 法向量点积 > 此值视为平行

# 面数范围
MIN_INSTANCE_FACES = 3
MAX_INSTANCE_FACES = 6

# 底面识别：底面法向量与两侧壁法向量都垂直
BOTTOM_PERP_MIN = 75.0
BOTTOM_PERP_MAX = 105.0


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def vec_norm(v):
    return math.sqrt(sum(x * x for x in v))


def angle_between_normals(n1, n2):
    """计算两个法向量之间的夹角（度），忽略方向（取绝对值点积）。"""
    d = abs(dot(n1, n2))
    d = max(-1.0, min(1.0, d))
    return math.degrees(math.acos(d))


# =============================================================================
# 简化版 StepParser（仅在无法导入 blind_hole 版本时使用）
# =============================================================================

class SimpleStepParser:
    """最小化 STEP 解析器，仅提取双侧通槽台阶识别所需的拓扑信息。"""

    def __init__(self, path):
        self.path = path
        self.entities = {}
        self.advanced_faces = {}
        self.face_bounds = {}
        self.edge_loops = {}
        self.oriented_edges = {}
        self.edge_curves = {}
        self.edge_curve_to_faces = defaultdict(set)
        self.surface_to_faces = defaultdict(list)
        self.axis2 = {}
        self.points = {}
        self.directions = {}
        self.surfaces = {}
        self.face_to_edge_curves = defaultdict(set)
        self.face_to_edges_by_bound = defaultdict(list)

    def parse(self):
        with open(self.path, "r", encoding="utf-8", errors="ignore") as handle:
            content = handle.read()
        data_match = re.search(r"DATA;\s*(.*?)\s*ENDSEC;", content, re.S | re.I)
        data = data_match.group(1) if data_match else content
        for match in re.finditer(r"#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*?)\)\s*;", data, re.S):
            eid = int(match.group(1))
            etype = match.group(2).upper()
            params = " ".join(match.group(3).split())
            self.entities[eid] = {"type": etype, "params": params}
        for eid, ent in self.entities.items():
            etype = ent["type"]
            params = ent["params"]
            if etype == "CARTESIAN_POINT":
                m = re.search(r"\(([^()]*)\)", params)
                if m:
                    self.points[eid] = tuple(float(x.strip()) for x in m.group(1).split(","))
            elif etype == "DIRECTION":
                m = re.search(r"\(([^()]*)\)", params)
                if m:
                    self.directions[eid] = tuple(float(x.strip()) for x in m.group(1).split(","))
            elif etype == "AXIS2_PLACEMENT_3D":
                refs = [int(x) for x in re.findall(r"#(\d+)", params)]
                self.axis2[eid] = refs[1] if len(refs) >= 2 else None
            elif etype == "PLANE":
                refs = [int(x) for x in re.findall(r"#(\d+)", params)]
                self.surfaces[eid] = {"type": "PLANE", "axis_ref": refs[0] if refs else None}
            elif etype == "ADVANCED_FACE":
                parts = self._split_top_level(params)
                if len(parts) >= 4:
                    bounds = [int(x) for x in re.findall(r"#(\d+)", parts[1])]
                    surface_refs = [int(x) for x in re.findall(r"#(\d+)", parts[2])]
                    if surface_refs:
                        self.advanced_faces[eid] = {"bounds": bounds, "surface": surface_refs[0]}
                        self.surface_to_faces[surface_refs[0]].append(eid)
            elif etype in ("FACE_BOUND", "FACE_OUTER_BOUND"):
                refs = [int(x) for x in re.findall(r"#(\d+)", params)]
                if refs:
                    self.face_bounds[eid] = refs[0]
            elif etype == "EDGE_LOOP":
                self.edge_loops[eid] = [int(x) for x in re.findall(r"#(\d+)", params)]
            elif etype == "ORIENTED_EDGE":
                parts = self._split_top_level(params)
                refs = [int(x) for x in re.findall(r"#(\d+)", parts[3] if len(parts) > 3 else params)]
                self.oriented_edges[eid] = refs[0] if refs else None
            elif etype == "EDGE_CURVE":
                refs = [int(x) for x in re.findall(r"#(\d+)", params)]
                if len(refs) >= 3:
                    self.edge_curves[eid] = {"v1": refs[0], "v2": refs[1], "curve": refs[2]}
        self._build_topology()

    def _split_top_level(self, text):
        parts, current, depth, in_string, quote = [], [], 0, False, ""
        for ch in text:
            if ch in ("'", '"'):
                if not in_string:
                    in_string, quote = True, ch
                elif quote == ch:
                    in_string = False
                current.append(ch)
            elif in_string:
                current.append(ch)
            elif ch == "(":
                depth += 1
                current.append(ch)
            elif ch == ")":
                depth -= 1
                current.append(ch)
            elif ch == "," and depth == 0:
                parts.append("".join(current).strip())
                current = []
            else:
                current.append(ch)
        if current:
            parts.append("".join(current).strip())
        return parts

    def _build_topology(self):
        for face_id, face in self.advanced_faces.items():
            for bound_id in face["bounds"]:
                loop_id = self.face_bounds.get(bound_id)
                if loop_id is None:
                    continue
                for oe_id in self.edge_loops.get(loop_id, []):
                    ec_id = self.oriented_edges.get(oe_id)
                    if ec_id is None:
                        continue
                    self.face_to_edge_curves[face_id].add(ec_id)
                    self.edge_curve_to_faces[ec_id].add(face_id)

    def face_surface_type(self, face_id):
        sid = self.advanced_faces.get(face_id, {}).get("surface")
        if sid is None:
            return "UNKNOWN"
        return self.entities.get(sid, {}).get("type", "UNKNOWN")

    def face_surface_id(self, face_id):
        return self.advanced_faces.get(face_id, {}).get("surface")

    def face_normal(self, face_id):
        """返回 PLANE 面的法向量，非 PLANE 返回 None。"""
        return _resolve_face_normal(self, face_id)


def _resolve_face_normal(parser, face_id):
    """从 STEP 解析器中提取 PLANE 面的法向量。兼容两种 axis2 存储格式。"""
    sid = parser.face_surface_id(face_id)
    if sid is None:
        return None
    surf = parser.surfaces.get(sid)
    if not surf or surf.get("type") != "PLANE":
        return None
    axis_ref = surf.get("axis_ref")
    if axis_ref is None:
        return None
    axis_data = parser.axis2.get(axis_ref)
    if axis_data is None:
        return None
    # blind_hole StepParser: axis2 存 dict {"point_ref":.., "axis_ref":.., "ref_direction_ref":..}
    if isinstance(axis_data, dict):
        dir_ref = axis_data.get("axis_ref")
    else:
        # SimpleStepParser 或其他格式：axis2 直接存 direction ref
        dir_ref = axis_data
    if dir_ref is None:
        return None
    return parser.directions.get(dir_ref)


def get_parser(path):
    """获取 STEP 解析器：优先使用 blind_hole 的 StepParser，否则使用内置简化版。"""
    if StepParser is not None:
        parser = StepParser(path)
        parser.parse()
        # 统一挂载 face_normal 方法
        def _fn(self_parser, fid):
            return _resolve_face_normal(self_parser, fid)
        import types
        parser.face_normal = types.MethodType(_fn, parser)
        return parser
    else:
        parser = SimpleStepParser(path)
        parser.parse()
        return parser


# =============================================================================
# 双侧通槽台阶识别器
# =============================================================================

class ThroughStepRecognizer:
    """基于几何规则的双侧通槽台阶识别器。

    核心逻辑：
    1. 筛选所有 PLANE 面
    2. 通过共享 EDGE_CURVE 构建面邻接图
    3. 在 PLANE 邻接图中搜索 3-6 面的连通子图
    4. 验证法向量角度模式：至少 2 对垂直（底面⊥侧壁）
    5. 识别底面（与另外两面都垂直的面）
    """

    def __init__(self, parser, *, feature_seg_id=FEATURE_SEG_ID):
        self.parser = parser
        self.feature_seg_id = feature_seg_id
        self.plane_faces = []  # [(face_id, normal)]
        self.adjacency = defaultdict(set)  # face_id -> set of adjacent face_ids
        self._centroid_cache = {}

    def _face_centroid(self, face_id):
        """计算面的重心（顶点坐标平均值）。"""
        if face_id in self._centroid_cache:
            return self._centroid_cache[face_id]
        pts = []
        for ec_id in self.parser.face_to_edge_curves.get(face_id, set()):
            edge = self.parser.edge_curves.get(ec_id)
            if not edge:
                continue
            for vid in (edge.get("v1"), edge.get("v2")):
                p = self._vertex_xyz(vid)
                if p is not None:
                    pts.append(p)
        if not pts:
            self._centroid_cache[face_id] = None
            return None
        n = len(pts)
        cx = sum(p[0] for p in pts) / n
        cy = sum(p[1] for p in pts) / n
        cz = sum(p[2] for p in pts) / n
        result = (cx, cy, cz)
        self._centroid_cache[face_id] = result
        return result

    def _vertex_xyz(self, vertex_id):
        """获取顶点的 3D 坐标。兼容两种 StepParser。"""
        # blind_hole StepParser: vertex_points -> points
        vp = getattr(self.parser, "vertex_points", None)
        pts = getattr(self.parser, "points", None)
        if vp is not None and vertex_id in vp:
            point_ref = vp.get(vertex_id)
            if point_ref is not None and pts is not None:
                return pts.get(point_ref)
        # Fallback: 直接从 entities 解析
        return None

    def _verify_through_open_ends(self, bottom_face, side_walls, n_bottom):
        """验证通槽底面在通槽走向的两端均有开放端面。

        核心逻辑：
        1. 计算通槽走向 = 底面法向量 × 侧壁方向（叉积）
        2. 收集底面的自由邻接面（非侧壁的邻接面）
        3. 将自由邻接面的重心投影到通槽方向
        4. 检查投影是否跨越正负两侧 → 两端开放

        区分通槽与盲槽/口袋/外凸角的关键验证。
        """
        c_bottom = self._face_centroid(bottom_face)
        c_a = self._face_centroid(side_walls[0])
        c_b = self._face_centroid(side_walls[1])

        if c_bottom is None or c_a is None or c_b is None:
            return False

        # 侧壁方向（从 A 到 B 的单位向量）
        d_wall = tuple(c_b[k] - c_a[k] for k in range(3))
        d_len = vec_norm(d_wall)
        if d_len < 1e-12:
            return False
        d_wall = tuple(c / d_len for c in d_wall)

        # 通槽走向 = 底面法向量 × 侧壁方向（叉积）
        through_dir = (
            n_bottom[1] * d_wall[2] - n_bottom[2] * d_wall[1],
            n_bottom[2] * d_wall[0] - n_bottom[0] * d_wall[2],
            n_bottom[0] * d_wall[1] - n_bottom[1] * d_wall[0],
        )
        td_len = vec_norm(through_dir)
        if td_len < 1e-12:
            return False
        through_dir = tuple(c / td_len for c in through_dir)

        # 收集底面的自由邻接面（非侧壁邻接面）
        wall_set = set(side_walls)
        bottom_ecs = self.parser.face_to_edge_curves.get(bottom_face, set())
        wall_a_ecs = self.parser.face_to_edge_curves.get(side_walls[0], set())
        wall_b_ecs = self.parser.face_to_edge_curves.get(side_walls[1], set())
        shared_ecs = (bottom_ecs & wall_a_ecs) | (bottom_ecs & wall_b_ecs)
        free_ecs = bottom_ecs - shared_ecs

        if len(free_ecs) < 2:
            return False

        # 收集自由边对应的邻接面重心
        projections = []
        for ec_id in free_ecs:
            for other_fid in self.parser.edge_curve_to_faces.get(ec_id, set()):
                if other_fid == bottom_face or other_fid in wall_set:
                    continue
                c_other = self._face_centroid(other_fid)
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

    def recognize(self):
        """返回 list of dict，每个 dict 是一个识别到的通槽实例。"""
        self._collect_plane_faces()
        self._build_adjacency()
        return self._find_instances()

    def _collect_plane_faces(self):
        """收集所有 PLANE 面及其法向量。"""
        for face_id in self.parser.advanced_faces:
            stype = self.parser.face_surface_type(face_id)
            if stype == "PLANE":
                normal = self.parser.face_normal(face_id)
                if normal is not None:
                    self.plane_faces.append((face_id, normal))

    def _build_adjacency(self):
        """通过共享 EDGE_CURVE 构建 PLANE 面邻接图。"""
        plane_set = {fid for fid, _ in self.plane_faces}
        for fid in plane_set:
            for ec_id in self.parser.face_to_edge_curves.get(fid, set()):
                for other_fid in self.parser.edge_curve_to_faces.get(ec_id, set()):
                    if other_fid != fid and other_fid in plane_set:
                        self.adjacency[fid].add(other_fid)

    def _find_instances(self):
        """在 PLANE 邻接图中搜索三角形（3 面互邻）并验证角度模式。

        策略：由于 PLANE 面通常形成大的连通图，不能用 BFS 找连通分量。
        改为：枚举所有互相邻接的 3 面组合（三角形），验证角度规则。
        """
        used_faces = set()  # 已被识别为某个实例的面
        instances = []

        normal_map = {fid: n for fid, n in self.plane_faces}

        # 枚举所有 (a, b, c) 三角形：a < b < c 且两两邻接
        plane_ids = sorted(normal_map.keys())
        for i, fa in enumerate(plane_ids):
            if fa in used_faces:
                continue
            for fb in sorted(self.adjacency.get(fa, set())):
                if fb <= fa or fb in used_faces:
                    continue
                # fa 和 fb 邻接，找它们的共同邻居 fc
                common = self.adjacency.get(fa, set()) & self.adjacency.get(fb, set())
                for fc in sorted(common):
                    if fc <= fb or fc in used_faces:
                        continue

                    trio = [fa, fb, fc]
                    trio_normals = {fid: normal_map[fid] for fid in trio if fid in normal_map}
                    if len(trio_normals) < 3:
                        continue

                    result = self._validate_3_faces(trio, trio_normals, trio)
                    if result is not None:
                        # 检查是否与已有实例重叠
                        result_faces = set(result["faces"])
                        if result_faces & used_faces:
                            continue
                        instances.append(result)
                        used_faces.update(result_faces)
                        break  # fa 已使用，跳出 fb 循环
                else:
                    continue
                break  # fa 已使用，跳出

        return instances

    def _validate_3_faces(self, faces, normal_map, component):
        """验证标准 3 面通槽模式。

        核心规则（纯 STEP 拓扑/几何，不依赖标注标签）：
        1. 3 个 ADVANCED_FACE，底面均为 PLANE
        2. 3 个面两两通过共享 EDGE_CURVE 邻接（调用方保证）
        3. 至少 2 对法向量夹角在 75°-105°（近似垂直）
        4. 存在唯一底面：其法向量与两侧壁法向量都近似垂直
        5. 两侧壁法向量在底面法线方向上的投影符号相反（分居底面两侧，
           这是通槽台阶与普通直角的本质区别）
        """
        f0, f1, f2 = faces
        n0, n1, n2 = normal_map[f0], normal_map[f1], normal_map[f2]

        # 计算 3 对角度
        a01 = angle_between_normals(n0, n1)
        a02 = angle_between_normals(n0, n2)
        a12 = angle_between_normals(n1, n2)
        angles = [a01, a02, a12]

        # 至少 2 对垂直
        perp_count = sum(1 for a in angles if PERP_MIN <= a <= PERP_MAX)
        if perp_count < 2:
            return None

        # 识别底面：与另外两个面都垂直的面
        bottom_face = None
        side_walls = []
        for i, fi in enumerate(faces):
            others = [faces[j] for j in range(3) if j != i]
            ni = normal_map[fi]
            all_perp = True
            for oj in others:
                nj = normal_map[oj]
                a = angle_between_normals(ni, nj)
                if not (BOTTOM_PERP_MIN <= a <= BOTTOM_PERP_MAX):
                    all_perp = False
                    break
            if all_perp:
                bottom_face = fi
                side_walls = others
                break

        if bottom_face is None:
            return None

        # 关键过滤：两侧壁法向量在底面法线方向上的投影符号必须相反
        # 这是通槽台阶（Π 形截面）与普通直角的本质区别：
        # - 通槽：侧壁分居底面两侧，法向量沿底面法线分量的符号相反
        # - 直角：侧壁在底面同侧，法向量沿底面法线分量的符号相同
        # 注意：当侧壁几乎完全垂直于底面时，投影接近零，符号不可靠，
        # 此时退化为使用面重心位置判断。
        n_bottom = normal_map[bottom_face]
        sw_a, sw_b = side_walls
        n_a = normal_map[sw_a]
        n_b = normal_map[sw_b]
        proj_a = dot(n_a, n_bottom)
        proj_b = dot(n_b, n_bottom)

        # 如果投影足够大（侧壁倾斜），用法向量投影判断
        if abs(proj_a) > 0.1 and abs(proj_b) > 0.1:
            if proj_a * proj_b >= 0:
                return None
        else:
            # 投影接近零（侧壁几乎垂直于底面），用面重心位置判断
            # 通槽特征：底面重心投影到底面法线方向上，应在两个侧壁重心之间
            c_bottom = self._face_centroid(bottom_face)
            c_a = self._face_centroid(sw_a)
            c_b = self._face_centroid(sw_b)
            if c_bottom is None or c_a is None or c_b is None:
                return None
            # 沿底面法线方向，侧壁重心投影
            d_a = sum((c_a[k] - c_bottom[k]) * n_bottom[k] for k in range(3))
            d_b = sum((c_b[k] - c_bottom[k]) * n_bottom[k] for k in range(3))
            # 两侧壁应在底面同侧（都在底面"下方"/"内部"），但在底面切平面方向上分居两侧
            # 用侧壁法向量在底面切平面上的分量来判断
            proj_a_tangent = tuple(n_a[k] - proj_a * n_bottom[k] for k in range(3))
            proj_b_tangent = tuple(n_b[k] - proj_b * n_bottom[k] for k in range(3))
            tangent_dot = sum(proj_a_tangent[k] * proj_b_tangent[k] for k in range(3))
            # 通槽：两侧壁法向量在底面切平面上的分量方向相反（指向对方）
            # 直角：两侧壁法向量在底面切平面上的分量方向相同或垂直
            if tangent_dot > -0.1:
                return None

        # ── 贯穿方向两端开放验证（非硬过滤）──
        # 作为参考信号记录。STEP 版本无评分系统，不过滤，
        # 因为 STEP 边界边可能缺少邻接面信息导致误拒。
        _through_verified = self._verify_through_open_ends(bottom_face, side_walls, n_bottom)

        return {
            "faces": sorted(component),
            "bottom_face": bottom_face,
            "side_walls": sorted(side_walls),
            "n_perpendicular_pairs": perp_count,
            "angles": {"{}_{}".format(min(faces[i], faces[j]), max(faces[i], faces[j])): round(a, 2)
                       for i in range(3) for j in range(i + 1, 3)
                       for a in [angle_between_normals(normal_map[faces[i]], normal_map[faces[j]])]},
        }

    def _validate_multi_faces(self, faces, normal_map, component):
        """验证 4-6 面情况（可能包含圆角过渡面）。

        策略：在所有 3 面组合中寻找满足核心规则的子集，
        然后将其余面归入该实例。
        """
        from itertools import combinations

        best = None
        for trio in combinations(faces, 3):
            result = self._validate_3_faces(list(trio), normal_map, component)
            if result is not None:
                if best is None or result["n_perpendicular_pairs"] > best["n_perpendicular_pairs"]:
                    # 记录完整 component 而不是 trio
                    result["faces"] = sorted(component)
                    best = result

        return best


# =============================================================================
# JSON 输出（与 AAGNet 训练标注格式一致）
# =============================================================================

def build_training_json(parser, instances, stp_path, *, feature_seg_id=FEATURE_SEG_ID,
                        pos_map=None, n_cells=None):
    """构建与 Geo-Rec 训练标注格式一致的标签 JSON。

    cell_id 空间：
      - 传入 pos_map（且 n_cells）→ NCTI ai.FaceID 位置索引，与 Geo-Rec 训练图严格对齐。
      - 否则 → STEP advanced_faces 排序下标（⚠ 不与训练对齐，仅无 NCTI 时调试/高亮用）。

    输出格式：
    [[ "part_name", { "seg": {...}, "inst": [[...]], "bottom": {...} } ]]
    """
    part_name = os.path.splitext(os.path.basename(stp_path))[0]

    # ── NCTI ai.FaceID 位置索引空间（与 Geo-Rec 训练标签对齐）──
    if pos_map is not None and n_cells is not None:
        n_faces = n_cells
        seg = {str(i): 0 for i in range(n_faces)}
        bottom = {str(i): 0 for i in range(n_faces)}
        inst = [[0] * n_faces for _ in range(n_faces)]

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
                    inst[a][b] = 1

        if missing_report:
            sys.stderr.write(
                "警告：{} 个通槽实例有面未映射到 NCTI cell_id（标签可能缺项）: {}\n".format(
                    len(missing_report),
                    ", ".join("#{}".format(f) for _, um in missing_report for f in um)))
        if instances and n_written == 0:
            sys.stderr.write(
                "⚠ 所有 {} 个通槽实例均未映射到 NCTI cell_id，输出的是全 0 标签"
                "（疑似 NCTI 对齐失败），勿用于训练。\n".format(len(instances)))
        return [[part_name, {"seg": seg, "inst": inst, "bottom": bottom}]]

    # ── STEP advanced_faces 排序下标空间（无 NCTI 回退，不与训练对齐）──
    # 按出现顺序建立 face_id -> 0-based index 映射
    face_order = sorted(parser.advanced_faces.keys())
    face_id_to_index = {fid: idx for idx, fid in enumerate(face_order)}
    n_faces = len(face_order)

    # 初始化 seg 和 bottom
    seg = {str(i): 0 for i in range(n_faces)}
    bottom = {str(i): 0 for i in range(n_faces)}
    inst = [[0] * n_faces for _ in range(n_faces)]

    # 填充每个实例
    for inst_info in instances:
        instance_faces = inst_info["faces"]
        bottom_face = inst_info.get("bottom_face")
        # seg 标记
        for fid in instance_faces:
            idx = face_id_to_index.get(fid)
            if idx is not None:
                seg[str(idx)] = feature_seg_id
        # bottom 标记
        if bottom_face is not None:
            idx = face_id_to_index.get(bottom_face)
            if idx is not None:
                bottom[str(idx)] = 1
        # inst 邻接矩阵
        for fid_a in instance_faces:
            idx_a = face_id_to_index.get(fid_a)
            if idx_a is None:
                continue
            for fid_b in instance_faces:
                idx_b = face_id_to_index.get(fid_b)
                if idx_b is None:
                    continue
                inst[idx_a][idx_b] = 1

    return [[part_name, {"seg": seg, "inst": inst, "bottom": bottom}]]


# =============================================================================
# 报告生成
# =============================================================================

def build_report(parser, instances, stp_path, elapsed_ms):
    """生成识别报告文本。"""
    lines = []
    lines.append("双侧通槽台阶 (2-sided through step) 识别报告")
    lines.append("输入文件：{}".format(stp_path))
    lines.append("处理时间：{:.3f} ms".format(elapsed_ms))
    lines.append("")
    lines.append("高级面数量：{}".format(len(parser.advanced_faces)))
    lines.append("PLANE 面数量：{}".format(sum(1 for fid in parser.advanced_faces if parser.face_surface_type(fid) == "PLANE")))
    lines.append("识别实例数量：{}".format(len(instances)))
    lines.append("")

    if not instances:
        lines.append("未识别到双侧通槽台阶。")
        return "\n".join(lines)

    for i, inst_info in enumerate(instances, 1):
        lines.append("实例 #{}：".format(i))
        lines.append("  面 ID：{}".format(", ".join("#{}".format(f) for f in inst_info["faces"])))
        lines.append("  底面：#{}".format(inst_info["bottom_face"]))
        lines.append("  侧壁：{}".format(", ".join("#{}".format(f) for f in inst_info["side_walls"])))
        lines.append("  垂直对数：{}".format(inst_info["n_perpendicular_pairs"]))
        if inst_info.get("angles"):
            angle_desc = ", ".join("{}={}°".format(k, v) for k, v in sorted(inst_info["angles"].items()))
            lines.append("  法向量角度：{}".format(angle_desc))
        lines.append("")

    return "\n".join(lines)


# =============================================================================
# 主入口
# =============================================================================

def process_stp(stp_path, *, output_dir=None, feature_seg_id=FEATURE_SEG_ID, save_json=True, save_report=True):
    """处理单个 STEP 文件，返回 (instances, json_data, report_text, elapsed_ms)。"""
    import time
    start = time.perf_counter()

    parser = get_parser(stp_path)
    recognizer = ThroughStepRecognizer(parser, feature_seg_id=feature_seg_id)
    instances = recognizer.recognize()

    elapsed_ms = (time.perf_counter() - start) * 1000.0

    # NCTI 对齐（可选）：STEP face_id → ai.FaceID 位置索引。NCTI 不可用/零匹配则回退 STEP 下标。
    pos_map = n_cells = None
    if build_pos_map_for_step is not None:
        step_centroids = {}
        for fid in parser.advanced_faces:
            c = recognizer._face_centroid(fid)
            if c is not None:
                step_centroids[fid] = (float(c[0]), float(c[1]), float(c[2]))
        ncti = _get_ncti()
        pos_map, n_cells = build_pos_map_for_step(
            stp_path, step_centroids, ncti=ncti, project_root=PROJECT_ROOT)
    aligned = bool(pos_map)
    if pos_map is not None and not aligned:
        sys.stderr.write("⚠ NCTI 已导入但几何对齐零匹配，回退 STEP 面下标（不对齐，勿训练）\n")

    json_data = build_training_json(
        parser, instances, stp_path, feature_seg_id=feature_seg_id,
        pos_map=(pos_map if aligned else None),
        n_cells=(n_cells if aligned else None))
    report_text = build_report(parser, instances, stp_path, elapsed_ms)

    if output_dir is None:
        output_dir = OUTPUT_DIR

    if save_json or save_report:
        os.makedirs(output_dir, exist_ok=True)

    stem = os.path.splitext(os.path.basename(stp_path))[0]

    if save_json:
        json_path = os.path.join(output_dir, "{}.json".format(stem))
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        print("JSON 已保存：{}".format(json_path))

    if save_report:
        report_path = os.path.join(output_dir, "{}_report.txt".format(stem))
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_text)

    return instances, json_data, report_text, elapsed_ms


def process_batch(input_dir, *, output_dir=None, feature_seg_id=FEATURE_SEG_ID):
    """批量处理目录下所有 STEP 文件。"""
    input_dir = Path(input_dir)
    if output_dir is None:
        output_dir = OUTPUT_DIR

    json_output_dir = os.path.join(output_dir, "labels")
    os.makedirs(json_output_dir, exist_ok=True)

    stp_files = sorted(
        p for p in input_dir.iterdir()
        if p.is_file() and p.suffix.lower() in (".stp", ".step")
    )

    total = len(stp_files)
    found_count = 0
    total_instances = 0

    print("开始批量处理：{} 个 STEP 文件".format(total))
    print("输出目录：{}".format(output_dir))
    print("")

    for idx, stp_path in enumerate(stp_files, 1):
        try:
            instances, json_data, report_text, elapsed_ms = process_stp(
                str(stp_path),
                output_dir=output_dir,
                feature_seg_id=feature_seg_id,
                save_json=False,
                save_report=False,
            )
            if instances:
                found_count += 1
                total_instances += len(instances)
                # 保存 JSON
                json_path = os.path.join(json_output_dir, "{}.json".format(stp_path.stem))
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(json_data, f, ensure_ascii=False, indent=2)
                print("[{}/{}] {} -> {} 个实例 (JSON 已保存)".format(idx, total, stp_path.name, len(instances)))
            else:
                print("[{}/{}] {} -> 无通槽".format(idx, total, stp_path.name))
        except Exception as exc:
            print("[{}/{}] {} -> 错误: {}".format(idx, total, stp_path.name, exc))

    print("")
    print("批量处理完成：")
    print("  总文件数：{}".format(total))
    print("  识别到通槽的文件数：{}".format(found_count))
    print("  总实例数：{}".format(total_instances))
    print("  JSON 输出目录：{}".format(json_output_dir))


def main():
    ap = argparse.ArgumentParser(
        description="双侧通槽台阶 (2-sided through step) 几何识别器。"
        "输出与 AAGNet 训练标注格式一致的 JSON。"
    )
    ap.add_argument("input", nargs="?", default=INPUT_STP_PATH or None,
                    help="STP/STEP 文件路径，或包含 STEP 文件的目录")
    ap.add_argument("-o", "--output-dir", default=OUTPUT_DIR,
                    help="输出目录（默认：脚本目录/output）")
    ap.add_argument("--seg-id", type=int, default=FEATURE_SEG_ID,
                    help="seg 标签值（默认：{}）".format(FEATURE_SEG_ID))
    ap.add_argument("--no-json", action="store_true", help="不保存 JSON 文件")
    ap.add_argument("--no-report", action="store_true", help="不保存报告文件")
    args = ap.parse_args()

    if not args.input:
        ap.error("请传入 STP/STEP 文件路径或目录，或在脚本顶部填写 INPUT_STP_PATH")

    input_path = Path(args.input)

    if input_path.is_dir():
        process_batch(str(input_path), output_dir=args.output_dir, feature_seg_id=args.seg_id)
    elif input_path.is_file():
        instances, json_data, report_text, elapsed_ms = process_stp(
            str(input_path),
            output_dir=args.output_dir,
            feature_seg_id=args.seg_id,
            save_json=not args.no_json,
            save_report=not args.no_report,
        )
        print("")
        print(report_text)
    else:
        ap.error("输入路径不存在：{}".format(input_path))

    # NCTI 原生 DLL 析构可能 segfault；本次进程初始化过 NCTI 就直接退出
    if _NCTI_CACHE["ncti"] is not None:
        os._exit(0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
