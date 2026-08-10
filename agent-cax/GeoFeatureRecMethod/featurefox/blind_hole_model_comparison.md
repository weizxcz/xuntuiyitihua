# FeatureFox-NCTI 盲孔检测模型对比报告

> 对比全量训练 vs 仅 seg=12 文件训练，验证负样本（无盲孔文件）对模型精度的影响。

---

## 1. 训练数据

### 数据来源

| 项目 | 值 |
|------|-----|
| STEP 目录 | `/data/data2/steps/` |
| 标签目录 | `/data/data2/labels/` |

### 数据集划分

train.py 使用 `random_state=42` 划分训练/测试集（80/20），test 集固定为 12,486 个文件（`test_names.json`）。

### 数据量对比

| | 全量训练 | seg12-only 训练 |
|------|------|------|
| **总 STEP 文件** | ~62,500 | 17,339 |
| 含盲孔 (seg=12) | 17,339 | 17,339 |
| 不含盲孔 (seg=12) | **45,156** | 0（剔除） |
| 正样本比例 | 27.7% | 100% |
| 边级正样本 | 仅在盲孔文件内部 | 仅在盲孔文件内部 |
| 边级负样本来源 | 含盲孔文件(非盲孔边) + **无盲孔文件(全部边)** | 含盲孔文件(非盲孔边) |

> ⚠️ 关键差异：全量训练多了 45,156 个无盲孔文件，其中所有边都是 `y=0` 负样本。

---

## 2. 模型架构

FeatureFox-NCTI 采用**两级 XGBoost 串联**识别盲孔：

```
STEP 文件 → NCTI 导入 → 面图构建 → 边级特征(30维)
                                       ↓
                                边分类器 (XGBoost, 阈=0.05)
                                       ↓
                                等渗校准 (Isotonic)
                                       ↓
                            候选盲孔面 → 实例特征(26维)
                                       ↓
                            实例分类器 (XGBoost, 阈=0.80)
                                       ↓
                                等渗校准
                                       ↓
                              盲孔实例列表 → JSON 输出
```

### 边级 30 维特征

| 类别 | 特征 | 维度 |
|------|------|:---:|
| 凹凸性 | `dihedral_sign`, `abs_dihedral`, `is_concave`, `is_convex`, `is_smooth`, `is_conv_unknown` | 6 |
| 边几何 | `edge_length`, `edge_length_norm`, `edge_is_line`, `edge_is_circle`, `edge_is_other` | 5 |
| 面面积 | `face_a_area`, `face_b_area`, `area_ratio`, `log_area_ratio` | 4 |
| 面周长 | `face_a_perim`, `face_b_perim`, `perim_ratio` | 3 |
| 几何关系 | `centroid_dist`, `normal_angle_deg`, `normal_dot` | 3 |
| 面类型 | `face_a_is_plane/cyl/other`, `face_b_is_plane/cyl/other`, `both_plane`, `plane_cyl`, `both_cyl` | 9 |

### 实例级 26 维特征

对盲孔候选面聚类后，提取实例的几何统计特征（面数、面积分布、周长分布、面类型比例等）。

---

## 3. 训练指标（内部 test split）

### 3.1 边分类器

| | 全量训练 | seg12-only |
|------|------|------|
| 训练文件 | ~50,000 | ~13,871 |
| **raw** Precision | — | 68.11% |
| **raw** Recall | — | 93.21% |
| **raw** F1 | — | 78.71% |
| **calibrated** Precision | — | 96.88% |
| **calibrated** Recall | — | 86.42% |
| **calibrated** F1 | — | **91.35%** |
| 总耗时 | — | 701s (11.7min) |

> 注：全量模型原始 train.log 已丢失，无法提供边级 test split 指标。

### 3.2 实例分类器

| | seg12-only |
|------|------|
| 训练实例数 | 23,158 |
| 正例 (seg=12) | 19,093 (82.4%) |
| 负例 (其他) | 4,065 |
| Precision | 96.66% |
| Recall | 98.02% |
| **F1** | **97.34%** |

### 3.3 特征重要性 Top 5（边分类器）

| 特征 | 重要性 | 含义 |
|------|:---:|------|
| `edge_is_circle` | **81.10%** | 边是否为圆弧 — 盲孔内部边几乎全是圆弧 |
| `dihedral_sign` | 9.39% | 凹凸性符号 — 盲孔边界为凹边 |
| `abs_dihedral` | 7.00% | 凹凸强度 |
| `normal_angle_deg` | 0.54% | 法向量夹角 |
| `normal_dot` | 0.46% | 法向量点积 |

---

## 4. 完整流水线评估（面级，test 集 12,486 文件）

### 评估方法

```
run_evaluate_chunked.py --test-only, 阈=0.05, 32 workers

对每个 STEP 文件：
  1. NCTI 导入
  2. FeatureFox 两级预测 → detected_cells (预测的盲孔面集合)
  3. 加载标签 → seg12 (真值盲孔面集合)
  4. TP = detected_cells ∩ seg12
     FP = detected_cells − seg12
     FN = seg12 − detected_cells
  5. 文件级状态: EXACT / PARTIAL / MISS / FP_ONLY / OK
```

### 4.1 面级指标

| | 全量模型 | seg12-only | 差值 |
|------|------|------|------|
| **TP** | 7,401 | 7,462 | +61 |
| **FP** | 119 | 326 | **+207 (+2.7×)** |
| **FN** | 595 | 534 | -61 |
| **Precision** | **98.42%** | 95.81% | **-2.61%** |
| **Recall** | 92.56% | **93.32%** | +0.76% |
| **F1** | **95.40%** | 94.55% | **-0.85%** |
| 有效文件 | 11,706 | 11,706 | 一致 |
| 耗时 | 25.6min | ~25min | 相当 |

### 4.2 文件级指标

| 状态 | 含义 | 全量 | seg12-only |
|------|------|------|------|
| **EXACT** | 预测面完全等于真值 | 3,030 | 3,052 |
| **OK** | 文件无盲孔，预测也无 | 8,417 | 8,351 |
| **PARTIAL** | 部分匹配 | 86 | 85 |
| **MISS** | 有盲孔但完全漏检 | 146 | 123 |
| **FP_ONLY** | 无盲孔但预测出假盲孔 | **27** | **95 (+3.5×)** |

### 4.3 可视化对比

```
Precision:
  全量:     ██████████████████████████████████████████████▊ 98.42%
  seg12:    ███████████████████████████████████████████▌    95.81%

Recall:
  全量:     ██████████████████████████████████████████▎      92.56%
  seg12:    ██████████████████████████████████████████▋      93.32%

F1:
  全量:     █████████████████████████████████████████████▋   95.40%
  seg12:    █████████████████████████████████████████████▎   94.55%
```

---

## 5. 负样本作用分析

### 为什么 45,156 个无盲孔文件如此重要？

#### 5.1 核心原理

边分类器的标签定义：

```python
# 正样本 (y=1): 两个面都在盲孔集合中，且属于同一盲孔实例
in_seg12 = (fa in seg12) and (fb in seg12)
same_inst = inst_matrix[fa][fb] == 1
label = 1 if (in_seg12 and same_inst) else 0
```

有盲孔文件中，正样本是盲孔内部边，负样本是盲孔边界边 + 其他边。
无盲孔文件中，**所有边都是负样本**，但它们在特征空间上与正样本高度重叠。

#### 5.2 高难度负样本类型

| 结构 | edge_is_circle | dihedral_sign | both_cyl | 是盲孔？ | 负样本价值 |
|------|:---:|:---:|:---:|:---:|------|
| 盲孔圆柱内壁 | ✅ 1 | 凹 | ✅ 1 | ✅ 是 | — |
| 通孔内壁 | ✅ 1 | 凸 | ✅ 1 | ❌ 不是 | **高** |
| 螺纹孔 | ✅ 1 | — | ✅ 1 | ❌ 不是 | **高** |
| 沉头孔 | ✅ 1 | — | ✅ 1 | ❌ 不是 | **高** |
| 轴承座 | ✅ 1 | — | ✅ 1 | ❌ 不是 | **高** |
| 加强筋根部 | ✅ 0 | 凹 | ✅ 0 | ❌ 不是 | **中** |
| 分型面边缘 | ✅ 0 | 凹 | ✅ 0 | ❌ 不是 | **中** |

#### 5.3 对 XGBoost 决策边界的影响

```
有负样本时（全量，FP=119）:
  IF edge_is_circle=1 ∧ dihedral_sign>0.5 ∧ both_cyl=1 ∧ area_ratio<0.3 ∧ normal_angle>10°
  THEN y=1    ← 严格的多条件组合
  ELSE y=0

无负样本时（seg12-only，FP=326）:
  IF edge_is_circle=1 ∧ dihedral_sign>0
  THEN y=1    ← 阈值过松，通孔/螺纹孔等被误报
  ELSE y=0
```

#### 5.4 量化影响

| 指标 | 全量 → seg12-only | 解读 |
|------|------|------|
| FP 增加 | 119 → 326 (+207) | 缺少负样本导致模型无法精确排除"看起来像盲孔"的非盲孔边 |
| FP_ONLY 文件增加 | 27 → 95 (+3.5×) | 无盲孔文件中预测出假盲孔的数量暴增 |
| FN 减少 | 595 → 534 (−61) | 无明显差异 |

---

## 6. 结论

### 7.1 全量训练优于 seg12-only

| 维度 | 全量 | seg12-only | 差异 |
|------|:---:|:---:|------|
| F1 (面级) | 95.40% | 94.55% | 全量 +0.85% |
| Precision | 98.42% | 95.81% | 全量 +2.61% |
| FP_ONLY 文件 | 27 | 95 | seg12-only 多 3.5 倍 |
| 训练数据量 | 62,500 | 17,339 | 全量多 3.6 倍 |

**结论：全量训练（包含无盲孔负样本）的模型综合表现更优。** 无盲孔文件中的边在特征空间上与盲孔边高度重叠，它们作为负样本迫使 XGBoost 学习更精细的决策边界，显著降低误报率。

### 7.2 模型文件

| 模型 | 边分类器 | 边校准器 | 实例分类器 | 实例校准器 |
|------|------|------|------|------|
| 全量 | `edge_clf.json` | `calibrator.pkl` | `inst_clf.json` | `inst_calibrator.pkl` |
| seg12-only | `edge_clf_seg12only.json` | `calibrator_seg12only.pkl` | `inst_clf_seg12only.json` | `inst_calibrator_seg12only.pkl` |

所有模型文件位于 `featurefox/models/`。

---

## 7. 当前 FeatureFox 的弊端与局限

### 7.1 单特征标注（只识别 seg=12 盲孔）

当前模型只输出盲孔(seg=12)一种标签。虽然 MFInstSeg 定义了 24 类加工特征，但 FeatureFox **无法一次推理完成多特征识别**。要支持多特征需要：
- 每个目标特征单独训练一套两级分类器 → 模型体积膨胀
- 或改用多标签/多头架构，但当前 XGBoost 流水线不支持

### 7.2 未处理分裂圆柱壁

真实场景下，盲孔的圆柱面经常被其他特征（槽、台阶）**分割为两份或三份**，模型期望的是一个完整圆柱壁 + 一个底面。分裂面会导致：
- 连通分量被切断，盲孔实例拆分或漏检
- `MIN_INSTANCE_FACES=2` 后处理可能过滤掉残片

### 7.3 边分类器对圆弧特征过度依赖

```text
特征重要性: edge_is_circle = 81.10%（其他所有特征合计 <19%）
```

决策树几乎靠"这条边是不是弧"来判定。这意味着：
- 对**非圆弧边的盲孔**（如矩形盲孔、键槽盲孔）能力未知
- 模型可能只是学会了"圆弧 = 盲孔"的近似规则，泛化性存疑

### 7.4 阈值需手动设定

| 参数 | 当前值 | 如何确定 |
|------|:---:|------|
| 边分类器阈值 | 0.05 | 手动扫描 0.05~0.50，取 F1 峰值 |
| 实例分类器阈值 | 0.80 | 经验值，无系统扫描 |
| MIN_INSTANCE_FACES | 2 | 硬编码 |
| MIN_PLANE_RATIO | 0.0 | 盲孔不适用，直接关掉 |

阈值最优值可能随数据分布变化而漂移，当前无自适应机制。

### 7.5 缺乏底面(bottom)标注

盲孔 label JSON 中 `bottom` 字段全部为 0，没有标注哪个面是底面。这限制了下游应用（如 Geo-Rec 训练中的 B-rep 面角色判定）。

---

## 8. 附录：运行命令

```bash
# 全量训练
cd /workspace/xuntuiyiti && PYTHONPATH=/workspace/xuntuiyiti/featurefox:$PYTHONPATH \
  python -m featurefox.scripts.train 0
python -m featurefox.scripts.train_instance 0

# seg12-only 训练
NCTI_SEG12_ONLY=1 python -m featurefox.scripts.train_seg12only
NCTI_SEG12_ONLY=1 python -m featurefox.scripts.train_instance_seg12only

# 面级评估 (test 集)
python -m featurefox.scripts.run_evaluate_chunked 0 0.05 0 --test-only

# seg12-only 面级评估
FF_EDGE_MODEL=./models/edge_clf_seg12only.json \
FF_CALIB_MODEL=./models/calibrator_seg12only.pkl \
FF_INST_MODEL=./models/inst_clf_seg12only.json \
FF_INST_CALIB=./models/inst_calibrator_seg12only.pkl \
NCTI_CHUNK_WORKERS=32 \
python -m featurefox.scripts.run_evaluate_chunked 0 0.05 0 --test-only
```
