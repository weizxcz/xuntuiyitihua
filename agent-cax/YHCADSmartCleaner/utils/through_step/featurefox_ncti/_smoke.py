#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""单件冲烟：验证 NctiPart 建图 + 特征符号 + 面数断言（无需训练模型）。

对一个通槽件 build_face_graph，核对：
  1. 面数断言（n_faces == STEP ADVANCED_FACE 数 → shell==ai.FaceID 假设）
  2. 凸凹性符号（通槽内部边应以 concave=+1 为主）
  3. 特征维度正确（30维）

用法（yhcad_py312 环境，从 utils/through_step/ 执行）:
    python -m featurefox_ncti._smoke
    python -m featurefox_ncti._smoke 20221121_154647_101.step
"""

import os
import sys
from collections import Counter

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
UTILS_DIR = os.path.dirname(os.path.dirname(THIS_DIR))
TS_DIR = os.path.dirname(THIS_DIR)
PROJECT_ROOT = os.path.dirname(UTILS_DIR)
for _p in (UTILS_DIR, TS_DIR, PROJECT_ROOT, THIS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from featurefox_ncti.edge_features import build_face_graph, FEATURE_NAMES  # noqa: E402
from featurefox_ncti.instance_data import list_step_files, load_label, STEPS_DIR  # noqa: E402
from ncti_backend import load_part, count_advanced_faces  # noqa: E402
from YHCADSmartCleaner.utils.through_step.featurefox.ncti_faceid_map import init_ncti_safe  # noqa: E402


def main():
    ncti = init_ncti_safe(PROJECT_ROOT)
    if ncti is None:
        sys.exit("NCTI 初始化失败：需 yhcad_py312 环境 + config/ncti_config.json。")

    # 取件：命令行指定 or 第一个含 seg=9 的件
    files = list_step_files(0, 0)
    target = sys.argv[1] if len(sys.argv) > 1 else None
    stp_path = name = None
    if target:
        fname = target if target.endswith(".step") else target + ".step"
        stp_path = os.path.join(STEPS_DIR, fname)
        name = os.path.splitext(fname)[0]
    else:
        print("扫描含 seg=9 的件（前500）...", flush=True)
        for f in files[:500]:
            nm = os.path.splitext(f)[0]
            seg9, _, _ = load_label(nm)
            if seg9:
                stp_path = os.path.join(STEPS_DIR, f)
                name = nm
                break
    if not stp_path or not os.path.exists(stp_path):
        sys.exit("未找到件（指定文件名，或确保 steps 含 seg=9 标签）")

    print("=" * 60, flush=True)
    print("冲烟: {}".format(name), flush=True)
    print("=" * 60, flush=True)

    doc = None
    try:
        part, doc = load_part(stp_path, ncti)

        # 1. 面数断言（shell==ai.FaceID 假设）
        expected = count_advanced_faces(stp_path)
        print("\n[1] 面数断言:", flush=True)
        print("    NCTI n_faces       = {}".format(part.n_faces), flush=True)
        print("    STEP ADVANCED_FACE = {}".format(expected), flush=True)
        if expected == part.n_faces:
            print("    OK 一致（shell==ai.FaceID 假设成立）", flush=True)
        else:
            print("    *** 不一致！cell_id 可能错位，需排查 NCTI 导入序列", flush=True)

        # 2. 建图
        edges, fa_attrs = build_face_graph(part)
        print("\n[2] AAG: {} 个面, {} 条边".format(part.n_faces, len(edges)), flush=True)

        # 3. 凸凹性分布（全局）
        conv_cnt = Counter(part.edge_convexity.values())
        print("\n[3] 全局凸凹性分布:", flush=True)
        for k in ("concave", "convex", "smooth"):
            print("    {:10s}: {}".format(k, conv_cnt.get(k, 0)), flush=True)

        # 4. seg=9 内部边符号（应凹为主）
        seg9, _, _ = load_label(name)
        if seg9:
            seg9_edges = [e for e in edges if e["fa"] in seg9 and e["fb"] in seg9]
            if seg9_edges:
                dih = [e["features"][0] for e in seg9_edges]  # dihedral_sign
                pos = sum(1 for d in dih if d > 0)
                neg = sum(1 for d in dih if d < 0)
                zero = sum(1 for d in dih if d == 0)
                print("\n[4] seg=9 内部边凸凹性（{}条）:".format(len(seg9_edges)), flush=True)
                print("    dihedral_sign >0 (concave 凹): {} ({:.0%})".format(
                    pos, pos / len(dih)), flush=True)
                print("    dihedral_sign <0 (convex 凸):  {} ({:.0%})".format(
                    neg, neg / len(dih)), flush=True)
                print("    dihedral_sign =0 (smooth):     {}".format(zero), flush=True)
                print("    (通槽内部应以凹边 concave 为主)", flush=True)

        # 5. dump 首条边特征（核对 30 维）
        if edges:
            e0 = edges[0]
            print("\n[5] 首条边特征 (fa={}, fb={}):".format(e0["fa"], e0["fb"]), flush=True)
            for fname, val in zip(FEATURE_NAMES, e0["features"]):
                print("    {:22s} = {:.4f}".format(fname, val), flush=True)
            assert len(e0["features"]) == len(FEATURE_NAMES), "特征维度不匹配"
            print("\n    特征维度: {} (OK)".format(len(FEATURE_NAMES)), flush=True)
    finally:
        if doc is not None:
            try:
                doc.Clear()
            except Exception:
                pass
    os._exit(0)


if __name__ == "__main__":
    main()
