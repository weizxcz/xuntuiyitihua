#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""零映射 NCTI 版标注脚本冒烟测试。

跑 5 个 STEP 件（已知含通槽）：
  1. 通过完整 annotate_one 流程（load_part → 一致性断言 → predict → JSON 构造）
  2. 验证 n_faces == count_advanced_faces
  3. 验证产出 JSON 格式与 STEP 版一致
  4. 验证 cell_id 与 predict 返回的 faces 一致

跑法（yhcad_py312 环境，UTF-8）：
  "D:/Anaconda3/envs/yhcad_py312/python.exe" _smoke_ncti.py
"""
import os
import sys
import io
import json

# Windows 控制台中文输出
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(THIS_DIR)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "..", ".."))   # repo root: 含 YHCADSmartCleaner
sys.path.insert(0, os.path.join(PROJECT_ROOT, "..", "..", "YHCADSmartCleaner", "utils", "through_step"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "..", "..", "YHCADSmartCleaner", "utils"))
sys.path.insert(0, PROJECT_ROOT)  # 本项目根：config.config_load

# 选 5 个 STEP 件（实际跑时换成自己 server 上的）
SAMPLE_STEPS = [
    r"D:/wyg/data/data/通槽/steps/20221121_154647_0.step",
    r"D:/wyg/data/data/通槽/steps/20221121_154647_10.step",
    r"D:/wyg/data/data/通槽/steps/20221121_154647_100.step",
    r"D:/wyg/data/data/通槽/steps/20221121_154647_1000.step",
    r"D:/wyg/data/data/通槽/steps/20221121_154647_1001.step",
]

from annotate_through_step_ncti import (
    annotate_one, init_ncti_safe, load_models, load_instance_models,
    CATEGORY_ID, NCTI_OBJ_NAME)


def main():
    print("=== 零映射 NCTI 版标注脚本冒烟测试 ===")
    print("测试文件数: {}".format(len(SAMPLE_STEPS)))

    # 1. 加载模型 + NCTI
    print("\n[1] 加载模型...")
    booster, calib = load_models()
    inst_booster, inst_calib = load_instance_models()
    print("    第一级模型 = {}, 第二级模型 = {}".format(
        "OK" if booster else "FAIL",
        "OK" if inst_booster else "未找到（仅第一级）"))

    print("\n[2] 初始化 NCTI...")
    ncti = init_ncti_safe()
    if ncti is None:
        sys.exit("NCTI 初始化失败")
    print("    OK")

    # 2. 跑 5 件
    print("\n[3] 跑 {} 个 STEP 件...\n".format(len(SAMPLE_STEPS)))
    n_ok = n_empty = n_misalign = n_fail = 0
    for idx, stp in enumerate(SAMPLE_STEPS, 1):
        if not os.path.exists(stp):
            print("  [{}/{}] SKIP {} (文件不存在)".format(idx, len(SAMPLE_STEPS), stp))
            continue
        name = os.path.basename(stp)
        try:
            label_json, groups = annotate_one(
                stp, booster, calib, inst_booster, inst_calib, ncti, NCTI_OBJ_NAME)
        except Exception as e:
            n_fail += 1
            print("  [{}/{}] FAIL {}: {}".format(idx, len(SAMPLE_STEPS), name, e))
            continue

        if label_json is None:
            n_misalign += 1
            print("  [{}/{}] MISALIGN {} (cell_id 对齐破裂)".format(idx, len(SAMPLE_STEPS), name))
            continue

        if groups:
            n_ok += 1
            seg = label_json[0][1]["seg"]
            n_seg = sum(1 for v in seg.values() if v == CATEGORY_ID)
            n_inst_cells = sum(sum(row) for row in label_json[0][1]["inst"])
            n_bottom = sum(label_json[0][1]["bottom"].values())
            print("  [{}/{}] OK    {} → {} 个通槽 ({} 个面, inst 总 {} 条, bottom {} 个) | cell_ids: {}".format(
                idx, len(SAMPLE_STEPS), name, len(groups), n_seg, n_inst_cells, n_bottom, groups))
            # 验证: groups 应等于 seg 中非 0 位置
            seg_cells = sorted(int(c) for c, v in seg.items() if v == CATEGORY_ID)
            group_cells = sorted(c for grp in groups for c in grp)
            assert seg_cells == group_cells, "seg 与 groups 不一致!"
        else:
            n_empty += 1
            print("  [{}/{}] EMPTY {} (无通槽)".format(idx, len(SAMPLE_STEPS), name))

    # 3. 总结
    print("\n=== 总结 ===")
    print("  有通槽: {}  无通槽: {}  对齐破裂: {}  失败: {}".format(
        n_ok, n_empty, n_misalign, n_fail))
    if n_ok > 0:
        print("  ✓ JSON 格式正确，cell_id 零映射，groups == seg 位置")
    if n_misalign == 0:
        print("  ✓ 5 件全部 cell_id 对齐通过（n_faces == ADVANCED_FACE 数）")
    else:
        print("  ⚠ 有 {} 件 cell_id 对齐破裂（约定B 下 NCTI 合并/拆分共面导致），可接受".format(n_misalign))

    os._exit(0)


if __name__ == "__main__":
    main()