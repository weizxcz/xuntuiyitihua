#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""FeatureFox-NCTI 数据驱动通槽识别 → NCTI 高亮桥接层。

与 on_find_through_step_featurefox.py 功能等价，但识别器换成 featurefox_ncti
（NCTI 原生数据源 + XGBoost 边分类 + 等渗校准 + 实例分类），输出 cell_id
（ai.FaceID 位置索引）零映射，直接对齐 Geo-Rec 训练图节点空间。

与 on_find_through_step_ncti.py 一样：
1. 直接使用 NCTI 数据，不需要 STP 文件路径
2. 无需 STEP face → NCTI cell_id 映射（识别输出即 cell_id）
3. 直接输出 cell_ids，供 show_selection() 高亮

关键设计：识别在用户已导入的 self.doc 上做（NctiPart 从 live doc 构造，不重新导入），
保证输出的 cell_id 与 GUI 显示的模型一致 → 高亮正确。若重新导入到独立 Document，
cell_id 空间会与 self.doc 脱节导致高亮错位。

流程：
1. NctiPart 从 live doc 构造（读取 ai.FaceID / ai.FaceAttr / ai.EdgeAttr）
2. featurefox_ncti predict_through_slots() 预测通槽实例（cell_id 空间，零映射）
3. 返回 (obj_names, cell_ids) 供 show_selection() 高亮
"""

import os
import sys

# 添加项目根目录
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from function.on_find_blind_hole_stp import unique_keep_order  # noqa: E402


def find_through_step_by_featurefox_ncti(ncti, doc, obj_name=None, threshold=None):
    """FeatureFox-NCTI 识别通槽并转换成 NCTI 可高亮的 obj_names/cell_ids。

    参数:
        ncti: NCTI 模块
        doc: NCTI Document 对象（用户已导入模型的文档）
        obj_name: 模型名称（默认为 doc.AllNames()[0]，单 body 时自动推断）
        threshold: 边剪枝阈值（None 时用 featurefox_ncti 默认 0.35）

    返回 dict 包含：
        instances: featurefox_ncti 识别到的通槽实例列表（cell_id 空间）
        cell_ids: NCTI cell_id 列表（ai.FaceID 位置索引，零映射，与 Geo-Rec 训练标签空间对齐）
        obj_names: NCTI 对象名列表（与 cell_ids 一一对应）
        obj_name: 主对象名
        ncti_faces_total: NCTI 面总数
    """
    names = list(doc.AllNames() or [])
    if not names:
        raise ValueError("当前文档中没有可识别对象，请先导入模型。")

    # obj_name 推断：默认为第一个对象（单 body 零件场景）
    if obj_name is None:
        obj_name = names[0]

    # 延迟导入（featurefox_ncti 依赖 NCTI / xgboost，避免主程序启动时加载）
    from utils.through_step.featurefox_ncti.predict import (
        load_models, load_instance_models, predict_through_slots,
    )
    from utils.through_step.featurefox_ncti.ncti_backend import NctiPart

    # 从已导入的 live doc 构造 NctiPart（不重新导入）。
    # ★必须复用 self.doc★：重新导入会建独立 Document，其 cell_id 空间与 GUI 显示模型
    #   脱节，show_selection 高亮会错位。NctiPart 直接读 live doc 的 ai.FaceID/FaceAttr/EdgeAttr。
    part = NctiPart(ncti, doc, obj_name)
    n_faces = part.n_faces

    booster, calibrator = load_models()
    inst_booster, inst_calib = load_instance_models()
    predict_kwargs = {"part": part,
                      "inst_booster": inst_booster, "inst_calibrator": inst_calib}
    if threshold is not None:
        predict_kwargs["threshold"] = threshold
    # part 已提供，stp_path 无需（仅 part=None 时用于内部导入）；传 None
    instances = predict_through_slots(None, booster, calibrator, **predict_kwargs)

    # faces 已是 cell_id（零映射），直接收集 → 高亮
    selected_cells = []
    for inst in instances:
        selected_cells.extend(inst["faces"])

    # 去重（同一面可能被多实例共享）
    pairs = unique_keep_order([(obj_name, cell_id) for cell_id in selected_cells])
    obj_names = [name for name, _ in pairs]
    cell_ids = [cell_id for _, cell_id in pairs]

    instance_count = len(instances)
    mapped_count = len(cell_ids)
    print("FeatureFox-NCTI 识别到的通槽数量: {}, 成功映射的面数量: {}".format(
        instance_count, mapped_count))
    for i, inst in enumerate(instances, 1):
        print("  通槽 #{}: {}面, score={:.3f}, inst_prob={:.3f}, faces={}".format(
            i, inst["n_faces"], inst["score"], inst.get("inst_prob", 1.0), inst["faces"]))

    return {
        "instances": instances,
        "cell_ids": cell_ids,
        "obj_names": obj_names,
        "obj_name": obj_names[0] if obj_names else obj_name,
        "selected_cells": selected_cells,
        "ncti_faces_total": n_faces,
        "selected_step_faces": None,  # NCTI 版无 STEP face 概念，占位保持返回结构一致
        "mapped_faces": None,
        "step_face_to_cell_id": None,
        "object_candidates": None,
        "shell_groups": None,
        "shell_matches": None,
    }
