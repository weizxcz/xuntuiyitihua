"""cad_feature 的「内核可达性」配置。

在 sketch 里，KernelRuntime 桥表示「宿主 NCTI 应用是否注册」；在 cad_feature
里，等价概念是「cad_feature 无头 CLI（cli/recognition_cli.py）是否可达」
（路径 + Python 解释器 + NCTI SDK 路径）。

配置来源（优先级从高到低）：
  1. ``set_cad_feature_config(...)`` 显式注入（gateway 启动时调用）。
  2. 环境变量 ``CAD_FEATURE_CLI`` / ``CAD_FEATURE_PYTHON`` / ``CAD_FEATURE_TIMEOUT``
     / ``NCTI_SDK_PATH``。
  3. 默认值（CLI 在本包 cli/ 子目录，python=当前解释器，sdk 取自 NCTI_SDK_PATH）。
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

#: recognition_cli.py 的默认相对位置（本包内的 cli/ 子目录，自包含于 NTIC-CAX-Agent）
_DEFAULT_CLI = os.path.normpath(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "cli", "recognition_cli.py",
    )
)


@dataclass
class CadFeatureConfig:
    cli_path: str
    python_path: str
    timeout: int = 300
    sdk_path: str | None = None  # NCTI SDK 目录；经 runner 注入子进程 env NCTI_SDK_PATH


_config: CadFeatureConfig | None = None


def set_cad_feature_config(
    cli_path: str,
    python_path: str | None = None,
    timeout: int = 300,
    sdk_path: str | None = None,
) -> None:
    """显式注入 CLI 路径 / Python 解释器 / NCTI SDK 路径（gateway 启动时调用）。"""
    global _config
    _config = CadFeatureConfig(
        cli_path=cli_path,
        python_path=python_path or sys.executable,
        timeout=timeout,
        sdk_path=sdk_path,
    )


def get_cad_feature_config() -> CadFeatureConfig:
    """返回配置；未显式注入时从环境变量惰性构造。"""
    global _config
    if _config is not None:
        return _config
    cli = os.environ.get("CAD_FEATURE_CLI") or _DEFAULT_CLI
    python = os.environ.get("CAD_FEATURE_PYTHON") or sys.executable
    try:
        timeout = int(os.environ.get("CAD_FEATURE_TIMEOUT", "300"))
    except ValueError:
        timeout = 300
    sdk = os.environ.get("NCTI_SDK_PATH") or None
    _config = CadFeatureConfig(cli_path=cli, python_path=python, timeout=timeout, sdk_path=sdk)
    return _config


def clear_cad_feature_config() -> None:
    global _config
    _config = None
