# FeatureFox — 数据驱动通槽识别

> 基于 FeatureFox (Fuchs et al., 2025) 路线，用 XGBoost 边分类 + 图剪枝替代手工规则。

## 方法原理

规则式（v5）到极限的瓶颈在于：TP 和 FP 的几何特征高度重叠，人工评分公式线性不可分。
FeatureFox 用**数据驱动**突破这个瓶颈：

```
STEP 文件
   ↓ StepParser 解析
带属性的面邻接图 (AAG)：每个面有面积/周长/重心/法向量/类型
                         每条共享边有 30 维特征（见下）
   ↓ XGBoost 边分类器（从 17800 个标注样本学习）
   ↓ P(这条边在通槽内部)
   ↓ 等渗校准
   ↓ 剪枝：保留概率 ≥ 阈值的边
   ↓ 连通分量 = 通槽实例
   ↓ 后处理：过滤面数<3 / 平面占比<50% 的实例
输出：通槽实例列表
```

## 边特征（30 维）

| 类别 | 特征 | 说明 |
|---|---|---|
| **凸凹性** | dihedral_sign, abs_dihedral, is_concave/convex/smooth/unknown | 连续凸凹符号值 + one-hot（**最重要，占 53-62%**） |
| **边几何** | edge_length, edge_length_norm, edge_is_line/circle/other | 边长度、归一化长度、类型 one-hot |
| **面面积** | face_a/b_area, area_ratio, log_area_ratio | 两面面积 + 比值 |
| **面周长** | face_a/b_perim, perim_ratio | 两面周长 + 比值 |
| **面间关系** | centroid_dist, normal_angle_deg, normal_dot | 重心距、法向量夹角、法向量点积 |
| **面类型** | face_a/b_is_plane/cyl/other, both_plane, plane_cyl, both_cyl | 类型 one-hot + 组合交互项 |

## 使用方法

### 训练

```bash
cd YHCADSmartCleaner/utils/through_step

# 用前 14000 个文件训练（自动划分 train/calib/test）
python -m featurefox.train 14000

# 用全部 17800 文件训练
python -m featurefox.train 0
```

输出：
- `edge_clf.json` — XGBoost 边分类器
- `calibrator.pkl` — 等渗校准器

### 评估

```bash
# 前 50 文件
python -m featurefox.evaluate 50 0.5

# 全部文件，阈值 0.5
python -m featurefox.evaluate 0 0.5

# 指定 offset（评估训练集外的文件，验证泛化）
python -m featurefox.evaluate 0 0.5 14000
```

### 单文件预测

```bash
python -m featurefox.predict "D:\wyg\data\data\通槽\steps\xxx.step" 0.5
```

## 模块结构

| 文件 | 职责 |
|---|---|
| `edge_features.py` | 边特征提取（30维）+ AAG 构建 + 边长度计算（LINE/CIRCLE）|
| `instance_data.py` | 标签加载 + 训练数据生成（y=1: 通槽内部边）|
| `train.py` | XGBoost 训练（200树/深度6/lr0.1）+ 等渗校准 |
| `predict.py` | 边剪枝 + 连通分量 → 通槽实例 |
| `evaluate.py` | 全量 P/R/F1 评估 |

## 标签设计

- **y=1（正样本）**：共享边两端的面都在同一个通槽实例中（seg=9 且 inst[i][j]=1）
- **y=0（负样本）**：所有其他边

预测时，连通分量自然恢复通槽实例（底面+两壁通过高概率边相连）。
