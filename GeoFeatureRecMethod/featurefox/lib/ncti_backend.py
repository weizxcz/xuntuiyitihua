#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""NCTI 数据后端 —— featurefox-NCTI 版的核心。

封装一个零件的 NCTI AiModel 数据视图，提供面邻接图、边凸凹性/类型/长度、
面几何查询（法向/重心/面积/类型/周长）。cell_id = ai.FaceID 位置索引(0..n-1)，
与 Geo-Rec 训练标签 cell_id 严格同空间（零映射）。

与 featurefox(STEP版) 的关系：
  - STEP 版用 StepParser 解析 STEP 文本，凸凹性靠质心偏移法反推；
  - NCTI 版直接用 NCTI EdgeAttr[0/1/2] 给的凸凹性（更准），面积取 FaceAttr[5]，
    边长取 EdgeAttr[3]，免 STEP→cell 映射（输出即 cell_id）。

复用：
  - NCTI 导入序列（约定A）与 ncti_faceid_map.import_step_to_ncti 一致；
  - 几何查询（GetNormalByUV/GetFacePointFromUV at 0.5,0.5）与
    detect_through_step_ncti._get_face_normal/_get_face_centroid 一致。

NCTI AiModel 数据布局（见 through_step/CLAUDE.md）：
  ai.FaceAttr[i]  # [0]=is_plane [1]=is_cylindrical [5]=face_area
  ai.EdgeAttr[i]  # [0]=concave [1]=convex [2]=smooth [3]=edge_length [4]=circular [9]=line
  ai.FaceEID/FaceFID  # 边的到/从 面位置索引
  ai.FaceID           # 面 ID 列表，len = 面数 n
"""

import re
from collections import defaultdict


def count_advanced_faces(stp_path):
    """从 STEP 文本统计 ADVANCED_FACE 数。

    用于面数断言：验证「shell ADVANCED_FACE 顺序 == ai.FaceID 位置索引」假设。
    OCC 合成数据 NCTI 不合并面，二者应相等；不等则该件 cell_id 可能错位，需跳过。
    """
    try:
        with open(stp_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return len(re.findall(r"ADVANCED_FACE\s*\(", content))
    except Exception:
        return None


class NctiPart:
    """一个零件的 NCTI 数据视图。

    cell_id = ai.FaceID 位置索引(0..n-1)，与 Geo-Rec 训练标签 cell_id 严格同空间。
    所有边表按 (min_cell, max_cell) 聚合（同一对面可能有多条共享边）。
    """

    def __init__(self, ncti, doc, obj_name):
        self.ncti = ncti
        self.doc = doc
        self.obj_name = obj_name

        ai = ncti.AiModel(doc, obj_name)
        self.n_faces = len(ai.FaceID)
        self.face_attrs = ai.FaceAttr       # list[list[float]]，按位置索引
        self.edge_attrs = ai.EdgeAttr       # list[list[float]]
        self.face_eids = ai.FaceEID         # list[int]，边的"到"面位置索引
        self.face_fids = ai.FaceFID         # list[int]，边的"从"面位置索引

        # 衍生表
        self.adjacency = defaultdict(set)            # cell_id -> set(cell_id)
        self.edge_convexity = {}                     # (min,max) -> concave/convex/smooth
        self.edge_dihedral = {}                      # (min,max) -> sign(+凹/-凸，与STEP版对齐)
        self.edge_type = {}                          # (min,max) -> line/circle/other
        self.edge_length_map = {}                    # (min,max) -> float(EdgeAttr[3]累加)

        self._build_edge_tables()

    def _build_edge_tables(self):
        """从 FaceEID/FaceFID/EdgeAttr 建邻接 + 4 张边表。

        同一对面可能有多条共享边（聚合规则）：
          - 凸凹性取首个非 smooth（凹/凸优先于光滑）；
          - 长度累加；
          - 类型取众数。
        """
        agg = defaultdict(lambda: {"conv": None, "len": 0.0,
                                    "line": 0, "circle": 0, "other": 0})
        n_e = min(len(self.face_eids), len(self.face_fids))
        for i in range(n_e):
            fa = self.face_eids[i]
            fb = self.face_fids[i]
            if fa is None or fb is None:
                continue
            # 邻接（双向）
            self.adjacency[fa].add(fb)
            self.adjacency[fb].add(fa)
            key = (min(fa, fb), max(fa, fb))
            ea = self.edge_attrs[i] if i < len(self.edge_attrs) else []

            # 凸凹性：取首个非 smooth（concave=凹, convex=凸）
            if agg[key]["conv"] is None:
                if len(ea) > 1 and ea[1]:
                    agg[key]["conv"] = "convex"
                elif len(ea) > 0 and ea[0]:
                    agg[key]["conv"] = "concave"
                else:
                    agg[key]["conv"] = "smooth"

            # 长度累加
            elen = ea[3] if len(ea) > 3 else 0.0
            try:
                agg[key]["len"] += float(elen) if elen else 0.0
            except (TypeError, ValueError):
                pass

            # 类型计数
            if len(ea) > 9 and ea[9]:
                agg[key]["line"] += 1
            elif len(ea) > 4 and ea[4]:
                agg[key]["circle"] += 1
            else:
                agg[key]["other"] += 1

        # 固化 4 张表
        for key, v in agg.items():
            conv = v["conv"] or "smooth"
            self.edge_convexity[key] = conv
            # dihedral 符号（与 STEP 版 concave=+/convex=- 对齐）
            self.edge_dihedral[key] = (
                1.0 if conv == "concave" else (-1.0 if conv == "convex" else 0.0))
            self.edge_length_map[key] = v["len"]
            tc = {"line": v["line"], "circle": v["circle"], "other": v["other"]}
            self.edge_type[key] = max(tc, key=tc.get)

    # ── 几何查询（UV 中心采样，与 detect_through_step_ncti 一致）──

    def face_normal(self, cell):
        """面法向（UV 中心）。对 PLANE 恒定；对 CYL 给 UV 中心处径向法向。"""
        try:
            vec = self.doc.GetNormalByUV(self.obj_name, cell, 0.5, 0.5)
            if vec is not None:
                return (vec.X, vec.Y, vec.Z)
        except Exception:
            pass
        return None

    def face_centroid(self, cell):
        """面重心（UV 中心采样点）。"""
        try:
            pt = self.doc.GetFacePointFromUV(self.obj_name, cell, 0.5, 0.5)
            if pt is not None:
                return (pt.X, pt.Y, pt.Z)
        except Exception:
            pass
        return None

    def face_area(self, cell):
        attr = self.face_attrs[cell] if 0 <= cell < len(self.face_attrs) else []
        try:
            return float(attr[5]) if len(attr) > 5 else 0.0
        except (TypeError, ValueError):
            return 0.0

    def face_ftype(self, cell):
        """面类型简化为 PLANE/CYL/OTHER。"""
        attr = self.face_attrs[cell] if 0 <= cell < len(self.face_attrs) else []
        if len(attr) > 0 and attr[0] == 1.0:
            return "PLANE"
        if len(attr) > 1 and attr[1] == 1.0:
            return "CYL"
        return "OTHER"

    def face_perimeter(self, cell):
        """该面所有邻接边长度之和（每条边 key 共享，只算一次）。"""
        total = 0.0
        for nb in self.adjacency.get(cell, set()):
            key = (min(cell, nb), max(cell, nb))
            total += self.edge_length_map.get(key, 0.0)
        return total


class NctiFaceAttrs:
    """NCTI 版 FaceAttrs，接口与 featurefox.edge_features.FaceAttrs 一致
    （area/centroid/normal/ftype/perimeter/total_perimeter），委托 NctiPart + 缓存。"""

    def __init__(self, part):
        self.part = part
        self._area = {}
        self._perim = {}
        self._centroid = {}
        self._normal = {}
        self._ftype = {}
        self._total_perim = None

    def area(self, cell):
        if cell not in self._area:
            self._area[cell] = self.part.face_area(cell)
        return self._area[cell]

    def centroid(self, cell):
        if cell not in self._centroid:
            self._centroid[cell] = self.part.face_centroid(cell)
        return self._centroid[cell]

    def normal(self, cell):
        if cell not in self._normal:
            self._normal[cell] = self.part.face_normal(cell)
        return self._normal[cell]

    def ftype(self, cell):
        if cell not in self._ftype:
            self._ftype[cell] = self.part.face_ftype(cell)
        return self._ftype[cell]

    def perimeter(self, cell):
        if cell not in self._perim:
            self._perim[cell] = self.part.face_perimeter(cell)
        return self._perim[cell]

    def total_perimeter(self):
        if self._total_perim is None:
            total = sum(self.part.edge_length_map.values())
            self._total_perim = total if total > 1e-12 else 1.0
        return self._total_perim


def load_part(stp_path, ncti, obj_name="testbox", doc=None):
    """导入 STEP 到 NCTI（约定A），返回 (part, doc)。

    doc 为 None 时新建 Document；提供 doc 时复用（doc.New 重置）。
    ★批量场景必须复用 doc★：每件新建 Document 会在 ~60 件后因 C++ 对象累积 segfault。
    单件场景（GUI/冲烟）可不传 doc。

    约定A：doc.New("OCC","DCM",0) + RunCommand(cmd_ncti_import_file)，
    与 Geo-Rec 训练建图、ncti_faceid_map.import_step_to_ncti 完全一致。
    禁调 SetImportAssemelFile/SetCreateGeGeom（会改面数，破坏 cell_id 对齐）。
    """
    if doc is None:
        doc = ncti.Document()
    # 约定A（与 Geo-Rec 训练建图、ncti_faceid_map.import_step_to_ncti 完全一致）
    doc.New("OCC", "DCM", 0)
    ok = doc.RunCommand("cmd_ncti_import_file", str(stp_path), obj_name)
    if not ok:
        raise RuntimeError("NCTI 导入失败: {}".format(stp_path))
    part = NctiPart(ncti, doc, obj_name)
    return part, doc
