#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FeatureFox 数据驱动通槽识别 → NCTI 高亮桥接层。

与 on_find_through_step_stp.py 功能等价，但识别器换成 FeatureFox
（XGBoost 边分类 + 等渗校准 + 图剪枝 + 连通分量），F1 远超规则式。

流程：
1. StepParser 解析 STEP 文本拓扑（一次解析，预测与映射共用）
2. FeatureFox predict_through_slots() 预测通槽实例（face_id 空间）
3. 通过 ncti.AiModel(doc, obj_name) 获取 ai.FaceID，用几何最近邻建立
   STEP face → ai.FaceID 位置索引的映射（cell_id = 位置索引，与 Geo-Rec 训练标签空间严格对齐）
4. 返回 (obj_names, cell_ids) 供 show_selection() 高亮
"""

import os
import sys

# 添加项目和 featurefox 根目录
_proj_parent = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_featfox_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _featfox_root not in sys.path:
    sys.path.insert(0, _featfox_root)
from featurefox.lib._env import get_project_root
_project_root = get_project_root()
if _project_root is None:
    _project_root = os.path.join(_proj_parent, "YHCADSmartCleaner")
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from function.on_find_blind_hole_stp import unique_keep_order
from utils.detect_blind_holes_and_export_stp_v15_22 import StepParser


# ---- 与 annotate_through_step.py 一致的 NCTI FaceID 位置映射 ----

def _ncti_point_to_tuple(pt):
    """NCTI 点 → (x,y,z)。兼容 Point(.X/.Y/.Z) 与序列([0]/[1]/[2])。"""
    try:
        return (float(pt.X), float(pt.Y), float(pt.Z))
    except (AttributeError, TypeError):
        return (float(pt[0]), float(pt[1]), float(pt[2]))


def _build_face_centroids_from_parser(parser, fa_attrs):
    """从 StepParser + face_attrs 提取每个 STEP 面的重心坐标。

    与 annotate_through_step.py 的 fa_attrs.centroid() 完全一致，
    用于与 NCTI GetFaceMidPoint 做几何最近邻匹配。
    """
    centroids = {}
    for fid in parser.advanced_faces:
        c = fa_attrs.centroid(fid)
        if c is not None:
            centroids[fid] = (float(c[0]), float(c[1]), float(c[2]))
    return centroids


def build_step_face_to_ncti_pos_map(parser, fa_attrs, doc, ncti, obj_name, tol=None):
    """STEP entity ID → NCTI ai.FaceID 位置索引（= Geo-Rec 训练标签 cell_id 空间）。

    DEBUG 数据确认：
      ai.FaceID[i] = entity_ID_at_position_i
      GetFaceMidPoint(name, cell_index) 第一个参数是 cell_index（位置），不是 entity ID
      entity ID 和 cell_index 是两套独立编号，不能互换！

    正确匹配：
      GetFaceMidPoint(name, i) → cell_index=i 位置面的中点
      ai.FaceID[i]            → cell_index=i 位置的 entity ID
      STEP 面重心(entity ID) 与中点做几何最近邻 → 找到该 entity 对应的 cell_index

    返回 (pos_map, n_faces)：pos_map[step_entity_id] = cell_index (= 训练标签 cell_id)
    """
    ai = ncti.AiModel(doc, obj_name)
    face_ids = ai.FaceID  # [fid0, fid1, ...]
    n_faces = len(face_ids)

    # NCTI 侧：以 cell_index 为 key，中点为 value
    # GetFaceMidPoint(name, cell_index) → cell_index 位置面的中点
    ncti_mids = {}  # cell_index → (x,y,z)
    for i in range(n_faces):
        try:
            pt = doc.GetFaceMidPoint(obj_name, i)  # i 是 cell_index，不是 entity ID
            ncti_mids[i] = _ncti_point_to_tuple(pt)
        except Exception:
            continue
    if not ncti_mids:
        return {}, n_faces

    # STEP 侧：每个 entity ID 的面重心
    step_centroids = _build_face_centroids_from_parser(parser, fa_attrs)
    if not step_centroids:
        return {}, n_faces

    # 自适应容差
    if tol is None:
        all_pts = list(step_centroids.values())
        xs = [p[0] for p in all_pts]
        ys = [p[1] for p in all_pts]
        zs = [p[2] for p in all_pts]
        diag = ((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2
                + (max(zs) - min(zs)) ** 2) ** 0.5
        tol = diag * 0.15

    # STEP entity ID → 最近 NCTI cell_index 的几何匹配
    entity_to_cell = {}  # step_entity_id → cell_index
    for eid, sc in step_centroids.items():
        best_cell, best_d = None, None
        for cell_idx, npt in ncti_mids.items():
            d = (sc[0] - npt[0]) ** 2 + (sc[1] - npt[1]) ** 2 + (sc[2] - npt[2]) ** 2
            if best_d is None or d < best_d:
                best_d, best_cell = d, cell_idx
        if best_cell is not None and best_d <= tol * tol:
            entity_to_cell[eid] = (best_cell, best_d)

    # 互为最近邻验证（避免多对一错配）
    cell_to_entity = {}
    for eid, (cid, _) in entity_to_cell.items():
        cell_to_entity.setdefault(cid, []).append(eid)
    pos_map = {}
    for eid, (cid, d2) in entity_to_cell.items():
        cands = cell_to_entity.get(cid, [])
        if len(cands) > 1:
            best_eid = min(cands, key=lambda e: entity_to_cell[e][1])
            if eid != best_eid:
                continue
        pos_map[eid] = cid  # cid 就是 cell_index = 训练标签 cell_id
    return pos_map, n_faces


# ---- 主入口 ----

def find_through_step_by_featurefox(doc, stp_path, ncti, obj_name=None, threshold=None):
    """FeatureFox 识别 STP 通槽并转换成 NCTI 可高亮的 obj_names/cell_ids。

    参数:
        doc: NCTI Document 对象（用户已导入 STEP 的文档）
        stp_path: STEP 文件路径
        ncti: NCTI 模块（用于创建 AiModel 获取 ai.FaceID）
        obj_name: 模型名称（默认为 doc.AllNames()[0]，单 body 时自动推断）
        threshold: 边剪枝阈值（None 时用 FeatureFox 默认 0.35）

    返回 dict 包含：
        instances: FeatureFox 识别到的通槽实例列表
        cell_ids: NCTI cell_id 列表（ai.FaceID 位置索引，与 Geo-Rec 训练标签空间对齐）
        obj_names: NCTI 对象名列表（与 cell_ids 一一对应）
        step_face_to_cell_id: STEP face → (obj_name, cell_id) 映射
    """
    names = list(doc.AllNames() or [])
    if not names:
        raise ValueError("当前文档中没有可识别对象，请先导入STP模型。")

    # obj_name 推断：默认为第一个对象（单 body 零件场景）
    if obj_name is None:
        obj_name = names[0]

    # 延迟导入（STEP 文本解析版，依赖原 featurefox 包）
    from utils.through_step.featurefox.predict import (
        load_models, load_instance_models, predict_through_slots,
    )
    from utils.through_step.featurefox.edge_features import build_face_graph

    # 一次解析，预测与映射共用
    parser = StepParser(stp_path)
    parser.parse()
    _, fa_attrs = build_face_graph(parser)  # 提取面属性（法向/重心），供几何映射

    booster, calibrator = load_models()
    inst_booster, inst_calib = load_instance_models()
    predict_kwargs = {"parser": parser,
                      "inst_booster": inst_booster, "inst_calibrator": inst_calib}
    if threshold is not None:
        predict_kwargs["threshold"] = threshold
    instances = predict_through_slots(stp_path, booster, calibrator, **predict_kwargs)

    # 建立 STEP face → NCTI cell_id 映射（几何最近邻，cell_id = ai.FaceID 位置索引）
    pos_map, n_faces = build_step_face_to_ncti_pos_map(
        parser, fa_attrs, doc, ncti, obj_name)

    # 收集所有实例的面 → 映射到 NCTI cell_id
    selected_step_faces = []
    mapped_faces = []
    missing_step_faces = []
    for inst in instances:
        for step_face_id in inst["faces"]:
            selected_step_faces.append(step_face_id)
            cell_id = pos_map.get(step_face_id)
            if cell_id is None:
                missing_step_faces.append(step_face_id)
                continue
            mapped_faces.append({
                "step_face": step_face_id,
                "obj_name": obj_name,
                "cell_id": cell_id,
            })

    if missing_step_faces:
        print("警告：以下 STEP face 未映射到 NCTI cell_id：{}".format(
            ", ".join("#{}".format(f) for f in missing_step_faces)
        ))

    # 去重（同一面可能被多实例共享）
    pairs = unique_keep_order(
        [(item["obj_name"], item["cell_id"]) for item in mapped_faces]
    )
    obj_names = [name for name, _ in pairs]
    cell_ids = [cell_id for _, cell_id in pairs]

    instance_count = len(instances)
    mapped_count = len(mapped_faces)
    print("FeatureFox 识别到的通槽数量: {}, 成功映射的面数量: {}".format(
        instance_count, mapped_count))
    for i, inst in enumerate(instances, 1):
        print("  通槽 #{}: {}面, score={:.3f}, faces={}".format(
            i, inst["n_faces"], inst["score"], inst["faces"]))

    return {
        "instances": instances,
        "cell_ids": cell_ids,
        "obj_names": obj_names,
        "obj_name": obj_names[0] if obj_names else "",
        "mapped_faces": mapped_faces,
        "selected_step_faces": selected_step_faces,
        "step_face_to_cell_id": pos_map,
        "ncti_faces_total": n_faces,
        "object_candidates": None,
        "shell_groups": None,
        "shell_matches": None,
    }
