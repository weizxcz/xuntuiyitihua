#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
双侧通槽台阶 (2-sided through step) STEP 识别 → NCTI 高亮桥接层。

参照 on_find_blind_hole_stp.py 的映射模式：
1. StepParser 解析 STEP 文本拓扑
2. ThroughStepRecognizer 识别通槽
3. _build_step_face_object_cell_map 建立 STEP face → NCTI cell_id 映射
4. 返回 (obj_names, cell_ids) 供 show_selection() 高亮
"""

import os
import sys

# 添加项目根目录
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 盲孔的映射工具函数
from function.on_find_blind_hole_stp import (
    _step_face_to_cell_id_map,
    _find_face_objects,
    _match_shells_to_objects,
    unique_keep_order,
)

from utils.through_step.detect_through_step import recognize_through_steps_from_stp  # noqa: E402


def _closed_shell_face_groups(step_parser):
    """提取 STEP 中 CLOSED_SHELL / OPEN_SHELL 内的面组。"""
    groups = []
    for shell_id, entity in step_parser.entities.items():
        if entity.get("type") not in {"CLOSED_SHELL", "OPEN_SHELL"}:
            continue
        face_ids = [
            ref
            for ref in step_parser._refs(entity.get("params", ""))
            if ref in step_parser.advanced_faces
        ]
        if face_ids:
            groups.append({
                "shell_id": shell_id,
                "shell_type": entity.get("type"),
                "face_ids": face_ids,
                "count": len(face_ids),
            })
    if groups:
        return groups
    return [{
        "shell_id": None,
        "shell_type": "ADVANCED_FACE_ORDER",
        "face_ids": list(step_parser.advanced_faces.keys()),
        "count": len(step_parser.advanced_faces),
    }]


def _build_step_face_object_cell_map(step_parser, doc):
    """构建 STEP face_id → (NCTI obj_name, cell_id) 映射。"""
    object_candidates = _find_face_objects(doc)
    shell_groups = _closed_shell_face_groups(step_parser)
    shell_matches = _match_shells_to_objects(shell_groups, object_candidates)

    total_shell_faces = sum(shell["count"] for shell in shell_groups)
    whole_body_matches = [
        item for item in object_candidates if item["count"] == total_shell_faces
    ]
    if len(whole_body_matches) == 1:
        flat_step_faces = []
        for shell in shell_groups:
            flat_step_faces.extend(shell["face_ids"])
        face_map = _step_face_to_cell_id_map(flat_step_faces, whole_body_matches[0]["face_ids"])
        return (
            {step_face_id: (whole_body_matches[0]["name"], cell_id)
             for step_face_id, cell_id in face_map.items()},
            object_candidates,
            shell_groups,
            {"all_shells": whole_body_matches[0]},
        )

    if not shell_matches and len(shell_groups) == 1:
        shell = shell_groups[0]
        same_count = [item for item in object_candidates if item["count"] == shell["count"]]
        if len(same_count) == 1:
            shell_matches[shell["shell_id"]] = same_count[0]

    step_face_to_object_cell = {}
    for shell in shell_groups:
        item = shell_matches.get(shell["shell_id"])
        if item is None:
            continue
        face_map = _step_face_to_cell_id_map(shell["face_ids"], item["face_ids"])
        for step_face_id, cell_id in face_map.items():
            step_face_to_object_cell[step_face_id] = (item["name"], cell_id)

    return step_face_to_object_cell, object_candidates, shell_groups, shell_matches


def _filter_by_edge_convexity(instances, face_map, ncti, doc, obj_name):
    """用 OCC 边凸凹性过滤误检实例 + NCTI 邻接面评分。

    两步过滤：
    1. 硬过滤：底面-侧壁共享边为凸边 → 直接排除（外凸角）
    2. 软过滤：底面邻接面过多 → 降低评分（盲槽/口袋信号）

    AiModel.EdgeAttr 布局：
        [0]=凹边, [1]=凸边, [2]=光滑边, [3]=边长, ...
    """
    if ncti is None or doc is None or not obj_name:
        return instances

    try:
        ai = ncti.AiModel(doc, obj_name)
    except Exception:
        return instances

    edge_attrs = ai.EdgeAttr      # list[list[float]]
    face_eids = ai.FaceEID        # 每条边的左侧面 ID
    face_fids = ai.FaceFID        # 每条边的右侧面 ID

    if not edge_attrs or not face_eids:
        return instances

    # 建立面-面之间边的凸凹性查找表
    # key: (min_cell, max_cell)，value: "concave" / "convex" / "smooth"
    edge_convexity = {}
    # 建立面邻接表（用于邻接面计数）
    adjacency = {}
    for idx in range(len(edge_attrs)):
        ea = edge_attrs[idx]
        fe = face_eids[idx]
        ff = face_fids[idx]
        if fe is None or ff is None:
            continue
        key = (min(fe, ff), max(fe, ff))
        if len(ea) > 1 and ea[1]:        # 凸边
            edge_convexity[key] = "convex"
        elif len(ea) > 0 and ea[0]:      # 凹边
            edge_convexity[key] = "concave"
        else:
            edge_convexity[key] = "smooth"
        # 邻接表
        adjacency.setdefault(fe, set()).add(ff)
        adjacency.setdefault(ff, set()).add(fe)

    filtered = []
    for inst in instances:
        bottom = inst["bottom_face"]
        walls = inst["side_walls"]

        # STEP face_id → (obj_name, cell_id)
        bottom_mapped = face_map.get(bottom)
        if bottom_mapped is None:
            filtered.append(inst)
            continue

        bottom_cell = bottom_mapped[1]  # 提取 cell_id
        wall_cells = []
        skip = False
        for w in walls:
            w_mapped = face_map.get(w)
            if w_mapped is None:
                skip = True
                break
            wall_cells.append(w_mapped[1])

        if skip:
            filtered.append(inst)
            continue

        # ── 硬过滤：底面-每个侧壁共享边为凸边 → 排除 ──
        is_through_step = True
        for wc in wall_cells:
            key = (min(bottom_cell, wc), max(bottom_cell, wc))
            conv = edge_convexity.get(key, "smooth")
            if conv == "convex":
                is_through_step = False
                break

        if not is_through_step:
            print("  凸凹性过滤：排除实例 faces={} (底面-侧壁共享边为凸边)".format(
                inst["faces"]
            ))
            continue

        # ── 软过滤：NCTI 邻接面评分调整 ──
        # 通槽底面邻接面少（2侧壁+2-4开放端=4-6），盲槽底面邻接面多（≥7）
        bottom_neighbors = len(adjacency.get(bottom_cell, set()))
        inst["bottom_neighbor_count"] = bottom_neighbors

        # 邻接面过多时扣分：每多一个超过5扣3分
        if bottom_neighbors > 5:
            penalty = (bottom_neighbors - 5) * 3.0
            inst["score"] = max(0, inst.get("score", 0) - penalty)

        filtered.append(inst)

    return filtered


def find_through_step_by_stp(ncti, doc, stp_path, obj_name=None):
    """识别 STP 双侧通槽台阶并转换成 NCTI 可高亮的 obj_names/cell_ids。

    返回 dict 包含：
        instances: 识别到的通槽实例列表
        cell_ids: NCTI cell_id 列表（用于高亮）
        obj_names: NCTI 对象名列表（与 cell_ids 一一对应）
        step_face_to_cell_id: STEP face → (obj_name, cell_id) 映射
    """
    names = list(doc.AllNames() or [])
    if not names:
        raise ValueError("当前文档中没有可识别对象，请先导入STP模型。")

    # STEP 侧识别
    result = recognize_through_steps_from_stp(stp_path)

    # 建立 STEP face → NCTI cell_id 映射
    face_map, object_candidates, shell_groups, shell_matches = _build_step_face_object_cell_map(
        result["step_parser"], doc
    )

    # 转换为 NCTI cell_id
    selected_step_faces = result["selected_step_faces"]
    cell_ids = []
    obj_names = []
    mapped_faces = []
    missing_step_faces = []

    for step_face_id in selected_step_faces:
        mapped = face_map.get(step_face_id)
        if mapped is None:
            missing_step_faces.append(step_face_id)
            continue
        mapped_obj_name, cell_id = mapped
        obj_names.append(mapped_obj_name)
        cell_ids.append(cell_id)
        mapped_faces.append({
            "step_face": step_face_id,
            "obj_name": mapped_obj_name,
            "cell_id": cell_id,
        })

    if missing_step_faces:
        print("警告：以下 STEP face 未映射到 NCTI cell_id：{}".format(
            ", ".join("#{}".format(f) for f in missing_step_faces)
        ))

    # ── OCC 边凸凹性过滤 + NCTI 邻接面评分调整 ──
    best_obj_name = obj_names[0] if obj_names else None
    if best_obj_name:
        before_count = len(result["instances"])
        result["instances"] = _filter_by_edge_convexity(
            result["instances"], face_map, ncti, doc, best_obj_name
        )
        filtered_count = before_count - len(result["instances"])
        if filtered_count > 0:
            print("凸凹性过滤：排除 {} 个误检实例".format(filtered_count))

    # ── 邻接面评分调整后，过滤低于阈值的实例 ──
    MIN_HYBRID_SCORE = 76.0
    before = len(result["instances"])
    result["instances"] = [inst for inst in result["instances"]
                           if inst.get("score", 0) >= MIN_HYBRID_SCORE]
    dropped = before - len(result["instances"])
    if dropped > 0:
        print("邻接面评分过滤：排除 {} 个低分实例(score<{})".format(dropped, MIN_HYBRID_SCORE))

    # 打印每个保留实例的详情
    for i, inst in enumerate(result["instances"], 1):
        n_neighbors = inst.get("bottom_neighbor_count", "?")
        print("  #{}: faces={}, score={:.1f}, bottom_neighbors={}".format(
            i, inst["faces"], inst.get("score", 0), n_neighbors))

    # 过滤后重新计算 cell_ids / obj_names（仅保留过滤后实例的面）
    instances = result["instances"]
    filtered_step_faces = []
    for inst in instances:
        filtered_step_faces.extend(inst["faces"])

    cell_ids = []
    obj_names = []
    mapped_faces = []
    for step_face_id in filtered_step_faces:
        mapped = face_map.get(step_face_id)
        if mapped is None:
            continue
        mapped_obj_name, cell_id = mapped
        obj_names.append(mapped_obj_name)
        cell_ids.append(cell_id)
        mapped_faces.append({
            "step_face": step_face_id,
            "obj_name": mapped_obj_name,
            "cell_id": cell_id,
        })

    # 去重
    pairs = unique_keep_order(list(zip(obj_names, cell_ids)))
    obj_names = [name for name, _ in pairs]
    cell_ids = [cell_id for _, cell_id in pairs]

    instance_count = len(result["instances"])
    mapped_count = len(mapped_faces)
    print("识别到的通槽数量: {}, 成功映射的面数量: {}".format(instance_count, mapped_count))

    result.update({
        "cell_ids": cell_ids,
        "obj_names": obj_names,
        "obj_name": obj_names[0] if obj_names else "",
        "mapped_faces": mapped_faces,
        "step_face_to_cell_id": face_map,
        "object_candidates": object_candidates,
        "shell_groups": shell_groups,
        "shell_matches": shell_matches,
    })
    return result
