#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
STEP/STP blind-hole recognizer, v11-standard-flat-sealed.

运行指令：
python detect_blind_holes_and_export_stp_v19_shared_disk_integrity.py STP文件路径
python detect_blind_holes_and_export_stp_v19_shared_disk_integrity.py stp_file\含倒角、圆角、通孔、盲孔(单solid).stp

也可以直接填写脚本顶部的 INPUT_STP_PATH / OUTPUT_STP_PATH / OUTPUT_LOG_PATH，
然后运行：
python detect_blind_holes_and_export_stp_v19_shared_disk_integrity.py
核心识别逻辑：

1. 使用更严格的标准盲孔加工特征定义：
完整的圆形开口 + 独立的圆柱壁 + 非贯穿轴 +
密封的内平面底部。允许开口处有倒角；锥形/圆弧形底部
默认排除。

2. 保留独立孔过滤器。不将回流通道、
长内通道、槽壁、圆形端面凹槽、侧向断孔
或部分圆柱边界区域计为盲孔。

3. 允许非常浅的干净平底盲孔：普通的沉孔/点孔
即使轴向跨度很短，只要具有两个干净的
圆形端环和简单的单环平面底部，仍然可以被视为有效的盲孔。

4. 排除底部平面为大型或
复杂共享平面而非单个圆形底部的假平底候选孔。

5. 遵循盲孔的加工特征定义：首选开口为
完整的圆形开口。不包括圆端凹槽、盲槽、口袋、
侧断孔和部分圆柱壁。

6. 共用的矩形内平面可作为底部封闭结构，但
末端圆锥面/环面/球面底部不
计入标准盲孔。
"""

import argparse
import datetime as _dt
import os
import re
import time
from collections import defaultdict, deque

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT_DIR = os.path.join(ROOT_DIR, "detailed检测结果")

# =============================================================================
# 可选配置区：如果不想从命令行传参，可以直接在这里填写路径。
# 命令行参数优先级更高；留空字符串表示使用默认逻辑。
# =============================================================================
INPUT_STP_PATH = "C:\\Users\\12290\\Desktop\\CAD\\YHCADSmartCleaner\\blind_hole\\stp_file\\BAACK-D25.stp"
OUTPUT_STP_PATH = ""
OUTPUT_LOG_PATH = ""
OUTPUT_STP_DIR = "C:\\Users\\12290\\Desktop\\CAD\\YHCADSmartCleaner\\blind_hole\\stp_export"
OUTPUT_LOG_DIR = "C:\\Users\\12290\\Desktop\\CAD\\YHCADSmartCleaner\\blind_hole\\log_export"

TERMINATING_SURFACES = {
    "PLANE",
    "CONICAL_SURFACE",
    "TOROIDAL_SURFACE",
    "SPHERICAL_SURFACE",
    "BSPLINE_SURFACE_WITH_KNOTS",
    "B_SPLINE_SURFACE_WITH_KNOTS",
}
ROUND_SURFACES = {"TOROIDAL_SURFACE", "SPHERICAL_SURFACE"}
# 入口过渡面：不仅 CONICAL_SURFACE 可能表示倒角入口，部分 STEP/OCC 导出
# 会把圆角/倒圆入口表示成 TOROIDAL_SURFACE，且该面通常带 SEAM_CURVE。
# 只要该过渡面在一跳内连接到外部 PLANE，就应按“入口倒角/圆角”处理。
ENTRY_TRANSITION_SURFACES = {"CONICAL_SURFACE", "TOROIDAL_SURFACE"}


def ref(num):
    return f"#{num}" if num is not None else "-"


def fmt_float(value):
    if value is None:
        return "-"
    text = f"{value:.10g}"
    return "0" if text == "-0" else text


def fmt_vec(values):
    if not values:
        return "-"
    return "(" + ", ".join(fmt_float(v) for v in values) + ")"


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


class StepParser:
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
        self.vertex_points = {}
        self.surfaces = {}
        self.face_to_edge_curves = defaultdict(set)
        self.face_to_edges_by_bound = defaultdict(list)

    def parse(self):
        with open(self.path, "r", encoding="utf-8", errors="ignore") as handle:
            content = handle.read()

        data_match = re.search(r"DATA;\s*(.*?)\s*ENDSEC;", content, re.S | re.I)
        data = data_match.group(1) if data_match else content

        # NOTE: This simple regex works for the tested OpenCASCADE AP214 text file.
        for match in re.finditer(r"#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*?)\)\s*;", data, re.S):
            eid = int(match.group(1))
            etype = match.group(2).upper()
            params = " ".join(match.group(3).split())
            self.entities[eid] = {"type": etype, "params": params, "raw": match.group(0)}

        for eid, ent in self.entities.items():
            etype = ent["type"]
            params = ent["params"]
            if etype == "CARTESIAN_POINT":
                self.points[eid] = self._parse_tuple(params)
            elif etype == "DIRECTION":
                self.directions[eid] = self._parse_tuple(params)
            elif etype == "VERTEX_POINT":
                self._parse_vertex_point(eid, params)
            elif etype == "AXIS2_PLACEMENT_3D":
                self._parse_axis2(eid, params)
            elif etype in {
                "CYLINDRICAL_SURFACE",
                "CONICAL_SURFACE",
                "TOROIDAL_SURFACE",
                "SPHERICAL_SURFACE",
                "PLANE",
                "BSPLINE_SURFACE_WITH_KNOTS",
                "B_SPLINE_SURFACE_WITH_KNOTS",
            }:
                self._parse_surface(eid, etype, params)
            elif etype == "ADVANCED_FACE":
                self._parse_advanced_face(eid, params)
            elif etype in {"FACE_BOUND", "FACE_OUTER_BOUND"}:
                self._parse_face_bound(eid, etype, params)
            elif etype == "EDGE_LOOP":
                self._parse_edge_loop(eid, params)
            elif etype == "ORIENTED_EDGE":
                self._parse_oriented_edge(eid, params)
            elif etype == "EDGE_CURVE":
                self._parse_edge_curve(eid, params)

        self._build_topology_indexes()

    def _split_top_level(self, text):
        parts = []
        current = []
        depth = 0
        in_string = False
        quote = ""
        for char in text:
            if char in {"'", '"'}:
                if not in_string:
                    in_string = True
                    quote = char
                elif quote == char:
                    in_string = False
                current.append(char)
            elif in_string:
                current.append(char)
            elif char == "(":
                depth += 1
                current.append(char)
            elif char == ")":
                depth -= 1
                current.append(char)
            elif char == "," and depth == 0:
                parts.append("".join(current).strip())
                current = []
            else:
                current.append(char)
        if current:
            parts.append("".join(current).strip())
        return parts

    def _parse_tuple(self, params):
        match = re.search(r"\(([^()]*)\)", params)
        if not match:
            return None
        values = []
        for item in match.group(1).split(","):
            try:
                values.append(float(item.strip()))
            except ValueError:
                pass
        return tuple(values)

    def _refs(self, text):
        return [int(item) for item in re.findall(r"#(\d+)", text)]

    def _parse_vertex_point(self, eid, params):
        refs = self._refs(params)
        if refs:
            self.vertex_points[eid] = refs[0]

    def _parse_axis2(self, eid, params):
        refs = self._refs(params)
        self.axis2[eid] = {
            "point_ref": refs[0] if len(refs) >= 1 else None,
            "axis_ref": refs[1] if len(refs) >= 2 else None,
            "ref_direction_ref": refs[2] if len(refs) >= 3 else None,
        }

    def _parse_surface(self, eid, etype, params):
        refs = self._refs(params)
        parts = self._split_top_level(params)
        data = {"type": etype, "axis_ref": refs[0] if refs else None, "radius": None, "semi_angle": None}
        if etype in {"CYLINDRICAL_SURFACE", "SPHERICAL_SURFACE"} and len(parts) >= 3:
            data["radius"] = self._to_float(parts[2])
        elif etype == "CONICAL_SURFACE" and len(parts) >= 4:
            data["radius"] = self._to_float(parts[2])
            data["semi_angle"] = self._to_float(parts[3])
        elif etype == "TOROIDAL_SURFACE" and len(parts) >= 4:
            data["major_radius"] = self._to_float(parts[2])
            data["minor_radius"] = self._to_float(parts[3])
            data["radius"] = data["minor_radius"]
        self.surfaces[eid] = data

    def _to_float(self, text):
        try:
            return float(text.strip())
        except (TypeError, ValueError):
            return None

    def _parse_advanced_face(self, eid, params):
        parts = self._split_top_level(params)
        if len(parts) < 4:
            return
        bounds = self._refs(parts[1])
        surface_refs = self._refs(parts[2])
        if not surface_refs:
            return
        surface_id = surface_refs[0]
        self.advanced_faces[eid] = {"bounds": bounds, "surface": surface_id, "same_sense": parts[3].upper() == ".T."}
        self.surface_to_faces[surface_id].append(eid)

    def _parse_face_bound(self, eid, etype, params):
        parts = self._split_top_level(params)
        refs = self._refs(parts[1] if len(parts) > 1 else params)
        self.face_bounds[eid] = {"type": etype, "loop": refs[0] if refs else None, "is_outer": etype == "FACE_OUTER_BOUND"}

    def _parse_edge_loop(self, eid, params):
        self.edge_loops[eid] = self._refs(params)

    def _parse_oriented_edge(self, eid, params):
        parts = self._split_top_level(params)
        refs = self._refs(parts[3] if len(parts) > 3 else params)
        curve = refs[0] if refs else None
        self.oriented_edges[eid] = {"curve": curve}

    def _parse_edge_curve(self, eid, params):
        refs = self._refs(params)
        if len(refs) >= 3:
            self.edge_curves[eid] = {"v1": refs[0], "v2": refs[1], "curve": refs[2]}

    def _build_topology_indexes(self):
        for face_id, face in self.advanced_faces.items():
            for bound_id in face["bounds"]:
                bound = self.face_bounds.get(bound_id, {})
                loop_id = bound.get("loop")
                curves = []
                for oriented_edge in self.edge_loops.get(loop_id, []):
                    curve = self.oriented_edges.get(oriented_edge, {}).get("curve")
                    if curve is None:
                        continue
                    curves.append({"bound": bound_id, "loop": loop_id, "oriented_edge": oriented_edge, "edge_curve": curve})
                    self.face_to_edge_curves[face_id].add(curve)
                    self.edge_curve_to_faces[curve].add(face_id)
                self.face_to_edges_by_bound[face_id].append(
                    {"bound": bound_id, "loop": loop_id, "is_outer": bound.get("is_outer", False), "curves": curves}
                )

    def face_surface_type(self, face_id):
        surface = self.advanced_faces.get(face_id, {}).get("surface")
        return self.entities.get(surface, {}).get("type", "UNKNOWN")

    def face_surface_id(self, face_id):
        return self.advanced_faces.get(face_id, {}).get("surface")

    def axis_info(self, surface_id):
        surface = self.surfaces.get(surface_id, {})
        axis = self.axis2.get(surface.get("axis_ref"), {})
        return {
            "point": self.points.get(axis.get("point_ref")),
            "direction": self.directions.get(axis.get("axis_ref")),
            "ref_direction": self.directions.get(axis.get("ref_direction_ref")),
        }

    def face_bound_count(self, face_id):
        bounds = self.advanced_faces.get(face_id, {}).get("bounds", [])
        outer = 0
        inner = 0
        for bound_id in bounds:
            if self.face_bounds.get(bound_id, {}).get("is_outer"):
                outer += 1
            else:
                inner += 1
        return outer, inner, len(bounds)

    def face_loop_curve_counts(self, face_id):
        """Return the number of unique EDGE_CURVE items in each FACE_BOUND loop."""
        counts = []
        for bound in self.face_to_edges_by_bound.get(face_id, []):
            counts.append(len({item["edge_curve"] for item in bound.get("curves", [])}))
        return counts

    def face_total_curve_count(self, face_id):
        return sum(self.face_loop_curve_counts(face_id))

    def vertex_xyz(self, vertex_id):
        point_ref = self.vertex_points.get(vertex_id)
        return self.points.get(point_ref)

    def edge_vertices_xyz(self, edge_curve_id):
        edge = self.edge_curves.get(edge_curve_id)
        if not edge:
            return []
        pts = []
        for vid in (edge.get("v1"), edge.get("v2")):
            p = self.vertex_xyz(vid)
            if p is not None:
                pts.append(p)
        return pts

    def edge_base_curve_type(self, edge_curve_id):
        edge = self.edge_curves.get(edge_curve_id)
        if not edge:
            return "UNKNOWN"
        curve_ref = edge.get("curve")
        ent = self.entities.get(curve_ref, {})
        if ent.get("type") == "SURFACE_CURVE":
            refs = self._refs(ent.get("params", ""))
            if refs:
                return self.entities.get(refs[0], {}).get("type", "UNKNOWN")
        return ent.get("type", "UNKNOWN")

    def edge_vertex_refs(self, edge_curve_id):
        edge = self.edge_curves.get(edge_curve_id)
        if not edge:
            return []
        return [edge.get("v1"), edge.get("v2")]

    def cylindrical_face_axial_span(self, surface_id, face_id):
        axis = self.axis_info(surface_id)
        p0 = axis.get("point")
        direction = axis.get("direction")
        if not p0 or not direction:
            return None
        values = []
        for bound in self.face_to_edges_by_bound.get(face_id, []):
            for item in bound["curves"]:
                for p in self.edge_vertices_xyz(item["edge_curve"]):
                    values.append(dot(tuple(p[i] - p0[i] for i in range(3)), direction))
        if not values:
            return None
        return max(values) - min(values)


class BlindHoleRecognizer:
    def __init__(
        self,
        parser,
        min_radius=0.0,
        min_depth_ratio=1.2,
        min_depth_abs=2.0,
        max_complex_span_ratio=20.0,
        max_intersection_trace_faces=14,
        max_simple_bottom_curves=4,
        require_circular_mouth=True,
        allow_shared_plane_bottom_mouth_exception=True,
    ):
        self.parser = parser
        self.min_radius = min_radius
        self.min_depth_ratio = min_depth_ratio
        self.min_depth_abs = min_depth_abs
        # A very long, single-complex-bound cylinder is often an internal passage or
        # channel wall rather than a blind hole. This is only applied to complex
        # single-bound/intersecting candidates, not to clean two-loop holes.
        self.max_complex_span_ratio = max_complex_span_ratio
        # Intersecting blind holes can touch several faces, but if the terminal trace
        # explodes into a large face network it is usually a recirculation/internal
        # channel boundary rather than an independent blind hole.
        self.max_intersection_trace_faces = max_intersection_trace_faces
        # A flat bottom should be a local bottom loop. If the plane has one boundary
        # but that loop contains many edges, it is a shared/complex plane, not a
        # simple blind-hole bottom.
        self.max_simple_bottom_curves = max_simple_bottom_curves
        # In the feature taxonomy used here, a Blind hole normally has a complete
        # circular mouth. Disable this only if you intentionally want to keep legacy
        # broad candidates with line/slot-like mouths. v9 additionally allows one
        # narrow exception for shared-rectangular-plane closed bottoms.
        self.require_circular_mouth = require_circular_mouth
        self.allow_shared_plane_bottom_mouth_exception = allow_shared_plane_bottom_mouth_exception

    def recognize(self):
        holes = []
        for surface_id, surface in sorted(self.parser.surfaces.items()):
            if surface["type"] != "CYLINDRICAL_SURFACE":
                continue
            radius = surface.get("radius")
            # v21-no-radius-through-fix: radius is not a blind-hole size gate.
            # It is still used later for geometry tolerance and depth ratio checks.
            for face_id in self.parser.surface_to_faces.get(surface_id, []):
                candidate = self._analyze_cylindrical_face(surface_id, face_id)
                if candidate:
                    holes.append(candidate)
        return self._dedupe_and_sort(holes)

    def _has_enough_axial_depth(self, surface_id, face_id):
        radius = self.parser.surfaces.get(surface_id, {}).get("radius")
        span = self.parser.cylindrical_face_axial_span(surface_id, face_id)
        if span is None:
            return True, None
        threshold = self.min_depth_abs
        if radius is not None:
            threshold = max(threshold, radius * self.min_depth_ratio)
        return span >= threshold, span

    def _analyze_cylindrical_face(self, surface_id, face_id):
        if face_id not in self.parser.advanced_faces:
            return None

        enough_depth, axial_span = self._has_enough_axial_depth(surface_id, face_id)

        end_infos = []
        for bound_info in self.parser.face_to_edges_by_bound.get(face_id, []):
            curves = [item["edge_curve"] for item in bound_info["curves"]]
            unique_curves = sorted(set(curves))
            if not unique_curves:
                continue

            if len(unique_curves) == 1:
                adjacent = self._adjacent_faces_for_curves(unique_curves, exclude_face=face_id)
                end_infos.append(self._make_end_info(face_id, bound_info, unique_curves, adjacent))
            else:
                # OpenCASCADE often puts several physical end/intersection edges in one FACE_BOUND.
                for curve in unique_curves:
                    curve_adjacent = self._adjacent_faces_for_curves([curve], exclude_face=face_id)
                    if not curve_adjacent:
                        continue
                    end_infos.append(self._make_end_info(face_id, bound_info, [curve], curve_adjacent))

        opening_ends = [item for item in end_infos if item["classification"] == "open"]
        terminal_ends = [item for item in end_infos if item["classification"] == "terminal"]
        ambiguous_ends = [item for item in end_infos if item["classification"] == "ambiguous"]
        if not opening_ends or not (terminal_ends or ambiguous_ends):
            return None

        # Several opening edge segments on the same external plane represent one physical mouth.
        opening_groups = self._group_openings_by_external_faces(opening_ends)
        if len(opening_groups) != 1:
            # True through slots or outer rounds normally expose different outside regions.
            return None
        opening = self._merge_ends(opening_groups[0], classification="open")
        terminal = self._merge_ends(terminal_ends if terminal_ends else ambiguous_ends, classification="terminal")

        hole_type = self._hole_type(face_id, opening, terminal)
        if hole_type is None:
            return None

        if not self._passes_candidate_filters(surface_id, face_id, hole_type, opening, terminal, axial_span, enough_depth):
            return None

        surface = self.parser.surfaces.get(surface_id, {})
        axis = self.parser.axis_info(surface_id)
        return {
            "type": hole_type,
            "cyl_surface": surface_id,
            "cyl_face": face_id,
            "radius": surface.get("radius"),
            "axis_point": axis["point"],
            "axis_direction": axis["direction"],
            "axial_span": axial_span,
            "opening": opening,
            "terminal": terminal,
            "all_ends": end_infos,
            "reason": self._reason(hole_type, opening, terminal),
        }

    def _make_end_info(self, cyl_face, bound_info, curves, adjacent):
        return {
            "bound": bound_info["bound"],
            "loop": bound_info["loop"],
            "edge_curves": sorted(set(curves)),
            "adjacent_faces": sorted(adjacent),
            "classification": self._classify_end(cyl_face, adjacent),
            "trace": self._trace_end(cyl_face, adjacent),
        }

    def _adjacent_faces_for_curves(self, curves, exclude_face):
        adjacent = set()
        for curve in curves:
            adjacent.update(self.parser.edge_curve_to_faces.get(curve, set()))
        adjacent.discard(exclude_face)
        return adjacent

    def _trace_end(self, cyl_face, start_faces, max_depth=1):
        seen = {cyl_face}
        queue = deque((face_id, 0) for face_id in start_faces)
        traces = []
        while queue:
            face_id, depth = queue.popleft()
            if face_id in seen:
                continue
            seen.add(face_id)
            surface_id = self.parser.face_surface_id(face_id)
            surface_type = self.parser.face_surface_type(face_id)
            outer, inner, total = self.parser.face_bound_count(face_id)
            traces.append(
                {
                    "face": face_id,
                    "surface": surface_id,
                    "surface_type": surface_type,
                    "outer_bounds": outer,
                    "inner_bounds": inner,
                    "total_bounds": total,
                    "depth": depth,
                }
            )
            if depth >= max_depth or self._looks_external_face(face_id):
                continue
            for curve in self.parser.face_to_edge_curves.get(face_id, set()):
                for next_face in self.parser.edge_curve_to_faces.get(curve, set()):
                    if next_face not in seen:
                        queue.append((next_face, depth + 1))
        return traces

    def _classify_end(self, cyl_face, adjacent_faces):
        if not adjacent_faces:
            return "ambiguous"

        immediate_types = [self.parser.face_surface_type(face_id) for face_id in adjacent_faces]
        if any(self.parser.face_surface_type(face_id) == "PLANE" and self._looks_external_face(face_id) for face_id in adjacent_faces):
            return "open"

        # Entry transition edge: CONICAL/TOROIDAL -> external PLANE within one step.
        # V15.10：倒角/圆角入口的过渡面可能带 SEAM_CURVE，且不一定只导出为
        # CONICAL_SURFACE；OCC 常把圆角入口导出为 TOROIDAL_SURFACE。
        # 这里不按过渡面的边界条数判断，只看它是否从孔口端一跳连到外部 PLANE。
        if set(immediate_types) & ENTRY_TRANSITION_SURFACES:
            trace = self._trace_end(cyl_face, adjacent_faces, max_depth=1)
            if any(item["depth"] <= 1 and item["surface_type"] == "PLANE" and self._looks_external_face(item["face"]) for item in trace):
                return "open"

        if any(surface_type == "CYLINDRICAL_SURFACE" for surface_type in immediate_types):
            return "terminal"
        if any(self.parser.face_surface_type(face_id) == "PLANE" and not self._looks_external_face(face_id) for face_id in adjacent_faces):
            return "terminal"

        trace = self._trace_end(cyl_face, adjacent_faces, max_depth=1)
        trace_types = {item["surface_type"] for item in trace}
        if trace_types & TERMINATING_SURFACES:
            return "terminal"
        return "ambiguous"

    def _looks_external_face(self, face_id):
        # In many OpenCASCADE STEP files, a broad outside PLANE is not always
        # represented as several FACE_BOUND loops. Some models export the whole
        # outside patch as one FACE_BOUND whose EDGE_LOOP contains several curves.
        #
        # v12/v13 originally used only `total_bounds >= 2`, which misses these
        # single-bound outside planes. In LGEWC-like parts that causes real blind
        # holes to have no opening side, while nearby large intersecting cylinders
        # are kept as false blind holes.
        if self.parser.face_surface_type(face_id) != "PLANE":
            return False
        outer, _, total = self.parser.face_bound_count(face_id)
        if total >= 2:
            return True
        counts = self.parser.face_loop_curve_counts(face_id)
        # 单边界 PLANE 的外部/内部不能只看曲线数量。
        # 含倒角/圆角/通孔/盲孔(单solid) 中真实相交盲孔的内部底面是
        # FACE_BOUND + [8]，如果仅按 [8] > 4 判断为外部面，会导致 6 个
        # 相交型盲孔全部丢失。
        # 因此单边界外部面要求该边界本身是 FACE_OUTER_BOUND；这样 L120
        # 中用于开口判断的外部平面 [6]/[8]/[38] 仍可识别，而普通内部
        # 底面 FACE_BOUND [8] 不再被误判为外部面。
        return bool(counts) and outer >= 1 and max(counts) > self.max_simple_bottom_curves

    def _external_face_key(self, end):
        faces = []
        for item in end["trace"]:
            if item["surface_type"] == "PLANE" and self._looks_external_face(item["face"]):
                faces.append(item["face"])
        return tuple(sorted(set(faces)))

    def _group_openings_by_external_faces(self, opening_ends):
        groups = defaultdict(list)
        for end in opening_ends:
            groups[self._external_face_key(end)].append(end)
        # Empty-key openings are not reliable for this use case.
        return [items for key, items in groups.items() if key]

    def _merge_ends(self, ends, classification):
        edge_curves = []
        adjacent_faces = []
        traces = []
        seen_trace = set()
        bound = ends[0]["bound"] if ends else None
        loop = ends[0]["loop"] if ends else None
        for end in ends:
            edge_curves.extend(end.get("edge_curves", []))
            adjacent_faces.extend(end.get("adjacent_faces", []))
            for item in end.get("trace", []):
                key = (item["face"], item["surface"])
                if key not in seen_trace:
                    seen_trace.add(key)
                    traces.append(item)
        return {
            "bound": bound,
            "loop": loop,
            "edge_curves": sorted(set(edge_curves)),
            "adjacent_faces": sorted(set(adjacent_faces)),
            "classification": classification,
            "trace": traces,
        }

    def _hole_type(self, cyl_face, opening, terminal):
        """Classify blind-hole candidates while preserving the v12 flat-bottom logic.

        The original v12 rule only accepted a direct internal PLANE bottom. That
        is still the preferred path and remains unchanged for ordinary flat-bottom
        holes.

        Added narrow fallback:
        - If the mouth is a confirmed chamfered opening, and
        - the cylindrical wall terminates into an internal conical/compound closed
          region that also reaches a non-external PLANE,
        then keep it as a chamfered compound-bottom blind hole.

        This deliberately does NOT restore generic drill-tip holes: a plain
        cylinder -> cone -> small plane with no chamfered external mouth is still
        rejected, so previous DPB-type false positives remain excluded.
        """
        term_types = {item["surface_type"] for item in terminal["trace"]}
        has_other_cylinder = any(
            item["surface_type"] == "CYLINDRICAL_SURFACE" and item["face"] != cyl_face
            for item in terminal["trace"]
        )
        has_chamfer = any(item["surface_type"] in ENTRY_TRANSITION_SURFACES for item in opening["trace"])

        # Preferred v12 path: terminal side directly touches a non-external PLANE.
        if self._has_direct_internal_plane_bottom(terminal):
            if has_other_cylinder:
                return "相交型平底盲孔"
            if has_chamfer:
                return "倒角入口平底盲孔"
            return "普通平底盲孔"

        # Narrow extension for LGHLH-like chamfered blind holes: the mouth is
        # explicitly chamfered to the outside, while the terminal side is a sealed
        # conical/compound bottom. This is not applied to non-chamfered drill-tip
        # holes, avoiding the earlier DPB false positive.
        if has_chamfer and self._has_internal_compound_bottom(terminal):
            return "倒角入口复合底盲孔"

        # V20 通用封闭底补充：盲孔底部不一定必须是 PLANE。
        # 对于没有入口倒角的孔，如果圆柱壁完整，终止端为 CONICAL/TOROIDAL/
        # SPHERICAL/B_SPLINE 等复合封闭面，并且该局部终止区域能追踪到
        # 内部非外部 PLANE 作为封闭证据，也作为普通复合底盲孔保留。
        # 若终止端还接触其他圆柱结构，则交给相交型规则处理，避免把
        # 堆叠孔/通道结构误加为普通复合底。
        if (not has_other_cylinder) and self._has_internal_compound_bottom(terminal):
            return "普通复合底盲孔"

        return None

    def _is_local_simple_plane_bottom(self, face_id):
        """A true flat blind-hole bottom should be one local loop, usually one circle.
        A single FACE_BOUND with dozens of edges is normally a large shared internal
        plane and should not be treated as a blind-hole bottom.
        """
        if self.parser.face_surface_type(face_id) != "PLANE":
            return False
        if self.parser.face_bound_count(face_id)[2] != 1:
            return False
        counts = self.parser.face_loop_curve_counts(face_id)
        if not counts:
            return False
        return max(counts) <= self.max_simple_bottom_curves

    def _has_clean_two_loop_wall(self, face_id):
        """Return True when face_id is a complete cylindrical hole wall.

        V17 no longer hard-codes the number of SEAM_CURVE/LINE edges.
        A wall is accepted when its boundary topology contains exactly two
        complete circular section rings matching the CYLINDRICAL_SURFACE,
        and every non-circular edge is only an axial connector/seam between
        those two rings.  LINE/CIRCLE/LINE slot boundaries are rejected because
        their LINE edges participate in the section profile rather than acting
        as axial connectors.
        """
        return _classify_complete_cylindrical_wall(self.parser, face_id).get("ok", False)

    def _is_single_loop_seam_cyl_wall(self, face_id):
        info = _classify_complete_cylindrical_wall(self.parser, face_id)
        return bool(info.get("ok") and info.get("mode") in {"single_loop_seam", "single_loop_axial_connector"})

    def _edge_curve_types(self, edge_ids):
        return [self.parser.edge_base_curve_type(edge_id) for edge_id in edge_ids]

    def _base_curve_entity_id(self, edge_curve_id):
        """Return the underlying geometry curve entity id of an EDGE_CURVE.

        OpenCASCADE STEP may store EDGE_CURVE -> SURFACE_CURVE -> CIRCLE.
        This helper unwraps SURFACE_CURVE so circular bottom/mouth checks can
        use the real CIRCLE entity.
        """
        edge = self.parser.edge_curves.get(edge_curve_id)
        if not edge:
            return None
        curve_ref = edge.get("curve")
        ent = self.parser.entities.get(curve_ref, {})
        if ent.get("type") == "SURFACE_CURVE":
            refs = self.parser._refs(ent.get("params", ""))
            return refs[0] if refs else curve_ref
        return curve_ref

    def _edge_circle_center_radius(self, edge_curve_id):
        """Return (center_xyz, radius) when EDGE_CURVE is based on CIRCLE."""
        curve_id = self._base_curve_entity_id(edge_curve_id)
        ent = self.parser.entities.get(curve_id, {})
        if ent.get("type") != "CIRCLE":
            return None, None
        refs = self.parser._refs(ent.get("params", ""))
        if not refs:
            return None, None
        parts = self.parser._split_top_level(ent.get("params", ""))
        radius = None
        if len(parts) >= 3:
            radius = self.parser._to_float(parts[2])
        axis = self.parser.axis2.get(refs[0], {})
        center = self.parser.points.get(axis.get("point_ref"))
        return center, radius

    def _is_partial_circle_edge(self, edge_curve_id):
        verts = [v for v in self.parser.edge_vertex_refs(edge_curve_id) if v is not None]
        return len(verts) == 2 and verts[0] != verts[1]

    def _internal_plane_faces_in_end(self, end):
        faces = set()
        for item in end.get("trace", []):
            face_id = item.get("face")
            if item.get("surface_type") == "PLANE" and not self._looks_external_face(face_id):
                faces.add(face_id)
        return faces

    def _is_unsealed_shared_bottom_slot_end(self, surface_id, face_id, terminal):
        """Reject only the real failure mode discussed in the CAD view.

        Some false intersecting-hole candidates are located at the two ends of a
        long circular-end pocket/slot. They do have a circular opening, but the
        so-called bottom is not a sealed local bottom: its terminal circular arc
        lies at the end of a shared internal PLANE boundary. The middle candidate
        is different: its terminal circular arc is inside the same shared bottom
        boundary, with bottom-plane material continuing on both sides.

        This is not a spatial 'keep the middle one' heuristic. It checks the
        sealing state of the terminal bottom plane itself. The filter is applied
        only to partial circular terminal edges on an internal PLANE that contains
        three or more similar partial circular bottom arcs. If the target arc is
        the first or last arc of that shared bottom boundary, it is treated as an
        unsealed circular-end-pocket end and excluded.
        """
        radius = self.parser.surfaces.get(surface_id, {}).get("radius")
        if not radius:
            return False

        internal_planes = self._internal_plane_faces_in_end(terminal)
        if not internal_planes:
            return False

        terminal_circle_edges = [
            edge_id for edge_id in terminal.get("edge_curves", [])
            if self.parser.edge_base_curve_type(edge_id) == "CIRCLE" and self._is_partial_circle_edge(edge_id)
        ]
        if not terminal_circle_edges:
            return False

        for plane_face in internal_planes:
            plane_curve_ids = []
            for bound in self.parser.face_to_edges_by_bound.get(plane_face, []):
                for item in bound.get("curves", []):
                    edge_id = item.get("edge_curve")
                    if self.parser.edge_base_curve_type(edge_id) == "CIRCLE" and self._is_partial_circle_edge(edge_id):
                        center, r = self._edge_circle_center_radius(edge_id)
                        if center is not None and r is not None and abs(r - radius) <= max(1.0e-5, radius * 1.0e-3):
                            plane_curve_ids.append(edge_id)

            # Need at least three partial circular bottom arcs to decide that a
            # shared bottom boundary has interior arcs and end arcs. With fewer
            # arcs, do not guess.
            plane_curve_ids = sorted(set(plane_curve_ids))
            if len(plane_curve_ids) < 3:
                continue

            centers = {}
            for edge_id in plane_curve_ids:
                center, _ = self._edge_circle_center_radius(edge_id)
                if center is not None:
                    centers[edge_id] = center
            if len(centers) < 3:
                continue

            # Find the dominant coordinate along which these bottom arcs are laid
            # out on the shared plane.
            spreads = []
            for i in range(3):
                vals = [c[i] for c in centers.values()]
                spreads.append(max(vals) - min(vals))
            dominant = max(range(3), key=lambda i: spreads[i])
            if spreads[dominant] <= max(1.0e-5, radius * 0.1):
                continue

            vals = {edge_id: centers[edge_id][dominant] for edge_id in centers}
            min_v = min(vals.values())
            max_v = max(vals.values())
            tol = max(1.0e-5, radius * 0.05)

            for target_edge in terminal_circle_edges:
                if target_edge not in vals:
                    continue
                v = vals[target_edge]
                if abs(v - min_v) <= tol or abs(v - max_v) <= tol:
                    return True
        return False

    def _external_faces_in_end(self, end):
        faces = set()
        for item in end.get("trace", []):
            if item["surface_type"] == "PLANE" and self._looks_external_face(item["face"]):
                faces.add(item["face"])
        return faces

    def _vector_norm(self, values):
        return sum(v * v for v in values) ** 0.5

    def _is_complete_circular_mouth(self, opening):
        """Return True only when the detected physical mouth is circular.

        Blind holes in the machining-feature sense correspond to type 12 in the
        common feature taxonomy: a closed circular mouth leading to a cylindrical
        wall. Circular-end pockets, blind slots and side-broken holes may contain
        cylindrical surfaces, but their mouths include line edges or only partial
        arcs, so they must be excluded.
        """
        edge_ids = opening.get("edge_curves", [])
        if not edge_ids:
            return False
        edge_types = self._edge_curve_types(edge_ids)

        # A valid circular mouth must contain at least one circular edge and must
        # not contain line/spline segments at the mouth. Mixed LINE+CIRCLE mouths
        # are typical for circular-end pockets, round-ended blind slots, or
        # broken-wall holes rather than blind holes.
        if not any(curve_type == "CIRCLE" for curve_type in edge_types):
            return False
        if any(curve_type != "CIRCLE" for curve_type in edge_types):
            return False

        # A single CIRCLE edge is how OpenCASCADE commonly exports a complete
        # circular loop, but it can also represent only a circular arc on slots,
        # external fillets, or convex connector caps.  Treat it as a valid mouth
        # only when the EDGE_CURVE is a closed circle: its start/end vertex is the
        # same, or the STEP record does not expose two distinct vertices.
        if len(edge_ids) == 1:
            return _circle_edge_nonpartial(self.parser, edge_ids[0])

        degree = defaultdict(int)
        for edge_id in edge_ids:
            verts = [v for v in self.parser.edge_vertex_refs(edge_id) if v is not None]
            if len(verts) != 2:
                return False
            v1, v2 = verts
            degree[v1] += 1
            degree[v2] += 1
        return bool(degree) and all(value == 2 for value in degree.values())

    def _has_internal_plane_bottom(self, terminal):
        """Return True when the terminal region contains a non-external PLANE.

        In some STEP exports, the real hole bottom is not a small circular face;
        it is merged into a larger rectangular/shared internal plane. For blind
        hole recognition this still counts as a closed bottom as long as the
        candidate is not a side-broken/slot-like mouth.
        """
        for item in terminal.get("trace", []):
            face_id = item.get("face")
            if item.get("surface_type") != "PLANE":
                continue
            if self._looks_external_face(face_id):
                continue
            return True
        return False

    def _has_internal_compound_bottom(self, terminal):
        """Return True for a sealed non-flat/compound terminal region.

        This helper is intentionally narrower than broad blind-hole recognition.
        It accepts a terminal side only when the trace contains a terminating
        surface such as CONICAL/TOROIDAL/SPHERICAL/B-spline and also contains a
        non-external PLANE somewhere in the same local terminal region. The
        non-external PLANE is used as evidence that the feature is closed inside
        the solid instead of escaping to another outside opening.
        """
        term_types = {item.get("surface_type") for item in terminal.get("trace", [])}
        has_compound_surface = bool(
            term_types & {
                "CONICAL_SURFACE",
                "TOROIDAL_SURFACE",
                "SPHERICAL_SURFACE",
                "BSPLINE_SURFACE_WITH_KNOTS",
                "B_SPLINE_SURFACE_WITH_KNOTS",
            }
        )
        return has_compound_surface and self._has_internal_plane_bottom(terminal)

    def _direct_internal_plane_bottom_faces(self, terminal):
        """Return direct non-external PLANE faces on the terminal side.

        v21-no-radius-through-fix:
        A PLANE reached only after passing through another face is not a flat
        bottom by itself.  For flat-bottom recognition we only accept PLANE faces
        directly adjacent to the cylindrical wall terminal edge.
        """
        adjacent_faces = set(terminal.get("adjacent_faces", []))
        faces = []
        for item in terminal.get("trace", []):
            face_id = item.get("face")
            if item.get("surface_type") != "PLANE":
                continue
            if self._looks_external_face(face_id):
                continue
            if item.get("depth", 0) == 0 or face_id in adjacent_faces:
                faces.append(face_id)
        return unique_keep_order(faces)

    def _has_direct_internal_plane_bottom(self, terminal):
        """Return True when the cylindrical wall terminal side directly touches
        a non-external PLANE.
        """
        return bool(self._direct_internal_plane_bottom_faces(terminal))

    def _has_valid_complex_shared_plane_bottom(self, surface_id, face_id, terminal, direct_plane_faces):
        """Check whether a complex/shared direct PLANE really seals the bottom.

        A through hole may expose a circular edge on a PLANE fragment that is
        stitched with other planar/conical faces.  Earlier logic treated any
        direct internal PLANE as a flat bottom, so such through holes could be
        kept as intersecting blind holes.

        For non-local direct PLANE bottoms, require the local circular disk around
        the terminal edge to be covered and not interrupted by other edges on the
        same PLANE.  This keeps true shared-bottom blind holes while rejecting
        stitched-through bottoms.
        """
        radius = self.parser.surfaces.get(surface_id, {}).get("radius")
        if radius is None:
            return False
        direct_plane_faces = set(direct_plane_faces or [])
        terminal_edges = terminal.get("edge_curves", [])
        for plane_face in direct_plane_faces:
            for edge_id in terminal_edges:
                if self.parser.edge_base_curve_type(edge_id) != "CIRCLE":
                    continue
                if plane_face not in self.parser.edge_curve_to_faces.get(edge_id, set()):
                    continue
                center, edge_radius, _, _ = _edge_circle_center_radius_axis(self.parser, edge_id)
                if center is None or edge_radius is None:
                    continue
                if abs(float(edge_radius) - float(radius)) > max(1.0e-5, float(radius) * 1.0e-3):
                    continue
                integrity = _shared_bottom_disk_local_integrity(self.parser, plane_face, edge_id, center, edge_radius)
                if integrity.get("ok"):
                    return True
        return False

    def _is_shared_plane_bottom_mouth_exception(self, surface_id, face_id, opening, terminal):
        """Narrow v9 exception for a real blind hole whose bottom is a shared
        rectangular/internal PLANE and whose exported mouth edge is LINE.

        This is NOT a generic permission for non-circular pockets. It is accepted
        only when:
        1) the opening has no CIRCLE edge but does have LINE edge(s);
        2) the line mouth is not the side-broken/half-open case;
        3) the terminal region contains a non-external PLANE closure.
        Circular-end pockets / blind slots normally fail condition 2 or 3.
        """
        edge_types = self._edge_curve_types(opening.get("edge_curves", []))
        if not edge_types:
            return False
        if any(curve_type == "CIRCLE" for curve_type in edge_types):
            return False
        if not any(curve_type == "LINE" for curve_type in edge_types):
            return False
        if self._is_half_open_line_mouth(surface_id, face_id, opening):
            return False
        if not self._has_internal_plane_bottom(terminal):
            return False
        return True

    def _is_half_open_line_mouth(self, surface_id, face_id, opening):
        """Detect a very specific false positive: a side-broken / half-open feature.

        It appears in STEP as a cylindrical face whose only detected mouth edge is
        a LINE on an external PLANE rather than a circular/arc mouth. Some valid
        side-entering complex holes may also have a line-like mouth, so the rule is
        deliberately narrow: it rejects only when the external mouth plane is
        laterally offset from the cylinder axis. In that case the feature is better
        interpreted as a side slot / broken wall opening, not an independent blind
        hole.
        """
        edge_types = self._edge_curve_types(opening.get("edge_curves", []))
        if not edge_types:
            return False
        if any(curve_type == "CIRCLE" for curve_type in edge_types):
            return False
        if not any(curve_type == "LINE" for curve_type in edge_types):
            return False

        cyl_axis = self.parser.axis_info(surface_id)
        cyl_point = cyl_axis.get("point")
        if not cyl_point:
            return False
        radius = self.parser.surfaces.get(surface_id, {}).get("radius") or 0.0
        tolerance = max(0.5, radius * 0.25)

        for ext_face in self._external_faces_in_end(opening):
            plane_surface = self.parser.face_surface_id(ext_face)
            plane_axis = self.parser.axis_info(plane_surface)
            plane_point = plane_axis.get("point")
            plane_normal = plane_axis.get("direction")
            if not plane_point or not plane_normal:
                continue
            delta = tuple(cyl_point[i] - plane_point[i] for i in range(3))
            normal_component = dot(delta, plane_normal)
            lateral = tuple(delta[i] - normal_component * plane_normal[i] for i in range(3))
            # If the external plane's reference point is not laterally aligned with
            # the cylinder axis, the line mouth is a side-broken cut instead of a
            # centered cylindrical opening.
            if self._vector_norm(lateral) > tolerance:
                return True
        return False

    def _is_planar_side_pocket_terminal(self, face_id, terminal):
        """Reject a cylindrical patch that is actually a round-ended slot/pocket wall.

        False candidates in the 20221121_* files are CYLINDRICAL_SURFACE patches,
        but their terminal boundary is LINE + CIRCLE + LINE and all directly
        adjacent terminal faces are PLANE faces. That is a pocket/slot side wall,
        not an independent circular blind-hole wall.
        """
        loop_counts = self.parser.face_loop_curve_counts(face_id)
        if len(loop_counts) != 1:
            return False

        edge_types = self._edge_curve_types(terminal.get("edge_curves", []))
        if not edge_types:
            return False
        type_set = set(edge_types)
        if "LINE" not in type_set or "CIRCLE" not in type_set:
            return False
        if type_set & {"B_SPLINE_CURVE_WITH_KNOTS", "B_SPLINE_SURFACE_WITH_KNOTS", "ELLIPSE"}:
            return False

        adjacent_faces = terminal.get("adjacent_faces", [])
        if not adjacent_faces:
            return False
        adjacent_types = {self.parser.face_surface_type(face_id) for face_id in adjacent_faces}
        return bool(adjacent_types) and adjacent_types <= {"PLANE"}

    def _is_external_round_cap_intersection_false_positive(self, surface_id, face_id, opening, terminal):
        """Reject assembly rounded-cap/outer edge cylinders misread as intersecting blind holes.

        In large assemblies, a rounded plastic/connector end can satisfy the broad
        intersecting-hole trace: CYLINDRICAL_SURFACE, one side reaches an external
        region, and the other side reaches PLANE faces.  The key difference is
        that the selected cylindrical face is an outward/convex face
        (same_sense=True) and its so-called terminal boundary is only axial LINE
        edges, not a circular or spline intersection/bottom edge.  This is a
        structural rounded cap, not a closed blind-hole bottom.
        """
        if not self.parser.advanced_faces.get(face_id, {}).get("same_sense"):
            return False
        term_edges = terminal.get("edge_curves", [])
        if not term_edges:
            return False
        term_types = self._edge_curve_types(term_edges)
        if any(t != "LINE" for t in term_types):
            return False
        # The false positives use a partial circular opening arc, not a complete
        # circular mouth.  This keeps normal full-circle outside openings intact.
        open_edges = opening.get("edge_curves", [])
        if len(open_edges) != 1 or self.parser.edge_base_curve_type(open_edges[0]) != "CIRCLE":
            return False
        if _circle_edge_nonpartial(self.parser, open_edges[0]):
            return False
        # Extra guard: the terminal trace of the rounded cap usually touches
        # several other cylindrical transition faces.
        cyl_trace_count = sum(
            1 for item in terminal.get("trace", [])
            if item.get("surface_type") == "CYLINDRICAL_SURFACE" and item.get("face") != face_id
        )
        return cyl_trace_count >= 2

    def _passes_candidate_filters(self, surface_id, face_id, hole_type, opening, terminal, axial_span, enough_depth):
        radius = self.parser.surfaces.get(surface_id, {}).get("radius")
        clean_two_loop = self._has_clean_two_loop_wall(face_id)

        # 0) Exclude a special half-open / wall-broken mouth.
        # This is intentionally narrower than the old v6 rule: do NOT reject every
        # candidate whose terminal trace can reach the same external plane, because
        # valid intersecting holes often have that topology after one-step tracing.
        if self._is_half_open_line_mouth(surface_id, face_id, opening):
            return False

        # 0.25) Bottom sealing filter. Do not count the end arc of a circular-end
        # pocket/slot as an intersecting blind hole. The rejected case is when the
        # terminal circular edge lies at the end of a shared internal PLANE boundary,
        # so the bottom is not closed on both sides.
        if hole_type == "相交型平底盲孔" and self._is_unsealed_shared_bottom_slot_end(surface_id, face_id, terminal):
            return False

        # 0.5) Feature-taxonomy filter: a blind hole should have a complete circular
        # mouth. v9 keeps one narrow exception: a real blind hole whose bottom is
        # closed by a shared rectangular/internal PLANE may be exported with a LINE
        # mouth. This exception is still blocked by the half-open/side-broken test.
        if self.require_circular_mouth and not self._is_complete_circular_mouth(opening):
            if not (
                self.allow_shared_plane_bottom_mouth_exception
                and self._is_shared_plane_bottom_mouth_exception(surface_id, face_id, opening, terminal)
            ):
                return False

        # 1) Keep the original v12 flat-bottom types, plus one narrow chamfered
        # compound-bottom type used for closed chamfered blind holes whose terminal
        # side is conical/compound rather than directly planar.
        if hole_type not in {"普通平底盲孔", "倒角入口平底盲孔", "相交型平底盲孔", "倒角入口复合底盲孔", "普通复合底盲孔"}:
            return False

        if hole_type in {"倒角入口复合底盲孔", "普通复合底盲孔"}:
            # 复合底盲孔仍必须是完整圆柱孔壁，不能是槽壁/口袋侧壁。
            if not clean_two_loop:
                return False
            # 标准盲孔是内凹加工特征。若主圆柱面 same_sense=True，
            # 在真实零件/装配体中更常见为外凸轴、凸台、接头圆柱或端盖，
            # 即使另一端能追踪到锥面/圆角/小平面，也不应按盲孔统计。
            if self.parser.advanced_faces.get(face_id, {}).get("same_sense"):
                return False
            if not enough_depth:
                return False
            if not self._has_internal_compound_bottom(terminal):
                return False
            # 普通复合底比倒角入口复合底更容易误伤钻尖/堆叠结构，
            # 因此要求终止端没有其他圆柱面参与。
            if hole_type == "普通复合底盲孔":
                if any(item.get("surface_type") == "CYLINDRICAL_SURFACE" and item.get("face") != face_id for item in terminal.get("trace", [])):
                    return False
                # 外凸轴端/装配凸台的复合端部在 STEP 中也可能表现为
                # 圆柱壁 + TOROIDAL/CONICAL + PLANE。普通复合底没有入口倒角作为
                # 内凹孔证据，因此 same_sense=True 的候选按外凸结构过滤。
                if self.parser.advanced_faces.get(face_id, {}).get("same_sense"):
                    return False
            return True

        # Bottom must be a direct internal PLANE adjacent to the cylindrical wall
        # terminal side.  A PLANE reached only after a cone/toroid/another plane is
        # sealing evidence at most; it is not a flat blind-hole bottom.
        direct_plane_faces = self._direct_internal_plane_bottom_faces(terminal)
        if not direct_plane_faces:
            return False

        # v21-no-radius-through-fix:
        # If the direct PLANE is a local simple bottom, accept it.  If it is a
        # complex/shared/stitched plane, require the local bottom disk around the
        # terminal circle to be intact.  This rejects through holes whose apparent
        # bottom is only a PLANE patch joined to other faces.
        has_local_simple_bottom = any(self._is_local_simple_plane_bottom(f) for f in direct_plane_faces)
        if not has_local_simple_bottom:
            if not self._has_valid_complex_shared_plane_bottom(surface_id, face_id, terminal, direct_plane_faces):
                return False

        # Ordinary flat-bottom holes should have clean two-loop cylindrical walls.
        # Intersecting flat-bottom holes may have a complex wall because the bottom
        # is cut by another feature, so they are handled separately below.
        if hole_type in {"普通平底盲孔", "倒角入口平底盲孔"}:
            if not clean_two_loop:
                return False
            # 单 FACE_BOUND + SEAM_CURVE 是完整圆柱壁的合法 STEP 表达，
            # 但如果这种 one-bound seam 圆柱特别长，通常是圆柱通道/结构腔，
            # 不是短的加工盲孔。该限制只作用于这种特殊导出形式，
            # 不影响普通 two-loop 圆柱壁和相交型盲孔。
            if self._is_single_loop_seam_cyl_wall(face_id) and radius and axial_span:
                # V20 修正：单 FACE_BOUND + SEAM_CURVE 是完整圆柱壁的合法表达，
                # 即使轴向很长，也可能是深盲孔。只有当终止端不是局部简单圆形
                # 底面时，才用长径比过滤通道/结构腔误检。
                has_local_simple_bottom = any(
                    item.get("surface_type") == "PLANE"
                    and not self._looks_external_face(item.get("face"))
                    and self._is_local_simple_plane_bottom(item.get("face"))
                    for item in terminal.get("trace", [])
                )
                if (not has_local_simple_bottom) and axial_span / radius > 8.0:
                    return False
            # v15.17 修正：标准平底盲孔应为内凹孔壁。
            # 若 clean two-loop 主圆柱壁 same_sense=True，通常是外凸轴端、
            # 凸台或接头圆柱；即使入口处有倒角/圆角，也不作为盲孔。
            if hole_type in {"普通平底盲孔", "倒角入口平底盲孔"} and self.parser.advanced_faces.get(face_id, {}).get("same_sense"):
                return False
            return True

        # Intersecting flat-bottom holes still need extra guards against channel
        # walls, circular-end pockets, and unsealed shared-plane slot ends.
        if hole_type == "相交型平底盲孔":
            if not enough_depth:
                return False
            if len(terminal.get("trace", [])) > self.max_intersection_trace_faces:
                return False
            if radius and axial_span and not clean_two_loop:
                if axial_span / radius > self.max_complex_span_ratio:
                    return False

            # Important v13 export/recognition correction:
            # A single complex cylindrical boundary with many ellipse/spline
            # pieces is usually not an independent blind-hole wall; in LGEWC-like
            # parts it is the wall of a through/intersecting passage or a larger
            # counterbore/channel feature. The actual blind holes in the same file
            # are clean two-bound walls or low-complexity shared-plane walls.
            # Keep low-complexity shared-plane cases such as loop [4], but reject
            # one-loop high-complexity candidates such as loop [7].
            loop_counts = self.parser.face_loop_curve_counts(face_id)
            if (not clean_two_loop) and len(loop_counts) == 1 and max(loop_counts or [0]) > self.max_simple_bottom_curves:
                # 这里不能简单按“单环曲线数 > 阈值”排除。
                # 真实相交型盲孔也可能因为圆角/相交切割而形成复杂单环，
                # 例如单 solid 测试件中的 [5]/[6]/[11]。
                # L120 中应排除的 r=7 误检面，终止边界主要是 ELLIPSE + B_SPLINE，
                # 且没有 CIRCLE；这种更像斜切/通道/沉台过渡面。
                terminal_edge_types = set(self._edge_curve_types(terminal.get("edge_curves", [])))
                if "ELLIPSE" in terminal_edge_types and "CIRCLE" not in terminal_edge_types:
                    return False

            # 严格过滤：单环圆柱 patch + LINE/CIRCLE/LINE 终止边 + 全 PLANE 邻接
            # 不是完整圆柱孔壁，而是圆端槽/口袋侧壁，不作为盲孔。
            if hole_type == "相交型平底盲孔" and self._is_planar_side_pocket_terminal(face_id, terminal):
                return False

            # V15.11 assembly-only patch:
            # 只过滤装配体外凸圆角端盖/连接器边缘误检，不改变普通复合底、
            # 倒角复合底、共享平面、广义截断等其他盲孔逻辑。
            if self._is_external_round_cap_intersection_false_positive(surface_id, face_id, opening, terminal):
                return False

            return True

        return False

    def _reason(self, hole_type, opening, terminal):
        if hole_type == "相交型平底盲孔":
            return "一端对外开口，另一端与其他圆柱结构相交，但终止区域存在内部平面底面封闭；沿自身孔轴没有第二个外部出口。"
        if hole_type == "倒角入口平底盲孔":
            return "一端经倒角入口对外开口，另一端直接由内部平面底面封闭；沿自身孔轴没有第二个外部出口。"
        if hole_type == "倒角入口复合底盲孔":
            return "一端经倒角入口对外开口，另一端由内部锥面/复合面及其关联内部平面封闭；沿自身孔轴没有第二个外部出口。"
        if hole_type == "普通复合底盲孔":
            return "一端为完整圆形开口，另一端由内部锥面/圆弧面/复合面及其关联内部平面封闭；沿自身孔轴没有第二个外部出口。"
        return "一端对外开口，另一端由内部平面底面封闭；沿自身孔轴没有第二个外部出口。"

    def _dedupe_and_sort(self, holes):
        keyed = {}
        for hole in holes:
            keyed[(hole["cyl_surface"], hole["cyl_face"])] = hole
        return sorted(keyed.values(), key=lambda item: (item["radius"] or 0.0, item["cyl_face"]))


class ReportWriter:
    def __init__(self, parser, holes, input_path, processing_ms=None):
        self.parser = parser
        self.holes = holes
        self.input_path = input_path
        self.processing_ms = processing_ms

    def build(self):
        lines = []
        lines.append("盲孔识别详细日志（v12-修正版：平底密封 + 倒角入口复合底盲孔规则版）")
        lines.append(f"输入文件：{self.input_path}")
        lines.append(f"识别时间：{_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if self.processing_ms is not None:
            lines.append(f"文件处理时间：{self.processing_ms:.3f} ms")
        lines.append("")
        lines.append("识别规则：STEP 拓扑追踪 + 完整圆形孔口优先 + 终止端直接内部平面密封；额外保留“倒角入口+内部复合封闭底”盲孔；仍排除非倒角钻尖孔/圆端口袋/盲槽/破壁孔。")
        lines.append(f"圆柱面数量：{sum(1 for item in self.parser.surfaces.values() if item['type'] == 'CYLINDRICAL_SURFACE')}")
        lines.append(f"高级面数量：{len(self.parser.advanced_faces)}")
        lines.append(f"盲孔总数：{len(self.holes)}")
        lines.append("")
        for index, hole in enumerate(self.holes, 1):
            lines.extend(self._hole_lines(index, hole))
            lines.append("")
        return "\n".join(lines)

    def _hole_lines(self, index, hole):
        opening = hole["opening"]
        terminal = hole["terminal"]
        lines = [
            f"盲孔 #{index}：",
            f"类型：{hole['type']}",
            f"管壁实体：{ref(hole['cyl_surface'])}，CYLINDRICAL_SURFACE，半径 = {fmt_float(hole['radius'])}",
            f"管壁面：{ref(hole['cyl_face'])}",
            f"孔轴定位点：{fmt_vec(hole['axis_point'])}",
            f"孔轴方向：{fmt_vec(hole['axis_direction'])}",
            f"管壁轴向跨度：{fmt_float(hole.get('axial_span'))}",
            f"开口端：边界 {ref(opening['bound'])} / EDGE_LOOP {ref(opening['loop'])}，边缘 {self._refs(opening['edge_curves'])}；{self._endpoint_detail(opening)}",
            f"终止/相交端：边界 {ref(terminal['bound'])} / EDGE_LOOP {ref(terminal['loop'])}，边缘 {self._refs(terminal['edge_curves'])}；{self._endpoint_detail(terminal)}",
        ]
        lines.append(f"判定：{hole['reason']}")
        return lines

    def _refs(self, values):
        return " / ".join(ref(value) for value in values[:20]) if values else "-"

    def _endpoint_detail(self, end):
        grouped = defaultdict(list)
        for item in end["trace"]:
            grouped[item["surface_type"]].append(f"#{item['face']}/#{item['surface']}")
        if not grouped:
            return "未找到相邻面"
        chunks = []
        for surface_type in sorted(grouped):
            chunks.append(f"{surface_type} {' / '.join(grouped[surface_type][:10])}")
        return "连接 " + "；".join(chunks)


# =============================================================================
# V13 exact-face blind-hole STP exporter
# =============================================================================

import math
import sys
from pathlib import Path
from collections import Counter

EXPORT_STP_DIR = None
EXPORT_LOG_DIR = None


def split_header_data_tail(text):
    m1 = re.search(r"\bDATA\s*;", text, re.I)
    if not m1:
        raise ValueError("输入文件不是标准 STEP 文本：未找到 DATA;")
    m2 = re.search(r"\bENDSEC\s*;", text[m1.end():], re.I)
    data_start = m1.end()
    if not m2:
        # Large assembly STEP files may miss ENDSEC/END-ISO.  Keep all complete
        # entity records after DATA; and skip the final incomplete record later.
        return text[:data_start], text[data_start:], ""
    data_end = m1.end() + m2.start()
    return text[:data_start], text[data_start:data_end], text[data_end:]


def find_record_end(text, start):
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


def parse_entity_records_from_data(data):
    records = {}
    order = []
    for m in re.finditer(r"#(\d+)\s*=", data):
        eid = int(m.group(1))
        try:
            end = find_record_end(data, m.start())
        except ValueError:
            # Robustness for truncated large STEP assemblies: ignore the last
            # incomplete entity instead of aborting the whole export.
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
    """Format a STEP reference list without losing separators across wrapped lines.

    A previous version wrapped long OPEN_SHELL face lists as:
        #1, #2
        #3, #4
    which is invalid STEP syntax because the comma between #2 and #3 is missing.
    Some CAD viewers then silently dropped/merged faces, causing individual
    blind-hole cylinders to disappear while their circular bottom faces remained.

    This function keeps commas between all references even when the text is wrapped.
    """
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


def is_external_plane(recognizer, face_id):
    try:
        return recognizer._looks_external_face(face_id)
    except Exception:
        return False



def _face_edge_ids(parser, face_id):
    edge_ids = []
    for bound in parser.face_to_edges_by_bound.get(face_id, []):
        for item in bound.get("curves", []):
            edge_id = item.get("edge_curve")
            if edge_id is not None:
                edge_ids.append(edge_id)
    return unique_keep_order(edge_ids)


def _shared_edge_ids(parser, face_a, face_b):
    return sorted(parser.face_to_edge_curves.get(face_a, set()) & parser.face_to_edge_curves.get(face_b, set()))


def _edge_type_list(parser, edge_ids):
    return [parser.edge_base_curve_type(edge_id) for edge_id in edge_ids]


def _is_local_circular_plane_bottom_for_export(parser, recognizer, hole, face_id):
    """Export only local circular PLANE bottoms.

    For exact-face export, copying a whole ADVANCED_FACE is safe only when that
    plane is a small local blind-hole bottom. In LGEWC-like intersecting holes,
    the terminal trace can reach shared rectangular rail/groove planes. Those
    planes help recognition, but if copied whole into the visualization STP they
    appear as long plates/strips and no longer look like blind-hole output.

    Therefore PLANE export is deliberately narrower than recognition:
    - keep a non-external PLANE when it shares a CIRCLE edge with the recognized
      cylindrical wall;
    - also keep the common OCC clean-bottom case where the PLANE has one circular
      boundary loop.
    Non-circular shared planes are skipped by default. The cylinder wall itself
    is still exported, so the blind-hole count and main feature visualization are
    preserved.
    """
    if face_id is None:
        return False
    if parser.face_surface_type(face_id) != "PLANE":
        return False
    if is_external_plane(recognizer, face_id):
        return False

    cyl_face = hole.get("cyl_face")
    shared_edges = _shared_edge_ids(parser, cyl_face, face_id)
    counts = parser.face_loop_curve_counts(face_id)

    # v15 修正：不能只要和圆柱壁共享 CIRCLE 就整面导出。
    # KCH50/KCH86 中有一些大共享平面同时包含 LINE + 多个 CIRCLE，
    # 它们参与封闭判断，但整面导出会变成长条黄面。
    # 因此，只有小的局部底面才直接导出；复杂共享平面后续改为局部圆盘重建。
    if any(parser.edge_base_curve_type(edge_id) == "CIRCLE" for edge_id in shared_edges):
        if counts and max(counts) <= recognizer.max_simple_bottom_curves:
            return True

    # Shared-plane blind hole: the closing bottom may not share a CIRCLE edge
    # with the cylindrical wall. In the LGEWC case the wall meets a small/simple
    # shared PLANE through a LINE edge. Exporting this simple PLANE is necessary
    # to make the extracted feature look like a blind hole instead of a through
    # cylinder. Do not export large/complex shared planes; those are filtered by
    # the same simple-bottom threshold.
    if shared_edges and counts and max(counts) <= recognizer.max_simple_bottom_curves:
        return True

    all_edges = _face_edge_ids(parser, face_id)
    if len(counts) == 1 and counts[0] == 1:
        if any(parser.edge_base_curve_type(edge_id) == "CIRCLE" for edge_id in all_edges):
            return True

    return False


def _adjacent_faces_of_face(parser, face_id):
    faces = set()
    for edge_id in parser.face_to_edge_curves.get(face_id, set()):
        faces.update(parser.edge_curve_to_faces.get(edge_id, set()))
    faces.discard(face_id)
    return faces


def _cyl_face_has_external_circular_mouth(parser, recognizer, face_id):
    """Return True when a cylindrical patch has a CIRCLE edge opening to an external plane.

    This is used only for the LGEWC-style shared-bottom intersecting blind hole.
    In that model the real visible blind-hole wall is not the small cylindrical
    bridge selected by the generic recognizer. The real wall patches are larger
    cylindrical faces that share the same bottom plane and have a circular mouth
    on the outside face.
    """
    if parser.face_surface_type(face_id) != "CYLINDRICAL_SURFACE":
        return False
    for edge_id in _face_edge_ids(parser, face_id):
        if parser.edge_base_curve_type(edge_id) != "CIRCLE":
            continue
        adjacent = set(parser.edge_curve_to_faces.get(edge_id, set()))
        adjacent.discard(face_id)
        for adj_face in adjacent:
            if recognizer._looks_external_face(adj_face):
                return True
    return False


def _replacement_cyl_faces_for_shared_bottom(parser, recognizer, hole, bottom_faces):
    """Find the actual wall patches for shared-plane intersecting blind holes.

    Some STEP exports describe a shared-bottom blind-hole feature with a small
    cylindrical bridge/intersection face plus two larger cylindrical wall patches.
    The V13 topology trace may select the bridge as hole['cyl_face']; if exported
    directly it looks like a through/intersection surface rather than the blind
    hole seen in CAD.

    When the accepted bottom is a shared PLANE, replace that bridge by the
    larger cylindrical faces that:
      1) are adjacent to the same bottom PLANE;
      2) have radius larger than the bridge radius;
      3) have an external circular mouth.
    This keeps normal clean blind holes unchanged.
    """
    original_face = hole.get("cyl_face")
    original_surface = hole.get("cyl_surface")
    if original_face is None or original_surface is None:
        return []
    original_radius = parser.surfaces.get(original_surface, {}).get("radius")
    if original_radius is None:
        return []

    replacements = []
    for bottom_face in bottom_faces or []:
        if parser.face_surface_type(bottom_face) != "PLANE":
            continue
        for adj_face in sorted(_adjacent_faces_of_face(parser, bottom_face)):
            if adj_face == original_face:
                continue
            if parser.face_surface_type(adj_face) != "CYLINDRICAL_SURFACE":
                continue
            surf_id = parser.face_surface_id(adj_face)
            radius = parser.surfaces.get(surf_id, {}).get("radius")
            if radius is None:
                continue
            # The target wall patch is the larger visible hole wall; the original
            # bridge in LGEWC is smaller and should not be exported as the wall.
            if float(radius) <= float(original_radius) * 1.15:
                continue
            if not _cyl_face_has_external_circular_mouth(parser, recognizer, adj_face):
                continue
            replacements.append(adj_face)
    return unique_keep_order(replacements)




def _hole_has_complete_circular_mouth(parser, recognizer, hole):
    """For the corrected v13 logic, every accepted blind-hole feature must have
    a real circular mouth.  A shared bottom may be non-local, but the mouth is
    still a hole mouth, not a LINE/B_SPLINE slot edge.
    """
    try:
        return recognizer._is_complete_circular_mouth(hole.get("opening", {}))
    except Exception:
        edge_types = [parser.edge_base_curve_type(e) for e in hole.get("opening", {}).get("edge_curves", [])]
        return bool(edge_types) and all(t == "CIRCLE" for t in edge_types)


def _filter_false_line_mouth_holes(parser, recognizer, holes):
    """Remove the failure mode found in LGEWC.

    The old v13 path could keep a candidate whose opening edge is LINE and whose
    cylindrical face is a complex single boundary patch.  It can trace to a
    shared PLANE, but it is not the circular-mouth blind hole seen in CAD.
    """
    kept = []
    rejected = []
    for h in holes:
        if _hole_has_complete_circular_mouth(parser, recognizer, h):
            kept.append(h)
        else:
            rejected.append({
                "cyl_face": h.get("cyl_face"),
                "cyl_surface": h.get("cyl_surface"),
                "type": h.get("type"),
                "reason": "非完整圆形孔口，通常是 LINE/B_SPLINE 相交桥接面，不作为盲孔主孔壁",
                "opening_edge_types": [parser.edge_base_curve_type(e) for e in h.get("opening", {}).get("edge_curves", [])],
                "loop_counts": parser.face_loop_curve_counts(h.get("cyl_face")),
            })
    return kept, rejected


def _face_edges(parser, face_id):
    for b in parser.face_to_edges_by_bound.get(face_id, []):
        for item in b.get("curves", []):
            yield item.get("edge_curve")


def _edge_is_circle(parser, edge_id):
    return parser.edge_base_curve_type(edge_id) == "CIRCLE"



def _base_curve_entity_id_from_parser(parser, edge_curve_id):
    """Return the underlying geometry curve id of an EDGE_CURVE, unwrapping SURFACE_CURVE."""
    edge = parser.edge_curves.get(edge_curve_id)
    if not edge:
        return None
    curve_ref = edge.get("curve")
    ent = parser.entities.get(curve_ref, {})
    if ent.get("type") == "SURFACE_CURVE":
        refs = parser._refs(ent.get("params", ""))
        return refs[0] if refs else curve_ref
    return curve_ref


def _edge_circle_center_radius_axis(parser, edge_curve_id):
    """Return (center_xyz, radius, axis_direction, ref_direction) for a circular EDGE_CURVE."""
    curve_id = _base_curve_entity_id_from_parser(parser, edge_curve_id)
    ent = parser.entities.get(curve_id, {})
    if ent.get("type") != "CIRCLE":
        return None, None, None, None
    refs = parser._refs(ent.get("params", ""))
    if not refs:
        return None, None, None, None
    parts = parser._split_top_level(ent.get("params", ""))
    radius = parser._to_float(parts[2]) if len(parts) >= 3 else None
    axis = parser.axis2.get(refs[0], {})
    center = parser.points.get(axis.get("point_ref"))
    direction = parser.directions.get(axis.get("axis_ref"))
    ref_direction = parser.directions.get(axis.get("ref_direction_ref"))
    return center, radius, direction, ref_direction


def _local_shared_bottom_disk_specs(parser, shared_cyl_faces, shared_bottom_faces):
    """Build local circular bottom disks for shared-plane blind holes.

    Exact-face export copies original ADVANCED_FACE. For shared-bottom blind holes, copying
    the whole PLANE pulls a long strip/large plate into the output. Here we keep the original
    cylindrical wall face, but replace the shared PLANE with a small synthetic circular PLANE
    using the same center/radius as the wall-bottom circle.
    """
    specs = []
    seen = set()
    for cyl_face in shared_cyl_faces or []:
        for plane_face in shared_bottom_faces or []:
            shared_edges = sorted(set(parser.face_to_edge_curves.get(cyl_face, set())) & set(parser.face_to_edge_curves.get(plane_face, set())))
            for edge_id in shared_edges:
                if not _edge_is_circle(parser, edge_id):
                    continue
                center, radius, circle_normal, ref_direction = _edge_circle_center_radius_axis(parser, edge_id)
                if center is None or radius is None:
                    continue
                plane_sid = parser.face_surface_id(plane_face)
                plane_axis = parser.axis_info(plane_sid)
                plane_normal = plane_axis.get("direction") or circle_normal
                key = (cyl_face, plane_face, tuple(round(float(x), 8) for x in center), round(float(radius), 8))
                if key in seen:
                    continue
                seen.add(key)
                specs.append({
                    "source_cyl_face": cyl_face,
                    "source_shared_plane_face": plane_face,
                    "source_circle_edge": edge_id,
                    "center": tuple(center),
                    "radius": float(radius),
                    "normal": tuple(plane_normal) if plane_normal is not None else (0.0, 0.0, 1.0),
                    "ref_direction": tuple(ref_direction) if ref_direction is not None else None,
                })
                break
    return specs


def _local_bottom_disk_spec_from_shared_complex_plane(parser, cyl_face, plane_face):
    """Build one local disk spec for a normal/intersecting hole whose true bottom is a complex shared PLANE.

    Recognition may need a large shared plane as sealing evidence, but visualization should not
    export that whole plane.  If the cylindrical wall and that PLANE share a circular edge,
    rebuild only a small circular bottom disk with the same center/radius.
    """
    if cyl_face is None or plane_face is None:
        return None
    shared_edges = sorted(set(parser.face_to_edge_curves.get(cyl_face, set())) & set(parser.face_to_edge_curves.get(plane_face, set())))
    for edge_id in shared_edges:
        if not _edge_is_circle(parser, edge_id):
            continue
        center, radius, circle_normal, ref_direction = _edge_circle_center_radius_axis(parser, edge_id)
        if center is None or radius is None:
            continue
        plane_sid = parser.face_surface_id(plane_face)
        plane_axis = parser.axis_info(plane_sid)
        plane_normal = plane_axis.get("direction") or circle_normal
        return {
            "source_cyl_face": cyl_face,
            "source_shared_plane_face": plane_face,
            "source_circle_edge": edge_id,
            "center": tuple(center),
            "radius": float(radius),
            "normal": tuple(plane_normal) if plane_normal is not None else (0.0, 0.0, 1.0),
            "ref_direction": tuple(ref_direction) if ref_direction is not None else None,
        }
    return None



# =============================================================================
# V17 generalized cylindrical-wall topology classifier
# =============================================================================

def _unique_edges_in_face(parser, face_id):
    out = []
    seen = set()
    for b in parser.face_to_edges_by_bound.get(face_id, []):
        for item in b.get("curves", []):
            e = item.get("edge_curve")
            if e is not None and e not in seen:
                seen.add(e)
                out.append(e)
    return out


def _circle_axis_center_radius(parser, edge_curve_id):
    curve_id = _base_curve_entity_id_from_parser(parser, edge_curve_id)
    ent = parser.entities.get(curve_id, {})
    if ent.get("type") != "CIRCLE":
        return None, None, None, None
    refs = parser._refs(ent.get("params", ""))
    if not refs:
        return None, None, None, None
    parts = parser._split_top_level(ent.get("params", ""))
    radius = parser._to_float(parts[2]) if len(parts) >= 3 else None
    axis = parser.axis2.get(refs[0], {})
    center = parser.points.get(axis.get("point_ref"))
    normal = parser.directions.get(axis.get("axis_ref"))
    ref_dir = parser.directions.get(axis.get("ref_direction_ref"))
    return center, radius, normal, ref_dir


def _point_line_distance(point, line_point, line_dir):
    if point is None or line_point is None or line_dir is None:
        return None
    d = _vector_unit(line_dir)
    if d is None:
        return None
    delta = _vector_sub(point, line_point)
    proj = _vector_dot(delta, d)
    perp = _vector_sub(delta, tuple(proj * x for x in d))
    return _vector_norm3(perp)


def _edge_is_standard_circular_section(parser, cyl_surface_id, edge_id, tol_scale=1.0e-3):
    if parser.edge_base_curve_type(edge_id) != "CIRCLE":
        return None
    surface = parser.surfaces.get(cyl_surface_id, {})
    cyl_radius = surface.get("radius")
    cyl_axis = parser.axis_info(cyl_surface_id)
    cyl_point = cyl_axis.get("point")
    cyl_dir = _vector_unit(cyl_axis.get("direction") or (0.0, 0.0, 0.0))
    center, radius, normal, _ = _circle_axis_center_radius(parser, edge_id)
    normal = _vector_unit(normal or (0.0, 0.0, 0.0))
    if cyl_radius is None or center is None or radius is None or cyl_point is None or cyl_dir is None or normal is None:
        return None
    tol = max(1.0e-5, abs(float(cyl_radius)) * tol_scale)
    if abs(float(radius) - float(cyl_radius)) > tol:
        return None
    if abs(_vector_dot(cyl_dir, normal)) < 0.995:
        return None
    dist = _point_line_distance(center, cyl_point, cyl_dir)
    if dist is None or dist > max(1.0e-5, abs(float(cyl_radius)) * 2.0e-3):
        return None
    t = _vector_dot(_vector_sub(center, cyl_point), cyl_dir)
    return {"edge": edge_id, "center": tuple(center), "radius": float(radius), "t": float(t), "normal": normal}


def _edge_vertices_t_values(parser, cyl_surface_id, edge_id):
    cyl_axis = parser.axis_info(cyl_surface_id)
    p0 = cyl_axis.get("point")
    d = _vector_unit(cyl_axis.get("direction") or (0.0, 0.0, 0.0))
    if p0 is None or d is None:
        return []
    vals = []
    for p in parser.edge_vertices_xyz(edge_id):
        vals.append(float(_vector_dot(_vector_sub(p, p0), d)))
    return vals


def _circle_edge_nonpartial(parser, edge_id):
    verts = [v for v in parser.edge_vertex_refs(edge_id) if v is not None]
    if len(verts) < 2:
        return True
    return verts[0] == verts[1]


def _circle_group_is_closed(parser, edges):
    if not edges:
        return False
    if any(_circle_edge_nonpartial(parser, e) for e in edges):
        return True
    degree = defaultdict(int)
    for edge_id in edges:
        verts = [v for v in parser.edge_vertex_refs(edge_id) if v is not None]
        if len(verts) != 2:
            return False
        degree[verts[0]] += 1
        degree[verts[1]] += 1
    return bool(degree) and all(v == 2 for v in degree.values())


def _group_circle_sections(parser, circle_infos, tol):
    groups = []
    for info in sorted(circle_infos, key=lambda x: x["t"]):
        placed = False
        for g in groups:
            if abs(info["t"] - g["t_mean"]) <= tol:
                g["items"].append(info)
                g["t_mean"] = sum(x["t"] for x in g["items"]) / len(g["items"])
                placed = True
                break
        if not placed:
            groups.append({"t_mean": info["t"], "items": [info]})
    for g in groups:
        g["edges"] = [x["edge"] for x in g["items"]]
        g["closed"] = _circle_group_is_closed(parser, g["edges"])
    return groups


def _edge_is_axial_connector(parser, cyl_surface_id, edge_id, section_ts=None, tol=None):
    typ = parser.edge_base_curve_type(edge_id)
    if typ == "SEAM_CURVE":
        # A SEAM_CURVE is the cylinder parameter-space seam.  If vertices exist,
        # they should span between the two circular sections; otherwise accept it
        # as connector because OCC often omits useful vertices for seam records.
        vals = _edge_vertices_t_values(parser, cyl_surface_id, edge_id)
        if len(vals) < 2:
            return True
    elif typ == "LINE":
        vals = _edge_vertices_t_values(parser, cyl_surface_id, edge_id)
        if len(vals) < 2:
            return False
    else:
        return False

    if tol is None:
        radius = parser.surfaces.get(cyl_surface_id, {}).get("radius") or 1.0
        tol = max(1.0e-5, abs(float(radius)) * 1.0e-2)
    tmin, tmax = min(vals), max(vals)
    if tmax - tmin <= tol:
        return False
    if section_ts and len(section_ts) >= 2:
        a, b = min(section_ts), max(section_ts)
        # Connector should link the two end-section levels, not lie inside a rim.
        if abs(tmin - a) > max(tol, abs(b-a) * 0.15):
            return False
        if abs(tmax - b) > max(tol, abs(b-a) * 0.15):
            return False
    return True


def _classify_complete_cylindrical_wall(parser, face_id):
    """Classify whether a CYLINDRICAL_SURFACE ADVANCED_FACE is a full hole wall.

    Accepted pattern: boundary contains exactly two complete circular section
    rings that match the underlying CYLINDRICAL_SURFACE.  All remaining edges
    must be axial connectors, typically SEAM_CURVE or true axial LINE edges.

    Rejected pattern: LINE/CIRCLE/LINE slot or pocket boundaries, ELLIPSE/B_SPLINE
    section profiles, partial circle-only patches, and any line/spline that
    participates in the mouth/bottom profile rather than connecting the two rings.
    """
    if parser.face_surface_type(face_id) != "CYLINDRICAL_SURFACE":
        return {"ok": False, "reason": "not_cylindrical_surface"}
    cyl_surface_id = parser.face_surface_id(face_id)
    radius = parser.surfaces.get(cyl_surface_id, {}).get("radius")
    if radius is None:
        return {"ok": False, "reason": "missing_radius"}
    edges = _unique_edges_in_face(parser, face_id)
    if not edges:
        return {"ok": False, "reason": "no_edges"}
    tol = max(1.0e-5, abs(float(radius)) * 1.0e-2)

    circle_infos = []
    bad_edges = []
    pending_connectors = []
    for edge_id in edges:
        typ = parser.edge_base_curve_type(edge_id)
        cinfo = _edge_is_standard_circular_section(parser, cyl_surface_id, edge_id)
        if cinfo is not None:
            circle_infos.append(cinfo)
            continue
        if typ in {"SEAM_CURVE", "LINE"}:
            pending_connectors.append(edge_id)
            continue
        bad_edges.append((edge_id, typ))

    groups = _group_circle_sections(parser, circle_infos, tol=tol)
    closed_groups = [g for g in groups if g.get("closed")]
    if len(closed_groups) != 2:
        return {
            "ok": False,
            "reason": "not_exactly_two_complete_circular_sections",
            "circle_groups": groups,
            "bad_edges": bad_edges,
            "connector_edges": pending_connectors,
        }

    section_ts = [g["t_mean"] for g in closed_groups]
    connector_edges = []
    rejected_connectors = []
    for edge_id in pending_connectors:
        if _edge_is_axial_connector(parser, cyl_surface_id, edge_id, section_ts=section_ts, tol=tol):
            connector_edges.append(edge_id)
        else:
            rejected_connectors.append((edge_id, parser.edge_base_curve_type(edge_id)))

    if bad_edges or rejected_connectors:
        return {
            "ok": False,
            "reason": "bad_profile_edges",
            "circle_groups": groups,
            "bad_edges": bad_edges,
            "rejected_connectors": rejected_connectors,
            "connector_edges": connector_edges,
        }

    # Mode is only diagnostic.  The decision does not depend on a fixed number of seams.
    bound_count = len(parser.face_to_edges_by_bound.get(face_id, []))
    connector_types = {parser.edge_base_curve_type(e) for e in connector_edges}
    if bound_count == 2 and not connector_edges:
        mode = "two_circle_loops"
    elif "SEAM_CURVE" in connector_types:
        mode = "single_loop_seam" if bound_count == 1 else "multi_loop_seam"
    elif "LINE" in connector_types:
        mode = "single_loop_axial_connector" if bound_count == 1 else "multi_loop_axial_connector"
    else:
        mode = "complete_circular_sections"

    return {
        "ok": True,
        "reason": "complete_cylindrical_wall",
        "mode": mode,
        "section_rings": closed_groups,
        "connector_edges": connector_edges,
        "bad_edges": [],
    }

def _is_clean_two_circle_cyl_wall(parser, face_id):
    # Historical name kept for compatibility.  V17 uses the generalized
    # complete-cylinder-wall classifier rather than requiring exactly two
    # one-edge CIRCLE loops.
    return _classify_complete_cylindrical_wall(parser, face_id).get("ok", False)


def _plane_shared_ring_score(parser, face_id):
    """Return (ok, circle_bound_count, line_outer_hint).

    A shared bottom in the problematic LGEWC case is a PLANE with multiple
    circular loops plus an outer boundary.  Annular step faces with only two
    circular loops are intentionally excluded here.
    """
    if parser.face_surface_type(face_id) != "PLANE":
        return (False, 0, False)
    outer, inner, total = parser.face_bound_count(face_id)
    if total < 3:
        return (False, 0, False)
    circle_loops = 0
    has_line_or_complex_outer = False
    for b in parser.face_to_edges_by_bound.get(face_id, []):
        edge_ids = [item.get("edge_curve") for item in b.get("curves", [])]
        types = [parser.edge_base_curve_type(e) for e in edge_ids]
        if len(edge_ids) == 1 and types and types[0] == "CIRCLE":
            circle_loops += 1
        if any(t in {"LINE", "B_SPLINE_CURVE_WITH_KNOTS", "B_SPLINE_SURFACE_WITH_KNOTS"} for t in types):
            has_line_or_complex_outer = True
    return (circle_loops >= 2 and has_line_or_complex_outer, circle_loops, has_line_or_complex_outer)


def _cylinder_adjacent_to_plane_by_circle(parser, cyl_face, plane_face):
    """True if a clean cylindrical wall touches the plane through a circular edge."""
    for e in _face_edges(parser, cyl_face):
        if not _edge_is_circle(parser, e):
            continue
        adj = parser.edge_curve_to_faces.get(e, set())
        if plane_face in adj:
            return True
    return False


def _axis_group_signature(parser, cyl_faces):
    """Build a loose signature to pair the two sides of the same stepped feature.

    For LGEWC, the same two physical holes appear on two parallel shared planes:
    the outer larger-radius section and the inner smaller-radius section.  They
    share the same axis direction and the same center positions transverse to the
    axis; only radius and plane side differ.  We use that to keep the smaller
    inner section as the actual blind-hole export group.
    """
    sig_items = []
    main_dir = None
    for f in cyl_faces:
        sid = parser.face_surface_id(f)
        axis = parser.axis_info(sid)
        p = axis.get("point") or (0.0, 0.0, 0.0)
        d = axis.get("direction") or (0.0, 0.0, 0.0)
        # dominant axis index; keep the two coordinates perpendicular to it
        k = max(range(3), key=lambda i: abs(d[i])) if d else 1
        if main_dir is None:
            main_dir = tuple(round(float(x), 3) for x in d)
        transverse = tuple(round(float(p[i]), 3) for i in range(3) if i != k)
        sig_items.append(transverse)
    return (main_dir, tuple(sorted(sig_items)))


def _face_axis_point(parser, face_id):
    sid = parser.face_surface_id(face_id)
    axis = parser.axis_info(sid) if sid is not None else {}
    return axis.get("point")


def _point_distance(a, b):
    if a is None or b is None:
        return None
    return sum((float(a[i]) - float(b[i])) ** 2 for i in range(3)) ** 0.5


def _filter_shared_cyls_by_rejected_bridge_anchor(parser, cyl_faces, rejected_line_mouth_holes, tolerance=1.0e-4):
    """Keep only the shared-plane wall(s) spatially related to the rejected bridge candidate.

    The LGEWC failure mode is not "every circular loop on the shared plane is a blind hole".
    The original recognizer first produced one false LINE/B_SPLINE bridge patch (#390).
    The shared-plane fallback should replace that false bridge with the nearby true circular
    wall, not promote every circular loop on the same large bottom plane.

    Therefore we use the rejected bridge cylinder axis point as an anchor.  Among candidate
    circular wall faces on a shared plane, keep only the nearest transverse hole position.
    This removes the unsealed opposite loop on the same shared bottom face while preserving
    the intended shared-plane blind hole.
    """
    cyl_faces = unique_keep_order(cyl_faces)
    if not rejected_line_mouth_holes or len(cyl_faces) <= 1:
        return cyl_faces, []

    anchors = []
    for h in rejected_line_mouth_holes:
        face_id = h.get("source_cyl_face") or h.get("cyl_face")
        p = _face_axis_point(parser, face_id)
        if p is not None:
            anchors.append((face_id, p))
    if not anchors:
        return cyl_faces, []

    distances = []
    for f in cyl_faces:
        p = _face_axis_point(parser, f)
        if p is None:
            continue
        dmin = min((_point_distance(p, a[1]) for a in anchors if _point_distance(p, a[1]) is not None), default=None)
        if dmin is not None:
            distances.append((f, dmin))
    if not distances:
        return cyl_faces, []

    min_d = min(d for _, d in distances)
    # Keep faces at the nearest hole station.  The tolerance also allows multiple
    # coaxial wall patches at the same station to remain grouped.
    keep = [f for f, d in distances if d <= min_d + max(tolerance, min_d * 1.0e-6)]
    dropped = [f for f in cyl_faces if f not in keep]
    return unique_keep_order(keep), unique_keep_order(dropped)



def _vector_sub(a, b):
    return tuple(float(a[i]) - float(b[i]) for i in range(3))


def _vector_dot(a, b):
    return sum(float(a[i]) * float(b[i]) for i in range(3))


def _vector_cross(a, b):
    return (
        float(a[1]) * float(b[2]) - float(a[2]) * float(b[1]),
        float(a[2]) * float(b[0]) - float(a[0]) * float(b[2]),
        float(a[0]) * float(b[1]) - float(a[1]) * float(b[0]),
    )


def _vector_norm3(v):
    return sum(float(x) * float(x) for x in v) ** 0.5


def _vector_unit(v):
    n = _vector_norm3(v)
    if n <= 1.0e-12:
        return None
    return tuple(float(x) / n for x in v)


def _plane_basis_for_face(parser, plane_face):
    sid = parser.face_surface_id(plane_face)
    axis = parser.axis_info(sid) if sid is not None else {}
    origin = axis.get("point")
    normal = _vector_unit(axis.get("direction") or (0.0, 0.0, 1.0))
    u = _vector_unit(axis.get("ref_direction") or (1.0, 0.0, 0.0))
    if origin is None or normal is None:
        return None
    if u is None or abs(_vector_dot(u, normal)) > 0.95:
        # Pick any stable direction perpendicular to the plane normal.
        candidate = (1.0, 0.0, 0.0) if abs(normal[0]) < 0.9 else (0.0, 1.0, 0.0)
        u = _vector_unit(_vector_cross(normal, candidate))
    v = _vector_unit(_vector_cross(normal, u))
    if u is None or v is None:
        return None
    return tuple(origin), normal, u, v


def _project_to_plane_2d(point, basis):
    origin, normal, u, v = basis
    d = _vector_sub(point, origin)
    return (_vector_dot(d, u), _vector_dot(d, v))


def _outer_loop_vertices_2d(parser, plane_face, basis):
    """Collect projected vertices from FACE_OUTER_BOUND line/curve loop.

    For the shared-rectangle bottom cases, the outer loop is a rectangle or a
    long strip.  We only need a conservative bounding box coverage test, so the
    exact curve order is not required.
    """
    pts = []
    for b in parser.face_to_edges_by_bound.get(plane_face, []):
        if not b.get("is_outer"):
            continue
        for item in b.get("curves", []):
            for p in parser.edge_vertices_xyz(item.get("edge_curve")):
                if p is not None:
                    pts.append(_project_to_plane_2d(p, basis))
    # Deduplicate approximately.
    out = []
    seen = set()
    for x, y in pts:
        key = (round(float(x), 7), round(float(y), 7))
        if key not in seen:
            seen.add(key)
            out.append((float(x), float(y)))
    return out


def _shared_plane_bbox_info(parser, plane_face, basis):
    pts = _outer_loop_vertices_2d(parser, plane_face, basis)
    if len(pts) < 4:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    return {
        "minx": minx,
        "maxx": maxx,
        "miny": miny,
        "maxy": maxy,
        "width": maxx - minx,
        "height": maxy - miny,
        "diag": ((maxx - minx) ** 2 + (maxy - miny) ** 2) ** 0.5,
    }


def _point_in_bbox_2d(pt, bbox, tol=1.0e-6):
    x, y = pt
    return (
        bbox["minx"] - tol <= x <= bbox["maxx"] + tol
        and bbox["miny"] - tol <= y <= bbox["maxy"] + tol
    )


def _shared_plane_circle_coverage(parser, plane_face, circle_center, circle_radius, samples=32):
    """Approximate whether the shared rectangle plane covers the circular bottom area.

    The old plane-first rule promoted every circular loop on a shared PLANE.
    Here the PLANE must be large enough and positioned so the candidate circle is
    not merely tangent/partially intersecting the shared face.  A bbox-based test
    is sufficient for the OpenCASCADE rectangular/strip planes in these STP files.
    """
    basis = _plane_basis_for_face(parser, plane_face)
    if basis is None or circle_center is None or circle_radius is None:
        return 0.0, None
    bbox = _shared_plane_bbox_info(parser, plane_face, basis)
    if not bbox:
        return 0.0, None

    c2 = _project_to_plane_2d(circle_center, basis)
    if not _point_in_bbox_2d(c2, bbox, tol=max(1.0e-5, circle_radius * 0.05)):
        return 0.0, bbox

    inside = 0
    for i in range(samples):
        ang = 2.0 * math.pi * i / samples
        p = (c2[0] + float(circle_radius) * math.cos(ang), c2[1] + float(circle_radius) * math.sin(ang))
        if _point_in_bbox_2d(p, bbox, tol=max(1.0e-5, circle_radius * 0.02)):
            inside += 1
    return inside / float(samples), bbox




def _segment_point_distance_2d(point, a, b):
    """Distance from 2D point to a 2D segment, returning (distance, t)."""
    px, py = point
    ax, ay = a
    bx, by = b
    vx = bx - ax
    vy = by - ay
    wx = px - ax
    wy = py - ay
    l2 = vx * vx + vy * vy
    if l2 <= 1.0e-18:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5, 0.0
    t = max(0.0, min(1.0, (wx * vx + wy * vy) / l2))
    qx = ax + t * vx
    qy = ay + t * vy
    return ((px - qx) ** 2 + (py - qy) ** 2) ** 0.5, t


def _edge_vertices_projected_on_plane(parser, edge_id, basis, plane_tol=1.0e-4):
    pts = parser.edge_vertices_xyz(edge_id)
    if len(pts) < 2:
        return None
    origin, normal, _, _ = basis
    out = []
    for p in pts[:2]:
        dist = abs(_vector_dot(_vector_sub(tuple(p), origin), normal))
        if dist > plane_tol:
            return None
        out.append(_project_to_plane_2d(tuple(p), basis))
    return out


def _circle_edge_center_radius(parser, edge_id):
    center, radius, _, _ = _edge_circle_center_radius_axis(parser, edge_id)
    if center is None or radius is None:
        return None, None
    return tuple(center), float(radius)


def _shared_bottom_disk_local_integrity(parser, plane_face, circle_edge, circle_center, circle_radius, samples=32):
    """Check whether the candidate shared PLANE locally behaves like an uncut bottom disk.

    A shared rectangular PLANE can contain many circular loops.  The valid blind-hole
    bottom is not decided by the whole plane, but by the local disk around the cylinder
    terminal circle.  The disk is rejected when another boundary edge on the same plane
    cuts into that circular area.  This catches the common false case where the bottom
    plane exists topologically but a LINE/slot boundary splits or truncates the local
    bottom region.

    The current circular edge is allowed and skipped.  Rectangular outer-loop lines are
    allowed only when they stay outside the disk.  Other circular loops, spline/ellipse
    edges, or line segments entering the disk make the shared-bottom candidate invalid.
    """
    if circle_center is None or circle_radius is None:
        return {"ok": False, "reason": "missing_circle_geometry", "coverage": 0.0, "clearance": 0.0}
    basis = _plane_basis_for_face(parser, plane_face)
    if basis is None:
        return {"ok": False, "reason": "missing_plane_basis", "coverage": 0.0, "clearance": 0.0}

    coverage, bbox = _shared_plane_circle_coverage(parser, plane_face, circle_center, circle_radius, samples=samples)
    if coverage < 0.85:
        return {"ok": False, "reason": "plane_does_not_cover_circle_bbox", "coverage": coverage, "clearance": 0.0}

    c2 = _project_to_plane_2d(circle_center, basis)
    r = float(circle_radius)
    tol = max(1.0e-5, r * 0.02)
    cut_edges = []
    min_clearance = 1.0e99

    for bound in parser.face_to_edges_by_bound.get(plane_face, []):
        for item in bound.get("curves", []):
            edge_id = item.get("edge_curve")
            if edge_id is None or edge_id == circle_edge:
                continue
            etype = parser.edge_base_curve_type(edge_id)

            if etype == "LINE":
                pts2 = _edge_vertices_projected_on_plane(parser, edge_id, basis, plane_tol=max(1.0e-4, r * 1.0e-4))
                if not pts2:
                    continue
                dist, t = _segment_point_distance_2d(c2, pts2[0], pts2[1])
                min_clearance = min(min_clearance, dist - r)
                # If a line segment actually enters the disk interior, it truncates
                # the local shared bottom.  Tangent/outside rectangle borders are OK.
                if dist < r - tol:
                    cut_edges.append((edge_id, etype, dist))

            elif etype == "CIRCLE":
                other_center, other_radius = _circle_edge_center_radius(parser, edge_id)
                if other_center is None or other_radius is None:
                    continue
                o2 = _project_to_plane_2d(other_center, basis)
                d = ((c2[0] - o2[0]) ** 2 + (c2[1] - o2[1]) ** 2) ** 0.5
                min_clearance = min(min_clearance, d - (r + other_radius))
                if d < (r + other_radius) - tol:
                    cut_edges.append((edge_id, etype, d))

            else:
                # For ellipse/spline/unknown curve, use vertices as a conservative
                # local interference check.  If any projected endpoint falls inside
                # the disk, this boundary is considered to cut the bottom.
                pts2 = _edge_vertices_projected_on_plane(parser, edge_id, basis, plane_tol=max(1.0e-4, r * 1.0e-4))
                if not pts2:
                    continue
                hit = False
                for pt in pts2:
                    d = ((pt[0] - c2[0]) ** 2 + (pt[1] - c2[1]) ** 2) ** 0.5
                    min_clearance = min(min_clearance, d - r)
                    if d < r - tol:
                        hit = True
                if hit:
                    cut_edges.append((edge_id, etype, 0.0))

    if min_clearance == 1.0e99:
        min_clearance = 0.0

    if cut_edges:
        return {
            "ok": False,
            "reason": "local_bottom_disk_interrupted_by_plane_edges",
            "coverage": coverage,
            "clearance": min_clearance,
            "cut_edges": cut_edges,
        }
    return {
        "ok": True,
        "reason": "local_bottom_disk_uninterrupted",
        "coverage": coverage,
        "clearance": min_clearance,
        "cut_edges": [],
    }

def _shared_plane_is_rectangular_strip(parser, plane_face, min_aspect=2.4):
    """Return True for the long rectangular shared bottom faces.

    This is an auxiliary guard, not the main criterion.  It prevents small annular
    faces, bolt pads, and local circular caps from being treated as shared bottom
    planes.
    """
    ok, circle_count, has_line_outer = _plane_shared_ring_score(parser, plane_face)
    if not ok or not has_line_outer:
        return False
    basis = _plane_basis_for_face(parser, plane_face)
    if basis is None:
        return False
    bbox = _shared_plane_bbox_info(parser, plane_face, basis)
    if not bbox:
        return False
    short_side = min(bbox["width"], bbox["height"])
    long_side = max(bbox["width"], bbox["height"])
    if short_side <= 1.0e-8:
        return False
    return (long_side / short_side) >= min_aspect


def _end_direct_adjacent_planes(parser, end):
    return [f for f in end.get("adjacent_faces", []) if parser.face_surface_type(f) == "PLANE"]


def _end_has_external_opening(recognizer, end):
    if end.get("classification") == "open":
        return True
    for item in end.get("trace", []):
        face_id = item.get("face")
        if item.get("surface_type") == "PLANE" and recognizer._looks_external_face(face_id):
            return True
    return False


def _shared_rect_candidate_from_cylinder(parser, recognizer, surface_id, face_id, existing_faces):
    """Cylinder-first shared-rectangle blind-hole rule.

    Correct rule direction:
      CYLINDRICAL_SURFACE -> two circular end rings -> one ring is external
      opening, the other ring directly touches a shared rectangular PLANE that
      covers the bottom circle.

    This avoids the previous plane-first failure mode where every cylinder on a
    multi-ring plane was exported.
    """
    if face_id in existing_faces:
        return None
    if parser.face_surface_type(face_id) != "CYLINDRICAL_SURFACE":
        return None
    if not _is_clean_two_circle_cyl_wall(parser, face_id):
        return None

    surface = parser.surfaces.get(surface_id, {})
    radius = surface.get("radius")
    if radius is None:
        return None

    axis = parser.axis_info(surface_id)
    cyl_dir = _vector_unit(axis.get("direction") or (0.0, 0.0, 0.0))
    if cyl_dir is None:
        return None

    axial_span = parser.cylindrical_face_axial_span(surface_id, face_id)
    if axial_span is None:
        return None
    # The shared-rectangle blind holes in this project are shallow/medium inserts
    # into a rail/strip floor.  Very long channels should remain excluded.
    if axial_span / float(radius) > 5.0:
        return None

    end_infos = _build_end_infos_for_cyl_face(parser, recognizer, face_id)
    if len(end_infos) != 2:
        return None
    for end in end_infos:
        if not recognizer._is_complete_circular_mouth({"edge_curves": end.get("edge_curves", [])}):
            return None

    candidates = []
    for bottom_idx, bottom_end in enumerate(end_infos):
        open_end = end_infos[1 - bottom_idx]
        if not _end_has_external_opening(recognizer, open_end):
            continue
        for plane_face in _end_direct_adjacent_planes(parser, bottom_end):
            if not _shared_plane_is_rectangular_strip(parser, plane_face):
                continue
            shared_edges = sorted(set(parser.face_to_edge_curves.get(face_id, set())) & set(parser.face_to_edge_curves.get(plane_face, set())))
            circle_edges = [e for e in shared_edges if _edge_is_circle(parser, e)]
            if not circle_edges:
                continue
            plane_normal = _vector_unit(_plane_normal_for_face(parser, plane_face) or (0.0, 0.0, 0.0))
            if plane_normal is None:
                continue
            if abs(_vector_dot(cyl_dir, plane_normal)) < 0.95:
                continue
            for edge_id in circle_edges:
                center, edge_radius, _, _ = _edge_circle_center_radius_axis(parser, edge_id)
                if center is None or edge_radius is None:
                    continue
                if abs(float(edge_radius) - float(radius)) > max(1.0e-5, float(radius) * 1.0e-3):
                    continue
                integrity = _shared_bottom_disk_local_integrity(parser, plane_face, edge_id, center, edge_radius)
                if not integrity.get("ok"):
                    continue
                coverage, bbox = _shared_plane_circle_coverage(parser, plane_face, center, edge_radius)
                candidates.append({
                    "plane_face": plane_face,
                    "bottom_edge": edge_id,
                    "bottom_center": tuple(center),
                    "coverage": integrity.get("coverage", coverage),
                    "bbox": bbox,
                    "bottom_end": bottom_end,
                    "open_end": open_end,
                    "local_bottom_clearance": integrity.get("clearance", 0.0),
                    "local_bottom_integrity": integrity,
                })

    if not candidates:
        return None
    # Prefer the larger coverage; tie-break by bigger rectangular plane.
    candidates.sort(key=lambda c: (c.get("coverage", 0.0), (c.get("bbox") or {}).get("diag", 0.0)), reverse=True)
    best = candidates[0]
    return {
        "cyl_face": face_id,
        "cyl_surface": surface_id,
        "radius": radius,
        "axis_point": axis.get("point"),
        "axis_direction": axis.get("direction"),
        "axial_span": axial_span,
        "plane_face": best["plane_face"],
        "bottom_edge": best["bottom_edge"],
        "bottom_center": best["bottom_center"],
        "coverage": best["coverage"],
        "opening": recognizer._merge_ends([best["open_end"]], classification="open"),
        "terminal": recognizer._merge_ends([best["bottom_end"]], classification="terminal"),
    }


def _candidate_distance_to_rejected_anchor(parser, candidate, rejected_line_mouth_holes):
    if not rejected_line_mouth_holes:
        return None
    p = _face_axis_point(parser, candidate.get("cyl_face"))
    if p is None:
        return None
    vals = []
    for h in rejected_line_mouth_holes:
        anchor_face = h.get("source_cyl_face") or h.get("cyl_face")
        a = _face_axis_point(parser, anchor_face)
        d = _point_distance(p, a)
        if d is not None:
            vals.append(d)
    return min(vals) if vals else None


def _plane_reference_distance(parser, plane_face, center):
    sid = parser.face_surface_id(plane_face)
    axis = parser.axis_info(sid) if sid is not None else {}
    return _point_distance(center, axis.get("point"))


def _dominant_center_axis(candidates):
    """Return the coordinate index along which shared-ring candidates are repeated.

    For rail/profile parts, wrong shared-plane candidates are usually repeated along
    the long profile direction.  The correct special shared-bottom hole is located
    near the functional block where ordinary blind holes already exist.  We use
    this dominant coordinate only as a selection axis; it is not a geometric hole
    test by itself.
    """
    pts = [c.get("bottom_center") for c in candidates if c.get("bottom_center") is not None]
    if not pts:
        return None
    spreads = []
    for i in range(3):
        vals = [float(p[i]) for p in pts]
        spreads.append(max(vals) - min(vals))
    k = max(range(3), key=lambda i: spreads[i])
    if spreads[k] <= 1.0e-8:
        return None
    return k


def _existing_hole_anchor_values(existing_holes, axis_index):
    vals = []
    if axis_index is None:
        return vals
    for h in existing_holes or []:
        if h.get("is_shared_multi_ring_plane_hole"):
            continue
        p = h.get("axis_point")
        if p is None:
            continue
        try:
            vals.append(float(p[axis_index]))
        except Exception:
            pass
    return vals


def _candidate_distance_to_existing_hole_anchor(candidate, axis_index, anchor_values):
    center = candidate.get("bottom_center")
    if center is None or axis_index is None or not anchor_values:
        return None
    v = float(center[axis_index])
    return min(abs(v - a) for a in anchor_values)


def _select_one_shared_candidate_per_plane(parser, candidates, rejected_line_mouth_holes=None, existing_holes=None):
    """Collapse repeated circular rings on shared rectangles using local bottom quality.

    V19主规则先用 `_shared_bottom_disk_local_integrity()` 排除局部底面被 LINE/其他边界
    截断的候选。剩余候选再做很窄的代表选择：
    - H48 这类确实存在 rejected bridge 时，用 bridge 作为辅助锚点，只解决成对候选哪一侧封闭；
    - 没有 bridge 时，不再用已有孔功能区或 PLANE reference 选孔，而按局部底面完整性、覆盖率、
      clearence 选择；
    - 对同一物理结构的内外两层共享面，默认 inner 由后续全局半径筛选保留较小半径组。
    """
    by_plane = defaultdict(list)
    for c in candidates:
        by_plane[c["plane_face"]].append(c)

    selected = []
    raw_groups = []
    for plane_face, items in by_plane.items():
        if rejected_line_mouth_holes:
            def key_bridge(c):
                d = _candidate_distance_to_rejected_anchor(parser, c, rejected_line_mouth_holes)
                return (
                    d if d is not None else 1.0e99,
                    -float(c.get("coverage") or 0.0),
                    -float(c.get("local_bottom_clearance") or 0.0),
                    int(c.get("cyl_face") or 10**12),
                )
            best = sorted(items, key=key_bridge)[0]
            reason = "rejected_bridge_anchor_after_local_integrity"
        else:
            def key_local(c):
                return (
                    -float(c.get("coverage") or 0.0),
                    -float(c.get("local_bottom_clearance") or 0.0),
                    int(c.get("cyl_face") or 10**12),
                )
            best = sorted(items, key=key_local)[0]
            reason = "local_uninterrupted_bottom_disk"

        selected.append(best)
        raw_groups.append({
            "plane_face": plane_face,
            "cyl_faces": [best["cyl_face"]],
            "dropped_unsealed_cyl_faces": [c["cyl_face"] for c in items if c["cyl_face"] != best["cyl_face"]],
            "candidate_cyl_faces_before_seal_filter": [c["cyl_face"] for c in items],
            "avg_radius": float(best["radius"]),
            "circle_count": len(items),
            "signature": _axis_group_signature(parser, [best["cyl_face"]]),
            "coverage": best.get("coverage"),
            "local_bottom_clearance": best.get("local_bottom_clearance"),
            "selection_reason": reason,
            "selection_axis": None,
        })
    return selected, raw_groups

def find_shared_multi_ring_plane_holes(parser, recognizer, existing_holes, selection="inner", rejected_line_mouth_holes=None):
    """Cylinder-first shared rectangular plane blind-hole finder.

    This replaces the old plane-first fallback.  It still returns the same data
    shape used by the exporter/report, but the decision starts from a cylindrical
    wall and proves one end is an opening while the other end is a shared
    rectangular bottom plane that covers the bottom circle.
    """
    existing_faces = {h.get("cyl_face") for h in existing_holes}
    candidates = []
    for surface_id, surface in sorted(parser.surfaces.items()):
        if surface.get("type") != "CYLINDRICAL_SURFACE":
            continue
        for face_id in parser.surface_to_faces.get(surface_id, []):
            c = _shared_rect_candidate_from_cylinder(parser, recognizer, surface_id, face_id, existing_faces)
            if c:
                candidates.append(c)

    # First collapse repeated rings on the same shared rectangle to one sealed representative.
    one_per_plane, raw_groups = _select_one_shared_candidate_per_plane(parser, candidates, rejected_line_mouth_holes, existing_holes=existing_holes)

    # If the same shared-bottom structure appears as inner/outer stepped planes,
    # keep the requested radius side.  This avoids exporting both the large outer
    # counterbore side and the smaller actual blind-hole side in H48/H60-like parts.
    if selection == "all" or len(one_per_plane) <= 1:
        selected = list(one_per_plane)
    else:
        radii = [float(c.get("radius") or 0.0) for c in one_per_plane]
        target = max(radii) if selection == "outer" else min(radii)
        tol = max(1.0e-6, abs(target) * 1.0e-6)
        selected = [c for c in one_per_plane if abs(float(c.get("radius") or 0.0) - target) <= tol]
        # If more than one candidate remains with the same target radius, keep the
        # one with the best local bottom quality.  This is a deterministic fallback,
        # not a plane-reference or functional-area heuristic.
        if len(selected) > 1:
            selected = [sorted(selected, key=lambda c: (-float(c.get("coverage") or 0.0), -float(c.get("local_bottom_clearance") or 0.0), int(c.get("cyl_face") or 10**12)))[0]]

    selected_keys = {(c["plane_face"], c["cyl_face"]) for c in selected}
    for g in raw_groups:
        if (g["plane_face"], g["cyl_faces"][0]) not in selected_keys:
            # This plane was the outer/inner side not selected. Keep it in diagnostics
            # but mark its representative as dropped.
            g["dropped_unsealed_cyl_faces"] = unique_keep_order(g.get("dropped_unsealed_cyl_faces", []) + g.get("cyl_faces", []))
            g["cyl_faces"] = []

    shared_holes = []
    for c in sorted(selected, key=lambda item: (item.get("plane_face") or 0, item.get("cyl_face") or 0)):
        shared_holes.append({
            "type": "共享多圆环平面盲孔",
            "is_shared_multi_ring_plane_hole": True,
            "cyl_face": c["cyl_face"],
            "cyl_surface": c["cyl_surface"],
            "radius": c["radius"],
            "axis_point": c["axis_point"],
            "axis_direction": c["axis_direction"],
            "axial_span": c["axial_span"],
            "opening": c.get("opening"),
            "terminal": c.get("terminal"),
            "shared_cyl_faces": [c["cyl_face"]],
            "shared_bottom_faces": [c["plane_face"]],
            "shared_group_avg_radius": float(c["radius"]),
            "shared_group_circle_count": 1,
            "dropped_unsealed_cyl_faces": [],
            "candidate_cyl_faces_before_seal_filter": [c["cyl_face"]],
            "shared_bottom_coverage": c.get("coverage"),
            "reason": "圆柱壁一端为外部开口，另一端完整圆环直接连接共享矩形 PLANE，且该共享平面对底部圆形成有效覆盖。",
        })
    return shared_holes, raw_groups




def _plane_normal_for_face(parser, face_id):
    sid = parser.face_surface_id(face_id)
    axis = parser.axis_info(sid) if sid is not None else {}
    normal = axis.get("direction")
    if normal is None:
        return None
    return tuple(float(x) for x in normal)


def _abs_dot_norm(a, b):
    if a is None or b is None:
        return None
    na = sum(float(x) * float(x) for x in a) ** 0.5
    nb = sum(float(x) * float(x) for x in b) ** 0.5
    if na <= 1.0e-12 or nb <= 1.0e-12:
        return None
    return sum(float(a[i]) * float(b[i]) for i in range(3)) / (na * nb)


def _external_plane_faces_from_end(recognizer, end):
    faces = []
    for item in end.get("trace", []):
        face_id = item.get("face")
        if item.get("surface_type") == "PLANE" and recognizer._looks_external_face(face_id):
            faces.append(face_id)
    return unique_keep_order(faces)


def _conical_faces_from_end(end):
    faces = []
    for item in end.get("trace", []):
        if item.get("surface_type") == "CONICAL_SURFACE":
            faces.append(item.get("face"))
    return unique_keep_order(faces)


def _build_end_infos_for_cyl_face(parser, recognizer, face_id):
    end_infos = []
    for bound_info in parser.face_to_edges_by_bound.get(face_id, []):
        curves = [item["edge_curve"] for item in bound_info.get("curves", [])]
        unique_curves = sorted(set(curves))
        if not unique_curves:
            continue
        if len(unique_curves) == 1:
            adjacent = recognizer._adjacent_faces_for_curves(unique_curves, exclude_face=face_id)
            end_infos.append(recognizer._make_end_info(face_id, bound_info, unique_curves, adjacent))
        else:
            for curve in unique_curves:
                adjacent = recognizer._adjacent_faces_for_curves([curve], exclude_face=face_id)
                if adjacent:
                    end_infos.append(recognizer._make_end_info(face_id, bound_info, [curve], adjacent))
    return end_infos


def _is_double_chamfer_slit_candidate(parser, recognizer, surface_id, face_id, existing_faces):
    """Disabled in v21-no-radius-through-fix.

    The old rule accepted a short cylinder whose two ends both connect to
    external planes through chamfers.  That is a through feature, so it is no
    longer considered a blind-hole candidate.
    """
    return None


def find_double_chamfer_slit_blind_holes(parser, recognizer, existing_holes):
    """Disabled: two-open-end double-chamfer cylinders are through holes."""
    return []



# =============================================================================
# V15.10 broad partial-mouth / partial-cylinder cluster blind-hole supplement
# =============================================================================

def _is_local_partial_cap_plane(parser, recognizer, plane_face, circle_edge, max_curves=6):
    """Return True for a local closed cap plane of a partial-cylinder blind hole.

    This broad rule handles dataset-style blind holes whose cylindrical wall is
    not a full 360-degree wall.  The cap may be a sector, crescent, or small
    multi-arc plane.  It is still accepted only when it is local, non-external,
    directly uses the terminal circular edge, and has only CIRCLE/LINE boundary
    curves.  Large shared planes, spline/ellipse slot boundaries, and external
    faces remain excluded.
    """
    if plane_face is None or parser.face_surface_type(plane_face) != "PLANE":
        return False
    if recognizer._looks_external_face(plane_face):
        return False
    if parser.face_bound_count(plane_face)[2] != 1:
        return False
    counts = parser.face_loop_curve_counts(plane_face)
    if not counts or max(counts) > max_curves:
        return False
    edge_ids = _face_edge_ids(parser, plane_face)
    if circle_edge not in edge_ids:
        return False
    types = [parser.edge_base_curve_type(e) for e in edge_ids]
    if "CIRCLE" not in types:
        return False
    if any(t not in {"CIRCLE", "LINE"} for t in types):
        return False
    # A local partial cap should not be a long polyline/slot floor.  It normally
    # has one to several circle arcs and at most a small number of line closures.
    if types.count("LINE") > 3:
        return False
    # CIRCLE + LINE + CIRCLE + LINE is the classic round-ended slot / elongated
    # pocket floor.  Even if it is locally closed, it represents a slot-like
    # feature rather than the blind-hole cap used by the broad partial-mouth
    # dataset examples.
    if len(types) == 4 and types.count("CIRCLE") == 2 and types.count("LINE") == 2:
        return False
    return True


def _classify_partial_cylindrical_sector_wall(parser, face_id):
    """Classify a partial cylindrical wall used by broad blind holes.

    Accepted topology:
      - CYLINDRICAL_SURFACE;
      - two standard CIRCLE section arcs at two axial levels;
      - arcs may be partial, not full loops;
      - remaining LINE/SEAM_CURVE edges must be axial connectors.

    Unlike strict blind holes, connector lines may touch adjacent cylindrical
    patches.  Those adjacent patches may be part of the same irregular blind-hole
    mouth.  The final cluster rule, not this single-face classifier, decides
    whether the group is closed by local cap planes.
    """
    if parser.face_surface_type(face_id) != "CYLINDRICAL_SURFACE":
        return {"ok": False, "reason": "not_cylindrical"}
    cyl_surface_id = parser.face_surface_id(face_id)
    radius = parser.surfaces.get(cyl_surface_id, {}).get("radius")
    if radius is None:
        return {"ok": False, "reason": "missing_radius"}
    edges = _unique_edges_in_face(parser, face_id)
    if len(edges) < 4:
        return {"ok": False, "reason": "too_few_edges"}

    circle_infos = []
    connector_edges = []
    bad_edges = []
    for edge_id in edges:
        cinfo = _edge_is_standard_circular_section(parser, cyl_surface_id, edge_id)
        if cinfo is not None:
            circle_infos.append(cinfo)
            continue
        etype = parser.edge_base_curve_type(edge_id)
        if etype in {"LINE", "SEAM_CURVE"}:
            connector_edges.append(edge_id)
        else:
            bad_edges.append((edge_id, etype))
    if bad_edges:
        return {"ok": False, "reason": "bad_edge_types", "bad_edges": bad_edges}

    tol = max(1.0e-5, abs(float(radius)) * 1.0e-2)
    groups = _group_circle_sections(parser, circle_infos, tol=tol)
    if len(groups) != 2:
        return {"ok": False, "reason": "not_two_section_levels", "circle_groups": groups}
    # Full circular walls are already handled by the strict recognizer.  Here we
    # specifically supplement incomplete/截断圆柱壁.
    if all(g.get("closed") for g in groups):
        return {"ok": False, "reason": "complete_wall_not_partial", "circle_groups": groups}
    if any(len(g.get("edges", [])) != 1 for g in groups):
        return {"ok": False, "reason": "split_partial_arc_not_supported", "circle_groups": groups}

    section_ts = [g["t_mean"] for g in groups]
    accepted_connectors = []
    rejected = []
    for edge_id in connector_edges:
        if _edge_is_axial_connector(parser, cyl_surface_id, edge_id, section_ts=section_ts, tol=tol):
            accepted_connectors.append(edge_id)
        else:
            rejected.append((edge_id, parser.edge_base_curve_type(edge_id)))
    if rejected:
        return {"ok": False, "reason": "non_axial_connectors", "rejected": rejected}
    if len(accepted_connectors) < 2:
        return {"ok": False, "reason": "not_enough_connectors"}

    return {
        "ok": True,
        "reason": "partial_cylindrical_sector_wall",
        "section_rings": groups,
        "circle_edges": [g["edges"][0] for g in groups],
        "connector_edges": accepted_connectors,
    }


def _find_direct_cap_plane_for_circle_end(parser, recognizer, end, circle_edge):
    out = []
    for f in end.get("adjacent_faces", []):
        if _is_local_partial_cap_plane(parser, recognizer, f, circle_edge):
            out.append(f)
    return unique_keep_order(out)


def _partial_axis_signature(parser, surface_id, ndigits=5):
    axis = parser.axis_info(surface_id)
    p = axis.get("point") or (0.0, 0.0, 0.0)
    d = _vector_unit(axis.get("direction") or (0.0, 0.0, 0.0)) or (0.0, 0.0, 0.0)
    # direction sign should not split the same physical axis
    if tuple(d) < tuple(-x for x in d):
        d = tuple(-x for x in d)
    return (
        tuple(round(float(x), ndigits) for x in p),
        tuple(round(float(x), ndigits) for x in d),
    )


def _partial_wall_candidate(parser, recognizer, surface_id, face_id, existing_faces):
    if face_id in existing_faces:
        return None
    wall = _classify_partial_cylindrical_sector_wall(parser, face_id)
    if not wall.get("ok"):
        return None
    radius = parser.surfaces.get(surface_id, {}).get("radius")
    span = parser.cylindrical_face_axial_span(surface_id, face_id)
    if radius is None or span is None:
        return None
    # v21-no-radius-through-fix: radius is not used as a size gate here.
    # Radius remains available only for geometric tolerance and depth proportion.
    # The broad dataset cases include shallow cut-off cylindrical caps, so do not
    # use the strict depth ratio here.  Still reject nearly zero-depth fillet-like
    # patches.
    if span < max(0.35, float(radius) * 0.20):
        return None

    end_infos = _build_end_infos_for_cyl_face(parser, recognizer, face_id)
    circle_ends = []
    for edge_id in wall.get("circle_edges", []):
        matched = [e for e in end_infos if e.get("edge_curves") == [edge_id]]
        if not matched:
            return None
        circle_ends.append(matched[0])
    if len(circle_ends) != 2:
        return None

    possible = []
    for i, open_end in enumerate(circle_ends):
        bottom_end = circle_ends[1 - i]
        open_edge = open_end.get("edge_curves", [None])[0]
        bottom_edge = bottom_end.get("edge_curves", [None])[0]
        if not _end_has_external_opening(recognizer, open_end):
            continue
        cap_planes = _find_direct_cap_plane_for_circle_end(parser, recognizer, bottom_end, bottom_edge)
        if not cap_planes:
            continue
        possible.append((open_end, bottom_end, open_edge, bottom_edge, cap_planes))
    if not possible:
        return None

    open_end, bottom_end, open_edge, bottom_edge, cap_planes = possible[0]
    axis = parser.axis_info(surface_id)
    return {
        "face": face_id,
        "surface": surface_id,
        "radius": float(radius),
        "span": span,
        "axis_point": axis.get("point"),
        "axis_direction": axis.get("direction"),
        "axis_sig": _partial_axis_signature(parser, surface_id),
        "opening": recognizer._merge_ends([open_end], classification="open"),
        "terminal": recognizer._merge_ends([bottom_end], classification="terminal"),
        "open_edge": open_edge,
        "bottom_edge": bottom_edge,
        "cap_planes": cap_planes,
        "connector_edges": wall.get("connector_edges", []),
        "all_ends": end_infos,
    }


def _partial_candidate_group_key(c):
    # group by same cylinder axis and radius.  This collects several partial wall
    # patches that together form one irregular blind-hole feature.
    return (
        c.get("axis_sig"),
        round(float(c.get("radius") or 0.0), 5),
    )


def _make_partial_cluster_hole(parser, recognizer, candidates):
    candidates = sorted(candidates, key=lambda c: c["face"])
    if not candidates:
        return None
    # At least one local cap plane must exist; all accepted candidates already
    # have one.  Avoid extremely large clusters unrelated to one feature.
    if len(candidates) > 6:
        return None
    cap_planes = unique_keep_order([p for c in candidates for p in c.get("cap_planes", [])])
    cyl_faces = unique_keep_order([c["face"] for c in candidates])
    if not cap_planes or not cyl_faces:
        return None

    first = candidates[0]
    # For a cluster, merge all openings/terminals so the report/export carries the
    # whole broad blind-hole feature.
    opening = recognizer._merge_ends([c["opening"] for c in candidates], classification="open")
    terminal = recognizer._merge_ends([c["terminal"] for c in candidates], classification="terminal")
    return {
        "type": "广义截断圆柱盲孔",
        "is_partial_mouth_sector_hole": True,
        "is_partial_mouth_cluster_hole": True,
        "cyl_surface": first["surface"],
        "cyl_face": first["face"],
        "radius": first["radius"],
        "axis_point": first.get("axis_point"),
        "axis_direction": first.get("axis_direction"),
        "axial_span": max(c.get("span") or 0.0 for c in candidates),
        "opening": opening,
        "terminal": terminal,
        "partial_cyl_faces": cyl_faces,
        "partial_bottom_faces": cap_planes,
        "partial_bottom_edges": unique_keep_order([c.get("bottom_edge") for c in candidates]),
        "partial_connector_edges": unique_keep_order([e for c in candidates for e in c.get("connector_edges", [])]),
        "all_ends": [e for c in candidates for e in c.get("all_ends", [])],
        "reason": "圆柱壁为一个或多个不完整圆柱扇区，开口圆弧被外部结构截断，终止圆弧由局部平面帽面/多圆弧底面封闭；按广义盲孔补充识别。",
    }


def find_partial_mouth_sector_blind_holes(parser, recognizer, existing_holes):
    existing_faces = {h.get("cyl_face") for h in existing_holes}
    candidates = []
    for surface_id, surface in sorted(parser.surfaces.items()):
        if surface.get("type") != "CYLINDRICAL_SURFACE":
            continue
        for face_id in parser.surface_to_faces.get(surface_id, []):
            c = _partial_wall_candidate(parser, recognizer, surface_id, face_id, existing_faces)
            if c:
                candidates.append(c)

    by_key = defaultdict(list)
    for c in candidates:
        by_key[_partial_candidate_group_key(c)].append(c)

    out = []
    for _, items in by_key.items():
        hole = _make_partial_cluster_hole(parser, recognizer, items)
        if hole:
            out.append(hole)
    return sorted(out, key=lambda h: (h.get("radius") or 0.0, h.get("cyl_face") or 0))



# =============================================================================
# V21-no-radius-through-fix variable-depth truncated-cylinder blind-hole supplement
# =============================================================================

def _is_local_variable_depth_cap_plane(parser, recognizer, plane_face, circle_edge, max_curves=6):
    """Local bottom cap for a variable-depth truncated cylindrical blind hole.

    Difference from the earlier partial-sector cap: the terminal circle can be a
    full CIRCLE, while the mouth side of the same CYLINDRICAL_SURFACE is cut by
    one or more transverse planes/cones.  Therefore the cylinder wall has more
    than two circular section levels, and the effective wall depth is not uniform
    around the circumference.
    """
    if plane_face is None or parser.face_surface_type(plane_face) != "PLANE":
        return False
    if recognizer._looks_external_face(plane_face):
        return False
    if parser.face_bound_count(plane_face)[2] != 1:
        return False
    counts = parser.face_loop_curve_counts(plane_face)
    if not counts or max(counts) > max_curves:
        return False
    edge_ids = _face_edge_ids(parser, plane_face)
    if circle_edge not in edge_ids:
        return False
    types = [parser.edge_base_curve_type(e) for e in edge_ids]
    if "CIRCLE" not in types:
        return False
    if any(t not in {"CIRCLE", "LINE"} for t in types):
        return False
    if types.count("LINE") > 3:
        return False
    return True


def _trace_edge_to_external_opening(parser, recognizer, cyl_face, edge_id):
    """Return True if a circular edge is an opening edge, directly or via entry transition."""
    adjacent = set(parser.edge_curve_to_faces.get(edge_id, set()))
    adjacent.discard(cyl_face)
    if not adjacent:
        return False
    # Direct external plane.
    for f in adjacent:
        if parser.face_surface_type(f) == "PLANE" and recognizer._looks_external_face(f):
            return True
    # Entry transition such as cone/toroid that reaches external plane in one step.
    adj_types = {parser.face_surface_type(f) for f in adjacent}
    if adj_types & ENTRY_TRANSITION_SURFACES:
        trace = recognizer._trace_end(cyl_face, adjacent, max_depth=1)
        for item in trace:
            if item.get("surface_type") == "PLANE" and recognizer._looks_external_face(item.get("face")):
                return True
    return False


def _classify_variable_depth_truncated_cyl_wall(parser, recognizer, face_id):
    """Detect one-face variable-depth truncated cylindrical blind-hole wall.

    Accepted topology:
      - CYLINDRICAL_SURFACE with a local closed bottom circle and PLANE cap;
      - one or more upper/mouth circular arcs at different axial levels that trace
        to an external opening, directly or through CONICAL/TOROIDAL transition;
      - other non-circular edges are SEAM_CURVE or axial LINE connectors;
      - more than two circular section levels are allowed, because transverse
        cutting planes make the wall depth non-uniform around the circumference.
    """
    if parser.face_surface_type(face_id) != "CYLINDRICAL_SURFACE":
        return {"ok": False, "reason": "not_cylindrical"}
    surface_id = parser.face_surface_id(face_id)
    radius = parser.surfaces.get(surface_id, {}).get("radius")
    if radius is None:
        return {"ok": False, "reason": "missing_radius"}
    # v21-no-radius-through-fix: radius is not used as a blind-hole size gate.

    edges = _unique_edges_in_face(parser, face_id)
    if len(edges) < 4:
        return {"ok": False, "reason": "too_few_edges"}

    circle_infos = []
    connector_edges = []
    bad_edges = []
    for edge_id in edges:
        cinfo = _edge_is_standard_circular_section(parser, surface_id, edge_id)
        if cinfo is not None:
            circle_infos.append(cinfo)
            continue
        etype = parser.edge_base_curve_type(edge_id)
        if etype in {"LINE", "SEAM_CURVE"}:
            connector_edges.append(edge_id)
        else:
            bad_edges.append((edge_id, etype))
    if bad_edges:
        return {"ok": False, "reason": "bad_edge_types", "bad_edges": bad_edges}

    tol = max(1.0e-5, abs(float(radius)) * 1.0e-2)
    groups = _group_circle_sections(parser, circle_infos, tol=tol)
    if len(groups) < 3:
        return {"ok": False, "reason": "not_variable_depth", "circle_groups": groups}

    # Generalized axial connector check: with variable-depth walls, connectors may
    # link adjacent section levels, not only global min/max.  A LINE/SEAM is valid
    # if its endpoints have two distinct axial coordinates close to any detected
    # circular section levels.  SEAM_CURVE without usable vertices is accepted.
    section_ts = [g["t_mean"] for g in groups]
    accepted_connectors = []
    rejected = []
    for edge_id in connector_edges:
        etype = parser.edge_base_curve_type(edge_id)
        if etype == "SEAM_CURVE":
            vals = _edge_vertices_t_values(parser, surface_id, edge_id)
            if len(vals) < 2:
                accepted_connectors.append(edge_id)
                continue
        elif etype == "LINE":
            vals = _edge_vertices_t_values(parser, surface_id, edge_id)
            if len(vals) < 2:
                rejected.append((edge_id, etype))
                continue
        else:
            rejected.append((edge_id, etype))
            continue
        if max(vals) - min(vals) <= tol:
            rejected.append((edge_id, etype))
            continue
        # Endpoints should be near two section levels.
        ok_vals = 0
        for v in (min(vals), max(vals)):
            if min(abs(v - t) for t in section_ts) <= max(tol, abs(max(section_ts)-min(section_ts)) * 0.08):
                ok_vals += 1
        if ok_vals == 2:
            accepted_connectors.append(edge_id)
        else:
            rejected.append((edge_id, etype))
    if rejected:
        return {"ok": False, "reason": "non_axial_or_unmatched_connectors", "rejected": rejected, "circle_groups": groups}

    # Bottom candidates: a closed circular section directly capped by a local PLANE.
    bottom_options = []
    for g in groups:
        if not g.get("closed"):
            continue
        for edge_id in g.get("edges", []):
            adj = set(parser.edge_curve_to_faces.get(edge_id, set()))
            adj.discard(face_id)
            caps = [f for f in adj if _is_local_variable_depth_cap_plane(parser, recognizer, f, edge_id)]
            if caps:
                bottom_options.append({"group": g, "edge": edge_id, "cap_planes": unique_keep_order(caps)})
    if not bottom_options:
        return {"ok": False, "reason": "no_local_closed_bottom_cap", "circle_groups": groups}

    # Opening evidence: at least one non-bottom circular edge reaches an external plane.
    open_edges = []
    bottom_edges = {o["edge"] for o in bottom_options}
    for g in groups:
        for edge_id in g.get("edges", []):
            if edge_id in bottom_edges:
                continue
            if _trace_edge_to_external_opening(parser, recognizer, face_id, edge_id):
                open_edges.append(edge_id)
    if not open_edges:
        return {"ok": False, "reason": "no_external_opening_edge", "circle_groups": groups, "bottom_options": bottom_options}

    # Prefer the deepest closed cap along the cylinder axis.  Sign is arbitrary,
    # so choose the cap farthest from all opening section levels.
    def bottom_score(opt):
        bt = opt["group"].get("t_mean", 0.0)
        if not open_edges:
            return 0.0
        edge_to_t = {ci["edge"]: ci["t"] for ci in circle_infos}
        distances = [abs(bt - edge_to_t[e]) for e in open_edges if e in edge_to_t]
        return max(distances or [0.0])
    best_bottom = sorted(bottom_options, key=bottom_score, reverse=True)[0]
    return {
        "ok": True,
        "reason": "variable_depth_truncated_cyl_wall",
        "circle_groups": groups,
        "bottom_edge": best_bottom["edge"],
        "bottom_cap_planes": best_bottom["cap_planes"],
        "opening_edges": unique_keep_order(open_edges),
        "connector_edges": unique_keep_order(accepted_connectors),
    }


def _variable_depth_wall_candidate(parser, recognizer, surface_id, face_id, existing_faces):
    if face_id in existing_faces:
        return None
    wall = _classify_variable_depth_truncated_cyl_wall(parser, recognizer, face_id)
    if not wall.get("ok"):
        return None
    radius = parser.surfaces.get(surface_id, {}).get("radius")
    span = parser.cylindrical_face_axial_span(surface_id, face_id)
    if radius is None or span is None:
        return None
    if span < max(0.35, float(radius) * 0.20):
        return None

    end_infos = _build_end_infos_for_cyl_face(parser, recognizer, face_id)
    open_parts = [e for e in end_infos if set(e.get("edge_curves", [])) & set(wall.get("opening_edges", []))]
    bottom_parts = [e for e in end_infos if wall.get("bottom_edge") in e.get("edge_curves", [])]
    if not open_parts or not bottom_parts:
        return None

    axis = parser.axis_info(surface_id)
    return {
        "face": face_id,
        "surface": surface_id,
        "radius": float(radius),
        "span": span,
        "axis_point": axis.get("point"),
        "axis_direction": axis.get("direction"),
        "opening": recognizer._merge_ends(open_parts, classification="open"),
        "terminal": recognizer._merge_ends(bottom_parts, classification="terminal"),
        "open_edges": unique_keep_order(wall.get("opening_edges", [])),
        "bottom_edge": wall.get("bottom_edge"),
        "cap_planes": unique_keep_order(wall.get("bottom_cap_planes", [])),
        "connector_edges": unique_keep_order(wall.get("connector_edges", [])),
        "all_ends": end_infos,
    }


def find_variable_depth_truncated_blind_holes(parser, recognizer, existing_holes):
    existing_faces = {h.get("cyl_face") for h in existing_holes}
    out = []
    for surface_id, surface in sorted(parser.surfaces.items()):
        if surface.get("type") != "CYLINDRICAL_SURFACE":
            continue
        for face_id in parser.surface_to_faces.get(surface_id, []):
            c = _variable_depth_wall_candidate(parser, recognizer, surface_id, face_id, existing_faces)
            if not c:
                continue
            opening = c["opening"]
            terminal = c["terminal"]
            out.append({
                "type": "变深截断圆柱盲孔",
                "is_partial_mouth_sector_hole": True,
                "is_variable_depth_partial_hole": True,
                "cyl_surface": c["surface"],
                "cyl_face": c["face"],
                "radius": c["radius"],
                "axis_point": c.get("axis_point"),
                "axis_direction": c.get("axis_direction"),
                "axial_span": c.get("span"),
                "opening": opening,
                "terminal": terminal,
                "partial_cyl_faces": [c["face"]],
                "partial_bottom_faces": c.get("cap_planes", []),
                "partial_bottom_edges": [c.get("bottom_edge")],
                "partial_connector_edges": c.get("connector_edges", []),
                "all_ends": c.get("all_ends", []),
                "reason": "圆柱壁被横向平面/过渡面截断，导致不同圆周位置深度不同；仍存在局部封闭底面和外部开口，按变深截断圆柱盲孔补充识别。",
            })
    return sorted(out, key=lambda h: (h.get("radius") or 0.0, h.get("cyl_face") or 0))




# =============================================================================
# V15.23 strict supplement: N-piece / multi-seam split cylindrical walls
# with PLANE or compound CONICAL/TOROIDAL/SPHERICAL split bottoms.
# Radius is not used as a blind-hole gate.  False positives are filtered by
# inner-cavity topology: complete circular opening, sealed internal bottom,
# and for same_sense=True split walls, a direct external mother-plane hole mouth.
# =============================================================================


SPLIT_WALL_COMPOUND_BOTTOM_SURFACES = {
    "CONICAL_SURFACE",
    "TOROIDAL_SURFACE",
    "SPHERICAL_SURFACE",
    "BSPLINE_SURFACE_WITH_KNOTS",
    "B_SPLINE_SURFACE_WITH_KNOTS",
}


def _circle_center_key_for_edge(parser, edge_id, ndigits=5):
    center, radius, _, _ = _edge_circle_center_radius_axis(parser, edge_id)
    if center is None or radius is None:
        return None
    return (tuple(round(float(x), ndigits) for x in center), round(float(radius), ndigits))


def _circle_center_key_for_edges(parser, edge_ids, ndigits=5):
    """Return one center/radius key for a circular section made of one or more arcs."""
    keys = [_circle_center_key_for_edge(parser, e, ndigits=ndigits) for e in edge_ids]
    keys = [k for k in keys if k is not None]
    if not keys:
        return None
    # All section arcs should share the same center/radius.  If tiny roundoff creates
    # multiple keys, use the first deterministic key; candidate grouping still requires
    # closed rings later, so this will not promote random arcs.
    keys = sorted(set(keys))
    return keys[0]


def _same_axis_radius_signature(parser, surface_id, ndigits=5):
    axis = parser.axis_info(surface_id)
    p = axis.get("point") or (0.0, 0.0, 0.0)
    d = _vector_unit(axis.get("direction") or (0.0, 0.0, 0.0)) or (0.0, 0.0, 0.0)
    if tuple(d) < tuple(-x for x in d):
        d = tuple(-x for x in d)
    radius = parser.surfaces.get(surface_id, {}).get("radius") or 0.0
    return (tuple(round(float(x), ndigits) for x in p), tuple(round(float(x), ndigits) for x in d), round(float(radius), ndigits))


def _classify_split_cylindrical_sector_wall(parser, face_id):
    """Classify one split cylindrical-wall patch.

    This is stricter than the broad partial-mouth rule, but more general than the
    old V15.19 half-cylinder rule:
      - the face must be CYLINDRICAL_SURFACE;
      - the face must contain exactly two axial circular section levels;
      - each section level may contain one arc or several arc segments split by
        SEAM_CURVE / repeated seam topology;
      - at least one of the two section levels must be open/partial on this single
        ADVANCED_FACE.  If both are already closed, the ordinary clean-wall rule
        should handle it;
      - all non-circular edges must be axial LINE/SEAM_CURVE connectors between the
        two section levels.

    The physical blind-hole decision is made after grouping several such patches:
    the grouped opening arcs and bottom arcs must form closed full circles.
    """
    if parser.face_surface_type(face_id) != "CYLINDRICAL_SURFACE":
        return {"ok": False, "reason": "not_cylindrical"}
    cyl_surface_id = parser.face_surface_id(face_id)
    radius = parser.surfaces.get(cyl_surface_id, {}).get("radius")
    if radius is None:
        return {"ok": False, "reason": "missing_radius"}
    edges = _unique_edges_in_face(parser, face_id)
    if len(edges) < 4:
        return {"ok": False, "reason": "too_few_edges"}

    circle_infos = []
    connector_edges = []
    bad_edges = []
    for edge_id in edges:
        cinfo = _edge_is_standard_circular_section(parser, cyl_surface_id, edge_id)
        if cinfo is not None:
            circle_infos.append(cinfo)
            continue
        etype = parser.edge_base_curve_type(edge_id)
        if etype in {"LINE", "SEAM_CURVE"}:
            connector_edges.append(edge_id)
        else:
            bad_edges.append((edge_id, etype))
    if bad_edges:
        return {"ok": False, "reason": "bad_edge_types", "bad_edges": bad_edges}

    tol = max(1.0e-5, abs(float(radius)) * 1.0e-2)
    groups = _group_circle_sections(parser, circle_infos, tol=tol)
    if len(groups) != 2:
        return {"ok": False, "reason": "not_two_section_levels", "circle_groups": groups}

    # If this single ADVANCED_FACE already owns two complete circular sections,
    # it is not a split-wall supplement case.  It belongs to the main recognizer.
    if all(g.get("closed") for g in groups):
        return {"ok": False, "reason": "complete_wall_not_split", "circle_groups": groups}

    section_ts = [g["t_mean"] for g in groups]
    accepted_connectors = []
    rejected = []
    for edge_id in connector_edges:
        if _edge_is_axial_connector(parser, cyl_surface_id, edge_id, section_ts=section_ts, tol=tol):
            accepted_connectors.append(edge_id)
        else:
            rejected.append((edge_id, parser.edge_base_curve_type(edge_id)))
    if rejected:
        return {"ok": False, "reason": "non_axial_connectors", "rejected": rejected, "circle_groups": groups}

    # A split sector should have connector/seam evidence.  This avoids promoting
    # isolated circular caps or decorative arcs.
    if len(accepted_connectors) < 1:
        return {"ok": False, "reason": "no_axial_connector"}

    return {
        "ok": True,
        "reason": "split_cylindrical_sector_wall",
        "section_rings": groups,
        "connector_edges": unique_keep_order(accepted_connectors),
    }


def _end_infos_by_edge(parser, recognizer, face_id):
    out = {}
    for e in _build_end_infos_for_cyl_face(parser, recognizer, face_id):
        edges = e.get("edge_curves", [])
        if len(edges) == 1:
            out[edges[0]] = e
    return out


def _section_group_traces_to_external(parser, recognizer, face_id, edges):
    """A section group is an opening only when all usable arc segments go outside."""
    edges = [e for e in edges if e is not None]
    if not edges:
        return False
    ok_count = 0
    for e in edges:
        if _trace_edge_to_external_opening(parser, recognizer, face_id, e):
            ok_count += 1
    return ok_count == len(edges)


def _section_group_internal_cap_planes(parser, recognizer, face_id, edges, by_edge):
    """Return internal PLANE cap faces directly adjacent to every edge in a section group."""
    edges = [e for e in edges if e is not None]
    if not edges:
        return []
    per_edge = []
    for edge_id in edges:
        end = by_edge.get(edge_id)
        if end is None:
            return []
        caps = []
        for f in end.get("adjacent_faces", []):
            if parser.face_surface_type(f) == "PLANE" and not recognizer._looks_external_face(f):
                caps.append(f)
        caps = set(caps)
        if not caps:
            return []
        per_edge.append(caps)
    common = set.intersection(*per_edge) if per_edge else set()
    if common:
        return sorted(common)
    # Sometimes a split bottom is made of several local PLANE pieces.  Allow the
    # union only when every edge has at least one internal cap; the final full-ring
    # closure test is still required.
    union = set()
    for s in per_edge:
        union.update(s)
    return sorted(union)




def _compound_cap_face_is_internal_for_split_wall(parser, recognizer, cyl_face, cap_face, local_cyl_faces=None):
    """Return True when a compound cap face is an internal blind-hole bottom piece.

    This is used only after a split cylindrical wall has already proven that the
    cylinder-side bottom arcs can merge into a full circular section.  The cap is
    accepted when it is a terminating surface adjacent to the bottom ring and its
    local trace does not escape to an external PLANE or into unrelated cylindrical
    channel walls.
    """
    st = parser.face_surface_type(cap_face)
    if st not in SPLIT_WALL_COMPOUND_BOTTOM_SURFACES:
        return False
    local_cyl_faces = set(local_cyl_faces or [])
    local_cyl_faces.add(cyl_face)

    # Walk one step from the compound cap.  A true drill/cone/toroid bottom may
    # touch another compound split face or a small internal plane; it should not
    # touch an external plane or another unrelated CYLINDRICAL_SURFACE passage.
    seen = {cyl_face, cap_face}
    queue = deque((n, 0) for e in parser.face_to_edge_curves.get(cap_face, set()) for n in parser.edge_curve_to_faces.get(e, set()) if n not in {cyl_face, cap_face})
    while queue:
        f, depth = queue.popleft()
        if f in seen:
            continue
        seen.add(f)
        fst = parser.face_surface_type(f)
        if fst == "PLANE" and recognizer._looks_external_face(f):
            return False
        if fst == "CYLINDRICAL_SURFACE" and f not in local_cyl_faces:
            return False
        if depth >= 1:
            continue
        # Continue only through local terminating surfaces, because a split cone
        # bottom may be divided into several conical/toroidal faces by seams.
        if fst in SPLIT_WALL_COMPOUND_BOTTOM_SURFACES:
            for e in parser.face_to_edge_curves.get(f, set()):
                for nf in parser.edge_curve_to_faces.get(e, set()):
                    if nf not in seen:
                        queue.append((nf, depth + 1))
    return True


def _section_group_internal_compound_caps(parser, recognizer, face_id, edges, by_edge):
    """Return compound cap faces directly adjacent to every bottom section arc.

    This is the compound-bottom counterpart of _section_group_internal_cap_planes().
    It supports a bottom that is one cone/toroid/sphere face, or several conical
    faces split by seam lines.  Every bottom arc must have at least one internal
    compound terminating face adjacent to it; otherwise the section is not treated
    as a sealed bottom.
    """
    edges = [e for e in edges if e is not None]
    if not edges:
        return []
    per_edge = []
    for edge_id in edges:
        end = by_edge.get(edge_id)
        if end is None:
            return []
        caps = []
        for f in end.get("adjacent_faces", []):
            if _compound_cap_face_is_internal_for_split_wall(parser, recognizer, face_id, f):
                caps.append(f)
        caps = set(caps)
        if not caps:
            return []
        per_edge.append(caps)
    common = set.intersection(*per_edge) if per_edge else set()
    if common:
        return sorted(common)
    union = set()
    for s in per_edge:
        union.update(s)
    return sorted(union)

def _merge_end_infos_for_edges(recognizer, by_edge, edges, classification):
    ends = [by_edge[e] for e in edges if e in by_edge]
    if not ends:
        return {"edge_curves": list(edges), "adjacent_faces": [], "trace": [], "classification": classification}
    return recognizer._merge_ends(ends, classification=classification)


def _end_has_direct_external_plane(parser, recognizer, end):
    """True when the section ring is directly a hole boundary on an external mother PLANE.

    This is the missing topological guard for same_sense=True split walls.
    A real blind-hole mouth can be exported with same_sense=True, but its opening
    ring still lies on the external mother face as a hole boundary.  An outward
    post/round cap usually reaches the external plane only after TOROIDAL/CONICAL
    transition faces; then the cylinder is an external convex feature, not an
    internal blind-hole wall.
    """
    for f in end.get("adjacent_faces", []):
        if parser.face_surface_type(f) == "PLANE" and recognizer._looks_external_face(f):
            return True
    return False


def _split_group_same_sense_inner_cavity_ok(parser, recognizer, candidates):
    """Reject split-cylinder groups whose wall normals indicate an outward solid.

    V15.23 correction: the previous V15.22 fallback allowed same_sense=True split
    walls when the opening ring touched an external plane.  That still lets solid
    outward posts pass, because a post root also touches the external mother plane
    and has a circular end cap.

    For a closed-shell STEP face, CYLINDRICAL_SURFACE has a natural radial normal
    pointing away from the cylinder axis.  A true blind-hole wall is an inner
    cavity wall, so the solid outward normal is reversed relative to that radial
    direction; in AP214/AP242 text this is normally represented by
    ADVANCED_FACE(..., CYLINDRICAL_SURFACE, .F.).

    Therefore split-wall blind holes must be composed of reversed cylinder faces.
    If any sector has same_sense=True, the grouped object is treated as an
    outward cylinder/post/cap and is not counted as a blind hole.  This uses
    orientation/topology rather than any radius threshold.
    """
    if not candidates:
        return False
    return not any(bool(c.get("same_sense")) for c in candidates)


def _split_wall_candidate(parser, recognizer, surface_id, face_id, existing_faces):
    """A single split cylinder patch; several candidates must merge into one closed wall."""
    if face_id in existing_faces:
        return None
    if parser.face_surface_type(face_id) != "CYLINDRICAL_SURFACE":
        return None
    # V15.23: do not reject every split-wall candidate only by same_sense.
    # In small connector blind holes, OCC may export two half-cylinder wall faces
    # with same_sense=True even though the grouped feature is an internal cavity.
    # Keep the strong convex-filter for larger same_sense cylinders below, after
    # the radius is known.
    same_sense = bool(parser.advanced_faces.get(face_id, {}).get("same_sense"))

    wall = _classify_split_cylindrical_sector_wall(parser, face_id)
    if not wall.get("ok"):
        return None

    radius = parser.surfaces.get(surface_id, {}).get("radius")
    span = parser.cylindrical_face_axial_span(surface_id, face_id)
    if radius is None or span is None:
        return None
    # V15.23: radius is not a blind-hole definition gate.  Small holes are not
    # skipped just because they are small, and large holes are not accepted/rejected
    # by size alone.  Radius is used only for geometric tolerance and the very
    # small non-zero axial-span guard below.
    if span < max(1.0e-5, float(radius) * 0.05):
        return None

    by_edge = _end_infos_by_edge(parser, recognizer, face_id)
    groups = wall.get("section_rings", [])
    if len(groups) != 2:
        return None

    for open_group in groups:
        open_edges = list(open_group.get("edges", []))
        if not _section_group_traces_to_external(parser, recognizer, face_id, open_edges):
            continue
        for bottom_group in groups:
            if bottom_group is open_group:
                continue
            bottom_edges = list(bottom_group.get("edges", []))
            cap_planes = _section_group_internal_cap_planes(parser, recognizer, face_id, bottom_edges, by_edge)
            compound_caps = [] if cap_planes else _section_group_internal_compound_caps(parser, recognizer, face_id, bottom_edges, by_edge)
            if not cap_planes and not compound_caps:
                continue
            axis = parser.axis_info(surface_id)
            bottom_kind = "plane" if cap_planes else "compound"
            return {
                "face": face_id,
                "surface": surface_id,
                "same_sense": same_sense,
                "radius": float(radius),
                "span": span,
                "axis_point": axis.get("point"),
                "axis_direction": axis.get("direction"),
                "axis_sig": _same_axis_radius_signature(parser, surface_id),
                "open_edges": open_edges,
                "bottom_edges": bottom_edges,
                "open_center_key": _circle_center_key_for_edges(parser, open_edges),
                "bottom_center_key": _circle_center_key_for_edges(parser, bottom_edges),
                "bottom_kind": bottom_kind,
                "opening": _merge_end_infos_for_edges(recognizer, by_edge, open_edges, classification="open"),
                "terminal": _merge_end_infos_for_edges(recognizer, by_edge, bottom_edges, classification="terminal"),
                "cap_planes": cap_planes,
                "compound_cap_faces": compound_caps,
                "cap_faces": unique_keep_order(cap_planes + compound_caps),
                "connector_edges": wall.get("connector_edges", []),
                "all_ends": list(by_edge.values()),
            }
    return None


def _split_wall_group_key(c):
    # Do not group by cap face id.  A real cone/toroid bottom can be split into
    # multiple terminating faces, one per cylinder sector.  The physical hole is
    # identified by the common cylinder axis/radius plus the same opening and
    # bottom circular section; bottom_kind prevents mixing plane and compound caps.
    return (c.get("axis_sig"), c.get("open_center_key"), c.get("bottom_center_key"), c.get("bottom_kind"))


def _make_split_wall_hole(parser, recognizer, candidates):
    candidates = sorted(candidates, key=lambda x: x.get("face") or 0)
    # More than 8 can occur when a STEP exporter inserts many seam splits; keep a
    # conservative upper bound to avoid grouping decorative repeated arcs.
    if len(candidates) < 2 or len(candidates) > 16:
        return None
    open_edges = unique_keep_order([e for c in candidates for e in c.get("open_edges", [])])
    bottom_edges = unique_keep_order([e for c in candidates for e in c.get("bottom_edges", [])])
    if len(open_edges) < 2 or len(bottom_edges) < 2:
        return None
    if not _circle_group_is_closed(parser, open_edges):
        return None
    if not _circle_group_is_closed(parser, bottom_edges):
        return None

    cap_planes = unique_keep_order([p for c in candidates for p in c.get("cap_planes", [])])
    compound_caps = unique_keep_order([p for c in candidates for p in c.get("compound_cap_faces", [])])
    cap_faces = unique_keep_order(cap_planes + compound_caps)
    cyl_faces = unique_keep_order([c.get("face") for c in candidates])
    if not cap_faces or not cyl_faces:
        return None

    bottom_kinds = {c.get("bottom_kind") for c in candidates}
    # A single physical split-wall hole should not mix direct plane caps and
    # compound caps in the same grouped section.
    if len(bottom_kinds) != 1:
        return None
    bottom_kind = next(iter(bottom_kinds))

    # V15.22 inner-cavity proof for same_sense=True split walls.  Do not use
    # radius thresholds to decide whether a same_sense wall is allowed.  If a
    # split cylinder looks same_sense=True, it must prove that its opening ring is
    # directly cut into an external mother PLANE.  Otherwise it is usually an
    # outward post/round cap/fillet, not a blind-hole wall.
    if not _split_group_same_sense_inner_cavity_ok(parser, recognizer, candidates):
        return None

    # Compound bottoms should themselves be local internal terminating surfaces.
    # Re-check with the whole cylinder-face group as local wall context, so split
    # conical faces touching neighboring wall sectors are not treated as channels.
    if bottom_kind == "compound":
        for cf in compound_caps:
            if not _compound_cap_face_is_internal_for_split_wall(parser, recognizer, first_face := candidates[0].get("face"), cf, local_cyl_faces=cyl_faces):
                return None

    first = candidates[0]
    opening = recognizer._merge_ends([c["opening"] for c in candidates], classification="open")
    terminal = recognizer._merge_ends([c["terminal"] for c in candidates], classification="terminal")
    hole_type = "多接缝分裂圆柱壁复合底盲孔" if bottom_kind == "compound" else "多接缝分裂圆柱壁平底盲孔"
    reason = (
        "同一孔壁被 STEP 拆成多个半圆柱/扇区圆柱面，且可能带多条 SEAM/LINE 接缝；这些圆柱弧面合并后形成完整圆形开口和完整圆形底部，底部由内部 CONICAL/TOROIDAL/SPHERICAL/B_SPLINE 等复合面封闭。"
        if bottom_kind == "compound"
        else
        "同一孔壁被 STEP 拆成多个半圆柱/扇区圆柱面，且可能带多条 SEAM/LINE 接缝；这些圆柱弧面合并后形成完整圆形开口和完整圆形底部，底部由内部 PLANE 封闭。"
    )
    return {
        "type": hole_type,
        "is_split_cyl_wall_hole": True,
        "is_partial_mouth_sector_hole": True,
        "is_split_compound_bottom_hole": bottom_kind == "compound",
        "cyl_surface": first.get("surface"),
        "cyl_face": first.get("face"),
        "radius": first.get("radius"),
        "axis_point": first.get("axis_point"),
        "axis_direction": first.get("axis_direction"),
        "axial_span": max(c.get("span") or 0.0 for c in candidates),
        "opening": opening,
        "terminal": terminal,
        "partial_cyl_faces": cyl_faces,
        "partial_bottom_faces": cap_faces,
        "partial_plane_bottom_faces": cap_planes,
        "partial_compound_bottom_faces": compound_caps,
        "partial_bottom_edges": bottom_edges,
        "partial_connector_edges": unique_keep_order([e for c in candidates for e in c.get("connector_edges", [])]),
        "all_ends": [e for c in candidates for e in c.get("all_ends", [])],
        "reason": reason,
    }


def find_split_cyl_wall_blind_holes(parser, recognizer, existing_holes):
    existing_faces = {h.get("cyl_face") for h in existing_holes}
    for h in existing_holes:
        for f in h.get("partial_cyl_faces", []) or []:
            existing_faces.add(f)
        for f in h.get("shared_cyl_faces", []) or []:
            existing_faces.add(f)
    candidates = []
    for surface_id, surface in sorted(parser.surfaces.items()):
        if surface.get("type") != "CYLINDRICAL_SURFACE":
            continue
        for face_id in parser.surface_to_faces.get(surface_id, []):
            c = _split_wall_candidate(parser, recognizer, surface_id, face_id, existing_faces)
            if c:
                candidates.append(c)
    by_key = defaultdict(list)
    for c in candidates:
        by_key[_split_wall_group_key(c)].append(c)
    holes = []
    for _, items in by_key.items():
        h = _make_split_wall_hole(parser, recognizer, items)
        if h:
            holes.append(h)
    return sorted(holes, key=lambda h: (h.get("radius") or 0.0, h.get("cyl_face") or 0))


def apply_corrected_v13_postprocess(
    parser,
    recognizer,
    holes,
    shared_plane_selection="inner",
    enable_broad_partial=False,
    enable_variable_depth=False,
):
    filtered, rejected = _filter_false_line_mouth_holes(parser, recognizer, holes)

    # V15-cylinder-first shared rectangular plane supplement:
    # do not rely on the accidental rejected bridge trigger, and do not scan a
    # PLANE first.  Start from clean cylindrical walls and require one circular
    # opening plus one shared rectangular bottom that covers the bottom circle.
    need_shared_scan = bool(rejected) or any(
        h.get("type") in {"相交型平底盲孔", "倒角入口复合底盲孔"}
        for h in filtered
    )
    if need_shared_scan:
        shared_holes, raw_shared_groups = find_shared_multi_ring_plane_holes(
            parser, recognizer, filtered, selection=shared_plane_selection, rejected_line_mouth_holes=rejected
        )
    else:
        shared_holes, raw_shared_groups = [], []

    # v21-no-radius-through-fix:
    # Remove the ESXZB-style double-chamfer slit supplement from the default
    # strict blind-hole definition.  That supplement accepts a short cylinder whose
    # two ends both connect to external planes; topologically this is a through
    # feature, not a blind hole.  Keeping it caused the 06470_11 through holes to
    # be reported as blind holes.
    double_chamfer_holes = []
    # V15.22 收紧：广义截断圆柱/变深截断圆柱规则容易把真实装配件中的
    # 圆端槽、外轮廓圆角、侧向开口槽、贯通口袋误识别为盲孔。
    # 因此默认只保留标准盲孔族：普通平底、倒角入口平底、相交型平底、
    # 倒角入口复合底、普通复合底、共享多圆环平面；切缝双倒角贯通孔不再作为盲孔补充。
    # 如需复现实验数据集的“广义截断圆柱盲孔”标注，可通过命令行开关显式打开。
    # V15.23 strict supplement: recover real blind holes whose cylindrical wall is
    # split into two or more partial CYLINDRICAL_SURFACE faces. Unlike the broad
    # partial rule, partial arcs must merge into a complete circular mouth and a
    # complete circular bottom; isolated arcs/slots remain excluded.
    split_cyl_wall_holes = find_split_cyl_wall_blind_holes(parser, recognizer, filtered + shared_holes + double_chamfer_holes)

    base_holes = filtered + shared_holes + double_chamfer_holes + split_cyl_wall_holes
    partial_mouth_holes = []
    if enable_broad_partial and not base_holes:
        partial_mouth_holes = find_partial_mouth_sector_blind_holes(parser, recognizer, base_holes)
    if enable_variable_depth and not base_holes:
        partial_mouth_holes += find_variable_depth_truncated_blind_holes(parser, recognizer, partial_mouth_holes)
    return base_holes + partial_mouth_holes, rejected, raw_shared_groups



def _partial_bottom_outer_bound_specs(parser, bottom_faces):
    """Build synthetic FACE_OUTER_BOUND caps for broad partial-mouth blind-hole bottoms.

    In several dataset STEP exports, the bottom of a broad truncated-cylinder blind
    hole is represented as a local PLANE whose only loop is stored as FACE_BOUND
    instead of FACE_OUTER_BOUND.  When that face is copied alone into an OPEN_SHELL,
    some CAD viewers treat it as a hole/inner loop and the cap is not highlighted,
    so the export looks as if only the cylindrical wall was selected.

    For visualization we reuse the original EDGE_LOOP and PLANE geometry but create
    a new FACE_OUTER_BOUND + ADVANCED_FACE.  This keeps the exact sector/crescent
    bottom outline instead of replacing it by a full disk, while making the cap
    visible as a filled face in the exported blind-hole STP.
    """
    specs = []
    seen = set()
    for face_id in unique_keep_order(bottom_faces or []):
        if face_id is None or parser.face_surface_type(face_id) != "PLANE":
            continue
        bounds = parser.advanced_faces.get(face_id, {}).get("bounds", [])
        if not bounds:
            continue
        # Prefer the largest loop if several are present, but broad partial caps
        # normally have exactly one local loop.
        best = None
        best_count = -1
        for bound_id in bounds:
            loop_id = parser.face_bounds.get(bound_id, {}).get("loop")
            if loop_id is None:
                continue
            count = len(parser.edge_loops.get(loop_id, []))
            if count > best_count:
                best = (bound_id, loop_id)
                best_count = count
        if best is None:
            continue
        source_bound, loop_id = best
        surface_id = parser.face_surface_id(face_id)
        if surface_id is None:
            continue
        same_sense = bool(parser.advanced_faces.get(face_id, {}).get("same_sense"))
        key = (face_id, loop_id, surface_id)
        if key in seen:
            continue
        seen.add(key)
        specs.append({
            "source_plane_face": face_id,
            "source_bound": source_bound,
            "loop": loop_id,
            "surface": surface_id,
            "same_sense": same_sense,
        })
    return specs

def select_exact_faces_from_holes(parser, recognizer, holes, include_chamfer=True):
    """选择用于可视化导出的原始盲孔面。

    识别逻辑仍使用 V13；这里增加一个共享平面相交盲孔的后处理：
    如果 V13 选中的圆柱面只是一个较小的相交桥接面，而同一个共享底面
    还连接着更大的、带外部圆形孔口的圆柱壁面，则导出这些真实孔壁面，
    而不是导出桥接面。
    """
    compound_bottom_types = {
        "CONICAL_SURFACE",
        "TOROIDAL_SURFACE",
        "SPHERICAL_SURFACE",
        "BSPLINE_SURFACE_WITH_KNOTS",
        "B_SPLINE_SURFACE_WITH_KNOTS",
    }

    selected = []
    per_hole = []
    for i, hole in enumerate(holes, 1):
        hole_type = hole.get("type")
        is_compound_hole = hole_type in {"倒角入口复合底盲孔", "普通复合底盲孔"}

        group = {
            "index": i,
            "type": hole_type,
            "cyl_face": hole.get("cyl_face"),
            "cyl_surface": hole.get("cyl_surface"),
            "radius": hole.get("radius"),
            "axis_point": hole.get("axis_point"),
            "axis_direction": hole.get("axis_direction"),
            "axial_span": hole.get("axial_span"),
            "bottom_faces": [],
            "compound_bottom_faces": [],
            "chamfer_faces": [],
            "replacement_cyl_faces": [],
            "skipped_shared_plane_faces": [],
            "dropped_unsealed_cyl_faces": [],
            "candidate_cyl_faces_before_seal_filter": [],
            "local_bottom_disk_specs": [],
            "export_faces": [],
            "cyl_face_loop_counts": parser.face_loop_curve_counts(hole.get("cyl_face")),
        }

        if hole.get("is_double_chamfer_slit_hole"):
            chamfers = unique_keep_order(hole.get("double_chamfer_faces", []))
            group["chamfer_faces"] = chamfers
            group["export_faces"] = unique_keep_order([hole.get("cyl_face")] + chamfers)
            group["double_chamfer_external_planes"] = unique_keep_order(hole.get("double_chamfer_external_planes", []))
            selected.extend(group["export_faces"])
            per_hole.append(group)
            continue

        if hole.get("is_partial_mouth_sector_hole"):
            partial_cyl_faces = unique_keep_order(hole.get("partial_cyl_faces", []) or [hole.get("cyl_face")])
            partial_bottom_faces = unique_keep_order(hole.get("partial_bottom_faces", []) or [hole.get("partial_bottom_face")])
            group["replacement_cyl_faces"] = partial_cyl_faces
            group["bottom_faces"] = partial_bottom_faces
            group["partial_bottom_edge"] = hole.get("partial_bottom_edge")
            group["partial_bottom_edges"] = unique_keep_order(hole.get("partial_bottom_edges", []))
            group["partial_connector_edges"] = unique_keep_order(hole.get("partial_connector_edges", []))
            group["partial_bottom_outer_bound_specs"] = _partial_bottom_outer_bound_specs(parser, partial_bottom_faces)
            # V15.11/V21-no-radius-through-fix：广义截断/变深截断圆柱盲孔不能只把圆柱壁当作“识别面”。
            # 这类数据集标注中的盲孔实例由“不完整圆柱壁 + 局部底面”共同组成，
            # 例如 20221121_154647_90 的 seg=12 源面应完整包含
            # 3 个 CYLINDRICAL_SURFACE 和 2 个 PLANE 底面。
            # 因此 source/export face list 直接包含原始底面 ADVANCED_FACE。
            # 同时仍保留 synthetic FACE_OUTER_BOUND cap，用来解决 FACE_BOUND-only
            # 底面单独导出时 CAD 不填充/不高亮的问题。
            # V15.22：分裂圆柱壁也可能是倒角/圆角入口盲孔。
            # 此分支原来只导出圆柱壁和底面，导致小型倒角孔的入口过渡面没有被选中。
            if include_chamfer:
                for item in hole.get("opening", {}).get("trace", []):
                    face_id = item.get("face")
                    if item.get("surface_type") in ENTRY_TRANSITION_SURFACES:
                        group["chamfer_faces"].append(face_id)
            group["chamfer_faces"] = unique_keep_order(group["chamfer_faces"])
            group["source_faces"] = unique_keep_order(partial_cyl_faces + partial_bottom_faces + group["chamfer_faces"])
            group["export_faces"] = group["source_faces"]
            selected.extend(group["export_faces"])
            per_hole.append(group)
            continue

        if hole.get("is_shared_multi_ring_plane_hole"):
            group["replacement_cyl_faces"] = unique_keep_order(hole.get("shared_cyl_faces", []))
            group["bottom_faces"] = unique_keep_order(hole.get("shared_bottom_faces", []))
            group["dropped_unsealed_cyl_faces"] = unique_keep_order(hole.get("dropped_unsealed_cyl_faces", []))
            group["candidate_cyl_faces_before_seal_filter"] = unique_keep_order(hole.get("candidate_cyl_faces_before_seal_filter", []))
            group["local_bottom_disk_specs"] = _local_shared_bottom_disk_specs(
                parser, group["replacement_cyl_faces"], group["bottom_faces"]
            )
            # 共享平面型盲孔不再把原始大 PLANE 整面导出；只导出原始圆柱壁，
            # 底面由 exporter 根据 local_bottom_disk_specs 生成同圆心/同半径的小圆面。
            group["export_faces"] = unique_keep_order(group["replacement_cyl_faces"])
            selected.extend(group["export_faces"])
            per_hole.append(group)
            continue

        cyl_face = hole.get("cyl_face")
        if cyl_face is not None:
            group["export_faces"].append(cyl_face)

        for item in hole.get("terminal", {}).get("trace", []):
            face_id = item.get("face")
            surf_type = item.get("surface_type")
            if face_id is None:
                continue

            if surf_type == "PLANE" and not is_external_plane(recognizer, face_id):
                if _is_local_circular_plane_bottom_for_export(parser, recognizer, hole, face_id):
                    group["bottom_faces"].append(face_id)
                    group["export_faces"].append(face_id)
                else:
                    group["skipped_shared_plane_faces"].append(face_id)
                    # v15 修正：复杂共享底面不整面导出，若与孔壁共享圆边，
                    # 生成同圆心/同半径的局部圆形底面用于可视化。
                    spec = _local_bottom_disk_spec_from_shared_complex_plane(parser, hole.get("cyl_face"), face_id)
                    if spec is not None:
                        group.setdefault("local_bottom_disk_specs", []).append(spec)

            if is_compound_hole and surf_type in compound_bottom_types:
                if face_id != cyl_face:
                    group["compound_bottom_faces"].append(face_id)
                    group["export_faces"].append(face_id)

        # 关键修复：共享平面相交盲孔中，V13 有时选到的是“相交桥接面”，
        # 不是用户在 CAD 里看到的盲孔圆柱壁。此时用同一底面上更大的、
        # 具有外部圆形孔口的圆柱壁面替换它。
        replacements = _replacement_cyl_faces_for_shared_bottom(parser, recognizer, hole, group["bottom_faces"])
        if replacements:
            group["replacement_cyl_faces"] = replacements
            if cyl_face in group["export_faces"]:
                group["export_faces"] = [f for f in group["export_faces"] if f != cyl_face]
            for f in replacements:
                group["export_faces"].insert(0, f)

        if include_chamfer:
            for item in hole.get("opening", {}).get("trace", []):
                face_id = item.get("face")
                if item.get("surface_type") in ENTRY_TRANSITION_SURFACES:
                    group["chamfer_faces"].append(face_id)
                    group["export_faces"].append(face_id)

        group["bottom_faces"] = unique_keep_order(group["bottom_faces"])
        group["compound_bottom_faces"] = unique_keep_order(group["compound_bottom_faces"])
        group["chamfer_faces"] = unique_keep_order(group["chamfer_faces"])
        group["replacement_cyl_faces"] = unique_keep_order(group["replacement_cyl_faces"])
        group["skipped_shared_plane_faces"] = unique_keep_order(group["skipped_shared_plane_faces"])
        group["export_faces"] = unique_keep_order(group["export_faces"])
        selected.extend(group["export_faces"])
        per_hole.append(group)

    return unique_keep_order(selected), per_hole

class ExactFaceStepExporter:
    """把原始 ADVANCED_FACE 原样导出为 OPEN_SHELL 可视化文件。

    这个版本不再人工创建圆柱面/圆边界，因此不会出现“两个圆重合但圆柱壁丢失”的问题。
    圆柱壁直接使用原文件中的 ADVANCED_FACE，例如：
        #97 = ADVANCED_FACE('', (#260,#261), #262, .F.);
    它内部的两个 FACE_OUTER_BOUND、EDGE_LOOP、ORIENTED_EDGE、EDGE_CURVE、CIRCLE 等依赖都会递归保留。
    """

    def __init__(self, input_path, source_parser=None):
        self.input_path = input_path
        # 装配体 STEP 可能非常大，且有些文件末尾缺少标准 ENDSEC/END-ISO。
        # 若识别阶段已经有 StepParser 实体表，这里直接复用，避免二次解析失败或耗时过长。
        # 这只影响导出稳定性，不改变盲孔识别逻辑。
        if source_parser is not None and getattr(source_parser, "entities", None):
            self.text = ""
            self.data = ""
            self.records = {}
            self.order = []
            for eid, ent in source_parser.entities.items():
                raw = ent.get("raw", "").strip()
                if not raw:
                    continue
                self.records[eid] = {
                    "id": eid,
                    "type": ent.get("type", "UNKNOWN"),
                    "raw": raw,
                    "refs": [int(x) for x in re.findall(r"#(\d+)", raw)],
                }
                self.order.append(eid)
        else:
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

    def _norm(self, xyz):
        return sum(float(v) * float(v) for v in xyz) ** 0.5

    def _unit(self, xyz):
        n = self._norm(xyz)
        if n <= 1.0e-12:
            return (0.0, 0.0, 1.0)
        return tuple(float(v) / n for v in xyz)

    def _dot(self, a, b):
        return sum(float(a[i]) * float(b[i]) for i in range(3))

    def _mul(self, a, s):
        return tuple(float(v) * float(s) for v in a)

    def _sub(self, a, b):
        return tuple(float(a[i]) - float(b[i]) for i in range(3))

    def _add(self, a, b):
        return tuple(float(a[i]) + float(b[i]) for i in range(3))

    def _orthogonal_ref_direction(self, normal, preferred=None):
        normal = self._unit(normal)
        candidates = []
        if preferred is not None:
            candidates.append(preferred)
        candidates.extend([(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)])
        for c in candidates:
            lateral = self._sub(c, self._mul(normal, self._dot(c, normal)))
            if self._norm(lateral) > 1.0e-8:
                return self._unit(lateral)
        return (1.0, 0.0, 0.0)

    def axis2_placement_3d(self, point_xyz, normal, ref_direction=None):
        normal = self._unit(normal)
        ref_direction = self._orthogonal_ref_direction(normal, ref_direction)
        p = self.point(point_xyz)
        d = self.direction(normal)
        r = self.direction(ref_direction)
        return self.add(f"AXIS2_PLACEMENT_3D( '', #{p}, #{d}, #{r} )")

    def vertex_point(self, xyz):
        p = self.point(xyz)
        return self.add(f"VERTEX_POINT( '', #{p} )")

    def make_local_circular_plane_face(self, spec):
        center = tuple(spec["center"])
        radius = float(spec["radius"])
        normal = self._unit(spec.get("normal") or (0.0, 0.0, 1.0))
        ref_dir = self._orthogonal_ref_direction(normal, spec.get("ref_direction"))
        start = self._add(center, self._mul(ref_dir, radius))

        v = self.vertex_point(start)
        circle_axis = self.axis2_placement_3d(center, normal, ref_dir)
        circle = self.add(f"CIRCLE( '', #{circle_axis}, {self._num(radius)} )")
        edge = self.add(f"EDGE_CURVE( '', #{v}, #{v}, #{circle}, .T. )")
        oriented = self.add(f"ORIENTED_EDGE( '', *, *, #{edge}, .T. )")
        loop = self.add(f"EDGE_LOOP( '', ( #{oriented} ) )")
        bound = self.add(f"FACE_OUTER_BOUND( '', #{loop}, .T. )")
        plane_axis = self.axis2_placement_3d(center, normal, ref_dir)
        plane = self.add(f"PLANE( '', #{plane_axis} )")
        face = self.add(f"ADVANCED_FACE( 'local_shared_bottom_disk', ( #{bound} ), #{plane}, .F. )")
        return face


    def make_outer_bound_copy_face(self, spec):
        """Create a visible cap face by wrapping an existing EDGE_LOOP as FACE_OUTER_BOUND."""
        loop_id = int(spec["loop"])
        surface_id = int(spec["surface"])
        same_sense = ".T." if spec.get("same_sense") else ".F."
        source_face = spec.get("source_plane_face")
        bound = self.add(f"FACE_OUTER_BOUND( 'partial_bottom_outer_bound', #{loop_id}, .T. )")
        face = self.add(f"ADVANCED_FACE( 'partial_bottom_cap_from_{source_face}', ( #{bound} ), #{surface_id}, {same_sense} )")
        return face

    def export(self, selected_faces, output_path, label="blind_holes_exact_faces_v21_no_radius_through_fix", local_bottom_disk_specs=None, partial_bottom_outer_bound_specs=None, dependency_face_seeds=None):
        selected_faces = unique_keep_order(selected_faces)
        missing = [f for f in selected_faces if f not in self.records]
        if missing:
            raise RuntimeError(f"选择的 ADVANCED_FACE 在原 STEP 中不存在：{missing}")

        local_bottom_disk_specs = list(local_bottom_disk_specs or [])
        partial_bottom_outer_bound_specs = list(partial_bottom_outer_bound_specs or [])
        dependency_face_seeds = list(dependency_face_seeds or [])

        local_bottom_face_ids = [self.make_local_circular_plane_face(spec) for spec in local_bottom_disk_specs]
        partial_bottom_face_ids = [self.make_outer_bound_copy_face(spec) for spec in partial_bottom_outer_bound_specs]
        shell_faces = unique_keep_order(selected_faces + local_bottom_face_ids + partial_bottom_face_ids)

        partial_source_faces = [spec.get("source_plane_face") for spec in partial_bottom_outer_bound_specs if spec.get("source_plane_face") is not None]
        dependency_seeds = unique_keep_order(selected_faces + dependency_face_seeds + partial_source_faces)
        keep = dependency_closure(self.records, dependency_seeds)
        kept_records = [self.records[eid]["raw"] for eid in self.order if eid in keep]

        face_refs = format_ref_list(shell_faces, per_line=10, indent="      ")
        shell = self.add(f"OPEN_SHELL( 'blind_hole_faces', ( {face_refs} ) )")
        model = self.add(f"SHELL_BASED_SURFACE_MODEL( '{label}', ( #{shell} ) )")
        origin = self.point((0.0, 0.0, 0.0))
        zdir = self.direction((0.0, 0.0, 1.0))
        xdir = self.direction((1.0, 0.0, 0.0))
        place = self.add(f"AXIS2_PLACEMENT_3D( '', #{origin}, #{zdir}, #{xdir} )")
        length_unit = self.add("( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) )")
        angle_unit = self.add("( NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.) )")
        solid_angle_unit = self.add("( NAMED_UNIT(*) SI_UNIT($,.STERADIAN.) SOLID_ANGLE_UNIT() )")
        uncertainty = self.add(f"UNCERTAINTY_MEASURE_WITH_UNIT( LENGTH_MEASURE(1.0E-07), #{length_unit}, 'distance_accuracy_value', 'confusion accuracy' )")
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
FILE_DESCRIPTION( ( 'V21 no-radius through-hole-fix blind-hole face export' ), '2;1' );
FILE_NAME( '{filename}', '{now}', ( 'blind-hole-export-v21-no-radius-through-fix' ), ( 'ChatGPT generated script' ), ' ', 'exact-face-v21-no-radius-through-fix-exporter', ' ' );
FILE_SCHEMA( ( 'AUTOMOTIVE_DESIGN' ) );
ENDSEC;
DATA;
"""
        body = "\n".join(kept_records + self.new_records)
        out = header + body + "\nENDSEC;\nEND-ISO-10303-21;\n"
        os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(out)
        return {
            "selected_faces": selected_faces,
            "local_bottom_face_ids": local_bottom_face_ids,
            "partial_bottom_face_ids": partial_bottom_face_ids,
            "shell_faces": shell_faces,
            "dependency_entity_count": len(kept_records),
            "wrapper_entity_count": len(self.new_records),
            "total_entity_count": len(kept_records) + len(self.new_records),
            "open_shell_id": shell,
            "surface_model_id": model,
        }


def count_selected_face_types(parser, selected_faces):
    counter = Counter()
    for f in selected_faces:
        counter[parser.face_surface_type(f)] += 1
    return counter


def build_exact_report(input_path, output_path, holes, selected_faces, per_hole, face_counter, export_info, elapsed_ms):
    lines = []
    lines.append("V21-no-radius-through-fix 标准盲孔贯通孔收紧版 STP 报告")
    lines.append(f"输入文件：{input_path}")
    lines.append(f"输出文件：{output_path}")
    lines.append(f"处理时间：{elapsed_ms:.3f} ms")
    lines.append("")
    lines.append(f"识别盲孔数量：{len(holes)}")
    lines.append(f"识别源 ADVANCED_FACE 数量：{len(selected_faces)}")
    lines.append("导出方式：标准盲孔使用原始 STEP 的圆柱壁和底面 ADVANCED_FACE；广义截断圆柱盲孔的源面同时包含不完整圆柱壁和原始底面 PLANE，并额外生成 FACE_OUTER_BOUND 底面副本用于可视化填充；共享平面型盲孔仍用局部圆形底面替代整块大平面。")
    lines.append("导出文件类型：OPEN_SHELL + SHELL_BASED_SURFACE_MODEL，用于盲孔面集可视化。")
    lines.append(f"面类型统计：{dict(face_counter)}")
    lines.append(f"写出实体数量：{export_info['total_entity_count']}，其中原始依赖实体 {export_info['dependency_entity_count']}，包装实体 {export_info['wrapper_entity_count']}")
    lines.append("")
    for g in per_hole:
        lines.append(f"盲孔 #{g['index']}：{g['type']}")
        lines.append(f"  圆柱壁面：ADVANCED_FACE #{g['cyl_face']} / CYLINDRICAL_SURFACE #{g['cyl_surface']} / 半径 {g['radius']}")
        lines.append(f"  圆柱壁原始边界环曲线数：{g['cyl_face_loop_counts']}")
        lines.append(f"  共享底面候选圆柱壁：{', '.join('#' + str(x) for x in g.get('candidate_cyl_faces_before_seal_filter', [])) or '-'}")
        lines.append(f"  共享底面保留圆柱壁：{', '.join('#' + str(x) for x in g.get('replacement_cyl_faces', [])) or '-'}")
        lines.append(f"  共享底面排除的非密封圆柱壁：{', '.join('#' + str(x) for x in g.get('dropped_unsealed_cyl_faces', [])) or '-'}")
        lines.append(f"  原始底面 PLANE：{', '.join('#' + str(x) for x in g['bottom_faces']) or '-'}")
        local_specs = g.get('local_bottom_disk_specs', [])
        if local_specs:
            desc = []
            for spec in local_specs:
                desc.append(f"源共享平面 #{spec.get('source_shared_plane_face')} / 圆边 #{spec.get('source_circle_edge')} / 圆心 {spec.get('center')} / 半径 {spec.get('radius')}")
            lines.append(f"  局部重建底面：{'；'.join(desc)}")
        else:
            lines.append("  局部重建底面：-")
        partial_caps = g.get('partial_bottom_outer_bound_specs', [])
        if partial_caps:
            desc = []
            for spec in partial_caps:
                desc.append(f"源底面 #{spec.get('source_plane_face')} / EDGE_LOOP #{spec.get('loop')} / PLANE #{spec.get('surface')}")
            lines.append(f"  广义截断底面外边界重建：{'；'.join(desc)}")
        else:
            lines.append("  广义截断底面外边界重建：-")
        lines.append(f"  复合底面：{', '.join('#' + str(x) for x in g.get('compound_bottom_faces', [])) or '-'}")
        lines.append(f"  入口倒角面：{', '.join('#' + str(x) for x in g['chamfer_faces']) or '-'}")
        lines.append(f"  跳过共享/非圆底平面：{', '.join('#' + str(x) for x in g.get('skipped_shared_plane_faces', [])) or '-'}")
        lines.append(f"  识别源面：{', '.join('#' + str(x) for x in g.get('source_faces', g['export_faces']))}")
        lines.append(f"  导出源面：{', '.join('#' + str(x) for x in g['export_faces'])}")
        lines.append(f"  孔轴点：{g['axis_point']}，孔轴方向：{g['axis_direction']}，轴向跨度：{g['axial_span']}")
        lines.append("")
    return "\n".join(lines)



def parse_args():
    ap = argparse.ArgumentParser(description="集成 V21-no-radius-through-fix 标准盲孔收紧识别，并导出原始盲孔源面集 STP。")
    ap.add_argument("input", nargs="?", default=INPUT_STP_PATH or None, help="原始 STP/STEP 文件路径")
    ap.add_argument("-o", "--output", default=OUTPUT_STP_PATH or None, help="输出 STP 路径；默认输出到输入文件同目录")
    ap.add_argument("--log", default=OUTPUT_LOG_PATH or None, help="输出日志路径；默认输出到输入文件同目录")
    ap.add_argument("--output-dir", default=OUTPUT_STP_DIR or None, help="输出目录；未指定 -o 时生效")
    ap.add_argument("--include-chamfer", action="store_true", default=True, help="导出入口倒角面，默认开启")
    ap.add_argument("--no-chamfer", action="store_true", help="不导出入口倒角面")
    ap.add_argument(
        "--shared-plane-selection",
        choices=["inner", "outer", "all"],
        default="inner",
        help="共享多圆环结构的选择策略：inner=较小半径内侧组；outer=较大半径外侧组；all=全部导出。",
    )
    ap.add_argument("--min-radius", type=float, default=0.0, help="兼容旧命令行参数；当前版本不再按盲孔半径大小过滤候选。")
    ap.add_argument("--min-depth-ratio", type=float, default=1.2)
    ap.add_argument("--min-depth-abs", type=float, default=2.0)
    ap.add_argument("--max-complex-span-ratio", type=float, default=20.0)
    ap.add_argument("--max-intersection-trace-faces", type=int, default=14)
    ap.add_argument("--max-simple-bottom-curves", type=int, default=4)
    ap.add_argument("--allow-non-circular-mouth", action="store_true")
    ap.add_argument("--disable-shared-plane-bottom-exception", action="store_true")
    ap.add_argument(
        "--enable-broad-partial",
        action="store_true",
        help="默认关闭。显式打开数据集口径的广义截断圆柱盲孔识别，可能误检圆端槽/口袋/外轮廓圆角。",
    )
    ap.add_argument(
        "--enable-variable-depth-partial",
        action="store_true",
        help="默认关闭。显式打开变深截断圆柱盲孔识别，通常只用于复现实验数据集标注。",
    )
    args = ap.parse_args()
    if not args.input:
        ap.error("请传入 STP/STEP 文件路径，或在脚本顶部填写 INPUT_STP_PATH")
    return args

def main():
    args = parse_args()
    input_path = os.path.abspath(args.input)
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"输入 STP/STEP 文件不存在：{input_path}")

    stem = os.path.splitext(os.path.basename(input_path))[0]
    base_dir = args.output_dir or EXPORT_STP_DIR or os.path.dirname(input_path) or "."
    output_path = os.path.abspath(args.output) if args.output else os.path.join(base_dir, f"{stem}_blind_holes_exact_faces_v21_no_radius_through_fix.stp")
    log_base_dir = OUTPUT_LOG_DIR or EXPORT_LOG_DIR or os.path.dirname(output_path) or "."
    log_path = os.path.abspath(args.log) if args.log else os.path.join(log_base_dir, f"{stem}_blind_holes_exact_faces_v21_no_radius_through_fix_log.txt")

    start = time.perf_counter()
    step = StepParser(input_path)
    step.parse()
    recognizer = BlindHoleRecognizer(
        step,
        min_radius=args.min_radius,
        min_depth_ratio=args.min_depth_ratio,
        min_depth_abs=args.min_depth_abs,
        max_complex_span_ratio=args.max_complex_span_ratio,
        max_intersection_trace_faces=args.max_intersection_trace_faces,
        max_simple_bottom_curves=args.max_simple_bottom_curves,
        require_circular_mouth=not args.allow_non_circular_mouth,
        allow_shared_plane_bottom_mouth_exception=not args.disable_shared_plane_bottom_exception,
    )
    raw_holes = recognizer.recognize()
    holes, rejected_line_mouth_holes, raw_shared_groups = apply_corrected_v13_postprocess(
        step,
        recognizer,
        raw_holes,
        shared_plane_selection=args.shared_plane_selection,
        enable_broad_partial=args.enable_broad_partial,
        enable_variable_depth=args.enable_variable_depth_partial,
    )
    if not holes:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        os.makedirs(os.path.dirname(os.path.abspath(log_path)) or ".", exist_ok=True)
        report = "\n".join([
            "V21-no-radius-through-fix 标准盲孔贯通孔收紧版 STP 报告",
            f"输入文件：{input_path}",
            f"输出文件：未生成，原因：未识别到标准盲孔",
            f"处理时间：{elapsed_ms:.3f} ms",
            "",
            f"原始 V13 候选数量：{len(raw_holes)}",
            f"标准盲孔识别数量：0",
            f"广义截断圆柱规则：{'开启' if args.enable_broad_partial else '关闭'}",
            f"变深截断圆柱规则：{'开启' if args.enable_variable_depth_partial else '关闭'}",
            "说明：默认关闭广义截断/变深截断规则，以避免把圆端槽、口袋、外轮廓圆角或贯通结构误识别为标准盲孔。",
        ])
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(report)
        print(f"日志已保存：{log_path}")
        return 0

    selected_faces, per_hole = select_exact_faces_from_holes(step, recognizer, holes, include_chamfer=not args.no_chamfer)
    local_bottom_disk_specs = []
    partial_bottom_outer_bound_specs = []
    dependency_face_seeds = []
    for g in per_hole:
        local_bottom_disk_specs.extend(g.get("local_bottom_disk_specs", []))
        partial_bottom_outer_bound_specs.extend(g.get("partial_bottom_outer_bound_specs", []))
        dependency_face_seeds.extend(g.get("bottom_faces", []))
    exporter = ExactFaceStepExporter(input_path, source_parser=step)
    export_info = exporter.export(
        selected_faces,
        output_path,
        local_bottom_disk_specs=local_bottom_disk_specs,
        partial_bottom_outer_bound_specs=partial_bottom_outer_bound_specs,
        dependency_face_seeds=dependency_face_seeds,
    )
    face_counter = count_selected_face_types(step, selected_faces)
    if local_bottom_disk_specs:
        face_counter["LOCAL_SHARED_BOTTOM_PLANE"] += len(local_bottom_disk_specs)
    if partial_bottom_outer_bound_specs:
        face_counter["LOCAL_PARTIAL_BOTTOM_CAP"] += len(partial_bottom_outer_bound_specs)
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    report = build_exact_report(input_path, output_path, holes, selected_faces, per_hole, face_counter, export_info, elapsed_ms)
    diag_lines = []
    diag_lines.append("\nV21-no-radius-through-fix 标准盲孔贯通孔收紧版诊断：")
    diag_lines.append(f"  原始 V13 候选数量：{len(raw_holes)}")
    diag_lines.append(f"  因非完整圆形孔口被排除的候选数量：{len(rejected_line_mouth_holes)}")
    for r in rejected_line_mouth_holes:
        diag_lines.append(f"    排除 #{r['cyl_face']} / #{r['cyl_surface']}：{r['reason']}；开口边类型={r['opening_edge_types']}；边界环={r['loop_counts']}")
    diag_lines.append(f"  共享多圆环平面选择策略：{args.shared_plane_selection}")
    diag_lines.append(f"  扫描到的共享多圆环平面候选组数量：{len(raw_shared_groups)}")
    diag_lines.append("  多片/多SEAM圆柱壁：不再使用半径硬阈值；same_sense=True 依靠直接外部母面孔口证明内凹。")
    for g in raw_shared_groups:
        diag_lines.append(
            f"    共享平面 #{g['plane_face']}：候选圆柱壁={', '.join('#'+str(x) for x in g.get('candidate_cyl_faces_before_seal_filter', g['cyl_faces']))}，"
            f"保留={', '.join('#'+str(x) for x in g['cyl_faces'])}，"
            f"排除非密封={', '.join('#'+str(x) for x in g.get('dropped_unsealed_cyl_faces', [])) or '-'}，"
            f"平均半径={g['avg_radius']:.6g}，圆环数={g['circle_count']}"
        )
    report = report + "\n" + "\n".join(diag_lines)
    os.makedirs(os.path.dirname(os.path.abspath(log_path)) or ".", exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(report)
    print(f"STP 已导出：{output_path}")
    print(f"日志已保存：{log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
