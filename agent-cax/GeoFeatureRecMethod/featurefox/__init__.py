#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""FeatureFox：盲孔(seg=12) / 通槽(seg=9) 两级 XGBoost 识别管线。

子包:
    lib/       — 核心库（NCTI 后端 + 特征提取 + 标签处理）
    scripts/   — 训练 / 预测 / 评估 / 标注脚本
    workers/   — 多进程子任务 worker
    debug/     — 单文件诊断 / holdout 分析（STEP-parser 版本）
    bridge/    — GUI 桥接层（on_find_through_step_featurefox）
    models/    — 训练好的 XGBoost 模型文件

用法:
    from featurefox.lib import build_face_graph, FEATURE_NAMES
    from featurefox.scripts.predict import load_models, predict_through_slots
"""
