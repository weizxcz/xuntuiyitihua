#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""验证 NCTI 环境能否正常加载和识别。"""

import os
import sys

SDK = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "SDK"))
sys.path.insert(0, SDK)
os.add_dll_directory(SDK)
os.add_dll_directory(os.path.join(SDK, "OCC"))

import ctypes
for dll in [
    "ncti_command.dll",
    "ncti_occ_plugin.dll",
    "ncti_doc_occ.dll",
    "ncti_render_vulkan.dll",
    "ncti_window.dll",
]:
    ctypes.CDLL(os.path.join(SDK, dll))

import ncti_python
ncti_python.Init(SDK)
print("NCTI Init OK")

doc = ncti_python.Document()
print("Document created OK")

# 模拟 import_file_dialog 的前置调用
doc.ResetCaseResult()
doc.SetCreateGeGeom(1)
doc.SetImportAssemelFile(1)

step_path = r"D:\wyg\data\data\通槽\steps\20221121_154647_1.step"
print(f"Loading: {step_path}")
ret = doc.RunCommand("cmd_ncti_import_file", step_path)
print(f"import ret: {ret}")

names = list(doc.AllNames() or [])
print(f"names: {names}")

if names:
    obj = names[0]
    ai = ncti_python.AiModel(doc, obj)
    print(f"FaceAttr len: {len(ai.FaceAttr)}")
    print(f"EdgeAttr len: {len(ai.EdgeAttr)}")
    print(f"FaceID: {ai.FaceID[:5]}...")

    # 测试 NCTI-native 通槽识别
    project_root = os.path.join(os.path.dirname(__file__), "..", "..")
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from utils.through_step.detect_through_step_ncti import recognize_through_steps_ncti
    result = recognize_through_steps_ncti(ncti_python, doc, obj)
    print(f"\n识别结果:")
    print(f"  实例数: {len(result['instances'])}")
    print(f"  选中面: {result['selected_cells']}")
    for i, inst in enumerate(result["instances"], 1):
        print(f"  #{i}: faces={inst['faces']}, score={inst.get('score',0):.1f}, "
              f"type={inst.get('type','?')}")
else:
    print("导入失败，names 为空")

print("\nDone.")
# 防止退出时 segfault
os._exit(0)
