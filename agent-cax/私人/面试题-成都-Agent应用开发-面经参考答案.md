# 成都 · Agent 应用开发 · 面经参考答案

> 基于图片面经 23 题整理，结合韦永根简历项目作答。  
> 原则：**不编造上线指标**；没做过的如实标注，并补「若我做会怎么迁移」。

---

## 使用说明

| 标签 | 含义 |
|------|------|
| **【项目】** | 可直接引用简历/源码里的真实经历 |
| **【通用】** | 行业通识 + 个人理解，面试时可接「我们项目里类似…」 |
| **【诚实】** | 项目没做过但要如实说，并补迁移思路 |

**我的项目速览（面试开场 30 秒）：**

> 我主要做 **CAD 草图建模 Agent（Sketch-Modeling-Agent）** 和 **就业匹配 Agent（FindJobs-Agent）**，核心能力是 Multi-Agent 编排、Tool 约束、上下文压缩、结构化输出。知识注入上更偏 **SKILL + reference 渐进披露**，不是典型「向量库 + 文档上传」RAG，但检索、融合、降噪的思路可以类比迁移。

---

## 一、图数据库 Neo4j

### Q1. Neo4j 如何定义实体类型？关系能有多少种？关系如何定义？实体属性如何映射？

**【诚实 + 通用】**

我实习项目 **没有落地 Neo4j**，但理解其建模方式，面试可这样答：

**实体类型（Label）**

- 用 **Label** 定义类型，如 `:Person`、`:Company`、`:Skill`
- 一个节点可有多个 Label：`(n:Person:Employee)`

**关系（Relationship）**

- 关系是 **有向、有类型** 的：`(a)-[:WORKS_AT {since: 2024}]->(b)`
- 类型数量 **没有硬上限**，按业务建模即可（`:HAS_SKILL`、`:MATCHES_JOB` 等）
- 关系上也可挂属性（权重、时间、来源）

**表 → 图的映射（以 FindJobs 为例类比）**

| 关系型表 | 图模型 |
|----------|--------|
| `student` 表一行 | 节点 `(:Student {id, name, major})` |
| `job` 表一行 | 节点 `(:Job {title, salary})` |
| `student_skill` 关联表 | 边 `(:Student)-[:HAS_SKILL {level: 0.8}]->(:Skill)` |
| 外键 `company_id` | 边 `(:Job)-[:POSTED_BY]->(:Company)` |

**设计原则：** 频繁 **多跳关联查询**（「某技能的学生 → 匹配岗位 → 公司」）用图库；强事务 CRUD 仍放 MySQL，**图 + 关系库双写** 是常见架构。

**若结合我的项目：** FindJobs 目前是 Python dict + 课程映射表，若升级可做 `Student -[:COVERS]-> Course -[:REQUIRES]-> Skill <-[:NEEDS]- Job` 做培养方案缺口分析，比多表 JOIN 更直观。

---

### Q2. 如何根据用户自然语言查询 Neo4j？查询内容如何映射到具体节点？

**【通用 + 迁移思路】**

典型链路：**NL → 结构化查询 → Cypher 执行 → 结果自然语言化**

```
用户问句
  → Query 理解（实体/关系抽取 或 Text-to-Cypher）
  → Cypher：MATCH (s:Student)-[:HAS_SKILL]->(sk:Skill {name:'Python'}) ...
  → 子图/路径结果
  → LLM 生成可读答案（可选）
```

**映射方式：**

1. **词典/同义词表**：「Python 编程」→ `Skill.name IN ['Python', 'python开发']`
2. **NER + 实体链接**：抽 `槽位` 再对齐到节点 ID
3. **Text-to-Cypher**：Few-shot 把 NL 翻成 Cypher（要防注入，只读 + 模板白名单）
4. **GraphRAG**：先从向量库找相关节点子图，再 Cypher 扩展邻居

**【项目类比】** Sketch Agent 里用户说「把圆半径改成 50」——不是查图库，但同样是 **NL → 结构化参数（task + current_file）→ 工具执行**。Neo4j 场景是把「圆半径」映射成属性或关系上的 filter。

---

## 二、RAG 架构与优化（面经核心）

### Q3. 用户提问时，如何同时检索文本块和相关图片块？chunk_size 如何确定？RecursiveCharacterTextSplitter 哪个参数避免句子被拦腰切断？

**【通用 + 项目类比】**

#### 文本 + 图片同时检索

| 方案 | 做法 |
|------|------|
| **统一多模态 Embedding** | 文本块、图片（或 caption）进同一向量空间，一次 ANN 检索 |
| **双索引 + 融合** | 文本走 BM25/向量，图片走 CLIP/多模态向量，RRF 合并 |
| **图片先结构化** | OCR/VLM 生成描述 + 表格 JSON，当文本块检索 |
| **Agent 按需读** | 目录/metadata 检索，命中后再 `read_file` 拉原文/图 |

**【项目】** Sketch 子 Agent 的 `attachments`：

- 用户 `@图片路径` → `extract_attachment_paths` 抽出路径
- 子 Agent 侧 `build_attachment_blocks`：PNG/JPG → base64 多模态 block；脚本 → text block
- **不是向量检索图片**，而是 **意图识别后把附件结构化传给 VLM**——适合 CAD「照图绘制」闭域场景

#### chunk_size 如何定

1. **看 Embedding 模型**：常用 256~512 token，不超过模型最大长度
2. **看文档类型**：API 文档按函数切；论文按段落；代码按函数/类
3. **看评测**：在验证集上网格搜索 chunk_size × overlap，看 Recall@K 和答案忠实度
4. **经验起点**：中文技术文档 `chunk_size=500~800 字符`，`overlap=10%~20%`

#### RecursiveCharacterTextSplitter 防硬切

- **`separators`**：优先级列表，如 `["\n\n", "\n", "。", " ", ""]`，**先在段落/句子边界切，最后才单字切**
- **`chunk_overlap`**：相邻块重叠，避免边界信息丢失
- **`length_function`**：按 token 还是字符计长
- **`is_separator_regex`**：分隔符是否正则

**核心：** 递归尝试 separators 列表，**尽量在语义边界切**，而不是固定字数一刀砍。

---

### Q4. 什么是召回率、精确率？为什么能高召回？两者权衡？

**【通用】**

以 RAG 检索为例，设「相关文档集合」为 Ground Truth：

| 指标 | 公式 | 含义 |
|------|------|------|
| **召回率 Recall** | 检索到的相关数 / 全部相关数 | 漏检少不少 |
| **精确率 Precision** | 检索到的相关数 / 检索返回总数 | 噪声少不少 |

**为什么能高召回？**

- 多路召回（向量 + BM25 + 关键词）
- Query 改写 / 多 query 扩展
- 增大 Top-K、降低相似度阈值
- HyDE（先生成假设答案再检索）

**代价：** 召回↑ 通常 精确率↓（塞进更多 chunk，噪声变多）→ 需要 **Rerank / 过滤 / 压缩** 拉回精确率。

**【诚实】** 我的主项目没有标准 RAG 评测集，没有 Recall/Precision 数字。若面试被追问，我会说：

> 我们 CAD 平台 **混合推理** 用几何规则 + GNN + 交集，本质也是「多路召回 + 融合」：规则召回率高、AI 补语义，交集策略提高精确率。评测上我会建 Golden QA，用 **Hit@K、MRR、答案忠实度** 做回归。

---

### Q5. 重排解决什么根本问题？为什么多路召回？「侧重重排」解决什么？

**【通用 + 项目类比】**

#### 重排（Rerank）解决的根本问题

**双塔向量检索**（Bi-Encoder）快但 **语义交互浅**；**Cross-Encoder Rerank** 对 `(query, doc)` 深度打分，解决：

> **「召回阶段排序不准」—— 相关文档在 Top50 里但不在 Top5。**

#### 为什么多路召回

单一路径有盲区：

| 路径 | 擅长 | 弱项 |
|------|------|------|
| 向量 | 语义相似、改写问法 | 专有名词、数字、ID |
| BM25/倒排 | 关键词精确匹配 | 同义词、口语化 |
| 知识图谱 | 结构化关系 | 覆盖不全 |
| 元数据过滤 | 权限/版本/类型 | 需提前标注 |

多路召回提高 **Recall**，再用 RRF / 加权融合 / Rerank 提 **Precision**。

#### 「侧重重排」

面经里常指：**召回可以宽（Top50~100），生成前用 Rerank 压到 Top3~5**，把算力花在「精排」而不是「盲目扩大 context」。

**【项目类比】**

- **Tool 白名单** ≈ 元数据硬过滤，先砍掉不可能相关的「工具文档」
- **API Index 正向列举** ≈ 高精度「检索」，模型不需要从海量 API 里猜
- **CAD 混合推理「交集」** ≈ 多路召回后的 **精确率兜底**

---

### Q6. 上下文爆炸怎么处理？召回了低质量文档如何过滤噪声？

**【项目 + 通用】**

#### 上下文爆炸（Context Explosion）

| 手段 | 说明 | 我的项目 |
|------|------|----------|
| **减少塞入量** | Rerank 后只留 Top-K | reference 按需 `read_file`，不全量灌 prompt |
| **上下文压缩** | 摘要、提取与 query 相关句子 | 三层 Memory 压缩（见下） |
| **外置状态** | 关键信息写文件/DB | Plan B「文件即状态」，脚本在磁盘不在对话里 |
| **子 Agent 隔离** | 长输出不回流主 Agent | Orchestrator–Worker，主 Agent 只留摘要 |
| **Lost in the Middle** | 关键约束放 system 首尾 | `api_index`、output 纪律放尾部 |

**【项目】`context.py` 三层压缩：**

1. **Layer 1 输出裁剪**：Tool 返回 snip，去掉大块代码回灌
2. **Layer 2 LLM 摘要**：超 50% 窗口触发，保留路径/决策/错误/待办
3. **Layer 3 硬折叠**：超 90% 只留 system + 最近 N 轮 + 摘要

#### 低质量召回过滤

1. **分数阈值**：向量相似度 < τ 丢弃
2. **Rerank 分阈值**：Cross-Encoder 分过低不进 context
3. **元数据过滤**：版本过期、无权限、来源不可信
4. **MMR**：去冗余相似 chunk
5. **LLM 相关性判断**：小模型/规则对每 chunk 打 yes/no（成本高）
6. **权重过滤**：问答策略里按来源、类型、新鲜度加权（见 Q9）

**【项目】** 没有向量 chunk，但 **动态 Tool 过滤** 等价于「不把无关工具文档暴露给模型」——从源头上减少噪声。

---

### Q8. 多模态为什么用双通路？什么时候 OCR，什么时候 LVM？

**【通用 + 项目】**

#### 为什么双通路（OCR + LVM）

| 单通路问题 | 双通路互补 |
|------------|------------|
| 纯 OCR | 版式、逻辑关系、示意图理解差 |
| 纯 VLM | 小字、表格数字、长文档成本高、偶发幻觉 |
| 工程现实 | 没有一种模型通吃所有版式 |

**典型双通路：**

```
PDF/图片
  ├─ 通路 A：OCR / 版面分析 → 结构化文本、表格 JSON（精确、可检索）
  └─ 通路 B：VLM → 页面摘要、图表语义、复杂版式理解
        → 融合后入向量库或送 LLM
```

#### 选型建议

| 场景 | 优先 |
|------|------|
| 发票、合同、密集表格 | OCR + 表格结构还原 |
| 扫描件、手写 | OCR + 纠错 |
| 流程图、CAD 截图、UI 原型 | **VLM**（要空间关系） |
| 图文混排说明书 | OCR 打底 + VLM 补语义 |
| 成本敏感、要可溯源 | OCR 为主，VLM 只处理 OCR 失败页 |

**【项目】** Sketch CAD Agent：

- 用户 `@草图.png` → **直接走 VLM 多模态 block**（要几何关系，不是抽文字）
- 用户 `@参考脚本.py` → **读文本**，不走 OCR
- 这是 **按附件类型路由**，和 RAG 双通路思想一致

---

### Q9. 多路召回的权重如何设计？

**【通用 + 诚实】**

#### 常见融合方式

1. **RRF（Reciprocal Rank Fusion）**  
   `score = Σ 1/(k + rank_i)`，**不需手工调权重**，工业界很常用（k 常取 60）

2. **线性加权**  
   `final = w1·vec + w2·bm25 + w3·graph`，在验证集上网格搜索 / 学习排序

3. **分场景权重**  
   - 专有名词多 → BM25 权重大  
   - 口语化问法 → 向量权重大  
   - 时效性强 → 新鲜度衰减因子

4. **级联**  
   先宽召回 100，Rerank 取 5——权重隐含在 Rerank 模型里

#### 问答策略里的「权重过滤」

面经常指：对不同 **来源类型** 设权，例如：

| 来源 | 权重 |
|------|------|
| 官方 FAQ | 1.0 |
| 内部 wiki | 0.9 |
| 爬虫网页 | 0.6 |
| 过期文档 | 0 或降权 |

再叠 **时间衰减**：`w' = w × exp(-λ × days)`

**【诚实】** 我没做过生产级 RRF 调参。若做 FindJobs 岗位匹配，我会对「课程库 / 岗位 JD / 学生简历」分源加权，官方课纲权重高于爬虫 JD。

---

### Q11~15. 指标、并行/串行、周期、耗时拆解、流式

#### Q11. 初版 vs 优化版 Recall/Precision（面经提到 91.6%）

**【诚实】**

> 面经里那位候选人做到约 **91.6% 准确率**，我 **没有同款 RAG 上线数据**，不会编造。

**若面试官追问「你的项目指标」—— 可答真实部分：**

| 项目 | 可说的指标 |
|------|------------|
| **FindJobs-Agent** | 端到端响应 **≤3s**；JSON Schema 约束后 15 项评分格式稳定 |
| **Sketch Agent** | Tool 白名单 + API Index 后，**无效工具调用显著减少**（定性，可说「子 Agent 收敛到 3 个工具」） |
| **CAD 特征平台** | DANN 域自适应缓解未见 CAD 厂商 **掉点**；混合推理交集策略提高 **误识别过滤** |

**若我做 RAG 评测会这样迭代：**

```
V1：单向量 Top5           → 建 50~100 条 Golden QA，看 Hit@5
V2：+ BM25 混合 + RRF     → 看 Recall@10 是否提升
V3：+ Rerank Top3         → 看答案忠实度 / 人工打分
V4：+ Query 改写 + 压缩   → 看端到端准确率和 token 成本
```

#### Q12. 多路召回并行还是串行？

**【通用】**

- **召回阶段：并行** — 向量、BM25、图谱各自独立，同时发请求，最后融合（延迟 ≈ max(各路)，不是 sum）
- **整体链路：串行阶段** — `改写 → 并行召回 → RRF → Rerank → 压缩 → LLM 生成`

```
         ┌─ 向量检索 ─┐
Query ──→├─ BM25 ─────┼→ RRF → Rerank → Compress → LLM
         └─ 图谱 ─────┘
              ↑ 并行
```

**【项目】** `agent.py` 里 **多个 read_file tool 并行**（`ThreadPoolExecutor max_workers=8`），同一哲学：独立 I/O 并行，有依赖的步骤串行。

#### Q13. 项目周期、问答模块耗时、迭代次数

**【诚实 + 项目真实周期】**

| 项目 | 周期 | 说明 |
|------|------|------|
| **Sketch-Modeling-Agent** | 2026.03–07（实习主线） | 多轮迭代：LangGraph 探索 → CoreCAX 生产定制；Memory/Tool 约束是 **持续迭代** 不是一次做完 |
| **CAD-Agent-Education** | 约 1 个月 | 验证配置驱动 + 动态 Tool |
| **FindJobs-Agent** | 2026.06–07 | Workflow 重构 + 前端 |

**面试话术（没有 RAG 周期时）：**

> 我没有独立「RAG 问答系统」的 3 个月周期，但有类似的 **知识注入 + 检索增强** 迭代：先 API 全塞 prompt（V1）→ 改 SKILL + reference 渐进披露（V2）→ 加 Tool 白名单和压缩（V3）。若做 RAG，我会预留 **2~4 周建评测集**，否则优化无法量化。

#### Q14. 单次请求耗时拆解（毫秒级）

**【通用模板 + 诚实】**

典型 RAG 链路（**以下为行业量级，非我的实测**）：

| 阶段 | 典型耗时 | 说明 |
|------|----------|------|
| 实体抽取 + Query 改写 | 200~800ms | 小模型/LLM 一次调用 |
| 多路召回（并行） | 50~300ms | 向量 ANN + ES BM25 |
| RRF 融合 | <10ms | 纯 CPU |
| Rerank（Top50→5） | 100~500ms | Cross-Encoder 批处理 |
| Context 压缩 | 0~500ms | 可选 LLM 摘要 |
| LLM 生成 | 1~5s | 视 token 与是否流式首字 |
| **端到端** | **2~8s** | 视模型与 K 值 |

**【项目】FindJobs ≤3s** 主要是：简历评分 + 画像 **单次/少量 LLM 调用**，无向量检索，Structured Output temperature=0.2。

**【项目】Sketch Agent** 瓶颈在 **多轮 Tool + 子 Agent**，不是检索；并行 read 可缩短单轮。

#### Q15. 流式还是一次性返回？

**【通用 + 项目】**

| 模式 | 适用 |
|------|------|
| **流式 SSE** | 生成阶段，改善首字延迟体验 |
| **一次性 JSON** | 结构化评分、Tool 调用、要完整解析时 |

**最佳实践：** 检索 / Rerank **后台一次性完成**；**仅 LLM 回答流式** 推给前端。

**【诚实】** FindJobs 当前是一次性 JSON；Sketch CLI 子 Agent 有工具进度打印，LLM token 流式 **可按产品需求加**，架构上 LLM 客户端支持 stream。

---

### Q20. RAG 项目完整流程？PDF 复杂表格如何处理？

**【通用 + 项目类比】**

#### 完整 RAG 流程

```
1. 需求 & 评测集     → 场景、权限、Golden QA
2. 数据采集          → PDF/网页/DB/多模态
3. 清洗 & 去重       → 编码、去页眉页脚、版本
4. 解析              → 文本/表格/图片/版式（见下）
5. 分块 & 元数据     → chunk + source/page/acl
6. Embedding & 索引  → 向量库 + 可选 BM25
7. 检索服务          → 多路召回 + 融合 + Rerank
8. 生成服务          → Prompt 拼装 + LLM + 引用
9. 评测 & 迭代       → Recall、忠实度、幻觉率
10. 运维             → 增量更新、监控、反馈闭环
```

#### PDF 复杂表格

| 难度 | 策略 |
|------|------|
| 简单表格 | `pdfplumber` / `camelot` → Markdown 表 |
| 合并单元格 | 版面分析（LayoutLM、PaddleOCR PP-Structure）保留单元格坐标 |
| 跨页表 | 按页切后再 **表合并算法** 或整表当一张图送 VLM |
| 扫描 PDF | OCR → 结构还原 |
| 检索友好 | 表转 **「行级 JSON」**：`{col: val, ...}` 每行一块，或 **表摘要 + 明细双索引** |

**【项目类比】** CAD 平台处理 STEP/B-Rep 不是 PDF，但 **「复杂结构先结构化再下游消费」** 同构：STEP → 图数据五类转换管线，否则 GNN 无法训练。RAG 里表格也一样：**先结构，再分块，再检索**。

---

## 三、Python 基础

### Q17. list 和 tuple 的区别

**【通用】**

| | list | tuple |
|--|------|-------|
| **可变性** | 可变 | **不可变** |
| **语法** | `[1, 2]` | `(1, 2)` |
| **性能** | 略慢、内存略大 | 略快，可作 dict key |
| **场景** | 动态增删改 | 固定结构、函数多返回值、配置项 |

**【项目】** Agent 里 `messages: list[dict]` 会追加；Tool 的 `parameters` schema 用不可变配置时常用 tuple 或 frozen dataclass。

---

### Q18. 变量作用域、LEGB、`global` 规则

**【通用】**

**LEGB 查找顺序：** Local → Enclosing → Global → Built-in

```python
a = 1  # Global

def foo():
    a = 2        # Local：赋值创建局部变量
    print(a)     # 2

def bar():
    global a
    a = 3        # 修改全局 a

def baz():
    print(a)     # 读取：无 local 赋值 → 找到 Global 的 a
```

**关键规则：**

- 函数内 **赋值** 默认创建 **局部变量**，除非 `global` / `nonlocal`
- **先读后写** 同一名字：若在函数内有赋值，整个函数体该名字视为 local，赋值前读取会 `UnboundLocalError`
- `nonlocal` 用于嵌套函数改 **外层（非全局）** 变量

**【项目】** Agent 循环里少用 `global`；会话状态放 `session` 对象或文件，避免全局可变状态难测。

---

### Q19. 类型注解用与不用有什么区别？解决什么问题？

**【通用 + 项目】**

| 不用注解 | 用注解 |
|----------|--------|
| 运行时无影响 | 运行时大多仍无强制（除非 pydantic/beartype） |
| IDE 补全弱 | **IDE 跳转、补全、重构** |
| 接口靠 docstring | **自描述函数契约** |
| 错误运行时才暴露 | `mypy` / `pyright` **静态检查** |

**解决的问题：** 团队协作可读性、重构安全、与 **Pydantic / FastAPI / JSON Schema** 联动。

**【项目】**

- FindJobs：`JSON Schema` 约束 LLM 输出 15 项评分
- Tool `parameters`：JSON Schema 即「运行时类型约束」
- `context.py` 若加 `def compress(messages: list[dict], budget: int) -> list[dict]` 更易维护

---

## 四、前端 Vue

### Q21. `v-if` vs `v-show`？Vue 3 响应式如何实现？

**【通用 + 项目】**

#### v-if vs v-show

| | v-if | v-show |
|--|------|--------|
| **DOM** | 条件假时 **不渲染** | 始终渲染，`display:none` |
| **切换成本** | 高（销毁/重建） | 低（只切 CSS） |
| **适用** | 不常切换、要懒加载 | 频繁切换 |

**【项目】** FindJobs React 三栏面板：类似逻辑用条件渲染；高频切换的 Tab 用 CSS 隐藏更合适。Vue 面试答法通用即可。

#### Vue 3 响应式

- **`Proxy`** 拦截 `get/set/delete`，追踪依赖、触发更新
- **`ref`**：基本类型包对象；**`reactive`**：对象代理
- 组件 `setup` 里返回的 ref 在模板自动解包
- 对比 Vue 2 `Object.defineProperty`：Proxy 可监听 **新增属性、数组索引**，无 Vue 2 那些补丁坑

---

## 五、Java / Spring Boot

### Q22. Java 线程池原理？Spring Bean 作用域？全局异常处理？

**【通用 + 项目类比】**

#### Java 线程池（ThreadPoolExecutor）

核心参数：

| 参数 | 含义 |
|------|------|
| `corePoolSize` | 核心线程数 |
| `maximumPoolSize` | 最大线程数 |
| `keepAliveTime` | 非核心线程空闲存活时间 |
| `workQueue` | 任务队列 |
| `RejectedExecutionHandler` | 队列满：Abort / CallerRuns / Discard |

**流程：** 任务来 → 核心线程满 → 入队 → 队满 → 扩到 max → 再满 → 拒绝策略

**【项目】** Python `ThreadPoolExecutor(max_workers=8)` 并行执行一轮多个 **只读** Tool；Java 线程池答法相同，可提 **Agent 场景要防写冲突**。

#### Spring Bean 作用域

| Scope | 说明 |
|-------|------|
| `singleton` | 默认，容器内单例 |
| `prototype` | 每次注入/new 新实例 |
| `request` | 每个 HTTP 请求一个 |
| `session` | 每个 HTTP Session |
| `application` | ServletContext 级 |

**【联想】** Agent `session_id` 隔离状态 ≈ request/session scope，我实习用 **文件目录分区** 实现。

#### 全局异常处理

```java
@RestControllerAdvice
public class GlobalExceptionHandler {
    @ExceptionHandler(BusinessException.class)
    public Result handle(BusinessException e) {
        return Result.fail(e.getCode(), e.getMessage());
    }
}
```

统一返回格式、打日志、隐藏堆栈。**【项目】** FindJobs Flask 可用 `@app.errorhandler` 同理。

---

## 六、DevOps

### Q23. Dockerfile 重要参数、常用命令、K8s 经验

**【通用 + 诚实】**

#### Dockerfile 结构

```dockerfile
FROM python:3.11-slim          # 基础镜像
WORKDIR /app                   # 工作目录
COPY requirements.txt .        # 先拷依赖清单 → 利用层缓存
RUN pip install -r requirements.txt
COPY . .
ENV APP_ENV=production         # 环境变量
EXPOSE 8000                    # 声明端口
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**重要概念：** 分层缓存、`.dockerignore`、多阶段构建（build 阶段编译，run 阶段只拷产物减小镜像）

#### 常用命令

```bash
docker build -t myapp:v1 .
docker run -d -p 8000:8000 --name myapp myapp:v1
docker ps / docker logs -f myapp
docker exec -it myapp bash
docker stop myapp && docker rm myapp
```

#### K8s

**【诚实】** 我实习项目 **未上 K8s 生产**，了解概念可答：

| 概念 | 作用 |
|------|------|
| Pod | 最小调度单元 |
| Deployment | 无状态应用多副本、滚动更新 |
| Service | 集群内负载均衡 |
| Ingress | HTTP 路由、TLS |
| ConfigMap / Secret | 配置与密钥 |
| HPA | 按 CPU/QPS 自动扩缩 |

**若部署 FindJobs / Agent API 上 K8s：** Deployment 跑 Flask/FastAPI；GPU 推理单独 Deployment；会话状态用 Redis；模型服务 HPA；Ingress 做 HTTPS。

**【项目】** 当前 Sketch 是 **CLI + session 落盘**；CAD 平台是 **内网 Flask + 桌面标注器**，属于 **工程交付** 而非大规模容器编排。

---

## 附录 A：面经高频追问 → 我的项目映射

| 面经考点 | 我的对应经历 |
|----------|--------------|
| 多路召回 | CAD 混合推理：几何 / AI / 交集 |
| 上下文压缩 | `context.py` 三层压缩 |
| 噪声过滤 | Tool 白名单 + 动态 Tool 过滤 |
| 多模态 | `attachments` 图片 base64 + 脚本文本 |
| 结构化输出 | FindJobs JSON Schema + Few-shot |
| 评测指标 | 【诚实】无 RAG 91.6%，有 ≤3s、格式稳定性 |
| 并行检索 | Tool 线程池并行 read |
| 知识库构建 | SKILL + reference 渐进披露，非向量库 |

---

## 附录 B：30 秒 / 3 分钟自我介绍（Agent 岗）

**30 秒：**

> 我是韦永根，桂电硕士，在国创中心做 AI 应用实习。独立做了 **CAD 草图建模 Multi-Agent**，解决闭源 API 工具幻觉和长上下文稳定性；另有 **FindJobs 三方协同 Agent** 和 **CAD 几何特征 GNN 平台**。擅长 Agent 编排、Tool 约束、上下文压缩和结构化输出。

**3 分钟（可展开 Sketch）：**

> 草图 Agent 采用 Orchestrator–Worker：主 Agent 委派 CAD 子 Agent，子 Agent 只有 3 个文件工具，配合 API Index 白名单防幻觉。长会话用三层 Memory 压缩 + 文件即状态。知识上不搞大而全向量库，而是 SKILL 配置 + reference 按需读取，和 RAG 的「少而精检索」是一个思路。FindJobs 侧用四阶段 Workflow + JSON Schema 把评分稳定到 15 个量化字段。我没有 Neo4j 和上线 RAG 的精确率数字，但检索融合和降噪的方法论和 Agent 工程是通的。

---

## 速背清单（进场前 5 分钟）

- [ ] **RAG 流程**：采集→解析→分块→索引→多路召回→RRF→Rerank→压缩→生成→评测
- [ ] **Recall vs Precision**：召回漏检 vs 精确噪声；多路提召回，Rerank 提精确
- [ ] **chunk**：`separators` + `chunk_overlap` 防硬切
- [ ] **多模态**：OCR 精确文字表，VLM 版式/草图；我项目 `@图片` 走 VLM
- [ ] **上下文爆炸**：Rerank TopK + 压缩 + 外置状态（我的三层 Memory）
- [ ] **并行**：多路召回并行，融合后串行 Rerank
- [ ] **Neo4j**：【诚实】没落地，能讲 Label/Relationship/Cypher 映射
- [ ] **Python**：LEGB；list 可变 tuple 不可变
- [ ] **Vue**：v-if 销毁 DOM，v-show 切 display；Proxy 响应式
- [ ] **线程池**：核心→队列→最大→拒绝策略；我 Python 侧 `max_workers=8`
- [ ] **指标**：【诚实】不编 91.6%，说 FindJobs ≤3s + 工程定性优化

---

*文档路径：`e:\个人材料\简历\面试题-成都-Agent应用开发-面经参考答案.md`*
