#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
双侧通槽台阶 NCTI-native 识别桥接层。

与 on_find_through_step_stp.py 功能等价，但：
1. 直接使用 NCTI 数据，不需要 STP 文件路径
2. 无需 STEP face → NCTI cell_id 映射
3. 凸凹性在检测器内部作为硬约束（非后过滤）
4. 直接输出 cell_ids，供 show_selection() 高亮
"""

import os
import sys

# 添加项目根目录
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from utils.through_step.detect_through_step_ncti import recognize_through_steps_ncti  # noqa: E402


def find_through_step_by_ncti(ncti, doc, obj_name=None):
    """NCTI-native 通槽识别 → NCTI 高亮。

    参数:
        ncti: NCTI 对象
        doc: NCTI Document 对象
        obj_name: 模型名称（默认取第一个对象）

    返回 dict 包含：
        instances: 识别到的通槽实例列表（cell_id 空间）
        cell_ids: NCTI cell_id 列表（用于高亮）
        obj_names: NCTI 对象名列表（与 cell_ids 一一对应）
        obj_name: 主对象名
    """
    names = list(doc.AllNames() or [])
    if not names:
        raise ValueError("当前文档中没有可识别对象，请先导入模型。")

    if obj_name is None:
        obj_name = names[0]

    # NCTI-native 识别（直接在 cell_id 空间）
    result = recognize_through_steps_ncti(ncti, doc, obj_name)

    # 构建 cell_ids / obj_names
    cell_ids = result["selected_cells"]
    obj_names = [obj_name] * len(cell_ids)

    # 去重（应该已经唯一，但保险）
    seen = set()
    unique_pairs = []
    for name, cid in zip(obj_names, cell_ids):
        key = (name, cid)
        if key not in seen:
            seen.add(key)
            unique_pairs.append((name, cid))

    obj_names = [name for name, _ in unique_pairs]
    cell_ids = [cid for _, cid in unique_pairs]

    # 打印结果
    instance_count = len(result["instances"])
    mapped_count = len(cell_ids)
    print("NCTI-native 通槽数量: {}, 映射面数量: {}".format(instance_count, mapped_count))

    for i, inst in enumerate(result["instances"], 1):
        fillet_str = ""
        if inst.get("fillets"):
            fillet_str = "，圆角 {}".format(inst["fillets"])
        n_neighbors = inst.get("bottom_neighbor_count", "?")
        print("  #{}: faces={}, bottom=#{}, walls={}, score={:.1f}, bottom_neighbors={}{}".format(
            i,
            inst["faces"],
            inst["bottom_face"],
            inst["side_walls"],
            inst.get("score", 0),
            n_neighbors,
            fillet_str,
        ))

    result.update({
        "cell_ids": cell_ids,
        "obj_names": obj_names,
        "obj_name": obj_name,
    })
    return result
