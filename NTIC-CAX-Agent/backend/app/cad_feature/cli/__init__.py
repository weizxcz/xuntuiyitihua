"""cad_feature 无头执行器子包（架构 A 落地）。

本子包**不会被** ``app.cad_feature`` 的 ``__init__`` 导入，因此即使在未安装
NCTI SDK / numpy / scikit-learn 的网关（uv）环境里扫描，也不会触发这些
重依赖。它们只在装了 NCTI SDK 的 wygcleaner 子进程内由 ``recognition_cli.py``
直接运行（subprocess）时才会被加载（依赖清单见同目录 ``requirements.txt``）。

关键点：``recognition_cli.py`` 是独立脚本，可用 ``python recognition_cli.py``
直接运行；``recognition_core.py`` 提供纯几何识别核心，无任何 YHCADSmartCleaner
依赖，便于独立仓库迁移。
"""
