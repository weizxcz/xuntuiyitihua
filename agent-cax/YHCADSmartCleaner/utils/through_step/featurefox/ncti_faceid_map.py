#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""STEP face → NCTI ai.FaceID 位置索引映射（= Geo-Rec 训练标签 cell_id 空间）。

本模块是 through_step 里 STEP-face 识别器（detect_through_step.py）、FeatureFox
评估（featurefox/evaluate.py）与 GUI 高亮桥接（on_find_through_step_featurefox.py）
共用的 NCTI 对齐层，避免同一映射逻辑在多处拷贝时产生分歧。

═══════════════════════════════════════════════════════════════════════
为什么单独成模块（历史教训）
═══════════════════════════════════════════════════════════════════════
同一映射曾有 4 份拷贝，其中 GetFaceMidPoint 的第二参数语义出现过致命分歧：

    GetFaceMidPoint(obj_name, ???)   ← ??? 到底是 entity ID 还是位置索引？

经真机 DEBUG 确认（见 on_find_through_step_featurefox.py 注释 / evaluate.py 注释）：

    ai.FaceID[i]            = 位置 i 处面的 entity ID
    GetFaceMidPoint(name, i) = 位置 i（cell_index）处面的中点
    —— entity ID 与 cell_index 是两套独立编号，不可互换！

⚠ annotate_through_step.py:205 传的是 entity ID（fid = face_ids[i]），与上述
正确语义不一致：当 entity ID ≠ 位置序号（NCTI 合并/拆分面后常见）时，它取到的
是「错位面的中点」，最近邻匹配随之错位 → 生成的训练标签 cell_id 与 Geo-Rec 训练图
错位。本模块锁定「位置索引」这一经 DEBUG 验证的正确语义。

═══════════════════════════════════════════════════════════════════════
NCTI 导入序列（与 Geo-Rec 训练建图严格一致 ——「约定 A」）
═══════════════════════════════════════════════════════════════════════
证据：Geo-Rec-Geo-Rec2.1/src/data_utils/transforms/step2graph_mfr_ncti.py:92-101

    doc = ncti.Document()
    doc.New("OCC", "DCM", 0)                                 # 第三参数是整数 0
    doc.RunCommand("cmd_ncti_import_file", stp_path, "testbox")  # 带 obj_name
    ai  = ncti.AiModel(doc, "testbox")

禁止调用 SetImportAssemelFile(1) / ResetCaseResult / SetCreateGeGeom（「约定 B」，
见 through_step/CLAUDE.md 的 test_batch_50_ncti 路径）——SetImportAssemelFile(1)
会拆分装配体、改变面数，导致同一 STEP 的 cell_id 空间与训练标签完全错位。

═══════════════════════════════════════════════════════════════════════
cell_id 定义（核心）
═══════════════════════════════════════════════════════════════════════
cell_id = 面在 ai.FaceID 列表中的【位置索引 i】（0..n-1）= Geo-Rec 图节点下标，
【不是】FaceID 的值本身，也【不是】doc.FindAllFaces 的顺序。

决定性证据：step2graph_mfr_ncti.py:315 feature_labels = np.zeros(len(ai.FaceID))，
:321-329 把 seg dict 的 key 直接当 feature_labels 的下标写入。故训练标签 JSON
[[name, {"seg": {cell_id: 9}, "inst": NxN, "bottom": {}}]] 中的 cell_id 即位置索引。
"""

import os
import sys


# =============================================================================
# 基础工具
# =============================================================================

def _point_to_tuple(pt):
    """NCTI 点 → (x, y, z)。

    GetFaceMidPoint 返回 Point 对象（只能 .X/.Y/.Z，不可下标），这里同时兼容
    Point 与普通序列，避免静默失败导致整张映射为空。
    """
    try:
        return (float(pt.X), float(pt.Y), float(pt.Z))
    except (AttributeError, TypeError):
        return (float(pt[0]), float(pt[1]), float(pt[2]))


# =============================================================================
# NCTI 初始化与导入
# =============================================================================

def init_ncti_safe(project_root=None):
    """初始化 NCTI 引擎，失败返回 None。

    project_root 为含 config/config_load.py 的项目根（detect_through_step.py 所在的
    YHCADSmartCleaner 根）。该 config_load.init_ncti_config() 返回 NCTI 模块或 None。
    """
    if project_root and project_root not in sys.path:
        sys.path.insert(0, project_root)
    try:
        from config.config_load import init_ncti_config  # type: ignore
    except Exception as e:
        sys.stderr.write("config.config_load 不可用（project_root={}）: {}\n".format(
            project_root, e))
        return None
    try:
        return init_ncti_config()
    except Exception as e:
        sys.stderr.write("init_ncti_config 失败: {}\n".format(e))
        return None


def import_step_to_ncti(ncti, stp_path, obj_name="testbox"):
    """把 STEP 导入 NCTI（与训练建图一致的「约定 A」）。返回 (doc, ai)。

    调用方负责在用完后 doc.Clear()（多文件批处理时每文件必须重置，否则面 ID 跨文件
    累积导致 cell_id 错位）。
    """
    doc = ncti.Document()
    doc.New("OCC", "DCM", 0)
    ok = doc.RunCommand("cmd_ncti_import_file", str(stp_path), obj_name)
    if not ok:
        raise RuntimeError("NCTI 导入失败: {}".format(stp_path))
    ai = ncti.AiModel(doc, obj_name)
    return doc, ai


# =============================================================================
# STEP face → NCTI 位置索引 映射（核心）
# =============================================================================

def build_step_face_to_ncti_pos_map(step_face_centroids, doc, ncti, obj_name, tol=None):
    """STEP face_id → ai.FaceID 位置索引（= Geo-Rec 训练标签 cell_id）。

    参数:
      step_face_centroids: {step_face_id: (x, y, z)}
          调用方按自己的面重心来源构造（detect_through_step.py 用 _face_centroid，
          FeatureFox 用 fa_attrs.centroid）。本函数与重心来源解耦，只吃一个 dict。
      doc / ncti / obj_name: 已用 import_step_to_ncti 导入 STEP 的 NCTI 文档。
      tol: 匹配容差（欧氏距离）；None 时用 STEP 重心包围盒对角线 × 0.15（自适应，
          覆盖 STEP↔NCTI tessellation 差异）。

    返回 (pos_map, n_faces):
      pos_map[step_face_id] = cell_index（位置索引，即训练标签 cell_id）
      n_faces = len(ai.FaceID)

    算法（双向最近邻 + 自适应容差）:
      1. NCTI 侧：每个位置 i 取 GetFaceMidPoint(obj_name, i) 中点（i=位置索引，非 entity ID）
      2. STEP 侧：每个面取重心
      3. 每个 STEP 面找最近 NCTI 位置，要求距离 ≤ tol
      4. 互为最近邻：NCTI 合并共面时多个 STEP 面指向同一 cell_index，只保留距离最近的
         （正向「多对一合并」可处理；对称零件「一对一错配」无解，需调用方留意）

    返回的 pos_map 天然可逆，既可用于写训练标签（cell_id），也可用于把 STEP face_id
    高亮（STEP entity 更适合 OCC 渲染）。
    """
    ai = ncti.AiModel(doc, obj_name)
    face_ids = ai.FaceID
    n_faces = len(face_ids)

    # NCTI 侧：cell_index → 中点。GetFaceMidPoint(obj_name, i)，i = 位置索引（DEBUG 验证）。
    ncti_mids = {}
    for i in range(n_faces):
        try:
            pt = doc.GetFaceMidPoint(obj_name, i)
            ncti_mids[i] = _point_to_tuple(pt)
        except Exception:
            continue
    if not ncti_mids:
        return {}, n_faces

    if not step_face_centroids:
        return {}, n_faces

    # 自适应容差（零件重心包围盒对角线 × 0.15）
    if tol is None:
        all_pts = list(step_face_centroids.values())
        xs = [p[0] for p in all_pts]
        ys = [p[1] for p in all_pts]
        zs = [p[2] for p in all_pts]
        diag = ((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2
                + (max(zs) - min(zs)) ** 2) ** 0.5
        tol = diag * 0.15

    # STEP face_id → 最近的 NCTI 位置索引
    step_to_cell = {}
    for fid, sc in step_face_centroids.items():
        best_cell, best_d = None, None
        for cell_idx, npt in ncti_mids.items():
            d = (sc[0] - npt[0]) ** 2 + (sc[1] - npt[1]) ** 2 + (sc[2] - npt[2]) ** 2
            if best_d is None or d < best_d:
                best_d, best_cell = d, cell_idx
        if best_cell is not None and best_d <= tol * tol:
            step_to_cell[fid] = (best_cell, best_d)

    # 互为最近邻：NCTI 合并共面时多个 STEP 面指向同一 cell_index，只留距离最近的
    cell_to_step = {}
    for fid, (cell, _) in step_to_cell.items():
        cell_to_step.setdefault(cell, []).append(fid)
    pos_map = {}
    for fid, (cell, _) in step_to_cell.items():
        cands = cell_to_step.get(cell, [])
        if len(cands) > 1:
            best_fid = min(cands, key=lambda f: step_to_cell[f][1])
            if fid != best_fid:
                continue
        pos_map[fid] = cell
    return pos_map, n_faces


def build_pos_map_for_step(stp_path, step_face_centroids, ncti=None, obj_name="testbox",
                           project_root=None, tol=None, verbose=True):
    """一站式：init NCTI + import STEP + 建映射 + doc.Clear。

    返回 (pos_map, n_faces)。NCTI 不可用或导入失败 → (None, None)（调用方可据此
    决定降级或报错）。verbose 时打印匹配率，低于 80% 告警（防通槽关键面静默漏匹配）。
    """
    if ncti is None:
        ncti = init_ncti_safe(project_root)
    if ncti is None:
        if verbose:
            sys.stderr.write(
                "警告：NCTI 未初始化——无法对齐到 ai.FaceID 位置索引。\n"
                "  请配置 config/ncti_config.json（或 YHCADSmartCleaner 的 system config），\n"
                "  确保 ncti_python 与 NCTI 动态库可加载。\n")
        return None, None

    try:
        doc, _ai = import_step_to_ncti(ncti, stp_path, obj_name)
    except Exception as e:
        if verbose:
            sys.stderr.write("NCTI 导入失败 ({}): {}\n".format(stp_path, e))
        return None, None

    try:
        pos_map, n_faces = build_step_face_to_ncti_pos_map(
            step_face_centroids, doc, ncti, obj_name, tol=tol)
    finally:
        try:
            doc.Clear()
        except Exception:
            pass

    if verbose:
        matched = len(pos_map)
        total_step = len(step_face_centroids)
        rate = (matched / total_step * 100.0) if total_step else 0.0
        sys.stderr.write(
            "NCTI 对齐：STEP 面 {}/{} 已映射 ({}%)，NCTI 面 {} 个\n".format(
                matched, total_step, round(rate, 1), n_faces))
        if total_step and rate < 80.0:
            sys.stderr.write("  ⚠ 匹配率偏低，部分通槽面可能未对齐（标签可能缺项）\n")
    return pos_map, n_faces
