#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
双侧通槽台阶 (2-sided through step) NCTI-native 几何识别器。

直接使用 NCTI AiModel 数据（FaceAttr/EdgeAttr/FaceEID/FaceFID），
在 cell_id 空间内完成识别，无需 STEP face → cell_id 映射。

核心改进：边凸凹性（EdgeAttr）作为候选生成阶段的硬约束，
从源头排除外凸角误检。

依赖：NCTI SDK（运行时需要 ncti/doc 对象）。
"""

import math
from collections import defaultdict
from itertools import combinations

from .geom_helpers import _dot, _angle_between_normals, _vec_len, _project_to_plane


# =============================================================================
# 阈值常量（与 STEP 版本一致）
# =============================================================================
PERP_MIN = 75.0
PERP_MAX = 105.0

MIN_INSTANCE_FACES = 3
MAX_INSTANCE_FACES = 6
MAX_RING_SIZE = 8            # 多边形环最大面数

# 多边形环检测阈值
PARALLEL_ANGLE_MAX = 15.0    # 对面平行判定（法向量夹角 < 15°视为平行）
RING_AREA_SYMMETRY_MIN = 0.2 # 环内对面面积比下限
RING_OPPOSED_MIN = 1         # 至少 1 对对面平行

CENTROID_T_MIN = -0.2
CENTROID_T_MAX = 1.2

MIN_FACE_AREA = 0.01
WALL_AREA_RATIO_MAX = 15.0
BOTTOM_WALL_RATIO_MIN = 0.5
WALL_ANGLE_MAX = 80.0
WALL_AREA_SYMMETRY_MIN = 0.3
BOTTOM_FREE_EDGES_MIN = 1

FILLET_AXIS_ALIGN_MIN = 75.0

MIN_SCORE = 35.0
MIN_HYBRID_SCORE = 82.0   # 矩形通槽（trio/extended）评分阈值
MIN_MIXED_SCORE = 76.0    # 混合 trio（含圆柱壁）评分阈值
MIN_RING_SCORE = 70.0     # 多边形环评分阈值
BOTTOM_NEIGHBOR_HARD_MAX = 7  # 底面邻接面数硬上限（通槽底面≤6，>7几乎不可能是通槽）


# =============================================================================
# NCTI-native 识别器
# =============================================================================

class ThroughStepRecognizerNCTI:
    """基于 NCTI AiModel 数据的双侧通槽台阶识别器。

    所有面 ID 均为 NCTI cell_id，无需 STEP→NCTI 映射。
    """

    def __init__(self, ncti, doc, obj_name):
        self.ncti = ncti
        self.doc = doc
        self.obj_name = obj_name

        # NCTI 原始数据
        ai = ncti.AiModel(doc, obj_name)
        self._face_ids = list(doc.FindAllFaces(obj_name) or [])
        self._face_attrs = ai.FaceAttr       # list[list[float]]
        self._edge_attrs = ai.EdgeAttr       # list[list[float]]
        self._face_eids = ai.FaceEID         # list[int] — 边的"到"面
        self._face_fids = ai.FaceFID         # list[int] — 边的"从"面

        # 衍生数据
        self._normal_map = {}    # cell_id → (nx, ny, nz)
        self._centroid_map = {}  # cell_id → (cx, cy, cz)
        self._area_map = {}      # cell_id → float
        self._adjacency = defaultdict(set)               # cell_id → set(cell_id)
        self._edge_convexity = {}                        # (min,max) → "concave"/"convex"/"smooth"
        self._edge_type = defaultdict(lambda: {"line": 0, "circle": 0, "other": 0})

        # 候选面分类
        self.plane_faces = []      # [(cell_id, normal_tuple)]
        self.cyl_faces = []        # [(cell_id, axis_dir_tuple)]
        self._all_candidate_ids = set()

        # 预计算
        self._build_face_id_index()
        self._precompute_face_data()
        self._precompute_adjacency_and_edges()

    # =========================================================================
    # 数据预计算
    # =========================================================================

    def _build_face_id_index(self):
        """构建 face_id → FaceAttr 索引映射。"""
        self._fid_to_idx = {}
        for i, fid in enumerate(self._face_ids):
            self._fid_to_idx[fid] = i

    def _precompute_face_data(self):
        """从 NCTI 提取面的法向量、重心、面积，并分类。"""
        for fid in self._face_ids:
            idx = self._fid_to_idx.get(fid)
            if idx is None:
                continue
            attr = self._face_attrs[idx]

            # 面积
            area = attr[5] if len(attr) > 5 else 0.0
            self._area_map[fid] = area

            # 法向量（平面：UV 中心点采样）
            normal = self._get_face_normal(fid)
            centroid = self._get_face_centroid(fid)

            if normal is not None:
                self._normal_map[fid] = normal
            if centroid is not None:
                self._centroid_map[fid] = centroid

            # 分类
            is_plane = attr[0] == 1.0 if len(attr) > 0 else False
            is_cyl = attr[1] == 1.0 if len(attr) > 1 else False

            if is_plane and normal is not None:
                self.plane_faces.append((fid, normal))
                self._all_candidate_ids.add(fid)
            elif is_cyl:
                # 圆柱面：通过两个采样点估算轴线方向
                axis_dir = self._get_cyl_axis(fid)
                if axis_dir is not None:
                    self.cyl_faces.append((fid, axis_dir))
                    self._all_candidate_ids.add(fid)

    def _precompute_adjacency_and_edges(self):
        """从 FaceEID/FaceFID 构建邻接图、凸凹性表、边类型表。"""
        for i in range(len(self._face_eids)):
            fa = self._face_eids[i]
            fb = self._face_fids[i]
            if fa is None or fb is None:
                continue
            # 只关心候选面之间的边
            if fa in self._all_candidate_ids and fb in self._all_candidate_ids:
                self._adjacency[fa].add(fb)
                self._adjacency[fb].add(fa)

            # 凸凹性
            key = (min(fa, fb), max(fa, fb))
            ea = self._edge_attrs[i] if i < len(self._edge_attrs) else []
            if len(ea) > 1 and ea[1]:      # 凸边
                self._edge_convexity[key] = "convex"
            elif len(ea) > 0 and ea[0]:    # 凹边
                self._edge_convexity[key] = "concave"
            else:
                self._edge_convexity[key] = "smooth"

            # 边类型统计
            if len(ea) > 9 and ea[9]:       # 直线
                self._edge_type[key]["line"] += 1
            elif len(ea) > 4 and ea[4]:     # 圆弧
                self._edge_type[key]["circle"] += 1
            else:
                self._edge_type[key]["other"] += 1

    # =========================================================================
    # NCTI 几何查询
    # =========================================================================

    def _get_face_normal(self, fid):
        """获取面法向量（UV 中心采样）。"""
        try:
            vec = self.doc.GetNormalByUV(self.obj_name, fid, 0.5, 0.5)
            if vec is not None:
                return (vec.X, vec.Y, vec.Z)
        except Exception:
            pass
        return None

    def _get_face_centroid(self, fid):
        """获取面重心（UV 中心采样）。"""
        try:
            pt = self.doc.GetFacePointFromUV(self.obj_name, fid, 0.5, 0.5)
            if pt is not None:
                return (pt.X, pt.Y, pt.Z)
        except Exception:
            pass
        return None

    def _get_cyl_axis(self, fid):
        """估算圆柱面轴线方向（两点差分）。"""
        try:
            p1 = self.doc.GetFacePointFromUV(self.obj_name, fid, 0.3, 0.5)
            p2 = self.doc.GetFacePointFromUV(self.obj_name, fid, 0.7, 0.5)
            if p1 is not None and p2 is not None:
                d = (p2.X - p1.X, p2.Y - p1.Y, p2.Z - p1.Z)
                length = _vec_len(d)
                if length > 1e-12:
                    return tuple(c / length for c in d)
        except Exception:
            pass
        return None

    # =========================================================================
    # 边统计工具
    # =========================================================================

    def _count_bottom_edges(self, bottom, walls):
        """统计底面的总边数、与侧壁共享的边数、自由边数。

        返回 (total_edges, shared_edges, free_edges)
        """
        # 底面所有邻接面
        bottom_neighbors = self._adjacency.get(bottom, set())
        wall_set = set(walls)

        # 遍历所有边，统计底面相关的边
        total = 0
        shared = 0
        for i in range(len(self._face_eids)):
            fa = self._face_eids[i]
            fb = self._face_fids[i]
            # 这条边是否连接底面
            if fa == bottom or fb == bottom:
                other = fb if fa == bottom else fa
                total += 1
                if other in wall_set:
                    shared += 1
        free = total - shared
        return total, shared, free

    # =========================================================================
    # 贯穿方向验证（核心优化）
    # =========================================================================

    def _verify_through_open_ends(self, bottom, walls, n_bottom):
        """验证通槽底面在通槽走向的两端均有开放端面。

        核心逻辑：
        1. 计算通槽走向 = 底面法向量 × 侧壁方向（叉积）
        2. 收集底面的自由邻接面（非侧壁邻接面）
        3. 将自由邻接面的重心投影到通槽方向
        4. 检查投影是否跨越正负两侧 → 两端开放

        这是区分通槽与盲槽/口袋/外凸角的关键：
        - 通槽：自由邻接面分布在通槽方向的两侧（两端开放）
        - 盲槽/口袋：自由邻接面集中在同侧（后壁）或环绕
        - 外凸角：自由邻接面分布不满足通槽结构

        Returns:
            (bool, dict): (是否通过验证, 调试信息)
        """
        c_bottom = self._centroid_map.get(bottom)
        c_a = self._centroid_map.get(walls[0])
        c_b = self._centroid_map.get(walls[1])

        if c_bottom is None or c_a is None or c_b is None:
            return False, {}

        # 侧壁方向（从 A 到 B 的单位向量）
        d_wall = tuple(c_b[k] - c_a[k] for k in range(3))
        d_len = _vec_len(d_wall)
        if d_len < 1e-12:
            return False, {}
        d_wall = tuple(c / d_len for c in d_wall)

        # 通槽走向 = 底面法向量 × 侧壁方向（叉积）
        through_dir = (
            n_bottom[1] * d_wall[2] - n_bottom[2] * d_wall[1],
            n_bottom[2] * d_wall[0] - n_bottom[0] * d_wall[2],
            n_bottom[0] * d_wall[1] - n_bottom[1] * d_wall[0],
        )
        td_len = _vec_len(through_dir)
        if td_len < 1e-12:
            return False, {}
        through_dir = tuple(c / td_len for c in through_dir)

        # 收集底面自由邻接面（非侧壁）
        wall_set = set(walls)
        free_neighbors = set()

        for i in range(len(self._face_eids)):
            fa = self._face_eids[i]
            fb = self._face_fids[i]
            if fa == bottom:
                other = fb
            elif fb == bottom:
                other = fa
            else:
                continue
            if other not in wall_set:
                free_neighbors.add(other)

        if len(free_neighbors) < 2:
            return False, {"n_free": len(free_neighbors)}

        # 将自由邻接面重心投影到通槽方向
        projections = []
        for fid in free_neighbors:
            c = self._centroid_map.get(fid)
            if c is None:
                continue
            d = sum((c[k] - c_bottom[k]) * through_dir[k] for k in range(3))
            projections.append(d)

        if len(projections) < 2:
            return False, {"n_proj": len(projections)}

        # 检查投影是否跨越正负两侧（通槽两端均有开放端面）
        has_pos = any(p > 1e-6 for p in projections)
        has_neg = any(p < -1e-6 for p in projections)

        return has_pos and has_neg, {
            "through_dir": through_dir,
            "n_free": len(free_neighbors),
            "projections": projections,
        }

    # =========================================================================
    # 核心验证（硬过滤）
    # =========================================================================

    def _validate_core(self, bottom, walls):
        """核心硬过滤。返回 result_dict 或 None。

        关键改进：凸凹性作为硬约束——底面与侧壁的共享边必须是凹边。
        """
        n_bottom = self._normal_map.get(bottom)
        n_wa = self._normal_map.get(walls[0])
        n_wb = self._normal_map.get(walls[1])
        if n_bottom is None or n_wa is None or n_wb is None:
            return None

        # ── 1. 垂直性检查 ──
        if not (PERP_MIN <= _angle_between_normals(n_bottom, n_wa) <= PERP_MAX):
            return None
        if not (PERP_MIN <= _angle_between_normals(n_bottom, n_wb) <= PERP_MAX):
            return None

        # ── 2. 互邻接验证 ──
        core = [bottom, walls[0], walls[1]]
        for i in range(3):
            for j in range(i + 1, 3):
                if core[j] not in self._adjacency.get(core[i], set()):
                    return None

        # ── 3. ★ 凸凹性检查（核心改进）──
        # 底面-每个侧壁的共享边必须是凹边或光滑边，不能是凸边
        for w in walls:
            key = (min(bottom, w), max(bottom, w))
            conv = self._edge_convexity.get(key, "smooth")
            if conv == "convex":
                return None  # 凸边 = 外凸角，不是内凹通槽

        # ── 3.5 底面邻接面数量（软评分，不再硬过滤）──
        # 通槽底面邻接面少（2侧壁 + 2-4开放端面 = 4-6）
        # 盲槽/口袋底面邻接面多（2侧壁 + 后壁 + 更多特征面 ≥ 7）
        bottom_neighbor_count = len(self._adjacency.get(bottom, set()))

        # ── 4. 通槽拓扑：底面应有自由边（开放端） ──
        total_ecs, shared_ecs, free_ecs = self._count_bottom_edges(bottom, walls)
        if free_ecs < BOTTOM_FREE_EDGES_MIN:
            return None

        # ── 5. 共享边类型：底面-侧壁共享边应主要为直线 ──
        for w in walls:
            key = (min(bottom, w), max(bottom, w))
            etype = self._edge_type.get(key, {})
            line_count = etype.get("line", 0)
            total_count = line_count + etype.get("circle", 0) + etype.get("other", 0)
            if total_count > 0 and line_count < total_count * 0.5:
                return None

        # ── 6. 侧壁夹角检查 ──
        wall_angle = _angle_between_normals(n_wa, n_wb)
        if wall_angle > WALL_ANGLE_MAX:
            return None

        # ── 7. 面积硬过滤 ──
        area_bottom = self._area_map.get(bottom, 0.0)
        area_wa = self._area_map.get(walls[0], 0.0)
        area_wb = self._area_map.get(walls[1], 0.0)

        if area_bottom < MIN_FACE_AREA and area_wa < MIN_FACE_AREA and area_wb < MIN_FACE_AREA:
            return None
        if area_bottom > 1e-12:
            if area_wa / area_bottom > WALL_AREA_RATIO_MAX or area_wb / area_bottom > WALL_AREA_RATIO_MAX:
                return None
        avg_wall_area = (area_wa + area_wb) / 2.0
        if area_bottom > 1e-12 and avg_wall_area > 1e-12:
            if area_bottom / avg_wall_area < BOTTOM_WALL_RATIO_MIN:
                return None
        if area_wa > 1e-12 and area_wb > 1e-12:
            if min(area_wa, area_wb) / max(area_wa, area_wb) < WALL_AREA_SYMMETRY_MIN:
                return None

        # ── 8. 重心位置硬过滤 ──
        c_bottom = self._centroid_map.get(bottom)
        c_a = self._centroid_map.get(walls[0])
        c_b = self._centroid_map.get(walls[1])
        centroid_t = None
        if c_bottom is not None and c_a is not None and c_b is not None:
            d = tuple(c_b[k] - c_a[k] for k in range(3))
            d_len_sq = sum(x * x for x in d)
            if d_len_sq > 1e-12:
                centroid_t = sum((c_bottom[k] - c_a[k]) * d[k] for k in range(3)) / d_len_sq
                if centroid_t < CENTROID_T_MIN or centroid_t > CENTROID_T_MAX:
                    return None

        # ── 9. 贯穿方向两端开放验证（改为评分加分项）──
        # 检测底面自由邻接面在通槽走向两侧的分布，记录结果用于评分。
        # 不再作为硬过滤，因为 NCTI 边数据可能缺少边界边的邻接面信息。
        through_ok, _ = self._verify_through_open_ends(bottom, walls, n_bottom)

        # ── 10. 底面邻接面数硬过滤 ──
        # 通槽底面邻接面少（2壁+2开放端面=4，含圆角≤6），
        # 邻接面 >7 说明底面被更多面包围，不是通槽。
        if bottom_neighbor_count > BOTTOM_NEIGHBOR_HARD_MAX:
            return None

        # ── 评分 ──
        score, _ = self._score_candidate(bottom, walls, n_bottom, n_wa, n_wb,
                                         area_bottom, area_wa, area_wb,
                                         total_ecs, shared_ecs, free_ecs,
                                         wall_angle, centroid_t, c_bottom, c_a, c_b)

        # ── 贯穿方向加分：验证通过 → +10 分 ──
        if through_ok:
            score = min(100, score + 10)

        # ── 邻接面软扣分：底面邻居过多 → 扣分（盲槽/口袋信号）──
        if bottom_neighbor_count > 5:
            penalty = (bottom_neighbor_count - 5) * 3.0
            score = max(0, score - penalty)

        # 角度信息
        normal_map = {bottom: n_bottom, walls[0]: n_wa, walls[1]: n_wb}
        angles = {}
        for i in range(3):
            for j in range(i + 1, 3):
                fi, fj = core[i], core[j]
                key = "{}_{}".format(min(fi, fj), max(fi, fj))
                angles[key] = round(_angle_between_normals(normal_map[fi], normal_map[fj]), 2)

        perp_count = sum(1 for v in angles.values() if PERP_MIN <= v <= PERP_MAX)

        return {
            "bottom_face": bottom,
            "side_walls": sorted(walls),
            "score": score,
            "angles": angles,
            "n_perpendicular_pairs": perp_count,
            "bottom_neighbor_count": bottom_neighbor_count,
            "centroid_t": centroid_t,
            "wall_angle": wall_angle,
        }

    # =========================================================================
    # 评分系统（8 维，总分 100）
    # =========================================================================

    def _score_candidate(self, bottom, walls, n_bottom, n_wa, n_wb,
                         area_bottom, area_wa, area_wb,
                         total_ecs, shared_ecs, free_ecs,
                         wall_angle, centroid_t,
                         c_bottom, c_a, c_b):
        """8 维评分（优化后权重分配，总分 100）。

        优化重点：增大法向量投影（U 型信号）和开放度权重，
        降低区分力不强的重心位置和底壁比权重。
        """
        # ── 1. 垂直精度分（25 分）─ 底面-侧壁⊥，通槽核心约束 ──
        a_b_wa = _angle_between_normals(n_bottom, n_wa)
        a_b_wb = _angle_between_normals(n_bottom, n_wb)
        q1 = max(0.0, 1.0 - abs(a_b_wa - 90.0) / 15.0)
        q2 = max(0.0, 1.0 - abs(a_b_wb - 90.0) / 15.0)
        s_perp = (q1 + q2) / 2.0 * 25.0

        # ── 2. 重心位置分（15 分）─ 底面重心应在两壁之间 ──
        s_centroid = 0.0
        if centroid_t is not None:
            s_centroid = max(0.0, 1.0 - abs(centroid_t - 0.5) / 0.5) * 15.0

        # ── 3. 面积对称性分（15 分）─ 两侧壁面积应相近 ──
        s_area = 0.0
        if area_wa > 1e-12 and area_wb > 1e-12:
            ratio = min(area_wa, area_wb) / max(area_wa, area_wb)
            s_area = ratio * 15.0

        # ── 4. 底面/侧壁面积比分（10 分）─ 通槽底面面积应合理 ──
        s_bottom_ratio = 0.0
        avg_wall = (area_wa + area_wb) / 2.0
        if avg_wall > 1e-12 and area_bottom > 1e-12:
            bw_ratio = area_bottom / avg_wall
            s_bottom_ratio = min(1.0, max(0.0, (bw_ratio - 0.3) / 0.7)) * 10.0

        # ── 5. 通槽开放度分（15 分）─ 自由边占比越高越像通槽 ──
        s_open = 0.0
        if total_ecs > 0:
            free_ratio = free_ecs / total_ecs
            s_open = min(1.0, free_ratio * 2.0) * 15.0

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
        n_neighbors_wa = len(self._adjacency.get(walls[0], set()))
        n_neighbors_wb = len(self._adjacency.get(walls[1], set()))
        s_edges = max(0.0, 5.0 - (max(n_neighbors_wa, n_neighbors_wb) - 4) * 1.0)

        # ── 8. 侧壁角度分（5 分） ──
        s_wall = max(0.0, 1.0 - wall_angle / 90.0) * 5.0

        score = round(s_perp + s_centroid + s_area + s_bottom_ratio +
                      s_open + s_proj + s_edges + s_wall, 1)
        return score, centroid_t

    # =========================================================================
    # 搜索路径 A：3 面 trio
    # =========================================================================

    def _find_trio_instances(self):
        """搜索 3 个平面面构成的简单通槽。"""
        normal_map = {fid: n for fid, n in self.plane_faces}
        plane_ids = sorted(normal_map.keys())
        results = []

        for fa in plane_ids:
            for fb in sorted(self._adjacency.get(fa, set())):
                if fb <= fa:
                    continue
                if fb not in normal_map:
                    continue
                common = self._adjacency.get(fa, set()) & self._adjacency.get(fb, set())
                for fc in sorted(common):
                    if fc <= fb:
                        continue
                    if fc not in normal_map:
                        continue
                    # 枚举哪个是底面
                    for bottom, walls in [(fa, [fb, fc]), (fb, [fa, fc]), (fc, [fa, fb])]:
                        result = self._validate_core(bottom, walls)
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
                                "wall_angle": result.get("wall_angle", 0),
                                "centroid_t": result.get("centroid_t"),
                                "bottom_neighbor_count": result.get("bottom_neighbor_count", 0),
                            })

        return results

    # =========================================================================
    # 搜索路径 B：4-6 面扩展组（含圆角过渡面）
    # =========================================================================

    def _find_extended_instances(self):
        """搜索带圆柱过渡面的通槽（4-6 面）。"""
        normal_map = {fid: n for fid, n in self.plane_faces}
        cyl_map = {fid: axis for fid, axis in self.cyl_faces}
        results = []

        for bottom_id, n_bottom in self.plane_faces:
            direct_neighbors = self._adjacency.get(bottom_id, set())

            # 垂直侧壁候选
            wall_candidates = []
            for fid in direct_neighbors:
                n_fid = normal_map.get(fid)
                if n_fid is not None:
                    angle = _angle_between_normals(n_bottom, n_fid)
                    if PERP_MIN <= angle <= PERP_MAX:
                        wall_candidates.append(fid)

            if len(wall_candidates) < 2:
                continue

            for i in range(len(wall_candidates)):
                for j in range(i + 1, len(wall_candidates)):
                    wa = wall_candidates[i]
                    wb = wall_candidates[j]

                    # 核心 trio 互邻接
                    if wb not in self._adjacency.get(wa, set()):
                        continue

                    # 核心验证（含凸凹性硬过滤）
                    core_result = self._validate_core(bottom_id, [wa, wb])
                    if core_result is None:
                        continue

                    # 寻找圆柱过渡面
                    relevant_fillets = []
                    for tfid, axis_dir in cyl_map.items():
                        if tfid not in direct_neighbors:
                            continue
                        adj_to_wa = tfid in self._adjacency.get(wa, set())
                        adj_to_wb = tfid in self._adjacency.get(wb, set())
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
                        "wall_angle": core_result.get("wall_angle", 0),
                        "centroid_t": core_result.get("centroid_t"),
                        "bottom_neighbor_count": core_result.get("bottom_neighbor_count", 0),
                    })

        return results

    # =========================================================================
    # 搜索路径 C：混合 trio（平面底面 + 平面壁 + 圆柱壁）
    # =========================================================================

    def _find_mixed_trio_instances(self):
        """搜索包含一个圆柱侧壁的通槽 trio。

        适用场景：通槽的一侧壁为圆柱面（如半圆截面），
        另一侧壁和底面为平面。例如 cell_ids [1, 2, 13] 中
        cell 2 是圆柱面充当侧壁。

        验证逻辑与 _validate_core 类似，但对圆柱壁使用
        轴线方向代替法向量做垂直性检查。
        """
        normal_map = {fid: n for fid, n in self.plane_faces}
        cyl_axis_map = {fid: axis for fid, axis in self.cyl_faces}
        results = []

        for bottom_id, n_bottom in self.plane_faces:
            bottom_neighbors = self._adjacency.get(bottom_id, set())

            # 找底面的平面壁候选（满足垂直 + 凹边）
            plane_wall_candidates = []
            for fid in bottom_neighbors:
                if fid not in normal_map:
                    continue
                n_fid = normal_map[fid]
                angle = _angle_between_normals(n_bottom, n_fid)
                if not (PERP_MIN <= angle <= PERP_MAX):
                    continue
                key = (min(bottom_id, fid), max(bottom_id, fid))
                conv = self._edge_convexity.get(key, "smooth")
                if conv == "convex":
                    continue
                plane_wall_candidates.append(fid)

            # 找底面的圆柱壁候选（轴线⊥底面法向量 + 凹边）
            cyl_wall_candidates = []
            for fid in bottom_neighbors:
                if fid not in cyl_axis_map:
                    continue
                axis = cyl_axis_map[fid]
                # 圆柱轴线应与底面法向量垂直（75-105°）
                axis_angle = _angle_between_normals(n_bottom, axis)
                if not (PERP_MIN <= axis_angle <= PERP_MAX):
                    continue
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
                    # 两个壁必须相邻
                    if cw not in self._adjacency.get(pw, set()):
                        continue
                    # 两个壁之间的边不能是凸边
                    key_wc = (min(pw, cw), max(pw, cw))
                    if self._edge_convexity.get(key_wc, "smooth") == "convex":
                        continue

                    # 验证混合 trio
                    result = self._validate_mixed_trio(
                        bottom_id, pw, cw, n_bottom, normal_map, cyl_axis_map
                    )
                    if result is not None:
                        faces = sorted([bottom_id, pw, cw])
                        results.append(result)

        return results

    def _validate_mixed_trio(self, bottom, plane_wall, cyl_wall,
                              n_bottom, normal_map, cyl_axis_map):
        """验证 平面底面+平面壁+圆柱壁 trio。"""
        n_pw = normal_map.get(plane_wall)
        axis_cw = cyl_axis_map.get(cyl_wall)
        if n_pw is None or axis_cw is None:
            return None

        # 底面邻接面数
        bottom_neighbor_count = len(self._adjacency.get(bottom, set()))

        # 自由边检查（底面应有不与壁共享的边）
        wall_set = {plane_wall, cyl_wall}
        total = 0
        shared = 0
        for i in range(len(self._face_eids)):
            fa = self._face_eids[i]
            fb = self._face_fids[i]
            if fa == bottom or fb == bottom:
                other = fb if fa == bottom else fa
                total += 1
                if other in wall_set:
                    shared += 1
        free = total - shared
        if free < BOTTOM_FREE_EDGES_MIN:
            return None

        # 面积检查
        area_bottom = self._area_map.get(bottom, 0.0)
        area_pw = self._area_map.get(plane_wall, 0.0)
        area_cw = self._area_map.get(cyl_wall, 0.0)
        if area_bottom < MIN_FACE_AREA and area_pw < MIN_FACE_AREA and area_cw < MIN_FACE_AREA:
            return None

        # 重心位置：平面壁重心、圆柱壁重心应在底面的两侧
        c_bottom = self._centroid_map.get(bottom)
        c_pw = self._centroid_map.get(plane_wall)
        c_cw = self._centroid_map.get(cyl_wall)

        # ── 贯穿方向两端开放验证（改为评分加分项）──
        through_ok, _ = self._verify_through_open_ends(bottom, [plane_wall, cyl_wall], n_bottom)

        # ── 底面邻接面数硬过滤 ──
        if bottom_neighbor_count > BOTTOM_NEIGHBOR_HARD_MAX:
            return None

        # 评分
        score = self._score_mixed_trio(
            bottom, plane_wall, cyl_wall,
            n_bottom, n_pw, axis_cw,
            area_bottom, area_pw, area_cw,
            total, shared, free,
            c_bottom, c_pw, c_cw
        )

        # ── 贯穿方向加分 ──
        if through_ok:
            score = min(100, score + 10)

        # 邻接面软评分
        if bottom_neighbor_count > 5:
            penalty = (bottom_neighbor_count - 5) * 3.0
            score = max(0, score - penalty)

        return {
            "faces": sorted([bottom, plane_wall, cyl_wall]),
            "bottom_face": bottom,
            "side_walls": sorted([plane_wall, cyl_wall]),
            "score": score,
            "angles": {},
            "n_perpendicular_pairs": 1,
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

        评分维度：
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
        # 混合 trio 的底面可能很窄（窄条），所以不用底壁比
        # 改用壁面面积是否合理（不能为 0）
        s_area = 0.0
        if area_pw > MIN_FACE_AREA and area_cw > MIN_FACE_AREA:
            # 两个壁面都有合理面积 → 满分
            s_area = 15.0
        elif area_pw > MIN_FACE_AREA or area_cw > MIN_FACE_AREA:
            # 至少一个壁面有合理面积 → 一半分
            s_area = 7.5

        # 5. 重心分布（10 分）— 两壁应在底面的不同侧
        s_centroid = 5.0  # 默认给一半
        if c_bottom is not None and c_pw is not None and c_cw is not None:
            d_pw = tuple(c_pw[k] - c_bottom[k] for k in range(3))
            d_cw = tuple(c_cw[k] - c_bottom[k] for k in range(3))
            dot_pw_cw = _dot(d_pw, d_cw)
            if dot_pw_cw < 0:
                # 两壁在底面两侧 → 更像通槽
                s_centroid = 10.0
            else:
                s_centroid = 2.0

        # 6. 边数合理性（10 分）
        n_pw_neighbors = len(self._adjacency.get(pw, set()))
        n_cw_neighbors = len(self._adjacency.get(cw, set()))
        s_edges = max(0.0, 10.0 - (max(n_pw_neighbors, n_cw_neighbors) - 3) * 1.5)

        return round(s_perp + s_axis + s_open + s_area + s_centroid + s_edges, 1)

    # =========================================================================
    # 搜索路径 D：多边形凹边环通槽（六边形等多边形截面）
    # =========================================================================

    def _find_ring_instances(self):
        """搜索由凹边连接的平面面环构成的多边形通槽。

        适用场景：六边形、八边形等非矩形截面的通槽。
        这些面之间不满足 90° 垂直关系，但具有：
        1. 全部由凹边连接（内凹槽）
        2. 对面平行（对称截面）
        3. 沿一个方向"贯通"（通槽走向）
        """
        normal_map = {fid: n for fid, n in self.plane_faces}
        plane_ids = set(normal_map.keys())
        results = []

        # ── 1. 构建仅凹边的邻接子图 ──
        concave_adj = defaultdict(set)
        for (fa, fb), conv in self._edge_convexity.items():
            if conv != "concave":
                continue
            if fa in plane_ids and fb in plane_ids:
                concave_adj[fa].add(fb)
                concave_adj[fb].add(fa)

        if not concave_adj:
            return results

        # ── 2. 找所有凹边环（DFS） ──
        rings = self._find_all_rings(concave_adj, plane_ids)

        # ── 3. 验证每个环 ──
        for ring in rings:
            if len(ring) < MIN_INSTANCE_FACES or len(ring) > MAX_RING_SIZE:
                continue
            validated = self._validate_ring(ring, normal_map)
            if validated is not None:
                results.append(validated)

        return results

    def _find_all_rings(self, concave_adj, valid_ids):
        """在凹边邻接子图上找所有简单环。

        使用 DFS + 回溯，限制环大小 ≤ MAX_RING_SIZE。
        为避免重复，只保留 sorted 的环。
        """
        found = set()  # frozenset 去重
        result = []

        for start in sorted(concave_adj.keys()):
            # DFS 栈: (当前节点, 路径, 访问集合)
            stack = [(start, [start], {start})]
            while stack:
                node, path, visited = stack.pop()
                for neighbor in sorted(concave_adj.get(node, set())):
                    if neighbor == start and len(path) >= MIN_INSTANCE_FACES:
                        # 找到环
                        ring_key = frozenset(path)
                        if ring_key not in found:
                            found.add(ring_key)
                            result.append(list(path))
                    elif neighbor > start and neighbor not in visited and len(path) < MAX_RING_SIZE:
                        # neighbor > start 避免重复（只从最小 ID 开始）
                        stack.append((neighbor, path + [neighbor], visited | {neighbor}))

        return result

    def _validate_ring(self, ring, normal_map):
        """验证一个凹边环是否为多边形通槽。

        检查：
        1. 环内无凸边（已经是凹边子图，但二次确认）
        2. 至少有 1 对对面平行
        3. 重心沿一个方向排列（通槽走向）
        4. 面积合理性
        """
        ring_set = set(ring)
        n = len(ring)

        # 环内法向量
        normals = {}
        for fid in ring:
            nm = normal_map.get(fid)
            if nm is None:
                return None
            normals[fid] = nm

        # ── 1. 确认环内所有边均为凹边 ──
        for i in range(n):
            fa = ring[i]
            fb = ring[(i + 1) % n]
            key = (min(fa, fb), max(fa, fb))
            conv = self._edge_convexity.get(key, "smooth")
            if conv == "convex":
                return None

        # ── 2. 找对面平行的面 ──
        opposed_pairs = []
        for i in range(n):
            for j in range(i + 1, n):
                angle = _angle_between_normals(normals[ring[i]], normals[ring[j]])
                if angle < PARALLEL_ANGLE_MAX or angle > (180.0 - PARALLEL_ANGLE_MAX):
                    # 平行（法向量同向或反向）
                    # 确认不是相邻面
                    j_next = (j + 1) % n
                    j_prev = (j - 1) % n
                    if ring[i] != ring[j_next] and ring[i] != ring[j_prev]:
                        area_i = self._area_map.get(ring[i], 0.0)
                        area_j = self._area_map.get(ring[j], 0.0)
                        opposed_pairs.append((ring[i], ring[j], area_i, area_j))

        if len(opposed_pairs) < RING_OPPOSED_MIN:
            return None

        # ── 3. 重心排列分析（通槽走向） ──
        centroids = {}
        for fid in ring:
            c = self._centroid_map.get(fid)
            if c is None:
                return None
            centroids[fid] = c

        # 计算所有面的重心均值和主方向
        cx = sum(centroids[fid][0] for fid in ring) / n
        cy = sum(centroids[fid][1] for fid in ring) / n
        cz = sum(centroids[fid][2] for fid in ring) / n

        # 计算重心散布的主方向（最大方差方向 = 通槽走向）
        # 用 PCA 思想：3x3 协方差矩阵最大特征值对应方向
        cov = [[0.0] * 3 for _ in range(3)]
        for fid in ring:
            dx = centroids[fid][0] - cx
            dy = centroids[fid][1] - cy
            dz = centroids[fid][2] - cz
            cov[0][0] += dx * dx
            cov[0][1] += dx * dy
            cov[0][2] += dx * dz
            cov[1][1] += dy * dy
            cov[1][2] += dy * dz
            cov[2][2] += dz * dz
        cov[1][0] = cov[0][1]
        cov[2][0] = cov[0][2]
        cov[2][1] = cov[1][2]

        # 幂迭代求最大特征向量（只需几次迭代）
        v = (1.0, 0.0, 0.0)
        for _ in range(20):
            vx = cov[0][0] * v[0] + cov[0][1] * v[1] + cov[0][2] * v[2]
            vy = cov[1][0] * v[0] + cov[1][1] * v[1] + cov[1][2] * v[2]
            vz = cov[2][0] * v[0] + cov[2][1] * v[1] + cov[2][2] * v[2]
            vlen = math.sqrt(vx * vx + vy * vy + vz * vz)
            if vlen < 1e-12:
                return None
            v = (vx / vlen, vy / vlen, vz / vlen)

        # 主方向 = 通槽走向
        through_dir = v

        # 沿通槽方向的重心投影，计算跨度
        projections = [_dot(centroids[fid], through_dir) for fid in ring]
        span = max(projections) - min(projections)
        if span < 1e-6:
            return None

        # 沿主方向散布 vs 垂直散布：通槽应有明显的沿通槽方向的延展
        perp_spreads = []
        for fid in ring:
            proj_along = _dot(centroids[fid], through_dir)
            residual = tuple(centroids[fid][k] - proj_along * through_dir[k] for k in range(3))
            perp_spreads.append(_vec_len(residual))
        avg_perp = sum(perp_spreads) / len(perp_spreads) if perp_spreads else 0
        # 通槽：沿走向跨度 >> 垂直散布
        if span < avg_perp * 0.5:
            return None

        # ── 4. 面积合理性 ──
        areas = {fid: self._area_map.get(fid, 0.0) for fid in ring}
        total_area = sum(areas.values())
        if total_area < MIN_FACE_AREA:
            return None

        # ── 5. 贯穿方向两端开放验证（多边形环） ──
        # 对于环结构，检查环外部的邻接面是否在通槽走向的两侧分布
        # （复用前面已计算的 cx, cy, cz 作为环的重心中心）
        ring_external_projs = []
        for fid in ring:
            for neighbor in self._adjacency.get(fid, set()):
                if neighbor in ring_set:
                    continue
                c_n = self._centroid_map.get(neighbor)
                if c_n is None:
                    continue
                d = ((c_n[0] - cx) * through_dir[0] +
                     (c_n[1] - cy) * through_dir[1] +
                     (c_n[2] - cz) * through_dir[2])
                ring_external_projs.append(d)

        # ── 5. 贯穿方向两端开放验证（改为评分加分项）──
        ring_through_ok = False
        if len(ring_external_projs) >= 2:
            has_pos_ext = any(p > 1e-6 for p in ring_external_projs)
            has_neg_ext = any(p < -1e-6 for p in ring_external_projs)
            ring_through_ok = has_pos_ext and has_neg_ext

        # ── 评分 ──
        score = self._score_ring(ring, opposed_pairs, normals, centroids, areas,
                                 through_dir, span, avg_perp)

        # ── 贯穿方向加分 ──
        if ring_through_ok:
            score = min(100, score + 10)

        # 邻接面软评分
        # 对环内的每个面，计算外部邻接面数（不含环内的）
        max_external = 0
        for fid in ring:
            external = len(self._adjacency.get(fid, set()) - ring_set)
            if external > max_external:
                max_external = external

        return {
            "faces": sorted(ring),
            "bottom_face": None,        # 多边形环无明确底面
            "side_walls": sorted(ring), # 整个环都是"壁面"
            "score": score,
            "angles": {},
            "n_perpendicular_pairs": 0,
            "type": "polygonal_{}ring".format(n),
            "fillets": [],
            "wall_angle": 0,
            "centroid_t": None,
            "bottom_neighbor_count": max_external,
            "opposed_pairs": len(opposed_pairs),
            "through_dir": through_dir,
            "span": span,
        }

    def _score_ring(self, ring, opposed_pairs, normals, centroids, areas,
                    through_dir, span, avg_perp):
        """多边形环通槽评分（总分 100）。

        评分维度：
        1. 对面平行对数（30 分）— 越多越像对称通槽
        2. 面积对称性（25 分）— 对面面积应相近
        3. 通槽走向延伸度（20 分）— 沿走向跨度 vs 垂直散布
        4. 面积均匀性（15 分）— 环内各面面积应相近
        5. 环完整性（10 分）— 环的面数越少越可靠
        """
        n = len(ring)
        n_opposed = len(opposed_pairs)

        # ── 1. 对面平行对数（30 分）──
        # 至少 1 对给基础分，每多 1 对加分，最多 3 对满
        max_possible = n // 2
        if max_possible > 0:
            s_opposed = min(1.0, n_opposed / max_possible) * 30.0
        else:
            s_opposed = 0.0

        # ── 2. 面积对称性（25 分）──
        # 每对对面的面积比取平均
        if opposed_pairs:
            ratios = []
            for fa, fb, area_a, area_b in opposed_pairs:
                if area_a > 1e-12 and area_b > 1e-12:
                    ratios.append(min(area_a, area_b) / max(area_a, area_b))
            avg_ratio = sum(ratios) / len(ratios) if ratios else 0.0
            s_area_sym = avg_ratio * 25.0
        else:
            s_area_sym = 0.0

        # ── 3. 通槽走向延伸度（20 分）──
        # span / (span + avg_perp) → 越接近 1 越好（通槽应沿走向延伸）
        elongation = span / (span + avg_perp) if (span + avg_perp) > 1e-12 else 0
        s_elongation = elongation * 20.0

        # ── 4. 面积均匀性（15 分）──
        # 环内各面面积的变异系数（CV），越小越好
        area_vals = [areas[fid] for fid in ring if areas[fid] > 1e-12]
        if area_vals:
            mean_area = sum(area_vals) / len(area_vals)
            if mean_area > 1e-12:
                variance = sum((a - mean_area) ** 2 for a in area_vals) / len(area_vals)
                cv = math.sqrt(variance) / mean_area
                s_uniform = max(0.0, 1.0 - cv) * 15.0
            else:
                s_uniform = 0.0
        else:
            s_uniform = 0.0

        # ── 5. 环完整性（10 分）──
        # 面数越少越可靠（4-6 面最佳）
        if n <= 6:
            s_ring = 10.0
        elif n <= 8:
            s_ring = 7.0
        else:
            s_ring = 3.0

        return round(s_opposed + s_area_sym + s_elongation + s_uniform + s_ring, 1)

    # =========================================================================
    # 合并 + 排序 + 贪心
    # =========================================================================

    def recognize(self):
        """返回 list of dict，每个 dict 是一个通槽实例。"""
        trio_results = self._find_trio_instances()
        extended_results = self._find_extended_instances()
        mixed_results = self._find_mixed_trio_instances()
        ring_results = self._find_ring_instances()

        all_results = trio_results + extended_results + mixed_results + ring_results

        # 评分过滤（基础门槛）
        all_results = [r for r in all_results if r.get("score", 0) >= MIN_SCORE]

        # 按类型使用不同阈值
        def _type_threshold(r):
            t = r.get("type", "")
            if t.startswith("mixed"):
                return MIN_MIXED_SCORE
            elif t.startswith("polygonal"):
                return MIN_RING_SCORE
            else:
                return MIN_HYBRID_SCORE

        before = len(all_results)
        all_results = [r for r in all_results if r.get("score", 0) >= _type_threshold(r)]
        dropped = before - len(all_results)
        if dropped > 0:
            for r in all_results:
                pass  # kept
            print("评分阈值过滤：排除 {} 个低分实例".format(dropped))

        # 去重（同 face 集合取高分）
        best = {}
        for r in all_results:
            key = tuple(r["faces"])
            if key not in best or r.get("score", 0) > best[key].get("score", 0):
                best[key] = r
        all_results = list(best.values())

        # 评分排序
        all_results.sort(key=lambda r: r.get("score", 0), reverse=True)

        # 贪心选面
        used_faces = set()
        instances = []
        for result in all_results:
            result_faces = set(result["faces"])
            if result_faces & used_faces:
                continue
            instances.append(result)
            used_faces.update(result_faces)

        return instances


# =============================================================================
# 对外接口
# =============================================================================

def recognize_through_steps_ncti(ncti, doc, obj_name):
    """NCTI-native 通槽识别入口。

    参数:
        ncti: NCTI 对象
        doc: NCTI Document 对象
        obj_name: 模型对象名称

    返回 dict:
        instances: list of dict（每个通槽实例，cell_id 空间）
        selected_cells: list of int（所有要高亮的 cell_id）
        obj_name: str
    """
    recognizer = ThroughStepRecognizerNCTI(ncti, doc, obj_name)
    instances = recognizer.recognize()

    selected_cells = []
    for inst in instances:
        selected_cells.extend(inst["faces"])
    # 去重保序
    seen = set()
    unique = []
    for cid in selected_cells:
        if cid not in seen:
            seen.add(cid)
            unique.append(cid)

    return {
        "instances": instances,
        "selected_cells": unique,
        "obj_name": obj_name,
    }
