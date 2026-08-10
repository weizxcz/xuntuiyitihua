# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

YHCADSmartCleaner 是一款面向 CAD/CAE 工程师的桌面端几何特征识别与清理工具。基于 wxPython 构建 GUI，集成炎核 SDK（OCC 几何引擎 + GMSH 网格引擎 + Vulkan 渲染引擎）和 AAGNet AI 模型，支持对 B-Rep CAD 模型的圆角、倒角、盲孔等特征的智能识别与清理。

## 构建与运行

```bash
# 运行应用（需要先在 config/system_config.json 中配置 SDK DLL 路径）
python main.py

# 安装依赖
pip install -r requirements.txt  # 当前仅有 wxPython~=4.2.4；AI 依赖：torch, dgl, numpy, scipy

# PyInstaller 打包（调试版）
pyinstaller --name=SmartClearner --icon=icons/ncti.ico --onedir main.py --add-data=icons:icons --add-data=SDK:SDK --add-data=config/system_config.json:config --add-data=ai/AAGNet_infer/weights:ai/AAGNet_infer/weights --hidden-import=scipy._lib.array_api_compat.numpy.fft --hidden-import=scipy._lib.array_api_compat.numpy --hidden-import=scipy._lib.array_api_compat

# PyInstaller 打包（发布版，无控制台窗口）
pyinstaller --name=SmartClearner --windowed --icon=icons/ncti.ico --onedir main.py --add-data=icons:icons --add-data=SDK:SDK --add-data=config/system_config.json:config --add-data=ai/AAGNet_infer/weights:ai/AAGNet_infer/weights --hidden-import=scipy._lib.array_api_compat.numpy.fft --hidden-import=scipy._lib.array_api_compat.numpy --hidden-import=scipy._lib.array_api_compat --hidden-import=scipy.special._special_ufuncs
```

本项目没有测试。

## 架构

### 入口与初始化

`main.py` 创建 wxPython 应用并启动 `CAEPlatform` 主窗口。在导入阶段，`config/config_load.py` 读取 `config/system_config.json`，将 SDK DLL 路径加入 `sys.path`，加载原生 DLL，并将 NCTI 模块初始化到 `global_scope["NCTI"]`，同时创建全局文档 `global_scope["doc"]`。

### 核心 UI 层（`ui/`）

- **`main_window.py`**（`CAEPlatform`）：唯一的主窗口框架。包含所有功能区选项卡（文件、常规、AI）、工具栏、事件处理器，协调对话框与功能模块的交互。持有 `self.NCTI`、`self.doc`、`self.cad_view` 和模型权重路径的引用。
- **`viewer.py`**（`CADViewer`）：一个 `wx.Panel`，通过 `view.CreateWindow(hwnd)` 嵌入原生 Vulkan 3D 渲染窗口。负责几何更新和尺寸调整。
- **`property_panel.py`** / **`assembly_panel.py`**：侧边面板（当前使用较少）。

### 业务逻辑层（`function/`）

每个特征有三种识别策略——几何方法（`on_find_fillet.py`）、AI 方法（`on_find_fillet_by_ai.py`）、混合方法（`on_find_fillet_hyper.py`）。流程一致：
1. 重置文档状态 → 调用识别算法 → 获取 `(cell_ids, obj_names)` → 显示选中 → 可选打开特征列表对话框。

特征移除在 `on_remove_feature.py` 中实现，调用 `doc.RunCommand("cmd_ncti_remove_features", ...)`。

### AI 模块（`ai/`）

- **`ai_recognizer.py`**：编排 AAGNet 推理流程。通过 `ncti.AiModel` 从 CAD 面提取邻接图，归一化几何数据，运行模型，使用基于邻接关系的分组进行后处理。支持局部选择（扩展到相邻面，然后压缩/解压索引）。
- **`AAGNet_infer/`**：AAGNet 模型实现（用于 B-Rep 面分割的图神经网络）。`base_utils.py` 中的 `AAGNetInference` 加载 `.pth` 权重，构建 DGL 图，运行推理，使用自适应阈值（Otsu + 直方图 + 梯度 + 双峰 + 密度方法）进行后处理。模型权重在 `AAGNet_infer/weights/` 目录。
- **`brep_mfr/`**：备选 BRep 分割模型（当前在主窗口中已注释掉）。

### 几何工具（`utils/`）

- **`b_face_classify.py`**：纯 numpy 实现的曲面类型分类器——平面（按法线/点集/两者）、圆柱面（按法线、按点集+法线）、圆锥面（按法线、按点集+法线+最小二乘拟合）。
- **`sampler.py`**：在 CAD 面上进行随机 UV 采样，通过 `doc.GetFacePointFromUV` / `doc.GetNormalByUV` 获取点云和法线。
- **`reindex.py`**（`IndexManager`）：在删除/导出/重新导入流程中跟踪面 ID，使用中点作为稳定引用。

### 对话框层（`dialog/`）

wxPython 对话框，用于文件 I/O、特征展示、参数输入。大多基于 `select_file_base.py` 扩展。

## 关键约定

- **NCTI SDK 交互**：所有 CAD 操作通过 `self.NCTI`（从原生 DLL 加载）和 `self.doc`（`NCTI.Document` 实例）进行。常用调用：`doc.RunCommand(...)`、`doc.FindAllFaces(...)`、`ncti.AiModel(...)`、`ncti.SelectionManager(...)`。
- **特征识别流程**：每种特征类型有三种策略——几何方法（对采样点/法线做纯数学计算）、AI 方法（AAGNet 图推理）、混合方法（AI + 几何过滤）。
- **UI 事件绑定**：工具栏按钮通过 `wx.NewIdRef()` 创建，通过 `toolbar.Bind(wx.EVT_TOOL, handler, id=button_id)` 绑定。
- **`config/system_config.json`** 中的 `dllPath` 必须指向 SDK 目录。该文件已加入 `.gitignore`，每位开发者需在本地配置。
- **AI 模型权重**（`ai/AAGNet_infer/weights/` 中的 `.pth` 文件）在运行时按特征类型加载。每种特征类型有独立的权重文件和统计 JSON。
- **代码注释和 UI 文本均使用中文**，请保持此约定。

# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
