# 高德地图 · AI 应用开发 · 一面真题参考答案

> 基于韦永根简历项目 + 源码整理。  
> 本题单偏 **RAG 全链路 + 代码分析 + Agent 机制**，与 Sketch / FindJobs / CAD 项目交叉作答。  
> 原则：不编造指标；没做过的诚实说，并给可迁移思路。

---

## 使用说明

| 标签 | 含义 |
|------|------|
| **【项目】** | 简历/源码里真实做过 |
| **【通用】** | 行业通识 + 个人理解 |
| **【诚实】** | 主项目未覆盖，如实说明 |

---

## Q1. 需求文档过来，怎么判断代码库里是否写过类似函数？

**【通用 + 项目类比】**

这是 **「需求 → 代码复用发现」** 问题，我会分层做，不指望单一手段：

### 第一层：确定性检索（快、准）

| 手段 | 适用 |
|------|------|
| **关键词 / 正则 / grep** | 函数名、类名、错误码、API 名 |
| **调用链追踪** | 已知入口反查被谁调用 |
| **IDE / LSP** | Symbol 索引、Find References |

**【项目】** Sketch 主 Agent 自带 `grep`、`glob` 工具——本质是 **让 Agent 先搜再写**，避免重复造轮子。若做需求匹配系统，会把 grep 封装成 Tool，返回文件路径 + 行号 + 片段。

### 第二层：语义检索（泛化）

1. 用 **AST 按函数/类分块**（见 Q2）  
2. Embedding 入向量库，元数据带 `repo_path、function_name、commit`  
3. 需求文档也 embedding，**双向检索**：需求 → Top-K 代码块  
4. **Rerank** 精排（见 Q9、Q10）

### 第三层：LLM 判读（贵、准）

把 Top-K 片段 + 需求摘要给模型：**是否已实现 / 部分实现 / 需新建**，输出引用路径和置信度。

### 我的工程顺序

> **先规则后向量再 LLM**。高德这种大仓，全库 embedding 成本高，通常 **路径/模块元数据先过滤**（如 `amap/navi/`），再语义检索。

**【诚实】** 我实习项目没有「需求文档自动对仓」产品，但 CAD 平台用 **SHA256 去重** 判断零件是否已入库，思路类似：**先廉价指纹，再深比对**。

---

## Q2. RAG 做代码时常用 AST 按函数切块，AST 怎么把代码变成树？

**【通用 + 理解】**

AST（Abstract Syntax Tree，抽象语法树）是源码的 **结构化表示**：保留语法层级，**去掉空格、注释、部分标点**。

### 例子（Python）

```python
def add(a, b):
    return a + b
```

树形直觉：

```text
FunctionDef(name='add')
├── arguments: a, b
└── body
    └── Return
        └── BinOp(+)
            ├── Name(a)
            └── Name(b)
```

### 和「字符串切块」的区别

| | 字符串切块 | AST 切块 |
|--|-----------|----------|
| 边界 | 字符/token 数 | **函数 / 类 / 模块** |
| 完整性 | 易切断函数 | 语义完整 |
| 用途 | 文档 RAG | **代码 RAG、重构、静态分析** |

### 常用工具

- Python：`ast` 标准库、`libcst`（保留格式）、`tree-sitter`（多语言）  
- Java：`JavaParser`、Eclipse JDT  

### 切块策略（代码 RAG）

- 以 **FunctionDef / ClassDef** 为叶子单元  
- 过大函数再按 **逻辑块** 二次切  
- 元数据挂：**签名、docstring、import、文件路径、起止行**

**【项目类比】** 我的 `SKILL.md` + `references/case-*.md` 是按 **「能力单元」** 切，不是按字符切——和 AST 按函数切是同一思想：**按语义边界切，不按长度切**。

---

## Q3. 纯文本代码变成语法树，要经过哪些步骤？

**【八股 + 理解】** 经典编译前端流水线：

```text
源代码（字符流）
    ↓ 词法分析 Lexical Analysis
Token 流（if, def, IDENT, NUMBER, …）
    ↓ 语法分析 Syntax Analysis
Parse Tree（仍偏具体）
    ↓ 语义动作 / AST 构建
AST（抽象化：去掉无意义节点）
    ↓（可选）语义分析 Semantic Analysis
符号表、类型检查
```

### 各步在干什么

1. **词法**：`return a+b` → `[RETURN, IDENT(a), PLUS, IDENT(b)]`  
2. **语法**：按文法规则归约，检查括号、缩进是否合法  
3. **AST**：折叠单子女节点、去掉 `;` 等，得到 **便于分析** 的树  

### 和 RAG 的关系

RAG 通常 **不需要跑完整编译器后端**（不生成机器码），只要 **前端 AST + 符号表** 就够做：

- 函数级索引  
- 调用关系图  
- 与注释/docstring 绑定  

**我的理解：** 代码 RAG 的质量上限，往往取决于 **切块是否尊重语法边界**，而不是 embedding 模型有多强。

---

## Q4. 代码片段和对应注释都要存进 RAG，存储结构怎么设计？

**【通用】推荐「主块 + 关联元数据 + 双通道索引」**

### 文档单元（Chunk Record）

```json
{
  "chunk_id": "repo:path:func:add:hash",
  "code_text": "def add(a, b): ...",
  "comment_text": "docstring + 行内注释抽取",
  "merged_text": "用于 embedding 的拼接视图",
  "ast_type": "FunctionDef",
  "symbol": "module.Class.add",
  "path": "src/utils/math.py",
  "start_line": 10,
  "end_line": 15,
  "language": "python",
  "commit": "abc123",
  "parent_class": "Calculator"
}
```

### 设计要点

| 问题 | 做法 |
|------|------|
| 注释和代码谁为主？ | **代码块为主键**；注释挂同一 `chunk_id` |
| Embedding 用什么？ | `code_text` 与 `comment_text` **各建一条向量**，或 `merged_text` 单条；检索时可 **双路召回再 RRF**（Q7） |
| 注释没了怎么办？ | 仅存 `code_text`；生成侧用 LLM 补摘要可选 |
| 更新 | `commit` + 文件 hash；变更函数级 **upsert** |

### 存储分层

- **向量库**：Milvus / ES dense vector  
- **倒排**：BM25 抓函数名、类名（代码搜索极重要）  
- **图库（可选）**：调用关系 `caller → callee`，需求匹配时扩展上下文  

**【项目类比】** Sketch 的 `references/case-init.md` 是 **「代码示例 + 说明表格」** 一体文档；存储上等价于 **merged_text 一条 chunk**，按需 `read_file` 加载——和向量库批量检索是两种工程路径。

---

## Q5. 单轮 RAG 问答和多轮 RAG 问答，推理过程有什么区别？

**【通用】**

| 维度 | 单轮 RAG | 多轮 RAG |
|------|----------|----------|
| **Query** | 当前问题 | 当前问题 + **对话历史** |
| **检索 Query** | 原问或改写 | 需 **指代消解 / 问题重写**（「它」「上一个」） |
| **上下文** | 检索 chunk + 问 | 历史摘要 + 本轮检索 + 问 |
| **状态** | 无状态 | 有 **session / memory** |
| **失败模式** | 检索偏一次定生死 | 多轮可澄清；但 **错误检索会累积** |

### 多轮额外步骤

1. **Query Rewriting**：「半径改成 50」→「将草图 circle c1 半径改为 50」  
2. **检索范围收窄**：上一轮命中的文件/模块作为 filter  
3. **Memory 压缩**：旧轮摘要，避免 history 挤掉检索内容（Q12、Q15）

**【项目】** FindJobs 基本是单轮（一份简历一次评分）；Sketch 是 **多轮 Agent**，不是经典 RAG，但 **「当前轮检索什么」** 同样依赖历史——例如续编必须带上 `current_file` 路径，等价于多轮 **状态外置**。

---

## Q6. Q1「需求匹配代码」场景，更适合单轮还是多轮？

**【观点】首选多轮，但第一轮就要给候选。**

### 原因

1. 需求文档常 **模糊**（「和上次导航偏航提醒类似」）→ 需澄清模块、版本、端  
2. 匹配结果要给研发 **确认**（「是 `YawAlertHandler` 吗？」）  
3. 单轮直接定论 **误报成本高**（大仓里相似函数多）

### 推荐流程（Plan + Execute）

```text
Round1：需求摘要 + 模块过滤 → 检索 Top-K → 输出「可能已存在」列表 + 证据路径
Round2：用户/PM 确认或补充约束 → 收窄检索 → 输出复用建议或缺口
Round3（可选）：生成对接说明 / 调用示例
```

**若需求极其明确**（带函数名、类名、接口路径）→ **单轮检索 + Rerank 即可**。

**【项目】** 类似主 Agent 先 `grep` 再决定是否 `cad_agent` 新建脚本——**先发现已有实现，再决定创建**。

---

## Q7. 多路检索结果合并排序，RRF 怎么工作？

**【八股 + 理解】** Reciprocal Rank Fusion（倒数排名融合）

对文档 \(d\)，在多路检索列表中的排名 \(rank_i(d)\)（从 1 开始）：

\[
RRF(d) = \sum_i \frac{1}{k + rank_i(d)}
\]

- 某路里 **排名越靠前**，贡献越大  
- **没出现在某路** 的文档，该项为 0  
- 不需要不同路的分数 **归一化**（向量分、BM25 分尺度不同，RRF 只看得名次）

### 直觉

> 在 **多路都靠前** 的文档更可信；一路偶然高分但其它路没有的，会被拉下来。

### 典型组合

- 向量检索 + BM25  
- 代码 embedding + 符号精确匹配  
- `code_text` 向量 + `comment_text` 向量（Q4 双通道）

**【诚实】** 我项目未上线 RRF；CAD 混合推理用 **几何 ∩ AI 交集**，是另一种融合哲学——**宁缺毋滥**，和 RRF「多路加分」互补。

---

## Q8. RRF 的 k 一般取多少？不同检索源要不要设不同权重？

**【通用】**

### k 取值

- 论文与工程常见 **k = 60**（Elastic 默认也常用 60 量级）  
- k **越大**：排名靠后的文档也有机会，融合更「平」  
- k **越小**：更看重头部排名，融合更「尖」  

实践中：**先用 60**，用 Golden Set 看 MRR/Recall@K 再调。

### 是否加权

标准 RRF **各源等权**。若某源明显更准（如代码场景 **BM25 命中符号名**），可用 **加权 RRF**：

\[
\sum_i w_i \cdot \frac{1}{k + rank_i(d)}
\]

| 源 | 权重倾向 |
|----|----------|
| 符号/BM25 | 代码需求匹配可 **略高** |
| 向量语义 | 自然语言需求可 **略高** |
| 新源实验期 | **低权** 防止噪声 |

**我的观点：** 权重要有 **离线评测** 支撑，不要拍脑袋；否则不如等权 RRF 稳定。

---

## Q9. 粗排已经有顺序了，为什么还需要 Rerank？

**【通用 + 理解】**

粗排和精排优化目标不同：

| | 粗排（Retrieval） | 精排（Rerank） |
|--|-------------------|----------------|
| **目标** | 高召回、快 | 高准确、准 |
| **模型** | 双塔 / BM25，query 与 doc **独立编码** | Cross-Encoder，query-doc **联合编码** |
| **规模** | 百万级 → Top 50~200 | 50~200 → Top 5~10 |
| **交互** | 浅 | 深（真正「读懂」是否匹配） |

### 为什么粗排顺序不够准

1. **双塔向量** 对细粒度差异不敏感（函数名差一个字母）  
2. **代码场景** 需要看参数类型、调用上下文，粗排 embedding 常丢  
3. 粗排要 **牺牲精度换速度**，故意放宽  

> 类比：粗排是海选，Rerank 是复试。**粗排漏掉的可通过多路召回补；粗排进来的误报靠 Rerank 剔。**

**【项目】** FindJobs 岗位匹配先用简单子串算法（粗），我知道误报问题——工程上应加 embedding Rerank，这是 **同一逻辑的微观版**。

---

## Q10. 粗排和精排分别负责什么？为什么不能一步只做精排？

**【通用】**

### 分工

- **粗排**：从全库快速缩小到 **候选集**（Recall 优先）  
- **精排**：对候选做 **精细相关性判断**（Precision 优先）  
- **（可选）生成**：LLM 基于 Top-K 作答，带引用  

### 为什么不能全库精排

1. **复杂度**：Cross-Encoder 对 N 个文档要做 N 次联合前向，**O(N)** 且常数大  
2. **延迟**：高德级代码仓 N 极大，全库精排不可接受  
3. **成本**：GPU 算力与 API 费用  

### 一步到位的替代

- **增大粗排模型**（ColBERT 等多向量细粒度）  
- **两阶段级联**：粗排 Top200 → 中排 Top20 → 精排 Top5  

**我的理解：** 面试答「不能一步精排」时，要提 **算力与延迟**；若面试官追问未来趋势，可说粗排模型变强后 **Rerank 候选数在变小**，但级联思想仍在。

---

## Q11. Markdown、PDF 文档怎么切分才能保留结构？

**【通用】**

### Markdown

| 策略 | 做法 |
|------|------|
| **标题层级** | `# / ## / ###` 为边界，子树不跨父节 |
| **代码块** | ` ``` ` 整块保留，不与正文混切 |
| **表格** | 整张表为一个 chunk 或按行块 + 表头重复 |
| **列表** | 同一列表项不拦腰切 |
| **过长节** | 节内二次按段落 / token 上限切，**元数据保留 `h1>h2>h3` 路径** |

### PDF

| 策略 | 做法 |
|------|------|
| **版面分析** | 标题字号、加粗、页眉页脚剔除 |
| **双栏** | 先排阅读顺序再切 |
| **表格** | Tabula / 多模态 OCR → 结构化 Markdown 再切 |
| **扫描件** | OCR + 布局模型，避免按页盲切 |

### 元数据必带

`doc_id, section_path, page, chunk_index`——生成时才能 **引用「第几章第几节」**。

**【项目】** `SKILL.md` 按 **Overview / Prerequisites / Workflow** 章节组织；`references/case-init.md` 按 **API 条目 + 表格** 组织——就是 Markdown **结构感知切块** 的手工版。

---

## Q12. Agent 做文档切分时，上下文放不下了怎么办？

**【通用 + 项目】**

### 策略矩阵

| 策略 | 说明 |
|------|------|
| **外置状态** | 切分结果写磁盘/DB，Agent 只持 **索引 + 进度指针** |
| **Map-Reduce** | 分段切分（Map）→ 每段摘要（Combine）→ 全局合并（Reduce） |
| **滑动窗口** | 长文档按 overlap 窗口处理，结果去重合并 |
| **子 Agent** | 切分任务委派子 Agent，主 Agent 只收 **统计摘要** |
| **Memory 压缩** | 旧轮 tool 输出 snip / LLM 摘要（Q15） |
| **不把所有 chunk 塞回 prompt** | 切完 **直接写向量库**，Agent 下一轮只带 `chunk_id` 列表 |

### 错误做法

> 把整篇 PDF 切出来的 500 个 chunk 全文贴回 messages——必炸。

### 【项目】Sketch 做法

1. **子 Agent 隔离**：CAD 长脚本不进主上下文  
2. **渐进披露**：reference 目录进 prompt，**全文按需 read**  
3. **三层压缩**：`context.py` 50% snip → 70% 摘要 → 90% 硬折叠  
4. **attachments 不落盘 session**：图片 base64 不写入 `session.json`  

若我做「Agent 自动切分知识库」产品：**切分 Worker 写库 + 进度 JSON**，编排 Agent 只读进度，不读全文。

---

## Q13. Skill 和 MCP 都能扩展能力，区别是什么？

**【项目】Skill 我深度用过；MCP 是协议层，可对比答。**

| 维度 | Skill（我的实践） | MCP |
|------|-------------------|-----|
| **本质** | **领域 SOP + 工具白名单 + Prompt 包** | **标准化工具/资源访问协议** |
| **载体** | `SKILL.md` + YAML frontmatter + references | MCP Server 暴露 tools/resources |
| **谁执行** | 宿主 Agent spawn 子 Agent，读 Skill 注入 system | Client 通过 JSON-RPC 调 Server |
| **扩展点** | 技能注册、allowed-tools、参考案例 | 统一鉴权、跨应用复用 Server |
| **状态** | 我这边 **文件即状态**（Plan B） | Server 可自有状态 |
| **生态** | 项目内约定（CoreCAX） | Anthropic 推动，多 IDE 接入 |

### 我的理解（不是背定义）

> **Skill 解决「怎么让 Agent 在某一领域按 SOP 干活」**——是 **认知 + 流程 + 工具子集**。  
> **MCP 解决「工具怎么跨进程、跨服务统一暴露」**——是 **连接层**。  

二者可叠加：**CAD 能力封装成 MCP Server**，宿主仍用 **Skill 告诉模型何时、如何调 MCP**。

**面试话术：**

> 我在 Sketch 里用 Skill 把 NCTI 建模收敛成六阶段 Pipeline + 三工具白名单；若接 MCP，会把 NCTI 运行时封成 Server，Skill 里只保留触发条件和参数约束，**Skill 管脑子，MCP 管手**。

---

## Q14. Agent 怎么记住之前交互？Memory 组件内部怎么工作？

**【通用架构 + 项目】**

### Memory 分层（常见教科书 + 我的实现）

| 类型 | 存什么 | 我项目 |
|------|--------|--------|
| **Working Memory** | 当前 `messages`、tool 结果 | `Agent.messages` |
| **Episodic** | 会话历史、摘要 | `session.json` + 压缩摘要 |
| **Semantic** | 长期事实、用户偏好 | 未单独做向量库；Skill/API Index 算 **静态语义** |
| **Procedural** | SOP、怎么做 | `SKILL.md` 正文 |
| **External** | 产物、大对象 | `output/<session_id>/*.py`（Plan B） |

### 内部怎么工作（简化）

```text
用户输入
  → 写入 messages
  → maybe_compress() 检查 token 阈值
  → LLM 推理（带 system + 全 history）
  → tool 结果再写入 messages
  → 循环
退出时 save_session() → 磁盘 JSON
```

### 关键点

1. **Memory ≠ 无限堆消息**——是 **写入策略 + 压缩策略 + 外置策略**  
2. **续编靠 `current_file` 路径**，不靠模型记住上千行脚本  
3. **子 Agent 独立 messages**，父 Agent 只保留 **一行摘要 + [产出文件]**  

**【项目源码】** `context.py`（压缩）、`session.py`（持久化）、`skill_agent.py`（结构化回传路径）。

---

## Q15. 对话越来越长，怎么防止上下文爆炸？

**【项目】这是我亲手实现的三层压缩，可细讲。**

### 触发阈值（`ContextManager`）

| 层级 | 阈值 | 动作 |
|------|------|------|
| Layer 1 | ~50% max_tokens | **Snip** 过长 tool 输出（保留首尾行） |
| Layer 2 | ~70% | **LLM 摘要**旧轮，保留最近 8 条 |
| Layer 3 | ~90% | **Hard collapse**，只留摘要 + 最近 4 条 |

### 其它手段（通用）

- 子 Agent / 多 Agent 隔离  
- Structured state 外置（文件、DB）  
- 检索结果只留 Top-K 摘要，不贴全文  
- 系统 prompt 静态，不重复膨胀  

### CAD-Agent-Education 补充

消息 >20 或 token >60% → **4 段式摘要**（目标/进度/参数/待办），比无脑截断更能续编。

**观点：** 防爆炸不是「删消息」这么简单，要 **删什么、留什么、外置什么** 一起设计——否则多轮任务必断片。

---

## Q16. ReAct 范式（推理与行动交替）是怎么运转的？

**【项目】主循环即 ReAct。**

### 标准循环

```text
1. Thought（推理）：模型决定下一步需要什么信息/动作
2. Action（行动）：发起 tool_call(name, args)
3. Observation（观察）：环境返回 tool result 字符串
4. 将 Observation 追加到 messages
5. 重复直到模型输出 Final Answer（无 tool_call）
```

### 我项目里的映射（`agent.py`）

- **Thought**：模型内部 chain-of-thought（不一定显式输出 `Thought:` 行）  
- **Action**：`resp.tool_calls`  
- **Observation**：`role: tool` 的 `content`  
- **终止**：无 tool_calls → `return resp.content`  

### 增强点

- **并行 Action**：一轮多个独立 tool，`ThreadPoolExecutor` 同时执行  
- **嵌套 ReAct**：`cad_agent` 子 Agent 内部再跑 50 轮  
- **失败 Observation**：`Error executing xxx` 回灌，模型可改参重试  

---

## Q17. ReAct 和 Agent Loop 都是循环推理+行动，区别是什么？

**【理解题】很多人混用，建议这样区分：**

| 维度 | ReAct | Agent Loop（工程泛指） |
|------|-------|-------------------------|
| **来源** | 论文范式，强调 Thought-Action-Obs 格式 | 工程实现，各种 while 循环 |
| **文本形态** | 常显式 `Thought:` / `Action:` / `Observation:` | 多用 **Native Tool Calling** API |
| **规划** | 每步即兴推理 | 可有 **Plan-and-Execute、图状态机、Workflow** |
| **状态** | 主要靠 messages | 可有 **外置 state、checkpoint、Skill** |
| **扩展** | 单 Agent 为主 | Multi-Agent、子 Agent、人机中断 |

### 一句话

> **ReAct 是一种认知范式；Agent Loop 是工程外壳。**  
> 我的 Sketch 是 **Agent Loop 实现 + ReAct 语义**，但没有手写 Thought 标签——因为 GPT/Kimi 的 tool calling 已把 Action 结构化。

### 和高德场景

地图 Agent 常有 **固定 Workflow**（查地点 → 算路 → 下单），可能是 **LangGraph 图 + ReAct 节点内循环** 混合——面试可说 **外层图管阶段，内层 ReAct 管单步工具**。

---

## 附录 A：17 题与简历项目速查

| 题号 | 主题 | 优先引用项目 |
|------|------|--------------|
| 1 | 需求匹配代码 | grep 工具；SHA256 去重类比 |
| 2-4 | 代码 AST / 存储 | SKILL/reference 切块类比 |
| 5-6 | 单轮/多轮 RAG | FindJobs vs Sketch 多轮 |
| 7-10 | RRF / 粗精排 | 通用 + FindJobs 匹配算法反思 |
| 11-12 | 文档切分 / 上下文 | SKILL.md 结构；三层压缩 |
| 13 | Skill vs MCP | **Sketch 六阶段 Skill Pipeline** |
| 14-15 | Memory / 防爆炸 | **context.py + session + Plan B** |
| 16-17 | ReAct / Agent Loop | **agent.py 循环** |

---

## 附录 B：进场前 5 分钟速背

- [ ] 代码 RAG：**AST 按函数切 + 双通道存代码/注释 + BM25+向量 RRF**  
- [ ] 粗排要 Recall，精排要 Precision，**不能全库 Cross-Encoder**  
- [ ] RRF：**k≈60**，加权看评测  
- [ ] 多轮 RAG：**Query 重写 + 历史摘要 + 状态外置**  
- [ ] Skill vs MCP：**Skill=SOP+白名单，MCP=工具协议**  
- [ ] 我的 Memory：**三层压缩 + session.json + 文件即状态**  
- [ ] ReAct vs Loop：**范式 vs 工程实现；我用 native tool calling**  

---

## 附录 C：若被问「你没做过代码 RAG，凭什么能答？」

> 我主项目是 **闭域 Agent + 渐进披露知识**（SKILL、API Index、reference 按需加载），和 RAG 的 **retrieve-then-generate** 同构；差别在检索介质是 Tool+文件而非向量库。代码 AST 切块、RRF、Rerank 我通过 **CAD 平台数据管线 + 自研评测阅读** 系统学过，愿意入职后在高德仓内快速落地评测闭环。

---

*文档路径：`e:\个人材料\简历\面试题-高德-AI应用一面.md`*
