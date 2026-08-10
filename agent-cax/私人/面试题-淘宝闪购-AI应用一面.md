# 淘宝闪购 · AI 应用开发 · 一面真题参考答案

> 基于韦永根简历项目 + 源码整理，结合真实经历作答。  
> 原则：**不编造上线指标**；没有的数据用工程判断和「显著/有效」表述；八股部分加个人理解。

---

## 使用说明

| 标签 | 含义 |
|------|------|
| **【项目】** | 可直接引用你简历/源码里的真实经历 |
| **【通用】** | 行业通识 + 我的理解，面试时可接「我们项目里类似…」 |
| **【诚实】** | 项目没做过但要如实说，并补迁移思路 |

---

## Q1. Agent 项目是否上线部署？

**【诚实 + 项目】**

分项目说：

| 项目 | 部署形态 |
|------|----------|
| **Sketch-Modeling-Agent** | **内部工程交付 + CLI 形态**，在国创中心 CAD 场景内使用；支持 `session.json` 断点续聊、`output/<session_id>/` 分区落盘，**不是面向 C 端的大规模公网 SaaS** |
| **CAD-Agent-Education** | LangGraph 探索版，本地/内网验证 |
| **FindJobs-Agent** | Flask API + React 前端，GitHub 开源；后端改造在本地验证通过，**【诚实】** 因环境原因前端未完整跑通部署 |
| **CAD 特征识别平台** | 桌面端标注器 + Flask 后端，**内网协作使用**，GNN 推理走 ONNX/本地引擎 |

**面试话术（30 秒）：**

> 我的 Agent 项目目前是 **工程化内测/内部交付**，不是千万级流量的线上服务。但部署相关的设计我做了：会话持久化、按 session 隔离产物目录、子 Agent 超时与 `MAX_ROUNDS_REACHED` 兜底。如果上生产，我会补 API 网关、鉴权、调用链日志、模型 fallback 和灰度发布——这些我在架构上预留了扩展点，只是实习阶段没走到全量上线。

**可能的追问：** 若上线你还缺什么？→ 监控（tool 成功率、P99 延迟）、限流、敏感数据脱敏、多租户 session 隔离。

---

## Q2. 是否使用过 LangChain 等框架？

**【项目】用过，且能说清为什么后来又自建循环。**

1. **CAD-Agent-Education**：`LangGraph` + `LangChain` 搭 Agent 图，验证 `soul.md` / `SKILL.md` 配置驱动、动态工具过滤、摘要压缩。
2. **FindJobs-Agent**：LangChain 调通义千问，做简历评分、能力画像 Workflow。
3. **Sketch-Modeling-Agent**：底座是 **CoreCAX（CoreCoder）**——从 Claude Code 核心模式提炼的 **轻量 Python Agent 循环**，不是 LangChain 包一层。

**我的取舍：**

> LangChain/LangGraph 适合快速搭 Workflow、要 checkpoint、要可视化图。CAD 草图场景是 **高频 Tool 循环 + 长子 Agent + 文件即状态**，用自研 `agent.py` 的 `while tool_calls` 循环更直观，改压缩、并行 tool、spawn 子 Agent 都在百行级代码里能看清。不是反对框架，是 **匹配场景复杂度**。

---

## Q3. 意图识别模块如何实现？

**【项目】没有单独训一个意图分类模型，而是「Skill 路由 + Tool 描述 + 主 Agent Planning」三层。**

### Sketch-Modeling-Agent

1. **Skill 触发（软意图）**  
   `SKILL.md` frontmatter 的 `description` 写清 Trigger：「用户请求草图建模、画线、加约束…」→ spawn 子 Agent 时注入 system prompt，模型据此判断是否在 CAD 域内。

2. **硬约束（强意图）**  
   `cad_agent` 工具的 `description` 写明 **MANDATORY**：凡 CAD/NCTI 请求必须委派，主 Agent 不应自己生成代码——这是 **Tool 层面的意图兜底**。

3. **多模态意图**  
   用户输入里的 `@图片路径` 由 `extract_attachment_paths` 抽出，主 Agent 文本侧只看到附件列表，委派时填入 `attachments`，子 Agent 侧 `build_attachment_blocks` 编码——**照图绘制** 靠结构化参数传递，不靠模型猜路径。

### FindJobs-Agent

Workflow 分段即意图：上传简历 → 评分 Agent；要画像 → Profile Agent；学校端 → 课程覆盖度 API——**流程节点 ≈ 意图边界**。

### 若面试官要「经典意图识别」

可补充：小模型 / BERT 做 query 分类、规则关键词、或 LLM 一次 JSON 输出 `{intent, slots}`。我的项目选 **LLM + Skill 配置** 是因为 CAD 意图和参数纠缠（「把圆半径改成 50」= 编辑意图 + 槽位），端到端更省维护成本。

---

## Q4. 项目用到哪些工具（Tool）？

**【项目】按系统列，体现你真写过 schema。**

### Sketch 主 Agent（7+ 工具，示意）

| 工具 | 作用 |
|------|------|
| `cad_agent` | 委派 CAD 子 Agent（核心） |
| `read_file` / `write_file` / `edit_file` | 文件读写（主 Agent 也可用） |
| `bash` / `glob` / `grep` | 工程辅助（子 Agent 侧会剥离） |

### CAD 子 Agent（Skill 白名单后仅 3 个）

`read_file`、`write_file`、`edit_file`——**刻意收敛**，降低幻觉面。

### 子 Agent .spawn 剥离

`_AGENT_SPAWN_TOOLS = {"agent", "cad_agent"}`，防止无限递归。

### FindJobs

LLM 评分、画像生成、岗位匹配；后端 REST API 聚合，不是全走 Tool Calling，但 **结构化输出** 等价于「工具返回 JSON」。

**源码锚点：** `corecoder/tools/` 目录、`cad_agent.py` 的 `parameters`（`task`、`current_file`、`attachments`）。

---

## Q5. 如何提升工具调用正确率？

**【项目】这是我 Sketch 项目最核心的工程题。**

| 手段 | 我项目里的落地 |
|------|----------------|
| **缩小工具集** | Skill `allowed-tools` 白名单；子 Agent 只有 3 个工具 |
| **API 正向列举** | `CAD_SYSTEM_PROMPT` 里 `<api_index>` 列出全部合法 NCTI 接口，禁止猜测 |
| **动态工具过滤** | CAD-Agent-Education：未激活 Skill 的专用工具对模型不可见 |
| **参数 Schema** | 每个 Tool 有 JSON Schema；`TypeError` 时返回可读错误让模型改参 |
| **执行后结构化回传** | `write_file`/`edit_file` 后追加 `[产出文件] path`，主 Agent 续编不依赖模型口述 |
| **禁止危险/无关工具** | 子 Agent 去掉 bash；主 Agent bash 有 `rm -rf` 等拦截（`test_tools.py`） |
| **Structured Output** | FindJobs：JSON Schema + Few-shot，评分字段不再漂移 |

**我的理解：** Tool 正确率 ≠ 模型变聪明，而是 **减少模型需要做选择题的范围**。闭源 API 场景尤其要做「白名单 + Index」，比事后纠错便宜得多。

---

## Q6. 知识库如何构建？

**【诚实】我的主项目不是典型「向量库 + 文档上传」RAG，但有可类比的「知识注入」体系。**

### Sketch-Modeling-Agent（领域知识库）

| 层级 | 内容 | 构建方式 |
|------|------|----------|
| **API 知识** | NCTI 合法接口全集 | 手写进 system prompt `<api_index>`（权威、不检索） |
| **SOP 知识** | 建模流程、变量命名 | `SKILL.md` 正文 |
| **案例知识** | 初始化、约束、编辑示例 | `references/case-*.md`，**按需 read_file**（渐进披露） |
| **状态知识** | 当前脚本 | 磁盘 `.py` 文件，Plan B「文件即状态」 |

构建流程：**人工整理 SDK 文档 → 拆成 SKILL + reference → 版本跟 Git 走**，不是爬网页灌向量库。

### FindJobs-Agent

- **课程知识**：`course_data.py` 手工维护课程–技能映射（学校域知识库）
- **岗位知识**：原项目爬虫数据 + 技能标签
- **评分规则**：写在 Prompt 里（行为知识）

### 若做标准 RAG 知识库（通用补充）

> 采集 → 清洗 → 去重 → 分块 → Embedding → 向量库 + 元数据（来源、版本、权限）→ 评测集回归。政企场景还要 **权限标签** 和 **更新审计**。

---

## Q7. RAG 项目的分块策略有哪些？

**【通用 + 项目类比】**

| 策略 | 做法 | 优 | 劣 |
|------|------|----|----|
| **固定长度** | 按 token/字符滑动窗口，可重叠 | 简单、长度可控 | 语义被拦腰切断 |
| **语义分块** | 按段落、标题、句子边界 | 块内完整 | 块大小不均 |
| **结构感知** | Markdown 标题、表格、代码块分开 | 适合文档/API | 依赖格式 |
| **Agentic Chunking** | LLM 先划边界再切 | 质量高 | 成本高 |
| **渐进披露（我的做法）** | 目录进 prompt，全文按需读 | 不占满 context | 多一轮 tool |

**项目类比：** `cad-sketch` 的 `references/` 就是 **按案例语义分块**；system prompt 只放 **reference 目录一行一条**，子 Agent 需要细节再 `read_file`——等价于 RAG 的 retrieve-on-demand，只是用 Tool 代替向量检索。

---

## Q8. 知识检索如何提升回答正确率？

**【通用】+ 可嫁接项目。**

1. **检索前**：Query 改写、HyDE、多 query 扩展  
2. **检索中**：混合检索（向量 + BM25）、元数据过滤（行业/版本）  
3. **检索后**：Rerank（Cross-Encoder）、去重、MMR 多样性  
4. **生成时**：要求引用来源、低温度、只答检索到的内容  
5. **评测闭环**：Golden QA 集 + 命中率/忠实度指标  

**我的项目里没有向量 Rerank，但有类似思想：**

- **Tool Constraint** 相当于「检索范围 = 白名单 API」→ 减少无关噪声  
- **FindJobs Few-shot** 相当于「检索到相似简历样例再生成」  
- **混合推理（CAD 平台）**：几何规则 + AI + 交集，类似 **多路召回再融合**

---

## Q9. 如何解析知识库中的表格/图片文件？

**【项目】Sketch 子 Agent 的 attachments 路径我真实做过。**

### 图片

`attachments.py`：`png/jpg/...` → base64 → OpenAI 多模态 `image_url` block，**仅在子 Agent 侧编码**，不写入 `session.json`（避免 MB 级膨胀）。

### 文本/脚本文件

同路径：读文件内容 → 包在 `<file>` 标签里作为 text block，供「照脚本仿制」。

### 失败降级

单文件读失败 **skip + warning**，不中断整批——工程上必须 graceful degradation。

### 表格（通用，项目未做向量库表格）

> 我倾向 **结构化抽取优先**：PDF/Excel → 转 Markdown 表格或 JSON → 再进检索；复杂表用多模态 LLM 做 OCR+结构还原，但要做 **单元格坐标元数据** 方便引用。纯图片表塞向量库效果通常不好。

---

## Q10. 系统是否用到 ReAct 模式？

**【项目】是，核心循环就是 ReAct 的工程实现。**

`agent.py` 逻辑：

```text
用户输入 → LLM（带 tools）
  → 有 tool_calls？→ 执行工具 → 结果写入 messages → 再 LLM
  → 无 tool_calls？→ 文本回复，结束
```

这就是 **Reasoning + Acting + Observation** 循环；Reasoning 在模型 hidden 链式思考里，Acting 是 `tool_calls`，Observation 是 `role: tool` 的返回。

**与教科书 ReAct 的差异：**

- 我没有单独拆 `Thought:` 文本行，而是依赖模型 native tool calling  
- 加了 **并行多 tool**（一轮多个独立 tool 同时执行）  
- 子 Agent 是 **嵌套 ReAct**，但上下文隔离  

CAD-Agent-Education 用 LangGraph 时，节点跳转是显式图；Sketch 用 **隐式 while 循环**，本质仍是 ReAct。

---

## Q11. 如何提升模型回答性能？

**【项目 + 通用】**

| 维度 | 做法 | 项目 |
|------|------|------|
| **延迟** | 并行 Tool、减少无效轮次、小模型做路由 | `ThreadPoolExecutor(max_workers=8)` |
| **成本** | 三层 Memory 压缩、子 Agent 隔离长输出 | `context.py` 50/70/90% |
| **质量** | 白名单、Structured Output、Few-shot | Sketch + FindJobs |
| **稳定性** | temperature 降低、max_rounds 上限 | FindJobs 0.2；`max_rounds=50` |
| **体验** | 流式 token、子 Agent 工具进度打印 | `skill_agent.py` `_on_tool` |

**我的观点：** 「性能」在面试里先问清是 **latency、吞吐、还是质量**——Agent 里三者常冲突，例如压缩能省 token 但多一次 LLM 摘要调用。

---

## Q12. Prompt 层面有哪些优化手段？

**【项目】能举很多具体例子。**

1. **分层 Prompt**：system（身份+纪律）/ skill SOP / reference 按需加载  
2. **正向约束 > 负向罗列**：`<api_index>` 列出「能用什么」比「禁止什么」有效  
3. **输出纪律**：`<output_discipline>` 强制子 Agent 一句话汇报，防废话回灌  
4. **Structured Output**：JSON Schema + Few-shot（FindJobs 15 项评分）  
5. **动态注入**：仅激活 Skill 的工具和 SOP 进 prompt，减干扰  
6. **中文对齐**：FindJobs 8 段中文 Prompt，解决英文 system 在中文简历上漂移  
7. **参数追问**：CAD prompt 写「缺参数必须回报，禁止默认假设」  
8. **压缩 Prompt**：摘要时要求保留路径、决策、错误、待办（`context.py`）

---

## Q13. Token 与字符的区别

**【通用 + 项目】**

| | 字符 | Token |
|--|------|-------|
| **定义** | 文本字符单位 | 模型 BPE/SentencePiece 子词单位 |
| **中英文** | 1 汉字 ≈ 1 字符 | 1 汉字常 1~2 token；英文按词根切 |
| **用途** | 存储、显示 | **计费、上下文窗口、API 限制** |

**项目里：** `context.py` 的 `_approx_tokens` 用 `len(text) // 3` 做 **混合中英文粗算**，不调 tokenizer——工程上够用来触发压缩层，精确计费再用 API 返回的 `usage`。

**我的理解：** Agent 开发要习惯 **按 token 预算设计**，不是按「几行字」。工具返回、代码块是 token 黑洞，所以先做 snip 再摘要。

---

## Q14. LangChain 与 LangGraph 的了解

**【项目 + 理解】**

### LangChain

- **定位**：LLM 应用「积木」—— Model I/O、PromptTemplate、Chain、Tool、Memory、Retriever  
- **我用过**：接通义、串评分 Workflow、封装 Prompt  
- **痛点（个人）**：抽象层厚，定制 Agent 循环时要跟框架「拔河」

### LangGraph

- **定位**：用 **有状态图** 表达 Agent——节点=步骤，边=条件跳转，自带 checkpoint  
- **我用过**：CAD-Agent-Education，Skill 配置 + 图状态  
- **适合**：多分支、Human-in-the-loop、要可视化、要持久化 state  

### 与 Sketch（CoreCAX）对比

> LangGraph 是 **显式图**；我的生产定制是 **薄循环 + Skill Pipeline**。CAD 场景路径相对固定（委派 → 子 Agent 写脚本），图的价值不大，反而 **Skill 六阶段 + 文件状态** 更贴业务。

---

## Q15. Agent 常见模式（ReAct / Plan and Execute 等）

**【通用 + 项目映射】**

| 模式 | 核心思想 | 我的项目 |
|------|----------|----------|
| **ReAct** | 交替推理与工具执行 | Sketch 主/子 Agent 循环 |
| **Plan and Execute** | 先出计划再逐步执行 | 主 Agent 委派 `cad_agent` + task 描述；Skill Workflow A/B/C |
| **MRKL / Tool Calling** | 专家工具路由 | `cad_agent` 专责 CAD |
| **Multi-Agent** | 多角色协作 | Orchestrator–Worker 双层 |
| **Reflection** | 执行后自检再改 | 工具错误回灌；`MAX_ROUNDS_REACHED` 显式失败 |
| **LATS / Tree** | 搜索多条推理链 | **未做**（成本高） |

**选型观点：** 工业 Agent 优先 **可观测、可约束** 的简单模式；Plan-and-Execute 适合步骤清晰的 CAD SOP，不适合开放域搜索。

---

## Q16. Lost in the Middle 问题的解决方案

**【通用 + 项目】**

**现象：** 长 context 里，模型对 **中间** 的信息利用率低，首尾记得牢。

**解法：**

1. **不要把关键信息放中间**——API Index、纪律放 system 首尾  
2. **RAG 减少塞入量**——少而精的 chunk + Rerank  
3. **摘要压缩**——旧轮压成短摘要（我的 Layer 2/3）  
4. **结构化状态外置**——关键参数写文件/DB，不依赖模型记（Plan B）  
5. **多轮拆分**——子 Agent 隔离，主 Agent 只留摘要  
6. **重排上下文**——把当前任务相关 tool 结果放最近  

**项目：** 三层压缩 + 子 Agent 隔离，本质都是 **减少「中间垃圾」的长度**；`current_file` 路径在每轮子 Agent task 里 **重复强调**，对抗中间遗忘。

---

## Q17. Prompt 的常见结构

**【通用 + 项目模板】**

经典 **CRISPE / 六段式**（FindJobs 用过类似 8 段中文结构）：

1. **Role** — 你是谁  
2. **Context** — 背景与输入  
3. **Instruction** — 要做什么  
4. **Constraints** — 边界、格式、禁止项  
5. **Examples** — Few-shot  
6. **Output Format** — JSON / 表格 / 一句话  

**Sketch `CAD_SYSTEM_PROMPT` 结构：**

```text
<script_structure>   → 环境约定
<naming>             → 命名规范
<capabilities>       → 能/不能
<api_index>          → 知识（放中部但块内自洽）
<discipline>         → 纪律
<tools>              → 工具规则
<output_discipline>  → 输出格式（放尾部强化）
```

**我的习惯：** 越靠近 **尾部** 的约束，对当前轮行为影响越大——所以 output 纪律放最后。

---

## Q18. 线程池参数

**【项目】** `agent.py`：`ThreadPoolExecutor(max_workers=8)`

**八股 + 思考：**

| 参数 | 含义 |
|------|------|
| **corePoolSize / max_workers** | 最大并发线程数 |
| **queue** | 等待队列（Python `ThreadPoolExecutor` 默认 `SimpleQueue`，无界需谨慎） |
| **keepAliveTime** | 空闲线程存活时间 |
| **拒绝策略** | 队列满时：抛异常 / 调用者跑 / 丢弃等 |

**我为什么选 8？** 一轮 tool_calls 通常 2~5 个，8 够覆盖且不对 CPU/IO 压太狠；工具若是 **bash/读文件** 偏 I/O，线程池合适；若是 **重 CPU** 应考虑进程池或限流。

**Agent 场景注意：** 并行 tool 必须 **无共享写冲突**——我读多个 reference 文件可以并行，写同一文件不行。我是按 **只读并行、写入串行** 设计的（一轮里多个 read 并行，write 通常单个）。

---

## Q19. 进程 / 线程 / 协程的区别

**【八股 + 自己的 Agent 语境】**

| | 进程 | 线程 | 协程 |
|--|------|------|------|
| **调度** | OS | OS | 用户态（事件循环） |
| **内存** | 独立 | 共享进程空间 | 共享 |
| **切换成本** | 高 | 中 | 低 |
| **GIL（CPython）** | 多进程可真并行 | IO 密集尚可，CPU 密集吃亏 | 单线程并发 IO |
| **典型用途** | 隔离、多核计算 | 并行 IO（我的 tool 池） | 高并发 socket、async FastAPI |

**我的选择：** Sketch 用 **线程池并行 tool**，因为同步 SDK + 同步 LLM 客户端，改造成本低；若上 asyncio 全链路，会换 **协程 + async tool**，但闭源 NCTI SDK 未必支持。

---

## Q20. HashMap 原理

**【八股 + 理解】**

1. **结构**：数组 + 链表/红黑树（JDK8+ 链表长度>8 转树）  
2. **hash**：`hash(key) % capacity` → 桶下标；扩容时 rehash（2 倍）  
3. **冲突**：拉链法；好的 hash 函数减少冲突  
4. **复杂度**：平均 O(1) 查找/插入；最坏 O(log n) 或 O(n)  
5. **线程安全**：`HashMap` 非线程安全；`ConcurrentHashMap` 分段锁/CAS  

**和 Agent 的联想（体现思考）：**  
我用 **SHA256 做零件去重**（CAD 平台入库）—— cryptographic hash 关注抗碰撞；HashMap 的 hash 关注 **均匀分布**。目的不同，不要混为一谈。Agent 里 **session_id → output_dir** 的映射，生产会用 **ConcurrentHashMap 或 Redis**，我实习阶段用文件系统路径分区代替。

---

## Q21. 除自身以外数组的乘积（LeetCode 238）

**【手撕思路】**

**要求：** O(n) 时间，**不用除法**（有 0 时除法麻烦）。

**思路：前缀积 × 后缀积**

```python
def productExceptSelf(nums: list[int]) -> list[int]:
    n = len(nums)
    ans = [1] * n
    prefix = 1
    for i in range(n):
        ans[i] = prefix
        prefix *= nums[i]
    suffix = 1
    for i in range(n - 1, -1, -1):
        ans[i] *= suffix
        suffix *= nums[i]
    return ans
```

**空间可优化：** 输出数组当前缀数组，再扫一遍乘后缀 → O(1) 额外空间。

**面试加分（思考）：** 这题和 **并行前缀和（scan）** 是同一族问题——GPU/向量里常用；Agent 里若要对多路 tool 结果做 **累积状态更新**，也会用到前缀思想（每步依赖前面产物）。和 CAD 项目无直接关系，但能体现你把算法和工程结构联系起来。

---

## 附录：面试官若追问「和闪购业务怎么结合」

| 闪购场景 | 可迁移能力 |
|----------|------------|
| 多轮对话下单/改单 | Multi-Agent + Memory 压缩 + 结构化状态 |
| 商家知识库问答 | RAG 分块 + Tool 白名单 + 引用溯源 |
| 高并发 Tool 调用 | 线程池/异步 + 超时降级 + 幂等 |
| 意图识别（订外卖/查订单） | Skill 路由 + Workflow 分段 |

**话术：** 我的 CAD Agent 和闪购 Agent 都是 **闭域工具 + 强约束 + 多轮状态**，差异在领域知识库和工具 API，架构层可迁移。

---

## 速背清单（进场前 5 分钟）

- [ ] 部署：**内部交付 + CLI**，非公网大规模，但有 session/分区设计  
- [ ] 框架：**LangGraph 用过**，生产用 **CoreCAX 薄循环**  
- [ ] 意图：**Skill Trigger + MANDATORY Tool 描述**  
- [ ] Tool 准确率：**白名单 + API Index + Schema + 结构化回传**  
- [ ] 知识库：**SKILL + reference 渐进披露**（非典型向量 RAG）  
- [ ] ReAct：**while tool_calls 就是**  
- [ ] 线程池：**max_workers=8**，只读并行  
- [ ] Lost in middle：**压缩 + 外置状态 + 关键信息放首尾**  

---

*文档路径：`e:\个人材料\简历\面试题-淘宝闪购-AI应用一面.md`*
