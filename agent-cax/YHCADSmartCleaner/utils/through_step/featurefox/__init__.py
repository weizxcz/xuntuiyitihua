#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""FeatureFox: 数据驱动的通槽识别（XGBoost 边分类 + 图剪枝）。

基于 FeatureFox (Fuchs et al., 2025) 路线，适配我们的 STEP 文本解析器。

模块结构:
    edge_features.py   — 从 STEP 提取边特征向量
    face_graph.py      — 构建带属性的面邻接图 (AAG)
    instance_data.py   — 加载标签 + 生成边训练数据
    train.py           — 训练 XGBoost 边分类器 + 等渗校准
    predict.py         — 预测通槽实例（边剪枝 + 连通分量）
    evaluate.py        — 评估 P/R/F1
"""

# 特征名顺序（与 edge_features.FEATURE_NAMES 一致）
from .edge_features import FEATURE_NAMES, build_face_graph
