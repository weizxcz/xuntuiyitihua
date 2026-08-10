#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""FeatureFox 环境配置 —— 统一路径解析。

所有脚本/worker 通过此模块获取项目根路径和数据路径，而非各自硬编码。
优先级：环境变量 > 函数参数 > 兜底（用户主目录下的 featurefox_data/）。

> 旧版隐式回退到 `featurefox/../YHCADSmartCleaner/` 已移除 —— 提交独立仓库后该兄弟目录不存在。
> debug/_env.py:24-30 改为返回空字符串并打 warning，不强依赖。
"""

import os
import sys
import warnings

# featurefox 包根目录（lib/ 的父目录）
FEATUREFOX_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def get_project_root():
    """返回 YHCADSmartCleaner 项目根路径（可选；仅 debug 脚本需要）。

    优先级:
      1. 环境变量 NCTI_PROJECT_ROOT
      2. 回退：featurefox/ 同级 YHCADSmartCleaner/（保留兼容，警告）
      3. 回退：空字符串（debug 脚本应早 fail 提示用户）
    """
    env = os.environ.get("NCTI_PROJECT_ROOT", "").strip()
    if env:
        return env
    legacy = os.path.join(os.path.dirname(FEATUREFOX_ROOT), "YHCADSmartCleaner")
    if os.path.isdir(legacy):
        warnings.warn(
            "自动发现 YHCADSmartCleaner 兄弟目录（{0}）。如需稳定，建议设置环境变量 NCTI_PROJECT_ROOT".format(legacy),
            DeprecationWarning,
            stacklevel=2,
        )
        return legacy
    return ""


def get_steps_dir():
    """返回 STEP 文件目录。环境变量 FEATUREFOX_STEPS_DIR 可覆盖。

    兜底: $HOME/featurefox_data/steps/（用户主目录下，首次使用可手动创建）
    """
    env = os.environ.get("FEATUREFOX_STEPS_DIR", "").strip()
    if env:
        return env
    return os.path.join(os.path.expanduser("~"), "featurefox_data", "steps")


def get_labels_dir():
    """返回标签 JSON 目录。环境变量 FEATUREFOX_LABELS_DIR 可覆盖。

    兜底: $HOME/featurefox_data/labels/
    """
    env = os.environ.get("FEATUREFOX_LABELS_DIR", "").strip()
    if env:
        return env
    return os.path.join(os.path.expanduser("~"), "featurefox_data", "labels")


def get_models_dir():
    """返回模型文件目录。环境变量 FEATUREFOX_MODELS_DIR 可覆盖。

    兜底: featurefox/models/（随仓库入库）
    """
    env = os.environ.get("FEATUREFOX_MODELS_DIR", "").strip()
    if env:
        return env
    return os.path.join(FEATUREFOX_ROOT, "models")


def setup_syspath():
    """确保 featurefox 和 project_root 在 sys.path 中（脚本/worker 启动时调用）。"""
    for _p in (FEATUREFOX_ROOT, get_project_root()):
        if _p and _p not in sys.path:
            sys.path.insert(0, _p)


if __name__ == "__main__":
    # 冒烟测试：打印所有解析结果
    print("FEATUREFOX_ROOT  :", FEATUREFOX_ROOT)
    print("get_project_root :", repr(get_project_root()))
    print("get_steps_dir    :", get_steps_dir())
    print("get_labels_dir   :", get_labels_dir())
    print("get_models_dir   :", get_models_dir())
