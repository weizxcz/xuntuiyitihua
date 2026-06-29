#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""通槽识别共享几何工具函数（无 STEP/NCTI 依赖）。"""

import math


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _angle_between_normals(n1, n2):
    """两个法向量之间的夹角（度），忽略方向。"""
    d = abs(_dot(n1, n2))
    d = max(-1.0, min(1.0, d))
    return math.degrees(math.acos(d))


def _vec_len(v):
    """向量长度。"""
    return math.sqrt(sum(x * x for x in v))


def _project_to_plane(vec, plane_normal):
    """将向量投影到平面（去除法向量分量）。"""
    d = _dot(vec, plane_normal)
    return tuple(vec[k] - d * plane_normal[k] for k in range(3))
