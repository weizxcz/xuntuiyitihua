# 字节 · AI 应用开发 · 二面参考答案

> 基于面经 13 题 + 自我介绍整理，结合韦永根简历项目作答。  
> 二面特点：**少八股、多架构取舍、多「你怎么设计」**——答案要体现工程判断，而不只是概念定义。

---

## 使用说明

| 标签 | 含义 |
|------|------|
| **【项目】** | 可直接引用简历/源码里的真实经历 |
| **【通用】** | 行业通识 + 个人理解 |
| **【诚实】** | 没做过但要如实说，并补迁移思路 |

**二面答题结构建议：** 先给 **1 句话结论** → **分层设计** → **项目里怎么落地/踩过什么坑** → **若上生产还会补什么**。

---

## 自我介绍

**【项目】30 秒版（背这个）：**

> 我是韦永根，桂林电子科技大学硕士，在国创中心做 AI 应用实习。我独立做了 **CAD 草图建模 Multi-Agent**：主 Agent 编排、CAD 子 Agent 写 NCTI 脚本，解决闭源 API 工具幻觉和长上下文稳定性；另有 **FindJobs 三方协同 Agent** 和 **CAD 几何特征 GNN 平台** 全链路经验。擅长 Agent 编排、Tool 约束、Memory 压缩和结构化输出，希望做 **能稳定落地的 Agent 工程**。

**3 分钟版（面试官让展开时）：**

> **Sketch-Modeling-Agent** 是我主线。CAD 场景是高频 Tool 循环 + 长子任务，我采用 Orchestrator–Worker：主 Agent 只委派和汇总，建模细节进子 Agent，用 **文件即状态** 支撑多轮增量编辑。针对 Tool Hallucination 做了 **Skill 白名单 + API Index**；针对 context 爆炸做了 **三层 Memory 压缩**。Skill 六阶段 Pipeline 让新能力只加配置、主循环零改。  
> **FindJobs-Agent** 是 Workflow 型 Agent：评分→画像→课程覆盖→岗位推荐，用 JSON Schema 稳住 15 项量化输出。  
> **CAD 特征平台** 让我有数据状态机、混合推理、失败降级经验。  
> 我的 Agent 目前是 **内部工程交付**，没有千万级流量，但 session 隔离、超时兜底、结构化日志这些生产意识我在架构里预留了。

---

## Q1. 设计 Agent Planner 时，如何防止每步都重新规划导致路径震荡？

**【通用 + 项目】**

**路径震荡** 典型表现：刚决定用方案 A，下一步又推翻改 B，Tool 反复调用、用户感知「来回横跳」。

### 设计原则：Plan 要「分层 + 有惯性 + 可修订边界」

| 手段 | 做法 | 我的项目 |
|------|------|----------|
| **Plan 粒度** | 粗计划（阶段）+ 细执行（单步 ReAct），不是每步都重算全局 Plan | 主 Agent 只规划「是否委派 CAD」；子 Agent 按 Skill SOP 执行 A/B/C 工作流 |
| **Plan 缓存** | 未遇到 **Plan 失效条件** 不重规划 | `current_file` 路径 + task 描述跨轮传递，子 Agent 增量编辑而非从零 |
| **失效条件显式化** | 仅当：工具失败、用户改意图、关键假设被否、超 round 上限 → 才 trigger replan | `MAX_ROUNDS_REACHED`、Tool 返回 `TypeError` 才回灌修正 |
| **状态外置** | Plan 写进结构化 state，不靠模型「记住刚才计划」 | Plan B：脚本在 `output/<session_id>/` 磁盘，Plan 锚定在文件 |
| **禁止频繁 flip** | Prompt 约束：「除非 observation 否定当前假设，否则继续当前分支」 | `<output_discipline>` 子 Agent 一句话汇报，减少主 Agent 误判 |
| **Plan-and-Execute 分离** | Planner 低频（1 次或每阶段 1 次），Executor 高频 ReAct | `cad_agent` 委派 = 一次 Plan；子 Agent 内部 while tool_calls |

### 架构示意

```
用户目标
  → Planner（低频）：拆阶段 / 是否 spawn 子 Agent
  → Executor（高频）：ReAct + Tool，遵循当前阶段 SOP
  → 失效？→ 局部 replan（只改当前阶段，不推翻已完成产物）
```

**面试话术：**

> 防震荡的核心不是「不让改计划」，而是 **限定 replan 触发条件 + 把已完成工作外置成不可变产物**。我们 CAD 场景里，草图脚本一旦 write 到磁盘，后续轮次是 **edit 增量**，Planner 不会每轮问「要不要建模」—— 意图在 Skill Trigger 和 MANDATORY Tool 层已经锁住了。

---

## Q2. Agent 同时要读知识库、调外部 API、融合用户历史偏好，三类 Context 优先级怎么处理？

**【通用 + 项目】**

不能简单「全部塞 prompt」，要 **分层 + 分阶段注入 + 冲突规则**。

### 优先级框架（推荐）

```
P0 安全/权限/时效   → 硬过滤，不满足直接拒绝
P1 当前任务指令     → 用户本轮 query + 显式参数
P2 权威结构化状态   → 文件/DB/API 返回的可验证事实
P3 检索知识         → RAG chunk，需标注来源
P4 用户长期偏好     → 默认风格，可被 P1 覆盖
P5 历史对话摘要     → 背景，最低优先
```

### 三类 Context 的具体策略

| 类型 | 注入方式 | 优先级逻辑 |
|------|----------|------------|
| **知识库** | Retrieve-on-demand，Top-K + Rerank | 与 P1 冲突时：**用户当前指令 > 文档**；多文档冲突见 Q4 |
| **外部 API** | Tool 结果作为 Observation，结构化 JSON | **API 实时数据 > 静态知识库**（价格、库存、CAD 几何状态） |
| **用户偏好** | 独立 preference store，摘要后注入 system 尾部 | **显式本轮要求 > 长期偏好**；偏好只影响默认值（单位、语言、详略） |

### 工程实现

1. **Context Budget**：给每类分配 token 上限（如 API 40%、RAG 30%、偏好 10%、历史 20%）
2. **分阶段可见**：Planning 阶段只看摘要 + 元数据；Execute 阶段再拉 API 详情
3. **冲突检测**：检索到的 chunk 与用户 query 语义距离过低 → 降权或丢弃

**【项目】Sketch Agent 的实际优先级：**

1. **P1** 用户 task + `@attachments`
2. **P2** 磁盘上的 `current_file` 脚本（可执行真相）
3. **P3** `SKILL.md` SOP + 按需 `read_file` reference（领域知识）
4. **P4** `<api_index>` 权威 API 列表（硬约束，不是 RAG）
5. **会话摘要** 只保留目标/参数/待办，不保留全文

> 我们没有典型向量知识库，但 **API Index > reference > 模型记忆** 的优先级是写死在 prompt 里的。

**FindJobs：** 简历内容（P1）> 课程库映射（P3）> 岗位 JD（P2/API）；评分规则在 Prompt 里是 P0 约束。

---

## Q3. 如何理解 Agent 里的「状态（State）」和「上下文（Context）」？

**【通用 + 项目】**

| | State（状态） | Context（上下文） |
|--|---------------|-------------------|
| **是什么** | 系统维护的 **结构化、可持久、可校验** 的任务进展 | 送给 LLM 的 **文本/token 视图** |
| **目的** | 驱动流程、恢复会话、审计 | 让模型「看见」足够信息做决策 |
| **典型载体** | DB、JSON、文件、LangGraph state | `messages[]`、system prompt |
| **关系** | State 是 **source of truth** | Context 是 State 的 **投影/快照** |
| **生命周期** | 跨轮持久 | 受窗口限制，可压缩/裁剪 |

### 类比

> **State = 游戏存档**（血量、位置、任务进度）  
> **Context = 当前屏幕能看到的 UI**（不是整个世界，是裁剪后的视图）

### Agent 工程要点

1. **不要把 State 全塞进 Context** — 会爆炸 + Lost in the Middle
2. **Context 应可由 State 重建** — 压缩丢细节，State 里仍保留路径/ID
3. **Tool 改 State，LLM 读 Context** — 写文件改 state；messages 里只留 `[产出文件] path`

**【项目】Sketch 的 State vs Context：**

| State（磁盘/session.json） | Context（messages） |
|----------------------------|---------------------|
| `output/<session_id>/sketch.py` | 子 Agent 摘要：「已创建矩形并约束」 |
| `session.json` 断点 | 压缩后的 4 段摘要（目标/进度/参数/待办） |
| `current_file` 路径 | 每轮 task 里重复强调路径 |
| Tool 白名单配置 | system prompt 里的 `<api_index>` |

**Plan B「文件即状态」** 的本质就是：**State 外置，Context 只留索引** — 这是我对二面这题最想强调的设计。

---

## Q4. RAG 召回了多篇互相矛盾的文档，Agent 不应简单丢给模型总结，该怎么处理？

**【通用 + 项目类比】**

**错误做法：** Top-K 全拼进 prompt → 模型「和稀泥」或随机选一个 → 幻觉。

### 推荐流水线

```
多 chunk 召回
  → 矛盾检测（可选：NLI 模型 / 规则 / LLM 结构化比对）
  → 分支处理：
       ├─ 按权威度/时间/版本选唯一来源
       ├─ 按场景/metadata 过滤（用户所在部门、产品版本）
       ├─ 并列呈现但强制模型「标注冲突点 + 引用来源」
       └─ 无法消解 → 追问用户或拒答
  → 生成答案必须带 citation
```

### 具体策略

| 策略 | 适用 |
|------|------|
| **来源分级** | 官方文档 > 内部 wiki > 社区帖 |
| **时间/version 元数据** | 同名 API 以最新版为准 |
| **矛盾显式化 Prompt** | 「若来源 A 与 B 冲突，列出差异，不得合并为单一事实」 |
| **Agent 工具化** | 增加 `verify_with_api`：静态文档 vs 实时 API 对账 |
| **拒答** | 低置信 + 高冲突 → 「当前知识库存在冲突，请确认版本/场景」 |

**【项目类比】**

1. **API Index vs reference 案例** — 若 reference 写了旧接口名，以 `<api_index>` 为准（**权威源分级**）
2. **CAD 混合推理** — 几何规则与 GNN 预测不一致时，用 **交集策略** 而非简单 union；相当于「矛盾时取可验证交集」
3. **FindJobs** — 简历自评 vs 课程覆盖度矛盾时，Workflow 分阶段输出，**不一次性让 LLM 混合所有信号**

**面试金句：**

> RAG 矛盾处理的本质不是「让模型更聪明」，而是 **在生成前做冲突消解或显式标注**；消解不了就 **升级给人**，而不是假装有唯一答案。

---

## Q5. Tool 调用成功但返回语义不完整，模型易误解——中间件层怎么设计？

**【通用 + 项目】**

这是 **Tool Result Normalization Layer**（工具结果归一化层），介于 Tool 执行与 LLM 之间。

### 中间件职责

```
Raw Tool Output
  → 解析/校验（schema、空字段、错误码伪装 success）
  → 语义补全（枚举映射、单位、默认值说明）
  → 结构化包装（固定 JSON 模板）
  → 置信度/完整性标记
  → 写入 messages（role: tool）
```

### 设计要点

| 问题 | 中间件做法 |
|------|------------|
| 返回 `{}` 或 null | 检测空结果 → 转成 `{ok: false, reason: "empty_response"}` |
| 字段缩写/枚举码 | 映射成人类可读 + 保留 raw |
| 过长/二进制 | 摘要 + 存文件，返回 `[产出文件] path` |
| 部分成功 | `{status: "partial", succeeded: [...], failed: [...]}` |
| 易误解的成功 | 如 HTTP 200 但 body 里 `error_code` → 统一判失败 |

### 中间件分层

1. **Transport 层** — 超时、重试、熔断
2. **Normalize 层** — schema 校验、字段映射（**本题核心**）
3. **Policy 层** — 决定给 LLM 看 full / summary / path
4. **Observability 层** — 原始响应落日志，给 LLM 看清洗版

**【项目】Sketch 已有类似实践：**

- `write_file` / `edit_file` 成功后追加 **`[产出文件] absolute_path`** — 模型不必猜文件在哪
- Tool 参数 `TypeError` → 返回 **可读错误** 让模型改参，而不是 silent fail
- `attachments.py` 单文件失败 **skip + warning**，批量里不污染整体语义
- `<output_discipline>` 强制子 Agent **一句话汇报** — 限制模型对长输出的过度解读

**若加强中间件我会加：**

> NCTI SDK 返回码 → 统一 `{ok, api, params, geometry_changed, hint}` 模板；不完整时 **禁止** 主 Agent 宣布「建模完成」。

---

## Q6. Agent 什么时候该追问用户，什么时候该继续自主推理？

**【通用 + 项目】**

### 决策矩阵

| 继续推理 | 追问用户 |
|----------|----------|
| 缺失参数有 **安全默认值** 且可逆 | 缺失参数 **不可逆/高风险**（删特征、覆盖文件、下单） |
| 可通过 Tool **探测** 得到（读文件、查 API） | 意图 **歧义** 且多条路径成本差异大 |
| Skill SOP 已覆盖标准流程 | 超出 Skill 边界或权限外操作 |
| 用户 said「你看着办」 | 用户 said「先问我」或 regulatory 场景 |
| 低 stakes 试探 + 结果可回滚 | 矛盾信息需用户确认版本/对象 |

### 工程实现

1. **Slot Filling 检查清单** — CAD prompt 写「缺参数必须回报，禁止默认假设」
2. **置信度阈值** — Planner 输出 `{need_clarify: true, questions: [...]}`
3. **最大自主步数** — 连续 N 步未达成子目标 → 升级追问
4. **Human-in-the-loop 节点** — LangGraph interrupt；Sketch 用 CLI 同步对话天然是人机交替

**【项目】**

- **Sketch CAD 子 Agent**：半径、约束类型缺失 → **必须追问**（Prompt 硬约束）
- **主 Agent 读 reference**：可 **自主** `read_file`，不需问用户
- **FindJobs**：简历字段齐全 → **自主** 跑完四阶段；缺关键字段 → API 返回缺项提示

**原则一句话：**

> **可逆 + 可探测 → 自主；不可逆 + 歧义 + 高风险 → 追问。**

---

## Q7. 模型生成很强但不擅长严格流程，如何接入强约束工作流？

**【通用 + 项目】**

核心思想：**不要让 LLM 当流程引擎，让它当流程里的「智能节点」**。

### 四层约束（由强到弱）

```
L1 代码/状态机     → 节点顺序硬编码，LLM 无权跳步
L2 Schema/Tool     → 每步输出 JSON Schema，校验不过不进入下一步
L3 Prompt/SOP      → Skill 文档规定 A→B→C
L4 模型自由生成    → 仅放在「内容生成」子任务
```

### 接入方式

| 模式 | 说明 | 我的项目 |
|------|------|----------|
| **Workflow 编排** | FindJobs 四阶段固定顺序 | 评分→画像→课程→岗位 |
| **Skill SOP** | Markdown 写死流程 | `SKILL.md` Workflow A/B/C |
| **Structured Output** | JSON Schema 锁字段 | FindJobs 15 项评分 |
| **Tool 白名单** | 每阶段只暴露允许的工具 | 子 Agent 仅 3 个文件工具 |
| **委派边界** | 主 Agent 只能 `cad_agent`，不能直写 CAD API | MANDATORY 委派 |
| **LangGraph** | 图边条件跳转 | CAD-Agent-Education 探索版 |

**【项目】话术：**

> CAD 建模我们不让主 Agent 自由写 NCTI，而是 **委派 + Skill Pipeline 六阶段 + API Index**。模型负责「理解任务、选 reference、生成脚本」，**流程由配置和代码守门**。FindJobs 更极端：几乎不用 ReAct，是 **纯 Workflow + Schema**。

**字节业务联想（可选）：**

> 闪购改单、售后判责适合 L1/L2；开放式客服问答才给 L4 空间。

---

## Q8. Agent 的失败恢复机制怎么设计？

**【通用 + 项目】**

失败分 **Tool 失败、模型失败、业务失败、系统失败** 四层，恢复策略不同。

### 恢复策略矩阵

| 失败类型 | 检测 | 恢复 |
|----------|------|------|
| Tool 超时/5xx | 中间件 | 指数退避重试（幂等操作） |
| Tool 参数错误 | Schema/异常 | 错误回灌 → 模型改参（1~2 次） |
| Tool 业务 reject | 返回码 | 换策略/换 Tool/追问用户 |
| 模型格式错 | JSON 解析失败 | 重试 + 「仅输出 JSON」 |
| 上下文触顶 | token 监控 | Memory 压缩 → 硬折叠 |
| 死循环 | max_rounds | `MAX_ROUNDS_REACHED` 显式失败 + 保留 state |
| 子 Agent 崩溃 | 超时/异常 | 主 Agent 收摘要，提示用户从 checkpoint 续 |

### _checkpoint 设计_

**【项目】Sketch：**

- `session.json` + `output/<session_id>/` → **断点续聊**
- 三层 Memory 压缩 → 触顶前 **主动降级** 而非 OOM 硬挂
- 并行 Tool 单路失败 → skip + warning，不拖垮整轮
- `MAX_ROUNDS_REACHED` → 明确告诉用户「未完成任务 + 当前文件路径」，可人工接管

**【项目】CAD 平台：**

- 入库 **5 态状态机** → 失败可回滚到上一态
- 混合推理：AI 路径失败 → **降级几何规则**

**生产还会补：**

> 幂等 idempotency key、dead letter queue、自动告警（连续 3 次同 session 失败）、fallback 小模型、人工工单升级。

---

## Q9. 如何判断任务该单 Agent 还是 Multi-Agent？

**【通用 + 项目】**

### 选 Multi-Agent 的信号

- **上下文隔离**：子任务输出很长，会污染主对话（CAD 建模）
- **工具集冲突**：主对话要广工具，子任务要窄白名单
- **角色/权限分离**：规划者 vs 执行者 vs 审核者
- **并行子任务**：多个独立检索/分析可并行
- **不同模型**：路由用小模型，生成用大模型

### 选 Single Agent 的信号

- 步骤少、工具 ≤5、无长输出污染
- 强 Workflow、低歧义（FindJobs 四阶段）
- 延迟敏感，Multi-Agent _spawn 开销不值
- 调试期，先单 Agent 跑通再拆

### 决策表

| 维度 | Single | Multi |
|------|--------|-------|
| 任务耦合 | 高 | 低，可委派 |
| 输出体积 | 小 | 大（代码、报告） |
| Tool 风险 | 低 | 高（需收敛） |
| 会话长度 | 短 | 长 |

**【项目】**

- **Sketch** → Multi：Orchestrator–Worker，**子 Agent 隔离 CAD 长输出**
- **FindJobs** → Single Workflow 链：**阶段清晰，无需多角色协商**
- **CAD-Agent-Education** → 单图多节点，本质是 **逻辑 Multi、物理单进程**

**面试话术：**

> 我拆 Multi-Agent 的第一问不是「酷不酷」，而是 **上下文会不会被单 Agent 撑爆、Tool 要不要收敛**。CAD 两条都中，所以拆；就业匹配是固定 pipeline，单链更合适。

---

## Q10. 生产环境 Agent 最难监控的指标是什么？

**【通用 + 诚实】**

### 候选「最难指标」

| 指标 | 难在哪 |
|------|--------|
| **任务真实成功率** | 「没报错」≠ 用户目标达成；CAD 脚本跑通 ≠ 几何正确 |
| **Silent failure / 幻觉成功** | Tool 返回 200 但语义错，用户很久才发现 |
| **长期 drift** | 模型/文档/API 变更后 gradual 退化，单点告警看不出 |
| **用户满意度 vs 自动化率** | 自主步数多可能更「聪明」但更惹恼用户 |
| **归因** | 失败是检索、规划、Tool、还是模型？多 Agent 链路长 |

### 我的答案（推荐二面这样说）

> 我认为最难的是 **「Silent task success rate」—— 用户目标是否真正达成，且系统没有意识到自己错了。**  
> 错误栈、P99 延迟都好监控；难的是 **Tool 成功 + 回答流畅 + 结果其实不对**。CAD 里脚本生成了但约束漏了，FindJobs 分数格式对但评分不合理，都属于这类。

### 怎么补监控

1. **Outcome 校验** — CAD：脚本可执行 + 几何断言；FindJobs：分数区间/一致性规则
2. **抽样人工标注** — 每周 Golden set 回归
3. **用户隐式信号** — 重试率、同 session 反复改同一参数、对话 abandonment
4. **全链路 Trace** — plan → tool → raw → normalized → llm，可回放
5. **对比监控** — 同 query 新旧版本答案 diff

**【诚实】** 我实习环境没有完整 APM，但 Sketch 留了 session 落盘和 tool 打印，**为 outcome 审计打了基础**。

---

## Q11. 若要做「可审计 Agent」，应保留哪些信息？

**【通用 + 项目】**

### 审计日志最小集（ALCOA 思路： attributable, legible, contemporaneous, original, accurate）

| 类别 | 保留字段 |
|------|----------|
| **请求** | user_id、session_id、timestamp、原始 query、附件 hash |
| **决策** | 选用的 Skill/Workflow、Planner 输出、模型版本、temperature |
| **检索** | 召回 chunk id、来源、分数、Rerank 后顺序 |
| **Tool** | 工具名、入参、**原始响应**、归一化响应、耗时、成功/失败 |
| **生成** | 每轮 LLM messages 快照或 diff、token usage |
| **产物** | 输出文件路径、hash、版本号 |
| **人工** | 用户反馈、是否 override、追问内容 |
| **安全** | 拒绝原因、权限校验结果 |

### 存储原则

- **Raw + Normalized 双写** — 争议时可查原始 API
- **不可篡改** — append-only / WORM 存储
- **PII 分级** — 审计可见 vs 展示脱敏
- **可回放** — 给定 session_id 能复现当时 context（或近似）

**【项目】已有/可扩展：**

| 已有 | 可扩展 |
|------|--------|
| `session.json` 断点 | 每轮 messages 增量归档 |
| `output/<session_id>/` 产物 | 文件 hash + 与对话关联 |
| Tool 执行打印 | 结构化 JSON log |
| Skill/API 版本跟 Git | 发布 tag 写入审计 |

**FindJobs：** 15 项评分 JSON 天然可审计；应再加 **输入简历 hash + Prompt 版本**。

---

## Q12. 为什么很多 Agent Demo 很惊艳，上线后却不稳定？

**【通用 + 项目】**

### Demo 与生产的差距

| Demo 常隐藏 | 生产必面对 |
|-------------|------------|
| 精心选的 3 个 case | 长尾 query、脏输入、 adversarial |
| 单用户、短会话 | 并发、长会话、context 触顶 |
| 最新模型 + 手工 Prompt | 成本、延迟、模型升级回归 |
| 失败手动重试 | 无人值守、需自动恢复 |
| 无权限/合规 | 越权 Tool、数据泄露 |
| 无评测集 | 改动无法量化，越改越坏 |
| 「成功路径」演示 | 异常 Tool 返回、矛盾 RAG、路径震荡 |

### 根因归纳

1. **把概率系统当确定性软件卖**
2. **State 在 Context 里飘**，没有外置与压缩
3. **缺 Tool 中间件**，raw 输出直接喂模型
4. **缺 Outcome 监控**，只有「没抛异常」
5. **Scope creep** — Demo 功能边界清晰，上线后需求堆进单 Agent

**【项目】我的反 Demo 设计：**

- **文件即状态** — 不是「聊完就忘」
- **Tool 白名单** — 不是「模型想用啥工具都行」
- **max_rounds + 显式失败** — 不是「无限 loop 直到碰巧成功」
- **JSON Schema** — FindJobs 不是「看起来对了就行」
- **【诚实】** 我们仍是内部交付，离字节级生产还有网关、灰度、全链路 trace 要补

**面试金句：**

> Demo 展示的是 **模型的上限**；生产需要的是 **系统的下限** —— 失败可恢复、边界可约束、结果可审计。

---

## Q13. AI Agent 方向，一面和二面最大区别是什么？

**【通用 + 结合本次面经】**

| 维度 | 一面（结合我准备的闪购/成都面经） | 二面（本次字节） |
|------|-----------------------------------|------------------|
| **深度** | 会不会：RAG 流程、ReAct、线程池、Vue 八股 | 为什么这样设计：Planner 震荡、State vs Context |
| **题型** | 知识点 + 项目经历罗列 | 开放设计题 + 取舍 + 失败场景 |
| **项目** | 「你做了什么」 | 「若重来/上生产你怎么改」 |
| **工程** | Tool、Prompt、框架用过啥 | 中间件、审计、监控、人机边界 |
| **思维** | 单点优化（Rerank、压缩） | 系统论（Demo vs Prod、Multi-Agent 边界） |

**我的体会（可原话）：**

> 一面考 **广度 + 基础是否扎实**，看我有没有真实做过 Agent/RAG；二面考 **架构成熟度**，看我在长会话、Tool 噪声、矛盾知识、生产监控这些 **「不性感但致命」** 的问题上有没有成体系的解法。一面可以背流程，二面要讲 **trade-off 和失败模式** —— 所以我回答时会主动带「我们项目里踩过 / 若上生产会补」。

---

## 附录 A：二面高频追问 → 我的项目一句话

| 追问 | 一句话 |
|------|--------|
| 你们 Planner 在哪？ | 主 Agent 委派 + Skill SOP；不是每步全局 replan |
| State 存哪？ | 磁盘脚本 + session.json；Context 只留摘要 |
| 矛盾知识？ | API Index > reference；混合推理用交集 |
| Tool 结果脏？ | 结构化回传 + 错误可读 + `[产出文件]` |
| 何时问用户？ | CAD 缺参必问；可读文件则自主 |
| 强流程？ | Workflow + Schema + 白名单 |
| 失败恢复？ | 压缩/ checkpoint / MAX_ROUNDS / 状态机 |
| 为何 Multi-Agent？ | 隔离长输出 + 收敛 Tool |
| 最难监控？ | Silent success — 看起来成功其实错了 |
| 审计留啥？ | session、产物、tool raw、模型/Prompt 版本 |

---

## 附录 B：与字节业务的迁移话术（可选）

| 字节场景 | 我的可迁移设计 |
|----------|----------------|
| 长对话助手 | 三层 Memory + State 外置 |
| 工具型 Bot（下单/改单） | 强 Workflow + 缺参追问 + 幂等 |
| 知识问答 | 矛盾检测 + 来源分级 + 拒答 |
| 多技能 Agent | Skill 配置化 + 动态 Tool 过滤 |
| 质量与审计 | 全链路 log + outcome 校验 |

---

## 速背清单（进场前 5 分钟）

- [ ] **防路径震荡**：粗 Plan + 失效才 replan + 文件即状态  
- [ ] **Context 优先级**：指令 > API/State > RAG > 偏好 > 摘要  
- [ ] **State vs Context**：存档 vs 屏幕；State 是 truth，Context 是投影  
- [ ] **RAG 矛盾**：分级/版本/显式冲突/拒答，不和稀泥  
- [ ] **Tool 中间件**：normalize + 完整性标记 + raw 落日志  
- [ ] **追问 vs 自主**：不可逆/歧义/高风险 → 问；可探测/可逆 → 做  
- [ ] **强约束**：Workflow/Schema/白名单，LLM 不当流程引擎  
- [ ] **失败恢复**：重试、回灌、压缩、checkpoint、max_rounds  
- [ ] **Multi-Agent**：长输出、Tool 收敛、上下文隔离时再拆  
- [ ] **最难监控**：Silent task success，不是 error rate  
- [ ] **Demo vs Prod**：系统下限 > 模型上限  
- [ ] **一面 vs 二面**：广度八股 → 架构取舍与失败模式  

---

*文档路径：`e:\个人材料\简历\面试题-字节-AI应用开发-二面参考答案.md`*
