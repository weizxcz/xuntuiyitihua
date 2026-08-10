#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""FeatureFox 核心库：数据后端 + 特征提取 + 标签处理 + 环境配置。

模块:
    _env                — 环境配置（统一路径解析，支持环境变量覆盖）
    geom_helpers        — 纯几何工具（无外部依赖）
    ncti_backend        — NCTI 数据后端（NctiPart + NctiFaceAttrs + load_part）
    ncti_faceid_map     — NCTI 初始化 + STEP↔NCTI 面映射
    face_registration   — STEP↔NCTI 面几何配准
    edge_features       — 30维边特征提取
    instance_data       — 标签加载 + 训练数据生成
    instance_features   — 26维实例特征提取
"""

from ._env import (
    FEATUREFOX_ROOT,
    get_project_root,
    get_steps_dir,
    get_labels_dir,
    get_models_dir,
    setup_syspath,
)
from .edge_features import FEATURE_NAMES, build_face_graph
from .instance_features import INSTANCE_FEATURE_NAMES, extract_instance_features
from .ncti_backend import NctiPart, NctiFaceAttrs, load_part, count_advanced_faces
from .ncti_faceid_map import init_ncti_safe
from .instance_data import load_label, list_step_files, STEPS_DIR, LABELS_DIR

__all__ = [
    # 环境配置
    "FEATUREFOX_ROOT",
    "get_project_root",
    "get_steps_dir",
    "get_labels_dir",
    "get_models_dir",
    "setup_syspath",
    # 特征
    "FEATURE_NAMES",
    "build_face_graph",
    "INSTANCE_FEATURE_NAMES",
    "extract_instance_features",
    # 数据后端
    "NctiPart",
    "NctiFaceAttrs",
    "load_part",
    "count_advanced_faces",
    # NCTI
    "init_ncti_safe",
    # 数据
    "load_label",
    "list_step_files",
    "STEPS_DIR",
    "LABELS_DIR",
]
