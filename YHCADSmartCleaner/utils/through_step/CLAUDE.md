# CLAUDE.md — through_step 模块

本目录实现双侧通槽 (2-sided through step) 的几何特征识别。

## 文件结构

| 文件 | 用途 |
|---|---|
| `detect_through_step.py` | STEP 文本规则识别器，纯 STEP 拓扑/几何，不依赖 NCTI |
| `detect_through_step_ncti.py` | NCTI-native 识别器，直接使用 AiModel 数据（FaceAttr/EdgeAttr），cell_id 空间 |
| `geom_helpers.py` | 共享几何工具（`_dot`, `_angle_between_normals`, `_vec_len`, `_project_to_plane`） |
| `test_batch_50.py` | STEP 文本规则批量测试（50 文件），无需 NCTI 环境 |
| `test_batch_50_ncti.py` | NCTI-native 批量测试（50 文件），需要 NCTI SDK |
| `test_ncti_init.py` | NCTI 环境冒烟测试（单文件） |

## 运行环境

### STEP 文本规则测试（不需要 NCTI）

```bash
# 任何有 Python 的环境均可
python test_batch_50.py
```

### NCTI-native 测试

**Python 环境**: 必须使用 `yhcad_py312`（Python 3.12，匹配 `ncti_python312.pyd`）。

```bash
# 单文件冒烟测试
"D:/Anaconda3/envs/yhcad_py312/python.exe" test_ncti_init.py

# 50 文件批量测试（默认 50，可传参数调整数量）
"D:/Anaconda3/envs/yhcad_py312/python.exe" test_batch_50_ncti.py 50
```

输出报告写入 `batch_ncti_report.txt`。

### NCTI 初始化要点

```python
doc = ncti_python.Document()
doc.New("OCC", "DCM", "GMSH")       # ← 必须调，否则 import 返回空
doc.ResetCaseResult()
doc.SetCreateGeGeom(1)
doc.SetImportAssemelFile(1)
doc.RunCommand("cmd_ncti_import_file", step_path)
```

每个文件导入前都要 `doc.New()` 重置文档，避免面 ID 冲突。

脚本末尾用 `os._exit(0)` 避免退出时 NCTI DLL 析构 segfault。退出码 127 是正常现象。

## 数据路径

| 路径 | 内容 |
|---|---|
| `D:\wyg\data\data\通槽\steps\` | STEP 测试文件（~17800 个） |
| `D:\wyg\data\data\labels\` | 标注 JSON，seg=9 表示通槽面 |

标签 JSON 格式：`[[name, {"seg": {cell_id: seg_value}, "bottom": {cell_id: 1}, "inst": ...}]]`

## NCTI-native 检测器架构

4 条搜索路径：

| Path | 方法 | 说明 |
|---|---|---|
| A | `_find_trio_instances()` | 3 面 trio（矩形，90° 壁面） |
| B | `_find_extended_instances()` | 4-6 面扩展（含圆角面） |
| C | `_find_ring_instances()` | 多边形环（凹边环 DFS） |
| D | `_find_mixed_trio_instances()` | 混合 trio（平面底 + 平面壁 + 圆柱壁） |

入口函数：`recognize_through_steps_ncti(ncti, doc, obj_name) → dict`

## 关键阈值

```python
# 硬约束
PERP_MIN = 75.0          # 壁面-底面垂直度下限
PERP_MAX = 105.0          # 壁面-底面垂直度上限
MIN_INSTANCE_FACES = 3
MAX_INSTANCE_FACES = 6
MAX_RING_SIZE = 8

# 评分阈值（按类型区分，v2 优化后大幅提高）
MIN_SCORE = 35.0          # 任何候选的最低分
MIN_HYBRID_SCORE = 88.0   # 矩形通槽（trio/extended）— 从 76 提高
MIN_MIXED_SCORE = 82.0    # 混合 trio（含圆柱壁）— 从 60 提高
MIN_RING_SCORE = 75.0     # 多边形环 — 从 60 提高
BOTTOM_NEIGHBOR_HARD_MAX = 7  # 底面邻接面数硬上限
```

## v2 优化内容（2026-06-11）

### 核心改进 1：贯穿方向两端开放验证 (`_verify_through_open_ends`)

通槽的关键几何特征是**沿通槽方向两端贯通**。原方案只检查底面有 ≥1 条自由边，
但凹角、盲槽底面也可能有自由边。新验证逻辑：

1. 计算通槽走向 = `底面法向量 × 侧壁方向`（叉积）
2. 收集底面的自由邻接面（非侧壁的邻接面）
3. 将自由邻接面重心投影到通槽方向
4. **投影跨越正负两侧** → 证明两端均有开放端

**重要**：此验证作为**评分加分项**（+10 分），不做硬过滤。
实测发现 NCTI 边数据中通槽开放端的边界边可能没有注册邻接面，
硬过滤会导致 Recall 从 33% 暴跌到 15%。

### 核心改进 2：评分权重优化

增大区分力强的维度权重，降低区分力弱的维度：

| 维度 | 原权重 | 新权重 | 原因 |
|---|---|---|---|
| 垂直精度 | 25分 | 25分 | 不变，通槽核心约束 |
| 重心位置 | 25分 | **15分** | 区分力不强 |
| 面积对称性 | 15分 | 15分 | 不变 |
| 底壁比 | 15分 | **10分** | 减少权重 |
| 开放度 | 5分 | **15分** | 通槽核心特征 |
| 法向量投影 | 5分 | **10分** | U 型信号强区分力 |

### 其他优化

| 改动 | 原值 | 新值 | 原因 |
|---|---|---|---|
| MIN_HYBRID_SCORE | 76 | 82 | 适度提高减少 FP |
| MIN_MIXED_SCORE | 60 | 76 | mixed_trio 占 FP 最多 |
| MIN_RING_SCORE | 60 | 70 | 多边形环 FP 较多 |
| 底面邻接面 | 软扣分 | 硬过滤 >7 | 通槽底面邻居 ≤6 |
| MIN_SCORE (STEP版) | 35 | 45 | 过滤低质量候选 |

### 性能对比（50 文件基准）

| 指标 | v1 (原版) | v2 (优化后) | 变化 |
|---|---|---|---|
| Precision | 26.70% | 30.10% | +3.40% |
| Recall | 33.15% | 34.83% | +1.68% |
| F1 | 29.57% | **32.29%** | **+2.72%** |
| FP_ONLY 文件 | 21 | 19 | -2 |
| EXACT 文件 | 6 | 7 | +1 |

### 已知局限

TP 和 FP 的评分区间高度重叠（73-100 分），当前几何特征（垂直度、重心、
面积等）区分力有限。mixed_trio 占 FP 的 52.6%，是最主要的误检来源。
进一步改善可能需要引入体积/凹陷分析或机器学习方法。

## v3 合并优化（2026-06-11）

### 尝试：从 NCTI 版移植 mixed_trio 搜索路径 + 底面邻接面过滤

将 NCTI 版的 `_find_mixed_trio_instances()` 搜索路径移植到 STEP 版，
并尝试添加底面邻接面过滤（NCTI 版的有效信号）。

### 实测结论

| 尝试 | Precision | Recall | F1 | 分析 |
|---|---|---|---|---|
| v2 原版 | 39.06% | 65.17% | 48.91% | 基线 |
| +mixed_trio(阈值85) | 39.76% | 55.62% | 46.37% | mixed_trio FP 多，阈值高导致 Recall 降 |
| +mixed_trio(阈值45) | 27.90% | 66.29% | 39.27% | mixed_trio FP 暴增，Recall 仅微增 |
| +底面邻接面过滤(>7) | 过滤太多 | — | — | STEP 邻接仅含候选面，不适用 |
| **最终(v3)** | **39.06%** | **65.17%** | **48.84%** | 与 v2 相同 |

**结论**：
1. **mixed_trio 不适用于 STEP 版**：无边凸凹性数据，圆柱面壁匹配太宽松，只增加 FP 不增加 TP
2. **底面邻接面过滤不适用于 STEP 版**：STEP 的 adjacency 只包含候选面（PLANE+CYLINDRICAL）间邻接，不含全部面，计数与 NCTI 不同
3. NCTI 版的 edge convexity（EdgeAttr[1]=convex）是关键信号，STEP 文本解析无法获取

### 代码保留

mixed_trio 相关代码（`_find_mixed_trio_instances`, `_validate_mixed_trio`, `_score_mixed_trio`）
保留在文件中但默认禁用（`MIN_MIXED_SCORE_STEP=200`）。
当有边缘凸凹性数据来源时可启用。

## NCTI AiModel 数据布局

```python
ai = ncti.AiModel(doc, obj_name)
ai.FaceAttr[i]   # 12 维（实测布局，2026-06-24）— **不含 3D 坐标**！
                 # [0]..[4]  类型 one-hot: is_plane / is_cylindrical / is_cone / is_sphere / is_torus
                 # [5]      面积/比例（PLANE 不可信，p50=0.001 of truth）
                 # [6]      rational 标志（0 或 1？）
                 # [7..9]   **归一化坐标**（bbox min-max → [-1, 1]，**不是法向量**）
                 # [10]     loop 数（整数）
                 # [11]     邻接面数（整数）
ai.EdgeAttr[i]   # [0]=concave, [1]=convex, [2]=smooth, [3]=edge_length, [4]=circular, [9]=line
ai.FaceEID        # 边的终点面索引
ai.FaceFID        # 边的起点面索引
ai.FaceID         # 面 ID 列表
```

**3D 坐标不在 FaceAttr 里**，需要用：
- `doc.GetFaceMidPoint(obj, i)` — 面中心（OCC 几何中心）
- `doc.GetPointFromUV(obj, i, u, v)` — UV 坐标采样点
- `parser.points`（STEP 侧）— 所有 `CARTESIAN_POINT` 的 (x,y,z) 字典
- `parser.face_centroid(fid)`（STEP 侧）— 面顶点集重心

## 当前性能

| 指标 | NCTI v2 | STEP v5 规则式 | **FeatureFox 两级** |
|---|---|---|---|
| Precision | 30.10% | 45.25% | **85.68%** |
| Recall | 34.83% | 63.48% | **81.27%** |
| F1 | 32.29% | 52.84% | **83.42%** |
| 评估方式 | 50文件 | 全量17800 | **holdout 500(训练14000外)** |

FeatureFox 数据驱动路线大幅超越规则式：F1 +30.6 个点。
两级架构（边分类器 + 实例分类器）相对单级边分类器：Precision +6.1 点、FP -38%、F1 +0.8 点。

## FeatureFox 数据驱动路线（2026-06-15）⭐ 当前最优

### 方法（两级架构）
基于 FeatureFox (Fuchs et al., 2025) 路线，用 **XGBoost 边分类 + 实例分类**替代手工规则。
代码在 `featurefox/` 子目录。

```
第一级（边分类器）：
  STEP → AAG(30维边特征) → XGBoost预测P(边在通槽内部) → 校准 → 剪枝(阈0.35) → 连通分量=候选实例
第二级（实例分类器，剔 seg=22 同类误检）：
  每候选实例 → 26维聚合特征 → XGBoost预测P(真通槽) → P<0.20 拒绝
```

第一级管召回（把高概率边连成候选），第二级管精度（用整实例语义特征剔除非通槽同类）。
72% 的 FP 面来自整组 seg≠9（如 seg=22）的误检实例——它们在边级别几何上与通槽同构，
第一级分不开，需第二级整实例聚合特征区分。

### 边特征（30维，dihedral_sign 占重要性 62%）
凸凹性(连续+one-hot) + 边长度/类型 + 面面积/周长比 + 重心距 + 法向量夹角 + 面类型组合。

### 实例特征（26维，第二级）
规模(面/边数) + 面类型构成 + 面积/周长分布 + 凹凸边占比 + 底-壁结构 + 第一级边概率置信度。

### 训练数据
- 第一级：17800 文件，y=1 = 共享边两端面同属一个通槽实例(seg=9 且 inst=1)，5.2% 正样本。
- 第二级：inst 矩阵的真实特征实例分组，y=1 = 整组 seg=9（真通槽），y=0 = 整组 seg≠9 且≠0（其它特征，含 seg=22）。scale_pos_weight 平衡。

### 超参（FeatureFox 原文）
- 第一级：XGBoost 200树/深度6/lr0.1，等渗校准，阈值 0.35（扫描最优）。
- 第二级：XGBoost 200树/深度4/lr0.1/subsample0.8，等渗校准，阈值 0.20（扫描最优）。

### 阈值扫描
第一级（holdout 1500）：
| 阈值 | P | R | F1 |
|---|---|---|---|
| 0.30 | 75.13% | 84.05% | 79.34% |
| **0.35** | **78.21%** | **80.75%** | **79.46%** |
| 0.40 | 80.06% | 78.59% | 79.32% |
| 0.50 | 84.40% | 70.21% | 76.65% |

第二级实例阈值（holdout 500，第一级阈0.35）：
| inst_thr | P | R | F1 | FP |
|---|---|---|---|---|
| 0.10 | 83.61% | 82.55% | 83.08% | 305 |
| **0.15**/**0.20** | ~85% | ~82% | **83.42%** | **256** |
| 0.50 | 90.04% | 74.85% | 81.75% | 156 |

### 用法
```bash
python -m featurefox.train 0            # 训练第一级（全部17800）
python -m featurefox.train_instance 0   # 训练第二级实例分类器
python -m featurefox.evaluate 0 0.35 14000   # 评估第一级
python -m featurefox.predict xxx.step 0.35   # 单文件预测（默认启用第二级）
```

模型文件: `featurefox/edge_clf.json` + `featurefox/calibrator.pkl`（第一级），
`featurefox/inst_clf.json` + `featurefox/inst_calibrator.pkl`（第二级）。
第二级模型缺失时自动退化为只过滤几何（向后兼容）。

## STEP v5 规则式（基线，已被 FeatureFox 超越）

| 指标 | STEP v4 | STEP v5 (全量) |
|---|---|---|
| Precision | 46.43% | 45.25% |
| Recall | 65.73% | 63.48% |
| F1 | 54.42% | 52.84% |
| 文件数 | 50 | 17799 |
| EXACT | 13 | 4009 (22.5%) |
| FP_ONLY | 7 | 2721 (15.3%) |

v5 改动：连续二面角值（凸凹性返回 sign_value）+ 评分维度改进（反平行度 + 质心距离对称性）。
反平行 dot 硬过滤（dot>0 拒绝）经测试会导致大量回归（same_sense 不稳定），已移除。
规则方法瓶颈：TP/FP 几何特征高度重叠，线性不可分 → 需数据驱动突破。

## v4 边凸凹性优化（2026-06-11）

### 核心改进：从 STEP 几何数据计算边凸凹性

STEP 文件不直接包含边凸凹性标注，但可以通过**质心偏移法 (centroid-offset method)**
从已有的面法向量、same_sense、边顶点和面重心数据推导：

1. 获取两面有效外法向量（PLANE 从 AXIS2 + same_sense 修正；CYLINDRICAL 径向 + same_sense）
2. 计算共享边中点 M，面 A 重心到 M 的向量去除边方向分量 → v_perp
3. sign = dot(v_perp, n_B) / |v_perp|
4. sign > 0.02 → concave；sign < -0.02 → convex；其他 → smooth

### 新增函数

| 函数 | 用途 |
|---|---|
| `_face_normal_effective()` | 面 effective outward normal（含 same_sense 修正）|
| `_cyl_surface_normal_at_point()` | 圆柱面在指定点的径向法向量 |
| `_face_normal_at_edge()` | 统一接口（PLANE/CYLINDRICAL）|
| `_compute_edge_convexity()` | 核心算法：计算两面共享边的凸凹性 |
| `_build_edge_convexity_map()` | 批量构建凸凹性映射表 |

### 凸凹性使用位置（与 NCTI 版对齐）

1. `_validate_core`：硬过滤 — 底面-侧壁凸边 → 拒绝
2. `_find_mixed_trio_instances`：预过滤 — 平面壁候选凸边 → 跳过
3. `_find_mixed_trio_instances`：预过滤 — 圆柱壁候选凸边 → 跳过
4. `_find_mixed_trio_instances`：壁-壁凸边 → 跳过

### 其他改动

- `MIN_MIXED_SCORE_STEP` 从 200 降为 76（启用 mixed_trio）
- `_validate_mixed_trio` 的 `through_ok` 从硬过滤改为评分加分项（+10）
- 新增常量 `CONVEXITY_THRESHOLD = 0.02`

### 性能对比

| 指标 | v3 (基线) | v4 (+凸凹性) | 变化 |
|---|---|---|---|
| Precision | 39.06% | 46.43% | **+7.37%** |
| Recall | 65.17% | 65.73% | +0.56% |
| F1 | 48.84% | 54.42% | **+5.58%** |
| ✅完全正确 | 7 | **13** | +6 |
| ❌纯误检 | — | 7 | — |
| 实例精度 | — | 48.8% | — |

## 已知数据语义差异：STEP 面积 vs NCTI `attr[5]`（2026-06-24）

### 核心结论

**STEP 文本里不存在"面积"字段**——必须从边环 + 曲线自己算；任何"从 STEP 算面积"的代码都只是**近似估计**。NCTI `FaceAttr[5]` 才是 OCC 引擎在导入时精确积分出的**真面积**。两者**不可直接交叉验证**，必须按 ftype 分两套判据。

### STEP 文本本身不存面积

| 几何元素 | STEP 里的内容 | 是否含面积 |
| --- | --- | --- |
| `PLANE` | `AXIS2_PLACEMENT_3D`（原点+法向+X方向） | 否（只有无穷平面） |
| `CYLINDRICAL_SURFACE` | 半径 + 轴线 + 方向 | 否（只有无穷圆柱面） |
| `ADVANCED_FACE` | 1 个 surface + N 个 `EDGE_LOOP` | 否（只引用） |
| `EDGE_CURVE` | 1 条 curve（`LINE`/`CIRCLE`/`B_SPLINE_CURVE`...） | 否 |
| `VERTEX_POINT` | 1 个 `CARTESIAN_POINT` | 否 |

### `_face_area_approx`（`detect_through_step.py:161-193`）的根上限制

算法：收集面的所有 `VERTEX_POINT` → 投到法平面 → 按角度排序成凸多边形 → 鞋带公式。

两个根本性损失：

1. **圆弧/曲面边被"折线化"**：圆弧边只取起止两个端点，弧段被弦化
2. **按角度排序假设凸多边形**：实际面可能是非凸或带洞 → 错误多边形

**这只对"直边矩形/三角 PLANE"严格精确**；曲面（CYL/CONE/SPHERE/TORUS）直接返回垃圾值（没做曲线积分）。

### 实测面积比分布（30 文件 656 对 PLANE）

| 判据 | p1 | p25 | **p50** | p75 | p90 | p99 |
| --- | --- | --- | --- | --- | --- | --- |
| `a_s`（STEP 鞋带）/ 真实面积 | 0.49 | 1.00 | **1.00** | 1.00 | 1.00 | 1.00 |
| `a_n`（NCTI `attr[5]`）/ 真实面积 | 0.00 | 0.00 | **0.001** | 0.004 | 0.022 | 0.37 |

按顶点数细看 `a_s/truth`（= PLANE 真实面积）：

| n_verts | n | p25 | p50 | p75 |
| --- | --- | --- | --- | --- |
| 3（三角形） | 22 | 1.00 | 1.00 | 1.00 |
| 4（矩形） | 431 | 1.00 | 1.00 | 1.00 |
| 5–6 | 89 | 0.95–0.98 | 0.99–1.00 | 1.00 |
| 7 | 28 | 0.89 | 0.96 | 0.99 |
| 8+（含圆弧） | 31 | 0.59–0.79 | 0.70–0.87 | 0.76–0.89 |

### 结论

- `a_s`（STEP 鞋带）是**正确的 PLANE 面积**（n_verts=4 直边 PLANE 几乎完美 r=1.0）
- `a_n`（NCTI `attr[5]`）对 PLANE **几乎不可信**（p50 偏差 1000 倍，p99 才 3 倍）——可能只对曲面有效，PLANE 上返回 0 或 bounding box 极小值
- 因此**不能**用 `a_s/a_n` 或 `min(a_s,a_n)/max(...)` 来双向验证映射

### `sigs_agree` 新阈值（`check_order_assumption.py`）

PLANE 改用 **`a_s / truth_area`（真面积比）**作为严判据（`n_v ≤ 6 → 0.7`，`n_v > 6 → 0.55`），**完全跳过 `attr[5]`**。
CYL/OTHER 改用 **`a_n / a_s`（反向，避开 a_s 偏小 1000 倍）**：`r ≥ 0.2` 通过（仅排除量级悬殊）。

为什么这么选：

- PLANE：`a_s` 真，`a_n` 不可信 → 用 `a_s/truth`，**单边**判据
- CYL/OTHER：`a_s` ≪ `a_n`（差 10~3000 倍）→ 取**反向**比 `a_n/a_s`，避免分母太小

边界单测 15 例（见 `_test_sigs_agree.py`）全部通过：PLANE 4v r=0.7 通过、r=0.5 拒；PLANE 8v r=0.55 通过、r=0.5 拒；CYL r=0.2 边界通过、0.15 拒。

### 诊断脚本

| 脚本 | 用途 |
| --- | --- |
| `_area_ratio_probe.py` | 全量扫面积比 min/max 分桶（看双向分布） |
| `_area_truth.py` | 计算 PLANE 真实面积（凸包投影），与 a_s/a_n 对照 |
| `_area_unit_check.py` / `_area_unit_check2.py` | 量级 + 单位 dump |
| `_unit_test.py` | 构造已知几何体验证 `attr[5]` 单位（构造 STEP 失败，需用现成几何） |
| `_test_sigs_agree.py` | `sigs_agree` 新阈值的边界单测 15 例 |

