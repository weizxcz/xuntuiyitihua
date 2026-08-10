# CLAUDE.md — featurefox_ncti 模块

> **一句话定位**：FeatureFox 的 **NCTI 原生数据源版** —— 识别直接在 NCTI AiModel 数据
> （`FaceAttr`/`EdgeAttr`）上做，输出 `cell_id`（`ai.FaceID` 位置索引）**零映射**，
> 直接对齐 Geo-Rec 训练图节点空间。是 featurefox(STEP版) 的升级版，与之平行、不混合。

## 为什么有这个模块

featurefox(STEP版) 在 STEP 文本上识别，输出 STEP face_id，须经几何最近邻映射到 NCTI cell_id
才能喂 Geo-Rec 训练图。该映射对曲面类特征（圆角/倒角/锥面/自由曲面）不可靠，阻碍多特征
scale 到 Geo-Rec 训练。本模块消除映射：识别在 NCTI 空间做，输出即 cell_id。

**额外收益**：NCTI `EdgeAttr[0/1/2]` 直接给凸凹性（占边特征重要性 62%），比 STEP 版质心
偏移法反推更准；`FaceAttr[5]` 给面积、`EdgeAttr[3]` 给边长，免去 STEP 文本反推。

## 与 featurefox(STEP版) 的差异

| 维度 | STEP 版 | **NCTI 版（本模块）** |
|---|---|---|
| 数据源 | StepParser 解析 STEP 文本 | NctiPart（NCTI AiModel） |
| 凸凹性 | `_build_edge_convexity_map` 质心偏移法反推（连续值） | `EdgeAttr[0/1/2]` 直接给（离散 ±1/0） |
| 面积/边长/边类型 | 鞋带公式 / 弦长反推 / curve 实体解析 | `FaceAttr[5]` / `EdgeAttr[3]` / `EdgeAttr[9,4]` 直接取 |
| 法向/重心 | `_face_normal_effective` / `_face_centroid`（StepParser） | `GetNormalByUV` / `GetFacePointFromUV` at UV(0.5,0.5) |
| 输出面号 | STEP face_id（entity_id）→ **需几何映射** | **cell_id（位置索引），零映射** |
| 训练数据 | `通槽\steps`（17799） | `D:\wyg\data\data\steps`（62495，超集，多类标注 0-24） |
| 运行依赖 | 纯 Python（任何环境） | **NCTI SDK + yhcad_py312** |
| 分类器 | XGBoost 200/d6 + 200/d4 | **同（必须重训，特征分布变了）** |

**30 维边特征定义（FEATURE_NAMES）与 26 维实例特征定义（INSTANCE_FEATURE_NAMES）与 STEP 版完全一致**，仅数据来源不同 → 特征重要性可与 STEP 版直接对比。

## 文件结构

| 文件 | 职责 | 与 STEP 版关系 |
|---|---|---|
| `ncti_backend.py` | NCTI 数据后端：`NctiPart`/`NctiFaceAttrs`/`build_face_graph`/`load_part` | **新写** |
| `edge_features.py` | 30 维边特征 + `build_face_graph(part)` | 改写（保留 FEATURE_NAMES，数据换 backend） |
| `instance_features.py` | 26 维实例特征 + `extract_instance_features` | 小改（parser→part） |
| `instance_data.py` | 标签加载 + 边训练数据（零映射） | 小改（路径 + 删 shell_face_order） |
| `train.py` | 第一级边分类器训练 + 校准 | 小改（ncti 参数 + os._exit） |
| `train_instance.py` | 第二级实例分类器（组件同源） | 小改（part + os._exit） |
| `predict.py` | 预测（输出 cell_id，零映射） | 小改（删 StepParser） |
| `evaluate.py` | 评估 P/R/F1（零映射直比 seg9） | 小改（删全部映射逻辑） |
| `_smoke.py` | 单件冲烟（建图 + 特征 dump + 面数断言） | 新写（诊断） |

模型产物（训练后生成）：`edge_clf.json` + `calibrator.pkl`（第一级）、`inst_clf.json` + `inst_calibrator.pkl`（第二级）。

## 关键设计决策

1. **cell_id 零映射**：cell_id = `ai.FaceID` 位置索引（0..n-1），与 Geo-Rec 训练标签 cell_id 严格同空间。沿用 Geo-Rec 假设（shell ADVANCED_FACE 顺序 == ai.FaceID 顺序）；`NctiPart` 建图时用 `count_advanced_faces(stp_path)` 断言 `n_faces == ADVANCED_FACE 数`，不等则告警+跳过（`instance_data.collect_dataset` / `train_instance.collect_instance_dataset` 已实现）。

2. **符号约定对齐**（FEATURE_NAMES[0] dihedral_sign）：concave=+1 / convex=-1 / smooth=0，与 STEP 版一致。但分布从连续值变离散 ±1/0 → **旧 STEP 版模型失效，必须用新 62495 件 + NCTI 特征从零重训**。

3. **NCTI 导入约定A**（`load_part`）：`doc.New("OCC","DCM",0)` + `RunCommand("cmd_ncti_import_file", stp, obj)`，与 Geo-Rec `step2graph_mfr_ncti`、`ncti_faceid_map.import_step_to_ncti` 完全一致。**禁调** `SetImportAssemelFile`/`SetCreateGeGeom`（会改面数，破坏 cell_id 对齐）。

4. **组件同源训练**（第二级，`train_instance`）：原样保留 STEP 版方法论 —— 用第一级边剪枝连通分量作训练样本（非 inst 矩阵真实分组），保证 train/serve 一致（featurefox §6.1 教训）。

## 用法

所有命令从 `YHCADSmartCleaner/utils/through_step/` 执行，**必须用 yhcad_py312 环境**（匹配 `ncti_python312.pyd`）：

```bash
# 单件冲烟（验证 NctiPart 建图 + 特征符号，无需训练模型）
"D:/Anaconda3/envs/yhcad_py312/python.exe" -m featurefox_ncti._smoke

# 训练第一级边分类器（0=全量 62495；数字=前 N 件）
"D:/Anaconda3/envs/yhcad_py312/python.exe" -m featurefox_ncti.train 0

# 训练第二级实例分类器（组件同源）
"D:/Anaconda3/envs/yhcad_py312/python.exe" -m featurefox_ncti.train_instance 0

# 评估（文件数 阈值 offset；offset 测训练集外文件验证泛化）
"D:/Anaconda3/envs/yhcad_py312/python.exe" -m featurefox_ncti.evaluate 0 0.35 50000

# 单文件预测
"D:/Anaconda3/envs/yhcad_py312/python.exe" -m featurefox_ncti.predict "D:\wyg\data\data\steps\xxx.step" 0.35
```

环境变量：`PYTHONIOENCODING=utf-8`（中文输出）。所有脚本末尾 `os._exit(0)` 防 NCTI DLL 析构 segfault（退出码 127 正常）。

## 验证点（实现后必查）

1. **单件冲烟**：`_smoke.py` 对一个通槽件 `build_face_graph`，dump 30 维特征，核对凸凹性符号（通槽内凹边 dihedral_sign=+1、外凸角=-1）+ 面数断言（n_faces == ADVANCED_FACE 数）。
2. **面数断言**：`collect_dataset` 抽样统计面数不匹配占比；若 >1% 需排查 NCTI 导入序列。
3. **NCTI 环境**：`config_load.init_ncti_config()` 非 None；`test_ncti_init.py` 冒烟通过。
4. **第一级训练**：`train 0` 全量 62495，test 集 F1 持平/超 STEP 版；特征重要性 top1 仍是凸凹性维度。
5. **第二级训练**：`train_instance 0`，组件同源，test F1。
6. **端到端 F1**：`evaluate 0 0.35 50000`（holdout 训练外），面级 F1 目标 ≥ STEP 版 85%（NCTI 凸凹性更准，预期略高）。
7. **零映射 sanity**：predict 输出 cell_id 集合与 seg9 **直接比**（不经任何映射），EXACT 率正常。

## 批量训练工程方案（subprocess 隔离 + 崩件容错）

**问题**：NCTI 批量处理有两个 segfault 来源（已定位）：
1. **C++ 累积**：批量 50-100 件后 NCTI 内部资源累积 segfault（约定A/B 都崩，非 Document 累积、非 ResetCaseResult 能解）。
2. **特殊崩件**：少数 STEP 件（如 `20221121_154647_1052.step`）触发 NCTI 导入/建图 segfault（独立进程单件也崩），杀整个 worker 进程。

**解法**（已实施于 `collect_dataset` / `collect_instance_dataset`）：
- **subprocess 子进程隔离**：每 40 件一个独立 python 进程（[`_chunk_worker.py`](_chunk_worker.py) / [`_inst_chunk_worker.py`](_inst_chunk_worker.py)），进程退出彻底释放 NCTI → 解决累积。
- **增量 pickle**：worker 每处理成功一件就原子写 pickle（`.tmp` + `os.replace`）；崩件 segfault 杀 worker 时，崩件前数据已落盘，主进程读 pkl 合并（崩件及同 chunk 后续丢失，少数件可接受）。
- **不 check 退出码**：worker exit 127（NCTI 析构正常）/139（崩件）都非0，主进程只看 pkl 是否存在。

**验证**：train 100 + train_instance 100 全通过（崩件 1052 容错，两级模型生成，dihedral_sign 0.70 top1 / edge_prob_mean top1，符合 featurefox §10 预期）。

**代价**：每 chunk python 启动 + NCTI init 开销（~3-5s/chunk）。62495 件 / 40 ≈ 1562 chunks，每级训练数小时。

## 风险

- **NCTI 运行时依赖**：训练 + 推理都要 NCTI SDK + yhcad_py312（不像 STEP 版纯 Python）。推理时 GUI 本就用 NCTI，训练离线进行。
- **性能**：NCTI 导入 ~0.3s/件 vs STEP 正则 ~5ms/件。62495 件第一级训练 ~5h+，第二级更久。建议先小批（如 2000）跑通再全量。
- **shell==ai.FaceID 假设**：OCC 合成数据成立；真实工业件 NCTI 可能合并共面致假设破裂。本版只服务 62495 合成件训练+评估；真实件推理若面数不匹配，降级告警+跳过（不硬映射）。
- **多类扩展**：本版通槽单类（seg=9）。多类 panoptic（第二级输出 24 类 seg）列为后续。

## 依赖

- **NCTI SDK**（yhcad_py312 环境，`config/config_load.py:init_ncti_config`）
- `xgboost`、`scikit-learn`（等渗校准）、`networkx`（连通分量）、`numpy`
- 复用：`ncti_faceid_map.py`（`init_ncti_safe`）、`geom_helpers.py`（`_dot`/`_vec_len`/`_angle_between_normals`）
- 参照：`detect_through_step_ncti.py`（NCTI 几何查询范式）、`featurefox/edge_features.py`（30 维聚合公式）
