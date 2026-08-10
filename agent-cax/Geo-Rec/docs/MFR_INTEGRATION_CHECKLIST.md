# BrepMFR 整合到 Geo-RecV2.0 清单



本文档按 **数据处理 → 构图 → 训练** 顺序，列出将 BrepMFR 模型整合到 Geo-RecV2.0 的完整清单与实施步骤。

---

## 一、流程对比概览

| 步骤 | AAGNet | BrepMFR (监督) | BrepMFR (域适应) |
|------|---------------|------------------|------------------|
| 1. 标签处理 | public/real_data_generate_labels | **相同**（共用） | **相同**（共用） |
| 2. 数据划分 | divide_train_val_test | **相同**（共用） | **相同**（共用） |
| 3. 构图 | step2graph_ncti (AAG格式JSON) | **BrepMFR_json_to_graph** (MFR格式JSON) | **BrepMFR_json_to_graph** (MFR格式JSON) |
| 4. 格式转换 | 无 | **json_to_bin** (JSON→DGL bin) | **json_to_bin** (JSON→DGL bin) |
| 5. 无效清理 | 无 | **check_and_clean_invalid** | **check_and_clean_invalid** |
| 6. 训练 | aagnet_train (DGL+MFInstSegDataset) | **BrepMFR_train** (DGL bin+CADSynth+PyTorch Lightning) | **BrepMFR_domain_adapt** (TransferDataset+DANN+PyTorch Lightning) |

---

## 二、数据处理 (Data Processing)

### 2.1 标签处理 ✅ 共用
- **文件**: `src/data_utils/processors/public_data_generate_labels.py`, `real_data_generate_labels.py`
- **说明**: 两个模型共用，无需修改
- **输出**: `processed_label_data` 下的 JSON 标签

### 2.2 数据划分 ✅ 共用
- **文件**: `src/data_utils/processors/divide_train_val_test.py`
- **说明**: 与 BrepMFR 的 `divide_train_val_test_txt.py` 逻辑一致，已统一使用 config 驱动
- **输出**: `train.txt`, `val.txt`, `test.txt`

### 2.3 新增：MFR 专用配置
- **文件**: `configs/configs.yaml`
- **任务**: 增加 `model_name: brepMFR` 时的数据路径配置
- **建议配置项**:
  ```yaml
  # MFR 专用路径（当 model_name=brepMFR 时使用）
  mfr_data_infos:
    graphs_mfr_json: "data/processed/round/graphs_mfr_json"   # MFR JSON 图输出
    bin_data: "data/processed/round/bin"                      # DGL bin 输出
  ```

---

## 三、构图 (Graph Construction)

### 3.1 AAGNet 构图（现有）— 保持不变
- **工具**: `src/utils/step2graph_tools_ncti.py` — AAGGraphExtraToolNcti
- **转换**: `src/data_utils/transforms/step2graph_ncti.py` — step2graph_batch
- **输出格式**: JSON，含 `graph`, `graph_face_attr`, `graph_edge_attr`, `graph_face_grid`
- **attr_standard**: AAGNet 会计算并保存 `attr_stat.json`，用于训练时标准化

### 3.2 BrepMFR 构图 — 需新增/整合
- **attr_standard**: BrepMFR **不需要**计算 attr_standard，其图结构与 AAGNet 不同，不使用 `attr_stat.json`

#### 3.2.1 新增 MFR 构图转换模块
- **目标文件**: `src/data_utils/transforms/step2graph_mfr_ncti.py`
- **来源**: 整合 `BrepMFR-main/data/BrepMFR_json_to_graph_ncti.py`
- **改动要点**:
  1. 使用 `src.utils.base_functions` 的 `load_config_basic`, `init_ncti`, `save_json_data`
  2. 使用 `src.utils.step2graph_tools_ncti` 中可复用的工具（如有）
  3. 路径从 config 读取，支持 `use_absolute_path`
  4. 移除硬编码的 LD_LIBRARY_PATH、dllpath 等，统一用 `configs.yaml` 的 `ncti_path_config`

#### 3.2.2 整合 ExtractorNCTI
- **目标文件**: `src/utils/extractor_mfr_ncti.py` 或放在 `step2graph_mfr_ncti.py` 同目录
- **来源**: `BrepMFR-main/data/extractor_ncti.py`
- **说明**: 计算 d2_distance、a3_distance、spatial_pos、edge_path 等 MFR 图属性

#### 3.2.3 MFR 图输出格式（与 AAGNet 不同）
```json
{
  "graph": { "num_nodes", "num_edges", "src_nodes", "dst_nodes" },
  "node_data": { "x", "a", "y", "z", "l", "f" },
  "edge_data": { "x", "l", "t", "a", "c" },
  "graph_labels": { "angle_distance", "d2_distance", "spatial_pos", "edges_path" }
}
```

### 3.3 JSON → Bin 转换（MFR 专用）
- **目标文件**: `src/data_utils/processors/json_to_bin.py`
- **来源**: `BrepMFR-main/data/json_to_bin.py`
- **功能**: 将 MFR JSON 转为 DGL 二进制，供 CADSynth 数据集加载
- **调用时机**: 在 `step2graph_mfr_batch` 之后、`check_and_clean_invalid` 之前

### 3.4 无效数据清理（MFR 专用）
- **目标文件**: `src/data_utils/processors/check_and_clean_invalid.py`
- **来源**: `BrepMFR-main/data/check_and_clean_invalid.py`
- **功能**: 检查 bin 中 spatial_pos 是否含 -2147483648，删除对应 step、label、bin
- **改动**: 路径从 config 读取，支持 Windows/Linux

---

## 四、训练 (Training)

### 4.1 BrepMFR 模型与数据集
- **模型目录**: `src/models/brepMFR/`（已存在空目录）
- **需复制/整合**:
  - `BrepMFR-main/models/brepseg_model.py` → `src/models/brepMFR/brepseg_model.py`
  - `BrepMFR-main/models/modules/` → `src/models/brepMFR/modules/`（brep_encoder, layers, uvnet_encoders 等）

- **数据集**:
  - `BrepMFR-main/data/dataset.py` → `src/data_utils/dataloader/brepmfr_dataset.py`（CADSynth 类）
  - `BrepMFR-main/data/collator.py` → `src/data_utils/dataloader/brepmfr_collator.py`
  - `BrepMFR-main/data/utils.py` → 合并到 `src/utils/` 或 dataloader 目录（get_random_rotation, rotate_uvgrid）

### 4.2 BrepMFR 训练器
- **目标文件**: `src/trainers/brepmfr_train.py`
- **来源**: 整合 `BrepMFR-main/segmentation.py`
- **改动要点**:
  1. 使用 `load_config_basic` 读取 dataset_path、batch_size、num_workers 等
  2. 使用统一的 logging
  3. 模型保存路径从 config 读取
  4. 保留 PyTorch Lightning + BrepSeg + CADSynth 的调用方式

### 4.3 域适应训练（新增迁移学习功能）
- **域适应模型**: `src/models/brepMFR/transfer_model.py`（DomainAdapt 类）
  - 基于 DANN (Domain-Adversarial Neural Network) 实现
  - 包含源域监督损失、目标域熵损失、域对抗损失
- **域适应数据集**: `src/data_utils/dataloader/brepmfr_dataset.py`（TransferDataset 类）
  - 联合加载源域和目标域数据
- **域适应批处理**: `src/data_utils/dataloader/brepmfr_collator.py`（collator_st 函数）
  - 联合批处理源域和目标域数据
- **域适应模块**: `src/models/brepMFR/modules/domain_adv/`
  - `domain_discriminator.py`: 域判别器
  - `dann.py`: 域对抗损失
  - `grl.py`: 梯度反转层 (Gradient Reverse Layer)
- **域适应训练器**: `src/trainers/brepmfr_train.py`（brepmfr_domain_adapt_trainer_module 函数）
  - 支持源域预训练 + 目标域微调的域适应流程

### 4.4 入口与路由
- **文件**: `train_main.py`
- **逻辑**: 根据 `configs.yaml` 的 `model_name` 和 `brepmfr_train_mode` 选择流程
  ```python
  model_name = config['model_infos']['model_name']
  if model_name == 'aagnet':
      data_processing_workflow()  # 现有 AAGNet 流程
      trainer_module()           # aagnet_train
  elif model_name == 'brepMFR':
      train_mode = config.get("model_infos", {}).get("brepmfr_train_mode", "supervised")
      if train_mode == "domain_adapt":
          brepmfr_domain_adapt_trainer_module()  # 域适应训练
      else:
          brepmfr_trainer_module()  # 监督训练
  ```

---

## 五、data_workflow 扩展

### 5.1 新增 MFR 数据流程
- **文件**: `src/data_workflow.py`
- **新增函数**: `data_processing_workflow_mfr()`
- **流程顺序**:
  1. `generate_public_data_labels()` / `generate_real_data_labels()`（若启用）
  2. `divide_data_into_splits()` — 共用
  3. `step2graph_mfr_batch()` — MFR 专用构图
  4. `json_to_bin_batch()` — MFR JSON→bin
  5. `check_and_clean_invalid()` — 清理无效 step/label/bin
  6. （可选）再次 `divide_data_into_splits()` — 因清理后需更新 train/val/test.txt

**注意**: MFR readme 建议 divide 在 step2 之后，防止 txt 中出现已删除的文件名。当前 Geo-RecV2.0 的 divide 基于 labels，若 labels 在 clean 时被删，则需在 clean 之后重新 divide。

---

## 六、step2graph_tools_ncti 可复用性

- **现有**: `AAGGraphExtraToolNcti`、`find_standardization`、`check_zero_std`
- **MFR 使用**: MFR 构图逻辑与 AAGNet 差异大，主要复用：
  - NCTI 初始化方式（通过 base_functions.init_ncti）
  - 若 MFR 需要 UV 网格，可参考 `extract_face_point_grid` 的思路，但 MFR 的 `extract_face_point_grid` 已在 BrepMFRExtractor 中实现（7 维：3 坐标 + 3 法线 + 1 掩码）
- **结论**: `step2graph_mfr_ncti.py` 建议**独立实现**，仅复用 config、logging、路径解析等基础设施。

---

## 七、实施顺序建议

| 序号 | 任务 | 优先级 | 依赖 |
|------|------|--------|------|
| 1 | 扩展 configs.yaml，增加 MFR 路径与模型配置 | P0 | 无 |
| 2 | 新增 `step2graph_mfr_ncti.py` + 整合 extractor_ncti | P0 | 1 |
| 3 | 新增 `json_to_bin.py` processor | P0 | 2 |
| 4 | 新增 `check_and_clean_invalid.py` processor | P0 | 3 |
| 5 | 整合 BrepMFR 模型到 `src/models/brepMFR/` | P0 | 无 |
| 6 | 整合 CADSynth 数据集与 collator | P0 | 5 |
| 7 | 新增 `brepmfr_train.py` 训练器（包含监督训练） | P0 | 5, 6 |
| 8 | 新增域适应组件：transfer_model.py, TransferDataset, collator_st, domain_adv/ | P0 | 5, 6 |
| 9 | 新增域适应训练器函数到 `brepmfr_train.py` | P0 | 8 |
| 10 | 新增 `data_processing_workflow_mfr()` | P0 | 2, 3, 4 |
| 11 | 修改 `train_main.py` 实现模型路由（支持 domain_adapt 模式） | P0 | 7, 9, 10 |
| 12 | 新增 `configs/model_configs/brepMFR/` 配置 | P1 | 1 |

---

## 八、目录结构预览（整合后）

```
Geo-RecV2.0/
├── configs/
│   ├── configs.yaml              
│   └── model_configs/
│       ├── aagnet/
│       └── brepMFR/              
├── src/
│   ├── data_workflow.py          
│   ├── data_utils/
│   │   ├── processors/
│   │   │   ├── json_to_bin.py         
│   │   │   └── check_and_clean_invalid.py  
│   │   ├── transforms/
│   │   │   ├── step2graph_ncti.py     
│   │   │   └── step2graph_mfr_ncti.py 
│   │   └── dataloader/
│   │       ├── brepmfr_dataset.py     
│   │       └── brepmfr_collator.py    
│   ├── models/
│   │   └── brepMFR/
│   │       ├── brepseg_model.py
│   │       ├── transfer_model.py      # 域适应模型
│   │       ├── modules/
│   │       │   ├── brep_encoder.py
│   │       │   ├── layers.py
│   │       │   ├── uvnet_encoders.py
│   │       │   └── domain_adv/        # 域适应模块
│   │       │       ├── domain_discriminator.py
│   │       │       ├── dann.py
│   │       │       └── grl.py
│   ├── trainers/
│   │   ├── brepmfr_train.py           # 包含监督和域适应训练器
│   │   └── aagnet_train.py
│   ├── utils/
│   │   ├── step2graph_tools_ncti.py   
│   │   └── extractor_mfr_ncti.py
```      
│   ├── models/
│   │   ├── aagnet/
│   │   └── brepMFR/                   
│   └── trainers/
│       ├── aagnet_train.py
│       └── brepmfr_train.py           
└── train_main.py                  
```

---

## 九、注意事项

1. **NCTI 环境**: BrepMFR 构图依赖 NCTI，需确保 `ncti_path_config` 正确，Windows 下注意 DLL 路径。
2. **divide 与 clean 顺序**: MFR readme 建议 divide 在 json_to_bin 之后；若 check_and_clean 会删文件，应在 clean 之后重新执行 divide。
3. **数据集目录**: MFR 训练期望 CADSynth 结构：根目录下含 `bin/`, `label/`, `step/`, `train.txt`, `val.txt`, `test.txt`。
4. **依赖**: BrepMFR 需要 `dgl`, `pytorch_lightning`, `prefetch_generator` 等，需在 requirements 中补充。
