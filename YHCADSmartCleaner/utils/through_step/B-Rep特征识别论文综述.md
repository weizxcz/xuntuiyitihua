# B-Rep 几何特征识别方法 — 学术论文综述

> 整理日期：2026-06-12  
> 重点方向：规则式识别（AAG / 凸凹性）、规则+AI混合方案、通槽/台阶/凹槽识别算法  
> 时间范围：侧重 2020–2025 近五年，包含经典奠基文献

---

## 目录

1. [方法分类总览](#1-方法分类总览)
2. [规则式（Rule-Based）方法](#2-规则式rule-based方法)
   - 2.1 面邻接图 AAG
   - 2.2 边凸凹性（Edge Convexity / Concavity）
   - 2.3 体分解法（Volume Decomposition）
   - 2.4 提示驱动法（Hint-Based）
3. [深度学习方法](#3-深度学习方法)
   - 3.1 AAGNet — 图神经网络 + gAAG
   - 3.2 BRepNet — 拓扑消息传递
   - 3.3 Hierarchical CADNet — 层级图表示
   - 3.4 BRepFormer — Transformer 架构（2025 SOTA）
   - 3.5 BrepMFR — 深度学习 + 域适应
   - 3.6 MFTReNet — 多任务拓扑关系预测
   - 3.7 FeatureFox — 轻量级全景分割（2025）
   - 3.8 EAGIS / Edge-Modulated Dual-GNN
4. [通槽/台阶/凹槽的具体识别算法](#4-通槽台阶凹槽的具体识别算法)
5. [公开数据集与基准](#5-公开数据集与基准)
6. [开源工具](#6-开源工具)
7. [对我们项目的优化建议](#7-对我们项目的优化建议)
8. [参考文献列表](#8-参考文献列表)

---

## 1. 方法分类总览

| 类别 | 核心思路 | 代表方法 | 优势 | 劣势 |
|------|---------|---------|------|------|
| **规则式** | AAG 图匹配 + 几何规则 | Joshi & Chang (1988), Analysis Situs | 可解释、无需训练 | 规则维护难、交叉特征处理差 |
| **体分解** | 毛坯-零件差体积分解 | Woo (1982), Kim & Wilde (1992) | 理论严谨 | 收敛性/复杂度高 |
| **提示驱动** | 制造线索 + 推理重建 | Han & Requicha (1997) | 可处理交叉特征 | 提示定义复杂 |
| **GNN 深度学习** | 面邻接图 + 图神经网络 | AAGNet (2024), CADNet (2022) | 泛化强、端到端 | 需大量标注数据 |
| **Transformer** | 注意力机制处理 B-Rep | BRepFormer (2025) | 全局/局部特征融合好 | 计算量大 |
| **轻量/混合** | 规则特征 + 树模型 | FeatureFox (2025) | 数据需求极低、可解释 | 非端到端、边界错误传播 |

---

## 2. 规则式（Rule-Based）方法

### 2.1 面邻接图 AAG（Attributed Adjacency Graph）

**核心思想**：将 B-Rep 模型转换为图结构，节点 = 面，边 = 面之间的邻接关系，边上附带属性（凸凹性、二面角、边类型等）。特征识别 = 在 AAG 中搜索匹配预定义特征模式的子图。

**奠基工作**：
- **Joshi & Chang (1988)** — 首次将 AAG 用于加工特征识别。将面的凹凸性作为图的边属性，通过子图同构匹配识别槽、孔、台阶等特征。
- **Gao & Shah (1998)** — 引入"最小条件子图"（Minimal Condition Subgraph）来处理交叉特征的识别。

**近期发展**：
- **Extended AAG (EAAG)** — 扩展了传统 AAG，增加更丰富的属性编码（面类型分布、曲率信息等），用于结构特征识别。（SPIE 2025）
- **Multidimensional Attributed Face-Edge Graph (maFEG)** — 用于钣金件的加工特征自适应识别，将面和边的属性统一到多维图中。（Nature Scientific Reports, 2024）
- **Fragmented Surface AAG** — 针对碎片化表面模型的加工特征识别算法，基于 AAG 方法处理非理想拓扑情况。（ACM 2025）

**AAG 属性清单（用于特征识别的关键属性）**：

| 属性 | 作用 | 典型取值 |
|------|------|---------|
| 边凸凹性 | 区分特征边界 | convex / concave / smooth |
| 二面角 | 量化面间夹角 | 0°~360° |
| 边类型 | 线段/圆弧/样条 | line / circle / ellipse / spline |
| 面类型 | 几何面类型 | plane / cylinder / cone / torus |
| 面面积 | 归一化后用于区分 | 连续值 |
| 质心距离 | 拓扑距离的补充 | 归一化连续值 |

### 2.2 边凸凹性（Edge Convexity / Concavity）

**核心概念**：在 B-Rep 中，当两个面共享一条边时，可以通过法向量关系判断该边是凸的（convex）、凹的（concave）还是光滑过渡的（smooth/tangent）。

**判断方法**（经典算法）：
1. 获取共享边 `e` 的两个面 `f₁`, `f₂`
2. 在边 `e` 上取一点 `P`
3. 计算 `f₁` 在 `P` 处的外法向量 `n₁`，`f₂` 在 `P` 处的外法向量 `n₂`
4. 计算边的切向量 `t`
5. 令 `cross = n₁ × n₂`，判断 `cross · t` 的符号：
   - **> 0** → 凹边（concave）
   - **< 0** → 凸边（convex）
   - **≈ 0** → 光滑过渡（G1 连续/smooth）

**在特征识别中的作用**：
- **通槽（through slot）**：由一组凹边围成的面组，两侧面平行，底面与侧面凹边相连
- **盲孔（blind hole）**：圆柱面，所有边都是凹边或光滑边
- **台阶（step）**：一侧凸边、一侧凹边的组合模式
- **圆角（fillet）**：光滑边（G1 连续）连接两个面

**在深度学习中的使用**：
- BRepFormer：将凸凹性编码为 3 维 one-hot 向量（concave/convex/smooth），作为边属性输入
- BrepMFR：凸凹性测试涉及判断共享边的两个面是否形成凹角、凸角或 G1 连续
- Hierarchical CADNet：B-Rep 面之间的边凸凹性是关键输入特征

### 2.3 体分解法（Volume Decomposition）

**核心思想**：将"毛坯体积 - 零件体积"（delta volume）分解为可加工的子体积，然后对子体积分类和合并形成加工特征。

**关键工作**：
- **Woo (1982)** — 交替体积求和分解（ASV），通过凸分解的并/差操作表示实体
- **Kim & Wilde (1992)** — 引入分割技术改进 ASV 的收敛性问题
- **Volume Decomposition Part I (1995)** — 通过凹边的半空间交叉将多面体分解为最大单元（maximal cells）

**与我们项目的关系**：通槽和台阶本质上是"从毛坯中去除的材料体积"的特定形状，体分解法提供了理论支撑。

### 2.4 提示驱动法（Hint-Based）

**核心思想**：从 B-Rep 模型中提取拓扑/几何"线索"（hint），然后通过推理规则重建不完整的特征信息。

**关键工作**：
- **Vandenbrande & Requicha (1993)** — 空间推理自动识别可加工特征
- **Han & Requicha (1997)** — 集成特征设计和特征识别
- **Rahmani & Arezoo (2007)** — 混合提示 + 图方法处理交叉铣削特征

**局限性**：需要人工定义全面且精确的提示和推理规则，难以实现完全自动化。

---

## 3. 深度学习方法

### 3.1 AAGNet（2024）— 图神经网络 + gAAG

- **论文**：Wu, Lei, Peng & Gao. *"AAGNet: A graph neural network towards multi-task machining feature recognition."* Robotics and Computer-Integrated Manufacturing, 2024.
- **代码**：https://github.com/whjdark/AAGNet
- **核心贡献**：
  - 提出 **gAAG**（geometric Attributed Adjacency Graph），在传统 AAG 基础上增加几何采样信息
  - **多任务学习**：同时完成语义分割（每面类别）、实例分割（特征实例分组）、基础分割
  - 在 MFInstSeg 数据集上达到 99.15% 面级准确率
- **输入表示**：
  - 面：UV 网格采样（位置 + 法向量 + 可见性掩码）
  - 边：1D 采样（位置 + 切向量 + 法向量 + 曲率 + 挠率）
  - 属性：面类型、面积、边类型、长度、凸凹性
- **模型架构**：CNN（几何编码）+ GNN（拓扑传播）的多头管道

### 3.2 BRepNet（2021）— 拓扑消息传递

- **论文**：Lambourne et al. *"BRepNet: A topological message passing system for solid models."* CVPR 2021.
- **核心贡献**：
  - 直接在 B-Rep 数据结构上定义卷积核，基于有向共边（coedge）
  - 从面、边、共边提取几何特征（表面类型、边几何、边凸凹性等）
  - 无需转换为体素/点云/网格等中间表示
- **后续工作**：
  - TU Munich 团队将 BRepNet 应用于 MFCAD 数据集，通过迁移学习增强加工特征识别

### 3.3 Hierarchical CADNet（2022）— 层级图表示

- **论文**：Colligan et al. *"Hierarchical CADNet: Learning from B-Reps for Machining Feature Recognition."* Computer-Aided Design, 2022.
- **代码**：
  - GitHub: https://github.com/AndrewColligan/CADNet
  - GitLab: https://gitlab.com/qub_femg/machine-learning/hierarchical-brep-graphs
- **核心贡献**：
  - 提出层级 B-Rep 图表示，编码面拓扑和曲面几何
  - 上层：面邻接图（FAG）捕获拓扑信息
  - 下层：网格面片表示几何细节
  - 边凸凹性作为关键输入特征

### 3.4 BRepFormer（2025）— Transformer 架构 ⭐SOTA

- **论文**：Dai, Huang et al. *"BRepFormer: Transformer-Based B-rep Geometric Feature Recognition."* ICMR 2025.
- **arXiv**：https://arxiv.org/abs/2504.07378
- **核心贡献**：
  - **Transformer 架构**处理 B-Rep，引入虚拟面（virtual face）捕获全局特征
  - 注意力偏置（attention bias）融合边特征和拓扑特征，加强几何约束
  - 提出 CBF 数据集（20,000 个复杂 B-Rep 模型）
  - 在 MFInstSeg、MFTRCAD、CBF 三个数据集上均达到 SOTA
- **详细架构**：
  1. **Feature Extractor**：提取拓扑特征（面最短距离、面角度距离、面质心距离、最短边路径）和几何特征（UV 采样 + 属性）
  2. **Feature Encoder**：边/拓扑特征编码为注意力偏置，面特征编码为 token
  3. **Transformer Block**：8 层 GQA（Grouped Query Attention）+ RMS Norm + SwiGLU
  4. **Recognition Head**：融合全局/局部特征，MLP 分类器
- **关键几何属性编码**：
  - 面属性：类型（9维 one-hot）、面积、质心坐标、是否有理 B 样条
  - 边属性：类型（11维 one-hot）、长度、**凸凹性（3维 one-hot: concave/convex/smooth）**
- **实验结果**：
  - MFInstSeg：Accuracy 99.62%，mIoU 98.74%
  - MFTRCAD：Accuracy 93.16%（比前 SOTA 高 3.28%）
  - 消融实验：边属性（含凸凹性）移除后性能下降最大（-3.65% Accuracy）

### 3.5 BrepMFR（2024）— 深度学习 + 域适应

- **论文**：*"BrepMFR: Enhancing machining feature recognition in B-rep models through deep learning and domain adaptation."* Computer Aided Geometric Design, 2024.
- **代码**：https://github.com/zhangshuming0668/BrepMFR
- **核心贡献**：
  - 专门设计用于 B-Rep 加工特征识别的深度学习网络
  - **语义几何特征增强**：将表面类型、边凸凹性等显式几何特征融入 CNN
  - 建立大规模合成数据集（24 种典型加工特征）
  - 凸凹性测试：判断共享边的两面是否形成凹角、凸角或 G1 连续

### 3.6 MFTReNet（2024）— 多任务拓扑关系预测

- **论文**：Xia, Zhao & Hu. *"Machining feature and topological relationship recognition based on a multi-task graph neural network."* Advanced Engineering Informatics, 2024.
- **核心贡献**：
  - 在 AAGNet 的 gAAG 多任务基础上，增加特征间拓扑关系预测头
  - 同时预测：语义类别、实例分组、特征间拓扑关系
  - MFInstSeg 面级准确率 99.56%

### 3.7 FeatureFox（2025）— 轻量级全景分割 ⭐值得关注

- **论文**：Fuchs, Kacan, Haag & Lohse. *"FeatureFox: Sample-Efficient Panoptic Graph Segmentation for Machining Feature Recognition in B-Rep 3D-CAD Models."* arXiv 2604.26770, 2025.
- **核心贡献**：
  - **全景分割范式**（Panoptic Segmentation）统一实例分组 + 语义分类
  - **极致数据效率**：仅 ~250 个训练样本即可达到 PQ > 0.9（AAGNet 需要 ~5000 个）
  - **训练极快**：全量 MFInstSeg 训练仅需 8 秒（AAGNet 需 38 分钟）
  - **首次在真实工业 CAD 零件上验证**（270 个手动标注的真实零件 → 泛化到 NIST 测试零件）
- **方法流程**：
  1. 构建 gAAG 面邻接图
  2. 将面属性传播到边，构建**增强边属性**（二面角、凹凸性、面积/周长比、归一化长度、面质心距离等）
  3. 训练校准的**二值 XGBoost 边分类器**：判断边的两个面是否属于同一特征实例
  4. 剪枝图 → 连通分量 = 特征实例
  5. 对每个实例提取聚合属性（面数、边数、对数特征长度、面/边类型直方图、曲率分布、图谱拓扑特征、边界环数等）
  6. 训练语义 XGBoost 分类器预测实例类别
- **关键洞察**：规则式特征（凸凹性、二面角、面积比等）在轻量模型中依然是最核心的判据
- **对我们的意义**：FeatureFox 证明了**精心设计的手工特征 + 树模型**可以达到接近 GNN 的效果，且不需要大量数据，非常适合工业场景

### 3.8 EAGIS / Edge-Modulated Dual-GNN

- **EAGIS**：Li et al. *"Edge Adjacency Graph and Neural Network Architecture for Machining Feature Recognition."* Int. J. Adv. Manuf. Technol., 2025. — 将边作为节点训练 GNN，特征实例检测 = 二值边预测任务。
- **Edge-Modulated Dual-GNN**：*"An Edge-Modulated Dual-Graph Neural Network for Interacting Machining Feature Recognition."* ResearchGate 2025. — 双图结构处理交叉特征。

---

## 4. 通槽/台阶/凹槽的具体识别算法

### 4.1 通槽（Through Slot）的规则式识别

**几何定义**：一个完全贯穿零件的槽形凹陷，由 3 个或更多面围成（底面 + 两个侧面 + 可选的端面），两侧面平行或近似平行。

**基于 AAG 的识别规则**：
1. 在 AAG 中搜索满足以下条件的子图：
   - 存在一个**平面底面** `F_bottom`
   - `F_bottom` 通过**凹边**与两个**平面侧面** `F_left`, `F_right` 相邻
   - 两个侧面大致**平行**（法向量反向：n_left ≈ -n_right）
   - 底面与两侧面的**二面角**均在约 80°~100° 范围内（近似垂直）
   - 底面法向量与侧面的交线方向大致垂直
2. **通槽 vs 盲槽**的区分：
   - 通槽：槽的两端没有封闭面，即槽的侧面/底面在槽的两端通过**凸边**与非槽面相邻
   - 盲槽：至少一端有封闭面（通过凹边与底面/侧面相邻）
3. **通槽方向的确认**：通过侧面法向量的方向确认槽的延伸方向

### 4.2 台阶（Step）的规则式识别

**几何定义**：零件表面的阶梯状变化，由两个以上面围成，一侧升高形成台阶。

**识别规则**：
1. 在 AAG 中搜索满足：
   - 存在一个**平面台阶面** `F_step`
   - `F_step` 通过**凹边**与一个**平面侧面** `F_wall` 相邻
   - `F_wall` 通过**凸边**与上方的**平面顶面** `F_top` 相邻
   - `F_step` 的法向量与 `F_top` 的法向量大致平行（方向相同）
   - `F_wall` 的法向量与 `F_step`、`F_top` 的法向量大致垂直
2. 区分**单台阶**和**多级台阶**：检查是否存在连续的凹-凸边交替模式

### 4.3 凹槽/口袋（Pocket）的规则式识别

**几何定义**：零件表面的封闭凹陷区域，由底面和多个侧面围成。

**识别规则**：
1. 在 AAG 中搜索满足：
   - 存在一个**平面底面** `F_bottom`
   - `F_bottom` 通过**凹边**与一组**侧面** `{F_wall_i}` 相邻
   - 所有侧面围成一个**封闭环**（通过凹边或光滑边相连）
   - 底面法向量指向材料内部（凹陷方向）
2. **盲口袋 vs 通口袋**：
   - 盲口袋：底面完整存在，所有侧面通过凹边与底面连接
   - 通口袋：底面不存在（贯穿零件），侧面直接通过凸边与另一侧的面相邻

### 4.4 圆角（Fillet/Blend）的识别

**识别规则**：
1. 在 AAG 中搜索满足：
   - 存在**圆柱面或 B 样条面** `F_fillet`
   - `F_fillet` 通过**光滑边**（G1 连续/相切）与两个相邻面相连
   - `F_fillet` 的曲率半径一致或渐变
2. 圆角半径可通过面的几何参数直接获取

### 4.5 交叉特征的处理

**问题**：当通槽与另一个通槽交叉时，共享区域的面可能属于两个特征，导致拓扑结构变化。

**经典策略**：
- **最小条件子图**（Gao & Shah 1998）：放宽子图匹配条件，允许部分属性缺失
- **体分解 + 合并**：先分解为基本体积单元，再按规则合并为特征
- **提示驱动推理**：从不完整的残留线索重建完整特征

**深度学习策略**：
- **实例分割**：AAGNet/MFTReNet 通过实例分组处理交叉特征
- **全景分割**：FeatureFox 通过边分类器剪枝图，自然处理交叉

---

## 5. 公开数据集与基准

| 数据集 | 规模 | 特征类别数 | 特点 | 来源 |
|--------|------|-----------|------|------|
| **MFInstSeg** | 62,495 模型 | 24 类加工特征 | 含语义+实例标签，最广泛使用 | AAGNet 作者发布 |
| **MFTRCAD** | 28,661 模型 | 26 类 | 从 24 类细分，含拓扑关系标签 | MFTReNet 作者发布 |
| **CBF** | 20,000 模型 | 4 类（含复杂特征） | 更复杂拓扑，贴近工业应用 | BRepFormer 作者发布 |
| **CADSynth** | 100,000 模型 | 24 类典型特征 | 大规模合成数据集 | SciDB |
| **MFCAD** | 未公开 | 24 类 | BRepNet 迁移学习使用 | — |
| **SMCAD** | 未公开 | 钣金特征 | 钣金零件 B-Rep | Nature Sci. Rep. 2024 |
| **NIST CAD Models** | 公开 | — | 真实工业 CAD 测试基准 | NIST |

**MFInstSeg 的 24 类加工特征**（供参考）：
blind-hole, through-hole, blind-slot, through-slot, rectangular-pocket, circular-pocket, chamfer, fillet, step, etc.

---

## 6. 开源工具

| 工具 | 地址 | 说明 |
|------|------|------|
| **Analysis Situs** | https://analysissitus.org / https://gitlab.com/ssv/AnalysisSitus | **唯一开源的通用 CAD 特征识别框架**，基于 OpenCASCADE，支持 AAG、凸凹性分析，内置槽/孔/圆角等特征识别 |
| **AAGNet** | https://github.com/whjdark/AAGNet | gAAG + GNN 多任务加工特征识别 |
| **BrepMFR** | https://github.com/zhangshuming0668/BrepMFR | B-Rep 加工特征识别 + 域适应 |
| **CADNet** | https://github.com/AndrewColligan/CADNet | 层级 B-Rep 图 + 深度学习 |
| **Hierarchical BRep Graphs** | https://gitlab.com/qub_femg/machine-learning/hierarchical-brep-graphs | 层级 B-Rep 图生成脚本 |

---

## 7. 对我们项目的优化建议

> 基于论文综述，结合我们当前 STEP 文件拓扑/几何规则识别方法的现状。

### 7.1 短期优化（保持规则式框架）

1. **完善 AAG 属性体系**
   - 当前已使用凸凹性，可增加：**二面角连续值**（不仅是离散的凸/凹/光滑）、**边长度归一化**、**面面积比**
   - 参考 FeatureFox 的增强边属性：面积/周长比、归一化长度、面质心距离

2. **增强通槽识别规则**
   - 当前可能仅依赖凹边环，可增加：侧面**平行度检测**（法向量反向且平行）、**贯穿性检测**（两端面为凸边）
   - 参考 Analysis Situs 的槽识别算法

3. **处理交叉特征**
   - 当通槽与台阶交叉时，引入"最小条件子图"策略：放宽匹配条件，允许部分属性缺失后补充推理

4. **增加面类型约束**
   - 通槽侧面应为平面、圆角面应为圆柱面/样条面 — 增加面类型作为 AAG 属性

### 7.2 中期优化（规则 + 轻量学习）

5. **参考 FeatureFox 路线**
   - 用规则生成训练标注 → 训练轻量 XGBoost 边分类器 → 剪枝图得到实例 → XGBoost 分类器识别类别
   - 优势：仅需 ~250 个标注样本，训练秒级，可解释
   - 适合我们的场景：数据量有限、需要可解释性

6. **规则标注 + GNN 微调**
   - 用我们现有的规则识别器在大量 STEP 文件上生成伪标签
   - 用伪标签训练 AAGNet 或类似 GNN 进行端到端识别
   - 在规则识别不确定的样本上用 GNN 补充

### 7.3 长期方向

7. **BRepFormer 级别的 Transformer 模型**
   - 如果需要处理极复杂特征和大规模数据，可考虑引入 Transformer 架构
   - 注意力偏置（融合凸凹性、拓扑距离）的设计思想可借鉴到规则方法中

8. **全景分割评估指标**
   - 引入 Panoptic Quality (PQ) 作为统一评估指标，同时衡量实例分组和类别识别的正确性

---

## 8. 参考文献列表

### 经典规则式方法

| # | 文献 | 年份 | 关键贡献 |
|---|------|------|---------|
| 1 | Joshi & Chang, *"Graph-based heuristics for recognition of machined features from a 3D solid model"* | 1988 | 首次将 AAG 用于特征识别 |
| 2 | Henderson, *"Extraction of feature information from three-dimensional CAD data"* | 1984 | 规则式特征识别先驱 |
| 3 | Gao & Shah, *"Automatic recognition of interacting machining features based on minimal condition subgraph"* | 1998 | 最小条件子图处理交叉特征 |
| 4 | Vandenbrande & Requicha, *"Spatial reasoning for automatic recognition of machinable features"* | 1993 | 提示驱动特征识别 |
| 5 | Rahmani & Arezoo, *"A hybrid hint-based and graph-based framework for recognition of interacting milling features"* | 2007 | 混合提示+图方法 |
| 6 | Woo, *"Feature extraction by volume decomposition"* | 1982 | 体分解法奠基 |
| 7 | Kim & Wilde, *"A convergent convex decomposition of polyhedral objects"* | 1992 | 改进 ASV 收敛性 |

### 近期规则式方法

| # | 文献 | 年份 | 关键贡献 |
|---|------|------|---------|
| 8 | SPIE, *"Structure feature recognition using EAAG"* | 2025 | 扩展 AAG |
| 9 | ACM, *"Machining feature recognition for models with fragmented surfaces"* | 2025 | 碎片化表面处理 |
| 10 | Nature Sci. Rep., *"Adaptive recognition of machining features in sheet metal parts"* | 2024 | maFEG 钣金特征识别 |

### 深度学习方法

| # | 文献 | 年份 | 关键贡献 |
|---|------|------|---------|
| 11 | Wu et al., *"AAGNet: A graph neural network towards multi-task machining feature recognition"* (RCIM) | 2024 | gAAG + 多任务 GNN |
| 12 | Lambourne et al., *"BRepNet: A topological message passing system for solid models"* (CVPR) | 2021 | B-Rep 拓扑消息传递 |
| 13 | Colligan et al., *"Hierarchical CADNet: Learning from B-Reps for Machining Feature Recognition"* (CAD) | 2022 | 层级图表示 |
| 14 | Dai et al., *"BRepFormer: Transformer-Based B-rep Geometric Feature Recognition"* (ICMR) | 2025 | Transformer + 注意力偏置，SOTA |
| 15 | *"BrepMFR: Enhancing machining feature recognition in B-rep models through deep learning and domain adaptation"* (CAGD) | 2024 | 深度学习 + 域适应 |
| 16 | Xia et al., *"MFTReNet: Machining feature and topological relationship recognition"* (AEI) | 2024 | 多任务 + 拓扑关系 |
| 17 | Fuchs et al., *"FeatureFox: Sample-Efficient Panoptic Graph Segmentation for Machining Feature Recognition"* (arXiv) | 2025 | 轻量全景分割，极致数据效率 |
| 18 | Li et al., *"Edge Adjacency Graph and Neural Network Architecture for Machining Feature Recognition"* (IJAMT) | 2025 | 边图神经网络 |
| 19 | *"Edge-Modulated Dual-GNN for Interacting Machining Feature Recognition"* | 2025 | 双图处理交叉特征 |

### 综述文献

| # | 文献 | 年份 |
|---|------|------|
| 20 | Shi et al., *"A critical review of feature recognition techniques"* (CAD&A) | 2020 |
| 21 | Babic et al., *"A review of automated feature recognition with rule-based pattern recognition"* (Computers in Industry) | 2008 |

---

> **文档维护说明**：如需补充新论文或更新方法细节，请直接在对应章节追加。本文档中的论文信息基于 2026-06 的搜索结果整理。
