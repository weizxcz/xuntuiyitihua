# Geo-Rec - 几何特征识别框架

## 项目简介

Geo-Rec是一个先进的几何特征识别框架，专注于从CAD模型中识别和提取几何特征。该系统集成了两种强大的模型：AAGNet和BrepMFR，支持监督学习和域适应训练模式，能够处理各种复杂的几何特征识别任务。

### 主要功能

- **多模型支持**：集成AAGNet和BrepMFR两种模型，适应不同场景的几何特征识别需求
- **域适应能力**：支持源域到目标域的知识迁移，提高模型在未见数据上的性能
- **完整数据流程**：从标签处理、数据划分、构图到训练的全流程支持
- **多平台兼容**：支持Windows和Linux操作系统
- **NCTI集成**：利用NCTI SDK进行CAD模型解析和特征提取

## 目录结构

```
Geo-Rec/
├── configs/               # 配置文件目录
│   ├── model_configs/     # 模型特定配置
│   │   ├── aagnet/        # AAGNet模型配置
│   │   └── brepMFR/       # BrepMFR模型配置
│   ├── attr_features_keys.json  # 属性特征键定义
│   └── configs.yaml       # 主配置文件
├── docs/                  # 文档目录
│   ├── MFR_INTEGRATION_CHECKLIST.md  # BrepMFR整合清单
│   └── 代码架构.md         # 代码架构文档
├── src/                   # 源代码目录
│   ├── data_workflow.py   # 数据处理工作流
│   ├── data_utils/        # 数据处理工具
│   │   ├── dataloader/    # 数据加载器
│   │   ├── processors/    # 数据处理器
│   │   └── transforms/    # 数据转换器
│   ├── models/            # 模型定义
│   │   ├── aagnet/        # AAGNet模型
│   │   └── brepMFR/       # BrepMFR模型
│   ├── trainers/          # 训练器
│   ├── utils/             # 通用工具
│   └── visualization/     # 可视化工具
├── infer_main.py          # 推理入口
├── test_main.py           # 测试入口
└── train_main.py          # 训练入口
```

## 系统要求

- **操作系统**：Windows 10+ 或 Linux
- **Python**：3.8+ 
- **依赖项**：
  - PyTorch 1.8+
  - DGL (Deep Graph Library)
  - PyTorch Lightning (用于BrepMFR)
  - NumPy
  - scikit-learn
  - NCTI SDK (用于CAD模型解析)

## 安装步骤

### 1. 克隆项目

```bash
git clone <项目仓库地址>
cd Geo-Rec
```

### 2. 新建容器

参考welink群空间容器教程：BrepMFR训练linux环境容器创建及远程连接教程

### 3. 配置NCTI SDK

- 下载并安装NCTI SDK
- 在 `configs/configs.yaml` 中配置NCTI路径：

```yaml
ncti_path_config:
  dll_path: "/path/to/YHCppSDK"  # Linux
```

## 配置说明

主要配置文件为 `configs/configs.yaml`，包含以下核心配置：

### 1. 数据路径配置

```yaml
data_paths:
  step_dir: "data/raw/step"        # 原始STEP文件目录
  label_dir: "data/raw/label"      # 原始标签目录
  processed_data: "data/processed"  # 处理后数据目录
```

### 2. 模型配置

```yaml
model_infos:
  model_name: "brepMFR"  # 可选: "aagnet" 或 "brepMFR"
  brepmfr_train_mode: "supervised"  # 可选: "supervised" 或 "domain_adapt"（正常训练或者迁移学习，选mfr模型时必填）
```

### 3. MFR专用配置

```yaml
mfr_data_infos:
  graphs_mfr_json: "data/processed/round/graphs_mfr_json"  # MFR JSON图输出
  bin_data: "data/processed/round/bin"                    # DGL bin输出
```

## 使用方法

### 1. 训练模型

#### 训练AAGNet模型

1. 在 `configs/configs.yaml` 中设置：
   ```yaml
   model_infos:
     model_name: "aagnet"
   ```

2. 运行训练脚本：
   ```bash
   python train_main.py
   ```

#### 训练BrepMFR模型

##### 监督训练（一般正常默认）

1. 在 `configs/configs.yaml` 中设置：
   ```yaml
   model_infos:
     model_name: "brepMFR"
     brepmfr_train_mode: "supervised"
   ```

2. 运行训练脚本：
   ```bash
   python train_main.py
   ```

##### 域适应训练

1. 在 `configs/configs.yaml` 中设置：
   ```yaml
   model_infos:
     model_name: "brepMFR"
     brepmfr_train_mode: "domain_adapt"
   ```

2. 运行训练脚本：
   ```bash
   python train_main.py
   ```

### 2. 推理与测试

#### 推理

MFR推理可视化：src\visualization\visualization.py 在windows本地运行（因为依赖wxpython不方便在服务器上运行）

## 数据处理流程

### AAGNet流程

1. **标签处理**：`public_data_generate_labels.py` 或 `real_data_generate_labels.py`
2. **数据划分**：`divide_train_val_test.py`
3. **构图**：`step2graph_ncti.py` (生成AAG格式JSON)
4. **训练**：`aagnet_train.py`

### BrepMFR流程

1. **标签处理**：与AAGNet共用
2. **数据划分**：与AAGNet共用
3. **构图**：`step2graph_mfr_ncti.py` (生成MFR格式JSON)
4. **格式转换**：`json_to_bin.py` (JSON→DGL bin)
5. **无效清理**：`check_and_clean_invalid.py`
6. **训练**：`brepmfr_train.py` (监督或域适应)

## 模型架构

### AAGNet

- **图结构**：基于属性邻接图(AAG)构建
- **特征**：面属性、边属性、面网格特征
- **训练**：使用DGL和MFInstSegDataset

### BrepMFR

- **图结构**：基于B-rep的几何特征图
- **特征**：包含d2_distance、a3_distance、spatial_pos等MFR特有属性
- **训练**：使用PyTorch Lightning和CADSynth数据集
- **域适应**：基于DANN (Domain-Adversarial Neural Network)实现

## 域适应功能

BrepMFR支持域适应训练，通过以下组件实现：

- **域适应模型**：`transfer_model.py` (DomainAdapt类)
- **域适应数据集**：`brepmfr_dataset.py` (TransferDataset类)
- **域适应批处理**：`brepmfr_collator.py` (collator_st函数)
- **域适应模块**：`domain_adv/` 目录下的域判别器、DANN损失和梯度反转层

## 常见问题与解决方案

### 1. NCTI初始化失败

**症状**：运行时出现"Failed to initialize NCTI"错误

**解决方案**：
- 确保NCTI SDK正确安装
- 检查`configs.yaml`中的`ncti_path_config`配置
- Windows下确保DLL路径正确

### 2. 数据清理后需要重新划分

**症状**：训练时出现"File not found"错误

**解决方案**：
- 在`check_and_clean_invalid.py`执行后，重新运行`divide_train_val_test.py`
- 或在`data_workflow.py`中配置自动重新划分

### 3. 内存不足

**症状**：训练时出现内存错误

**解决方案**：
- 减少`batch_size`配置
- 对于大型模型，考虑使用GPU训练

## 性能评估

### 评估指标

- **准确率**：正确识别的特征数占总特征数的比例
- **召回率**：正确识别的特征数占实际特征数的比例
- **F1分数**：准确率和召回率的调和平均值
- **域适应性能**：目标域上的性能提升百分比


### 添加新模型

1. 在`src/models/`下创建新模型目录
2. 实现模型定义和训练逻辑
3. 在`train_main.py`中添加模型路由
4. 在`configs/model_configs/`下添加模型配置

### 自定义数据流程

1. 在`src/data_utils/`下添加新的数据处理器或转换器
2. 在`src/data_workflow.py`中集成新的数据处理步骤



## 更新日志

### v2.1 (2026-04)

- 集成BrepMFR模型
- 添加域适应训练功能
- 统一数据处理流程
- 支持多平台配置

### v1.0 (2025-12)

- 初始版本
- AAGNet模型实现
- 基础数据处理流程
