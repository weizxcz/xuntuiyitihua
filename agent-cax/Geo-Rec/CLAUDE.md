# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**请使用中文回答用户的问题。**

## 项目概述

Geo-Rec 是一个几何特征识别深度学习系统，用于识别 B-rep CAD 模型上的几何特征（盲孔、圆角等）。系统读取 STEP 文件，通过 NCTI（燕何 GMDE）CAD 内核将其转换为图表示，然后训练图神经网络进行逐面分割。

支持两种模型架构：**AAGNet**（主要使用）和 **BrepMFR**。代码注释为中文。

## 常用命令

### 训练
```bash
nohup python train_main.py > nohup.out 2>&1 &
tail -f nohup.out                          # 查看实时日志
ps aux | grep train_main                   # 检查是否在运行
```

项目没有测试套件。`test_main.py` 和 `infer_main.py` 都是空文件。

## 配置系统

所有配置集中在 `configs/configs.yaml` 中，主要包含：

- **`recognize_task_infos`** — 任务名称和标签索引（如 "Blind hole"，索引 12）
- **`data_path_infos`** — 所有数据路径（公开/真实原始数据、处理后输出、划分结果）。通过 `use_absolute_path` 支持绝对和相对路径
- **`step2graph_infos`** — 图构建参数（并行进程数 `num_workers`、NCTI 开关）
- **`model_infos`** — 模型选择（`model_name`: "aagnet" 或 "brepMFR"）、检查点路径
- 模型超参数在 `configs/model_configs/` 下的独立 YAML 文件中

更换目标特征或数据集时，只需修改 `configs.yaml` 中的路径。Python 代码通过 `load_config_basic()` 动态读取所有路径。

## 架构

### 入口路由（`train_main.py`）

```
model_name == "aagnet"  →  data_processing_workflow()  →  trainer_module()
model_name == "brepMFR" →  brepmfr_trainer_module()  (数据处理已注释掉)
```

AAGNet 在训练前会自动执行数据处理；BrepMFR 假设数据已预处理完成。

### 数据处理流水线（`src/data_workflow.py`）

**AAGNet 流水线**（`data_processing_workflow`）：
1. `generate_public_data_labels()` / `generate_real_data_labels()` — 将原始标注转换为统一标签格式
2. `divide_data_into_splits()` — 训练/验证/测试集划分（8:1:1）→ train.txt, val.txt, test.txt
3. `step2graph_batch()` — STEP → graph JSON，通过 NCTI 并行处理（`multiprocessing.Pool`）
4. 计算属性标准化参数（`attr_stat.json`）

**BrepMFR 流水线**（`data_processing_workflow_mfr`）：
1. 相同的标签生成和划分步骤
2. STEP → MFR graph JSON → DGL 二进制 → 清理无效图
3. 域适应模式：额外处理无标签数据并生成源/目标划分

### 图构建

两条流水线都使用 NCTI 解析 STEP 文件。每个子进程通过 `init_ncti()` 初始化独立的 NCTI 实例：

- **AAGNet**（`AAGGraphExtraToolNcti`，位于 `src/utils/step2graph_tools_ncti.py`）：面属性（12维）、边属性（10维）、面 UV 网格（5×5×7）
- **BrepMFR**（`BrepMFRExtractor`，位于 `src/data_utils/transforms/step2graph_mfr_ncti.py`）：更丰富的特征，包括 d2/a3 距离直方图、空间位置（Floyd-Warshall）、边路径（BFS）

### 模型架构

**AAGNet**（`src/models/aagnet/`）：3 头模型（分割 + 实例 + 底面检测）。使用 PNAConv 消息传递 GNN，带残差连接。可配置权重的组合损失。使用原生 PyTorch 训练（AdamW + CosineAnnealing + EMA + 混合精度）。

**BrepMFR**（`src/models/brepMFR/`）：基于 Transformer 的 Graphormer 风格编码器。使用 PyTorch Lightning 训练。域适应变体使用 DANN（域对抗神经网络）加梯度反转。

### 关键依赖

- PyTorch、DGL（Deep Graph Library）、PyTorch Lightning
- NCTI SDK（私有库，路径在 `ncti_path_config` 中配置）
- fairseq（BrepMFR 编码器使用）
- NetworkX、scipy、torch_ema、torchmetrics、torch_geometric

## 数据流

```
STEP 文件 → [标签处理] → JSON 标签
          → [数据划分] → train.txt / val.txt / test.txt
          → [AAGNet]   step2graph_ncti.py → graph JSON → AAGNetSegmentor
          → [BrepMFR]  step2graph_mfr_ncti.py → MFR JSON → DGL bin → BrepSeg
```

处理后的数据统一存放在 `processed_data` 目录下（labels/、graph/、splits/）。公开数据和真实数据的标签会写入同一个输出目录——设置 `use_public_data: false` 可以只使用真实数据。
