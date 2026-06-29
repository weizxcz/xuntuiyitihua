# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Geo-Rec 是一个几何特征识别框架，从 CAD（B-rep/STEP）模型中提取制造特征。集成两种模型：**AAGNet**（属性邻接图）和 **BrepMFR**（基于 Transformer 编码器的 B-rep 特征识别），支持监督训练和域适应迁移学习。依赖 NCTI SDK 进行 CAD 模型解析。

## 常用命令

```bash
# 训练（模型和模式通过 configs/configs.yaml 选择）
python train_main.py

# 推理
python infer_main.py

# 可视化（仅 Windows，依赖 wxPython）
python src/visualization/visualization.py

# 单独运行数据处理流程
python src/data_workflow.py
```

本仓库无测试套件和 linter 配置。

## 配置系统

所有运行时行为由 **`configs/configs.yaml`** 驱动，无命令行参数。关键字段：

- `model_infos.model_name`：`"aagnet"` 或 `"brepMFR"`，选择模型管线
- `model_infos.brepmfr_train_mode`：`"supervised"` 或 `"domain_adapt"`，仅 brepMFR 使用
- `data_path_infos.use_absolute_path`：数据路径是绝对路径还是相对于项目根目录
- `data_path_infos.mfr_data_infos.*`：BrepMFR 专用数据路径（graphs_mfr_json、bin_data 等）
- `ncti_path_config`：NCTI SDK 路径，平台相关的 DLL/SO 位置
- `recognize_task_infos.name`：特征识别任务名（如 "round"、"blind_slot"）

模型超参数在 `configs/model_configs/<model>/` 下的独立 YAML 文件中（如 `aagnet/blind_slot_model_config.yaml`、`brepMFR/round_model_config.yaml`）。路径通过 `configs.yaml` 的 `model_infos.model_config_path`（AAGNet）或 `model_infos.brepmfr_config_path`（BrepMFR）指定。

## 架构

### 入口路由（`train_main.py`）

`train_main.py` 读取配置后分发：
- `model_name == "brepMFR"` → `data_processing_workflow_mfr()` → `brepmfr_trainer_module()`（监督）或 `brepmfr_domain_adapt_trainer_module()`（域适应）
- 其他 → `data_processing_workflow()` → `trainer_module()`（AAGNet）

### 两条模型管线

**AAGNet 管线**（`src/models/aagnet/`、`src/trainers/aagnet_train.py`）：
- 图格式：属性邻接图（AAG），含面/边属性和 UV 网格特征
- 数据加载：基于 DGL 的 `MFInstSegDataset_single_graph`，从 JSON 图文件加载
- 训练：PyTorch 原生训练循环 + EMA，使用 DGL 图
- 配置：`configs/model_configs/aagnet/*.yaml`
- 属性标准化：使用构图时计算的 `attr_stat.json`

**BrepMFR 管线**（`src/models/brepMFR/`、`src/trainers/brepmfr_train.py`）：
- 图格式：B-rep 图，含 d2_distance、a3_distance、spatial_pos、edge_path（MFR 特有）
- 数据加载：`CADSynth` 数据集从 DGL 二进制文件加载，`TransferDataset` 用于域适应
- 训练：PyTorch Lightning `Trainer`，`BrepSeg`（监督）或 `DomainAdapt`（迁移）Lightning 模块
- 域适应：DANN 框架，梯度反转层 + 域判别器 + 熵最小化
- **不使用** `attr_stat.json`，无属性标准化
- 配置：`configs/model_configs/brepMFR/*.yaml`

### 数据处理流程

**AAGNet**（`data_workflow.py` 中大部分步骤已注释）：
1. `generate_labels` → 2. `divide_train_val_test` → 3. `step2graph_batch`（AAG JSON）

**BrepMFR**（当前活跃）：
1. `generate_labels` → 2. `divide_train_val_test` → 3. `step2graph_mfr_batch`（MFR JSON）→ 4. `json_to_bin_batch`（DGL bin）→ 5. `check_and_clean_invalid` → 6. 重新执行 `divide_train_val_test`

域适应模式下，额外处理一路无标签数据（步骤 3–5），然后 `generate_domain_adapt_splits` 生成源域/目标域划分文件。

### 关键源码目录

- `src/data_utils/transforms/` — STEP→图转换器（`step2graph_ncti.py` 用于 AAG，`step2graph_mfr_ncti.py` 用于 MFR）
- `src/data_utils/processors/` — 标签生成、数据划分、JSON→bin 转换、无效数据清理
- `src/data_utils/dataloader/` — 两个模型的数据集类和 collator
- `src/utils/` — `base_functions.py`（配置加载、NCTI 初始化、日志、图工具），`extractor_mfr_ncti.py`（MFR 特征提取），`step2graph_tools_ncti.py`（AAG 图工具）
- `src/models/brepMFR/modules/` — Transformer 层、B-rep 编码器、UV-Net 编码器、位置编码
- `src/models/brepMFR/modules/domain_adv/` — DANN 组件：域判别器、梯度反转层、对抗损失

### 配置路径解析

`base_functions.load_config_basic()` 将项目根目录解析为 `base_functions.py` 往上两级目录（即仓库根目录）。当 `use_absolute_path` 为 false 时，数据路径会与该根目录拼接。各模块独立解析路径。

## NCTI 依赖

构图阶段需要 NCTI SDK 解析 STEP 文件。`base_functions.init_ncti()` 加载平台相关的共享库，在构图前调用。SDK 路径须在 `configs.yaml` 的 `ncti_path_config` 中配置。多进程场景下，`initializer()` 在每个 worker 进程中初始化 NCTI。

## 特征属性

定义在 `configs/attr_features_keys.json`：
- 面属性：平面/圆柱/圆锥/球面/环面类型、面积、有理 NURBS、质心（共 8 项，填充至 12 维）
- 边属性：凹/凸/光滑、长度、圆/闭合/椭圆/BSpline/直线类型（共 10 项）
- UV 网格：曲面 5x5，曲线 0（AAGNet 使用）

## 语言约定

代码注释、docstring、配置说明、文档均为**中文**，编辑时请保持。

---

## 编码规范（Karpathy Style）

以下行为准则旨在减少常见的 LLM 编码错误。偏向谨慎而非速度，对于简单任务请自行判断。

### 1. 先思考再编码

**不要假设。不要隐藏困惑。把权衡说清楚。**

在实现之前：
- 明确陈述你的假设。如果不确定，先问。
- 如果存在多种理解，全部列出来——不要默默选一个。
- 如果存在更简单的方案，说出来。该反驳时就反驳。
- 如果有不明白的地方，停下来。说清楚哪里不明白，然后问。

### 2. 简洁优先

**用最少的代码解决问题。不做任何推测性设计。**

- 不要添加未被要求的功能。
- 一次性代码不需要抽象。
- 不要做未被要求的"灵活性"或"可配置性"。
- 不可能发生的场景不需要错误处理。
- 如果写了 200 行但其实 50 行就够了，重写。

问自己："一个资深工程师会说这过度复杂了吗？"如果是，就简化。

### 3. 精准修改

**只改必须改的。只清理自己弄乱的。**

编辑现有代码时：
- 不要"改进"相邻的代码、注释或格式。
- 不要重构没坏的东西。
- 匹配现有风格，即使你会用不同的方式。
- 如果发现无关的死代码，提一下——不要删。

当你的改动产生了孤立代码时：
- 删除你的改动导致不再使用的 import/变量/函数。
- 不要删除之前就存在的死代码，除非被要求。

标准：每一行改动都应该能追溯到用户的需求。

### 4. 目标驱动执行

**定义成功标准。循环验证直到通过。**

把任务转化为可验证的目标：
- "添加验证" → "为无效输入写测试，然后让它们通过"
- "修复 bug" → "写一个能复现它的测试，然后让它通过"
- "重构 X" → "确保重构前后测试都通过"

多步骤任务，简要列出计划：
```
1. [步骤] → 验证: [检查方式]
2. [步骤] → 验证: [检查方式]
3. [步骤] → 验证: [检查方式]
```

明确的成功标准让你能独立循环。模糊的标准（"让它能用"）则需要不断确认。

---

**这些规范有效的标志：** diff 中不必要的改动更少，因过度复杂导致的重写更少，澄清问题出现在实现之前而非犯错之后。
 