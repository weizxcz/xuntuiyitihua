# FeatureFox

基于 AAG (Attributed Adjacency Graph) + 两级 XGBoost 的盲孔 (seg=12) / 通槽 (seg=9) 识别管线。

参考论文：*FeatureFox: A Graph Neural Network towards Multi-task Machining Feature Recognition* (AAGNet)

> **第一次用？** 看 [INSTALL.md](../INSTALL.md) — 5 分钟跑通。
> **想了解架构？** 看下文。

---

## 架构

```text
STEP 文件 → NCTI 导入 → NctiPart → 构建 AAG → 30维边特征
                                              ↓
                              第一级 XGBoost 边分类器 (edge_clf)
                                              ↓
                              等渗校准 → 剪枝 → 连通分量
                                              ↓
                              第二级 XGBoost 实例分类器 (inst_clf)
                                              ↓
                                         盲孔/通槽实例
```

---

## 目录结构

| 目录 | 说明 |
| --- | --- |
| `lib/` | 核心库：NCTI 后端、特征提取、标签处理、环境配置 (`_env.py`) |
| `scripts/` | 训练、预测、评估、批量标注脚本 |
| `workers/` | 子进程 worker（chunk 隔离，防止 NCTI segfault） |
| `debug/` | 诊断工具：单文件 dump、holdout 漏检分析、阈值扫描 |
| `bridge/` | GUI 桥接层（wxPython → NCTI 高亮） |
| `config/` | NCTI SDK 路径配置（`ncti_config.json`，客户自行填写） |
| `models/` | 训练好的 XGBoost 模型 + 校准器（**随仓库入库**） |

---

## 路径与数据

**所有路径通过 `lib/_env.py` 统一解析**，脚本不硬编码任何本地路径。

### 环境变量（推荐）

| 变量 | 说明 | 兜底（不设时） |
| --- | --- | --- |
| `FEATUREFOX_STEPS_DIR` | STEP 文件目录 | `~/featurefox_data/steps/` |
| `FEATUREFOX_LABELS_DIR` | 标签 JSON 目录 | `~/featurefox_data/labels/` |
| `FEATUREFOX_MODELS_DIR` | 模型文件目录 | `featurefox/models/`（仓库内） |
| `NCTI_PROJECT_ROOT` | YHCADSmartCleaner 项目根（仅 debug 脚本需要） | 无（debug 脚本会早 fail） |
| `FF_EDGE_MODEL` | 边分类器模型路径 | `models/edge_clf.json` |
| `FF_CALIB_MODEL` | 边校准器路径 | `models/calibrator.pkl` |
| `FF_INST_MODEL` | 实例分类器模型路径 | `models/inst_clf.json` |
| `FF_INST_CALIB` | 实例校准器路径 | `models/inst_calibrator.pkl` |

> **SDK 路径**单独在 `config/ncti_config.json` 的 `dllPath` 字段（**唯一**必须改的 JSON）。

### 数据格式

- **STEP 文件**：`*.step`（或 `.stp`）
- **标签 JSON**：与 STEP 同名，结构见 [INSTALL.md §3](../INSTALL.md)

---

## 训练

```bash
# 第一级边分类器（耗时 ~5h 全量）
python -m featurefox.scripts.train 0          # 0 = 全量
python -m featurefox.scripts.train 100        # 100 件冒烟

# seg12-only 边分类器（盲孔专项）
python -m featurefox.scripts.train_seg12only

# 第二级实例分类器
python -m featurefox.scripts.train_instance 0
```

---

## 推理

```python
from featurefox.scripts.predict import predict_part

instances = predict_part("part.step")
# instances[i] = {faces: [cell_id,...], score: float, n_faces: int, inst_prob: float}
```

或 CLI：

```bash
python -m featurefox.scripts.predict /your/data/steps/part.step
```

`predict_part` 自动读取 `config/ncti_config.json`，无需手动 import ncti_python。

---

## 评估

```bash
python -m featurefox.scripts.evaluate 0            # 全量（in-process）
python -m featurefox.scripts.run_evaluate          # Linux 单进程
python -m featurefox.scripts.run_evaluate_chunked  # 子进程隔离（生产用）
python -m featurefox.scripts.threshold_sweep 1000 14000  # 阈值扫描
```

---

## 调试工具（`debug/`）

`debug/` 下的脚本是**一次性诊断工具**（以下划线开头），不是核心管线的一部分。多数脚本需要 YHCADSmartCleaner 兄弟目录（STEP-parser 版）：

```bash
# 设置 YHCADSmartCleaner 兄弟目录（仅 debug 需要）
export NCTI_PROJECT_ROOT=/path/to/YHCADSmartCleaner

# 单文件分阶段 dump（特征 + 概率 + 连通分量 + 第二级）
python -m featurefox.debug._debug_one part.step

# 单文件分阶段耗时实测
python -m featurefox.debug._bench_one part.step

# holdout 漏检分桶统计
python -m featurefox.debug._stat_holdout 0 14000

# 第二级策略 sweep
python -m featurefox.debug._sweep_inst 0 14000
```

> debug 脚本的 `TARGET`（重点标注文件）现在通过 CLI 第 3 个参数传入，不再硬编码。

---

## 依赖

- **NCTI SDK**：炎核几何引擎，需 `config/ncti_config.json` 配 `dllPath`
- Python 3.8+，`pip install -r requirement.txt`
- （可选）YHCADSmartCleaner：仅 `debug/` 脚本需要（STEP-parser 版路径），可通过 `NCTI_PROJECT_ROOT` 指定

完整依赖见 [requirement.txt](requirement.txt)。

---

## 模型文件

| 模型 | 文件 | 说明 |
| --- | --- | --- |
| 边分类器 (全量) | `edge_clf.json` + `calibrator.pkl` | XGBoost 200棵树，等温校准 |
| 边分类器 (seg12) | `edge_clf_seg12only.json` + `calibrator_seg12only.pkl` | 仅含盲孔的样本训练 |
| 实例分类器 (全量) | `inst_clf.json` + `inst_calibrator.pkl` | 真盲孔 vs 硬负样本 |
| 实例分类器 (seg12) | `inst_clf_seg12only.json` + `inst_calibrator_seg12only.pkl` | seg12-only |

---

## 故障排查

| 症状 | 解法 |
| --- | --- |
| `FileNotFoundError: .../steps` | 没设 `FEATUREFOX_STEPS_DIR` 环境变量 |
| `dlopen: libncti_*.so: cannot open` | SDK 路径错或缺 `LD_LIBRARY_PATH` |
| `XGBoostError: edge_clf.json not found` | 模型文件缺失或 `FEATUREFOX_MODELS_DIR` 错 |
| `ModuleNotFoundError: detect_blind_holes_*` | debug 脚本需 YHCADSmartCleaner；设 `NCTI_PROJECT_ROOT` |
| 训练时 segfault | NCTI 批量资源冲突，用 `run_evaluate_chunked` |

更多见 [INSTALL.md §7](../INSTALL.md)。
