import os
import sys
from pathlib import Path

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from utils.detect_countersunk_holes_and_export_stp_v15 import (
    collect_feature_results,
    extract_refs,
    parse_step_file,
    unique_keep_order,
    _find_face_objects,
    _step_face_to_cell_id_map,
)


def _shell_face_groups_from_model(model):
    """Extract STEP shell/open-shell face groups for mapping to NCTI objects."""
    groups = []
    for shell_id, item in model.raw_entities.items():
        etype, params = item
        if etype.upper() not in {"CLOSED_SHELL", "OPEN_SHELL"}:
            continue
        face_ids = [ref for ref in extract_refs(params) if ref in model.face_surface]
        if face_ids:
            groups.append(
                {
                    "shell_id": shell_id,
                    "shell_type": etype.upper(),
                    "face_ids": face_ids,
                    "count": len(face_ids),
                }
            )

    if groups:
        return groups

    return [
        {
            "shell_id": None,
            "shell_type": "ADVANCED_FACE_ORDER",
            "face_ids": list(model.face_surface.keys()),
            "count": len(model.face_surface),
        }
    ]


def _match_shells_to_objects(shell_groups, object_candidates):
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
        if shell["shell_id"] not in matches:
            remaining_shells_by_count.setdefault(shell["count"], []).append(shell)

    remaining_objects_by_count = {}
    for item in available:
        if item["name"] not in used_names:
            remaining_objects_by_count.setdefault(item["count"], []).append(item)

    for count, shells in remaining_shells_by_count.items():
        items = remaining_objects_by_count.get(count, [])
        if len(shells) > 1 and len(shells) == len(items):
            for shell, item in zip(shells, items):
                matches[shell["shell_id"]] = item
                used_names.add(item["name"])

    return matches


def _build_step_face_object_cell_map(model, doc):
    object_candidates = _find_face_objects(doc)
    shell_groups = _shell_face_groups_from_model(model)
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
            {
                step_face_id: (whole_body_matches[0]["name"], cell_id)
                for step_face_id, cell_id in face_map.items()
            },
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


def _step_face_group_lookup(shell_groups):
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


def recognize_countersunk_holes_from_stp(stp_path, mode="both", include_terminal_faces=True):
    model = parse_step_file(Path(stp_path))
    features, selected_step_faces = collect_feature_results(
        model,
        mode=mode,
        include_terminal_faces=include_terminal_faces,
    )
    return {
        "model": model,
        "features": features,
        "selected_step_faces": selected_step_faces,
    }


def find_countersunk_hole_by_stp(
    doc,
    stp_path,
    obj_name=None,
    mode="both",
    include_terminal_faces=True,
):
    """Recognize v2 countersunk/counterbore holes and convert STEP faces to NCTI cells."""
    names = list(doc.AllNames() or [])
    if not names:
        raise ValueError("当前文档中没有可识别对象，请先导入 STP 模型。")

    result = recognize_countersunk_holes_from_stp(
        stp_path,
        mode=mode,
        include_terminal_faces=include_terminal_faces,
    )
    face_map, object_candidates, shell_groups, shell_matches = _build_step_face_object_cell_map(
        result["model"],
        doc,
    )

    cell_ids = []
    obj_names = []
    mapped_faces = []
    missing_step_faces = []
    for step_face_id in result["selected_step_faces"]:
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
        print("Countersunk STEP faces not mapped to NCTI cells:", ", ".join(missing_detail))

    pairs = unique_keep_order(list(zip(obj_names, cell_ids)))
    obj_names = [name for name, _ in pairs]
    cell_ids = [cell_id for _, cell_id in pairs]
    target_obj_name = obj_names[0] if obj_names else (obj_name or "")

    result.update(
        {
            "cell_ids": cell_ids,
            "obj_names": obj_names,
            "obj_name": target_obj_name,
            "mapped_faces": mapped_faces,
            "highlight_step_faces": result["selected_step_faces"],
            "step_face_to_cell_id": face_map,
            "object_candidates": object_candidates,
            "shell_groups": shell_groups,
            "shell_matches": shell_matches,
            "missing_step_faces": missing_step_faces,
        }
    )

    countersink_count = sum(1 for item in result["features"] if item.get("kind") == "countersink_hole")
    counterbore_count = sum(1 for item in result["features"] if item.get("kind") == "counterbore_hole")
    print(
        "识别到的沉头孔/沉孔数量: "
        f"countersink={countersink_count}, counterbore={counterbore_count}, "
        f"成功映射的面数量: {len(mapped_faces)}"
    )

    return result
