"""YHCADSmartCleaner 识别/清理能力的 Agent 工具层（M2，架构 A 落地）。

同构于 ``app.sketch/``：把 YHCADSmartCleaner 的识别/清理封装成确定性
LangChain 工具，经 ``config.yaml`` 的 ``tools:`` 注册，再由 cad-feature-cleaner
子 Agent 调用。

架构 A（Phase 0 spike v4 已证明无头可用）：后端进程外调
``cad_feature/cli/recognition_cli.py``（自包含于 NTIC-CAX-Agent，NCTI SDK 路径经
``NCTI_SDK_PATH`` 注入，同机 Windows + wygcleaner 环境），不依赖宿主 NCTI 应用
或 YHCADSmartCleaner 仓库。``runner.py`` 用 subprocess 调 CLI；``kernel.py`` 持有
CLI 路径 / Python 解释器 / SDK 路径配置（经环境变量或 set_cad_feature_config 注入）。
"""

from app.cad_feature.kernel import (
    CadFeatureConfig,
    clear_cad_feature_config,
    get_cad_feature_config,
    set_cad_feature_config,
)
from app.cad_feature.runner import CadFeatureRunnerError, clean, recognize
from app.cad_feature.tools import clean_cad_features_tool, recognize_cad_features_tool

__all__ = [
    "CadFeatureConfig",
    "set_cad_feature_config",
    "get_cad_feature_config",
    "clear_cad_feature_config",
    "recognize",
    "clean",
    "CadFeatureRunnerError",
    "recognize_cad_features_tool",
    "clean_cad_features_tool",
]
