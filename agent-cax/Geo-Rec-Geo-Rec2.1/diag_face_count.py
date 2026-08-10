#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""诊断：拆分后的 STEP 文件，【NCTI 建图面数】vs【STEP 文本面数】是否一致。

用法（在 Geo-Rec 项目根目录运行）:
    python diag_face_count.py <拆分后的step文件> [<另一个step> ...]

输出三类面数的对比，定位差异来源：
  - STEP 文本 ADVANCED_FACE 数（纯文本计数，= 导出时的"拆分后面数"）
  - NCTI AiModel FaceID 数（= 建图时的"NCTI 解析面数"）
  - 若提供标签 JSON：标签 seg 的面数
"""
import sys
import os
import re


def count_text_faces(step_path):
    """STEP 文本里 ADVANCED_FACE 的数量。"""
    with open(step_path, "r", errors="replace") as f:
        content = f.read()
    return len(re.findall(r"ADVANCED_FACE\b", content))


def count_ncti_faces(step_path):
    """NCTI AiModel 的 FaceID 数量（与建图脚本同一套导入逻辑）。"""
    from src.utils.base_functions import init_ncti
    ncti = init_ncti()
    doc = ncti.Document()
    doc.New("OCC", "DCM", 0)
    doc.RunCommand("cmd_ncti_import_file", str(step_path), "testbox")
    ai = ncti.AiModel(doc, "testbox")
    n = len(ai.FaceID)
    try:
        doc.Delete()
    except Exception:
        pass
    return n


def count_label_faces(step_path):
    """同名标签 JSON 里 seg 的面数（若有）。"""
    import json
    stem = os.path.splitext(os.path.basename(step_path))[0]
    # 常见标签目录候选（按需改）
    cands = [
        r"D:/wyg/data/data/通槽/label/{}.json".format(stem),
        os.path.join(os.path.dirname(step_path), stem + ".json"),
    ]
    for c in cands:
        if os.path.isfile(c):
            with open(c, "r", encoding="utf-8") as f:
                d = json.load(f)
            inner = d[0][1] if isinstance(d, list) and d and isinstance(d[0], list) else (d[0] if isinstance(d, list) else d)
            return len(inner.get("seg", {})), c
    return None, None


def main():
    if len(sys.argv) < 2:
        print("用法: python diag_face_count.py <step文件> [<step> ...]")
        sys.exit(1)

    for p in sys.argv[1:]:
        if not os.path.isfile(p):
            print("文件不存在: {}".format(p))
            continue
        t = count_text_faces(p)
        n = count_ncti_faces(p)
        lcount, lpath = count_label_faces(p)
        print("\n=== {} ===".format(os.path.basename(p)))
        print("  STEP 文本 ADVANCED_FACE 数 : {}".format(t))
        print("  NCTI AiModel FaceID 数      : {}".format(n))
        if lcount is not None:
            print("  标签 seg 面数 ({}): {}".format(os.path.basename(lpath), lcount))
        else:
            print("  标签 seg 面数               : (未找到同名 JSON)")
        if t == n:
            verdict = "文本==NCTI：建图没问题；若与标签不符，是【标签】侧面数/索引不对齐"
        elif t > n:
            verdict = "NCTI 少 {} 个：导入时【合并共面 / 丢弃退化面】（STEP 往返归一化）".format(t - n)
        else:
            verdict = "NCTI 多 {} 个：导入时【拆分面（如圆柱接缝）】".format(n - t)
        print("  => " + verdict)


if __name__ == "__main__":
    main()
