#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""FeatureFox-NCTI: NCTI 原生数据源的 FeatureFox 通槽识别（零映射版）。

基于 FeatureFox (Fuchs et al., 2026, arXiv:2604.26770) 路线，数据源从 STEP 文本
换成 NCTI AiModel（FaceAttr/EdgeAttr），输出 cell_id（ai.FaceID 位置索引）零映射，
直接对齐 Geo-Rec 训练图节点空间，是多特征 scale 到 Geo-Rec 训练的地基。

模块结构:
    ncti_backend.py      — NCTI 数据后端（NctiPart + NctiFaceAttrs + load_part）
    edge_features.py     — 边特征提取（30维，数据来自 NctiPart）
    instance_data.py     — 加载标签 + 生成边训练数据（零映射）
    train.py             — 训练 XGBoost 边分类器 + 等渗校准
    predict.py           — 预测通槽实例（输出 cell_id，零映射）
    instance_features.py — 实例级聚合特征（26维，第二级）
    train_instance.py    — 训练第二级实例分类器（组件同源）
    evaluate.py          — 评估 P/R/F1（零映射，直接比 seg9）
"""

# 特征名顺序（与 edge_features.FEATURE_NAMES 一致）
from .edge_features import FEATURE_NAMES, build_face_graph  # noqa: F401,E402
