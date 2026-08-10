
import sys
import os

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from blind_hole.detect_blind_holes_and_export_stp_v15_23 import (
    BlindHoleRecognizer,
    StepParser,
    apply_corrected_v13_postprocess,
    select_exact_faces_from_holes,
    unique_keep_order,
)

def _step_face_to_cell_id_map(step_face_ids, cell_ids):
    """按 STEP 面在 shell 内的顺序建立 NCTI cell_id 映射。

    这里的关键假设来自前面的验证：NCTI 导入后，某个 body 内部的
    cell_id 通常不是 STEP 的 #实体号，而是该 ADVANCED_FACE 在对应
    CLOSED_SHELL/OPEN_SHELL 中的 0 基顺序。
    """
    if len(step_face_ids) != len(cell_ids):
        raise ValueError(
            f"STEP面数量({len(step_face_ids)})与NCTI面数量({len(cell_ids)})不一致，"
            "无法使用顺序映射高亮。"
        )

    # 如果 NCTI 返回的 face id 正好是 0..n-1，直接使用 STEP shell 内索引。
    # 这样可以避免 FindAllFaces() 返回顺序不是升序时造成错配。
    expected_cell_ids = set(range(len(step_face_ids)))
    if set(cell_ids) == expected_cell_ids:
        return {step_face_id: index for index, step_face_id in enumerate(step_face_ids)}

    # 少数情况下 NCTI cell_id 不是连续 0..n-1，则退回到“同位置”映射。
    return {step_face_id: cell_ids[index] for index, step_face_id in enumerate(step_face_ids)}


def _closed_shell_face_groups(step_parser):
    """提取 STEP 中可参与映射的面组。

    大多数实体是 CLOSED_SHELL；部分装配体或片体数据会把有效面放在
    OPEN_SHELL 中。这里两者都收集，否则 OPEN_SHELL 内识别到的盲孔面
    会完全找不到 NCTI cell_id。
    """
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
            groups.append(
                {
                    "shell_id": shell_id,
                    "shell_type": entity.get("type"),
                    "face_ids": face_ids,
                    "count": len(face_ids),
                }
            )
    if groups:
        return groups
    # 极端兜底：如果 STEP 没有 shell 结构，就按 ADVANCED_FACE 出现顺序映射。
    return [
        {
            "shell_id": None,
            "shell_type": "ADVANCED_FACE_ORDER",
            "face_ids": list(step_parser.advanced_faces.keys()),
            "count": len(step_parser.advanced_faces),
        }
    ]


def _find_face_objects(doc):
    """读取 NCTI 当前文档中的对象及其所有面 id。"""
    candidates = []
    for name in list(doc.AllNames() or []):
        try:
            face_ids = list(doc.FindAllFaces(name) or [])
        except Exception:
            face_ids = []
        candidates.append({"name": name, "face_ids": face_ids, "count": len(face_ids)})
    return candidates


def _match_shells_to_objects(shell_groups, object_candidates):
    """将 STEP shell/open shell 与 NCTI body 按面数量配对。

    首选唯一面数量匹配；装配体中可能出现多个零件面数相同的情况，
    如果 STEP 与 NCTI 中该面数的数量一致，则按导入顺序一一配对。
    """
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

    remaining_shells_by_count = {}
    for shell in shell_groups:
        if shell["shell_id"] in matches:
            continue
        remaining_shells_by_count.setdefault(shell["count"], []).append(shell)

    remaining_objects_by_count = {}
    for item in available:
        if item["name"] in used_names:
            continue
        remaining_objects_by_count.setdefault(item["count"], []).append(item)

    for count, shells in remaining_shells_by_count.items():
        items = remaining_objects_by_count.get(count, [])
        # 同面数对象不唯一时，只有两边数量完全一致才按顺序配对。
        # 如果数量不一致，保持未匹配，让后面的诊断信息暴露问题。
        if len(shells) > 1 and len(shells) == len(items):
            for shell, item in zip(shells, items):
                matches[shell["shell_id"]] = item
                used_names.add(item["name"])

    return matches


def _build_step_face_object_cell_map(step_parser, doc):
    """构建 STEP face -> (NCTI object name, cell_id) 的完整映射表。"""
    object_candidates = _find_face_objects(doc)
    shell_groups = _closed_shell_face_groups(step_parser)
    shell_matches = _match_shells_to_objects(shell_groups, object_candidates)

    total_shell_faces = sum(shell["count"] for shell in shell_groups)
    whole_body_matches = [
        item for item in object_candidates if item["count"] == total_shell_faces
    ]
    if len(whole_body_matches) == 1:
        # BREP_WITH_VOIDS 等结构可能由多个 shell 组成，但 NCTI 只暴露为
        # 一个 body。此时把所有 shell 按 STEP 顺序展平后整体映射。
        flat_step_faces = []
        for shell in shell_groups:
            flat_step_faces.extend(shell["face_ids"])
        face_map = _step_face_to_cell_id_map(flat_step_faces, whole_body_matches[0]["face_ids"])
        return (
            {
                step_face_id: (whole_body_matches[0]["name"], cell_id)
                for step_face_id, cell_id in face_map.items()
            },
            object_candidates,
            shell_groups,
            {"all_shells": whole_body_matches[0]},
        )

    # 单 shell 单 body 的普通零件路径，例如 ESXAF。
    if not shell_matches and len(shell_groups) == 1:
        shell = shell_groups[0]
        same_count = [item for item in object_candidates if item["count"] == shell["count"]]
        if len(same_count) == 1:
            shell_matches[shell["shell_id"]] = same_count[0]

    if not shell_matches:
        step_counts = ", ".join(
            f"{item.get('shell_type', 'SHELL')}#{item['shell_id']}:{item['count']}"
            for item in shell_groups
        )
        obj_counts = ", ".join(
            f"{item['name']}:{item['count']}" for item in object_candidates
        ) or "无对象"
        pass

    step_face_to_object_cell = {}
    for shell in shell_groups:
        item = shell_matches.get(shell["shell_id"])
        if item is None:
            continue
        # 对每个已匹配的 shell/body，使用 shell 内 face 顺序映射 cell_id。
        face_map = _step_face_to_cell_id_map(shell["face_ids"], item["face_ids"])
        for step_face_id, cell_id in face_map.items():
            step_face_to_object_cell[step_face_id] = (item["name"], cell_id)

    return step_face_to_object_cell, object_candidates, shell_groups, shell_matches


def recognize_blind_holes_from_stp(stp_path):
    """只运行 STEP 侧盲孔识别，返回识别结果和待高亮的 STEP face。"""
    step = StepParser(stp_path)
    step.parse()
    recognizer = BlindHoleRecognizer(step)
    raw_holes = recognizer.recognize()
    holes, rejected_line_mouth_holes, raw_shared_groups = apply_corrected_v13_postprocess(
        step,
        recognizer,
        raw_holes,
    )
    selected_step_faces, per_hole = select_exact_faces_from_holes(
        step,
        recognizer,
        holes,
        include_chamfer=True,
    )
    return {
        "step_parser": step,
        "holes": holes,
        "raw_holes": raw_holes,
        "selected_step_faces": selected_step_faces,
        "per_hole": per_hole,
        "rejected_line_mouth_holes": rejected_line_mouth_holes,
        "raw_shared_groups": raw_shared_groups,
    }


def _is_ui_highlight_face(step_parser, step_face_id):
    """判断某个 STEP face 是否适合直接用 NCTI cell 高亮。

    NCTI 高亮只能亮整个原始面。对于共享大平面底面，如果直接高亮
    会出现“大黄平面”；因此普通 PLANE 只允许单圆边界的小底面。
    """
    if step_parser.face_surface_type(step_face_id) != "PLANE":
        return True

    edge_types = {
        step_parser.edge_base_curve_type(edge_id)
        for edge_id in step_parser.face_to_edge_curves.get(step_face_id, set())
    }
    loop_counts = step_parser.face_loop_curve_counts(step_face_id)
    # STEP里一些相交盲孔底部会落在较大的平面片上。导出脚本可以用局部圆盘
    # 表示这类底面，但当前NCTI只能高亮原始cell，所以UI里跳过多边大平面。
    return bool(loop_counts) and max(loop_counts) == 1 and edge_types <= {"CIRCLE"}


def _filter_ui_highlight_step_faces(step_parser, step_face_ids):
    """按 UI 高亮规则过滤 STEP face。"""
    return [
        step_face_id
        for step_face_id in step_face_ids
        if _is_ui_highlight_face(step_parser, step_face_id)
    ]


def _ui_highlight_step_faces_from_result(result):
    """从识别结果中得到最终用于 NCTI 高亮的 STEP face。

    v15_10+ 的广义截断/partial 盲孔，底面虽然是 PLANE，但它是识别
    脚本明确选出的局部源面，不能套用普通“大平面过滤”规则。
    """
    force_keep_faces = set()
    for group in result.get("per_hole", []):
        if group.get("partial_bottom_outer_bound_specs") is not None:
            force_keep_faces.update(group.get("export_faces", []))
            force_keep_faces.update(group.get("source_faces", []))

    return [
        step_face_id
        for step_face_id in result["selected_step_faces"]
        if step_face_id in force_keep_faces
        or _is_ui_highlight_face(result["step_parser"], step_face_id)
    ]


def _step_face_group_lookup(shell_groups):
    """建立 STEP face 到所在 shell/open shell 的诊断索引。"""
    lookup = {}
    for group in shell_groups:
        for index, step_face_id in enumerate(group["face_ids"]):
            lookup[step_face_id] = {
                "shell_id": group["shell_id"],
                "shell_type": group.get("shell_type", "SHELL"),
                "count": group["count"],
                "index": index,
            }
    return lookup


def find_blind_hole_by_stp(doc, stp_path, obj_name=None):
    """识别 STP 盲孔并转换成 NCTI 可高亮的 obj_names/cell_ids。"""
    names = list(doc.AllNames() or [])
    if not names:
        raise ValueError("当前文档中没有可识别对象，请先导入STP模型。")

    result = recognize_blind_holes_from_stp(stp_path)
    face_map, object_candidates, shell_groups, shell_matches = _build_step_face_object_cell_map(
        result["step_parser"],
        doc,
    )

    highlight_step_faces = _ui_highlight_step_faces_from_result(result)

    cell_ids = []
    obj_names = []
    mapped_faces = []
    missing_step_faces = []
    for step_face_id in highlight_step_faces:
        mapped = face_map.get(step_face_id)
        if mapped is None:
            missing_step_faces.append(step_face_id)
            continue
        mapped_obj_name, cell_id = mapped
        obj_names.append(mapped_obj_name)
        cell_ids.append(cell_id)
        mapped_faces.append(
            {
                "step_face": step_face_id,
                "obj_name": mapped_obj_name,
                "cell_id": cell_id,
            }
        )

    if missing_step_faces:
        # 这里通常不是识别失败，而是 STEP shell/open shell 与 NCTI body
        # 没有成功匹配。把缺失面的 shell 归属和 NCTI 对象面数打出来，
        # 方便判断是装配体合并、拆分、OPEN_SHELL，还是对象顺序问题。
        group_lookup = _step_face_group_lookup(shell_groups)
        missing_detail = []
        for step_face_id in missing_step_faces:
            group = group_lookup.get(step_face_id)
            if group:
                missing_detail.append(
                    f"#{step_face_id} in {group['shell_type']}#{group['shell_id']}"
                    f"[{group['index']}/{group['count']}]"
                )
            else:
                missing_detail.append(f"#{step_face_id} not in STEP shell")
        obj_counts = ", ".join(
            f"{item['name']}:{item['count']}" for item in object_candidates
        ) or "无对象"
        pass

    pairs = unique_keep_order(list(zip(obj_names, cell_ids)))
    # 同一个面可能被多个盲孔分组重复选中；高亮前按 obj_name+cell_id 去重。
    obj_names = [name for name, _ in pairs]
    cell_ids = [cell_id for _, cell_id in pairs]
    target_obj_name = obj_names[0] if obj_names else ""
    result.update(
        {
            "cell_ids": cell_ids,
            "obj_names": obj_names,
            "obj_name": target_obj_name,
            "mapped_faces": mapped_faces,
            "highlight_step_faces": highlight_step_faces,
            "step_face_to_cell_id": face_map,
            "object_candidates": object_candidates,
            "shell_groups": shell_groups,
            "shell_matches": shell_matches,
        }
    )
    
    hole_count = len(result["holes"])
    mapped_face_count = len(mapped_faces)
    print(f"识别到的盲孔数量: {hole_count}, 成功映射的面数量: {mapped_face_count}")
    
    return result
