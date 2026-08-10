# NTIC-CAX-Agent 面试一页纸

> 适用场景：投递 Agent / LLM 应用 / 工程研发智能化岗位时的项目介绍。
> 定位：基于 **DeerFlow（LangGraph 超级 Agent 框架）** 的二次开发，面向 **CAX（CAD/CAE/CAM）工程研发 + DOE（实验设计）** 领域。

---

## 1. 一句话介绍（开场 30 秒）

> "我参与的项目是一个全栈 AI Agent 平台：后端基于 DeerFlow（LangGraph + FastAPI 的超级 Agent），把通用 Agent 能力下沉成框架层，在应用层针对 CAX 工程研发和 DOE 实验设计做领域适配；核心护城河是把 NCTI 草图内核接进了 Agent 的工具/沙箱链，让 Agent 能真正'画草图、出工程产物'。"

---

## 2. 整体架构（四层 + 双记忆）

```
T1 接入层   Nginx(2026) 反向代理 / 前端(3000, Next.js)
T2 应用层   app/gateway (FastAPI 8001) + app/channels (IM 渠道)
T3 框架层   packages/harness/deerflow/  (Agent/工具/沙箱/Skill/记忆/子Agent)
T4 外部依赖  LLM / MCP / NCTI 草图内核 / 数据库(SQLite·Postgres)
        ┌─ 短期记忆 ckpt：LangGraph Checkpointer (thread 级, 框架拥有, 断点恢复)
        └─ 长期记忆 mem：memory.json (user 级, LLM 提取事实, 注入 system prompt)
```

**分层铁律**：`app` 可 import `deerflow`，反向禁止（CI 用 `test_harness_boundary.py` 强制校验）。
**设计意图**：框架可独立升级，领域业务不污染框架。

---

## 3. 设计思路（6 条主线）

| # | 维度 | 设计决策 | 解决的问题 |
|---|------|----------|-----------|
| 1 | 选型 | 基于 DeerFlow 而非从零造 | 复用人在回路/SSE/多智能体/工具生态 |
| 2 | 分层 | harness(框架) / app(业务) 单向依赖 | 框架与业务解耦、可独立测试 |
| 3 | 编排 | LangGraph 循环图 + 20 中间件链 | 图管"怎么思考"，中间件管"兜什么底" |
| 4 | 扩展 | Skill + 工具(MCP/沙箱) + 子Agent 插件化 | 能力不写死，靠配置扩展 |
| 5 | 隔离 | 沙箱 Provider 渐进：Local→Docker→k3s | 本地内核依赖 + 数据不出域 |
| 6 | 记忆 | 短期 Checkpointer + 长期 memory.json 双层 | 短期保对话不丢，长期保用户画像 |

---

## 4. 关键技术点（面试追问预备）

### Q1. 为什么用 LangGraph 而不是纯 LangChain？
- **不是二选一，是配合用**：LangGraph（StateGraph）管 Agent 的**循环控制流**（LLM→工具→回到 LLM，支持反思/重试/打断、人在回路）；LangChain LCEL 管**线性工具链/DAG**。
- 选 LangGraph 的核心原因：需要**有状态、可恢复、可打断**的 Agent 循环，这是 LCEL 表达不了的。

### Q2. 沙箱为什么选本地/Docker，不用 E2B？
- 项目**实际没用 E2B**（仅 lockfile/demo 文本残留）。
- 选本地：NCTI 草图内核是**本地二进制依赖**，且工程数据要求**不出域（数据主权）**，云沙箱接不上也不合规。
- Provider 模式支持渐进升级到 Docker / k8s Pod，按部署环境切换。

### Q3. Skill 是什么？怎么触发？内容是什么？
- **是什么**：`SKILL.md`（frontmatter + markdown），把"某类任务的领域知识"沉淀成可注入提示词包。
- **怎么触发**：① 被动注入（enabled skill 进 system prompt 缓存）；② 主动 `/skill-name task` 语法（由 `SkillActivationMiddleware` #9 解析，整篇 SKILL.md 注入为隐藏上下文）。
- **权限**：`allowed-tools` 白名单收敛工具调用范围。

### Q4. 短期记忆 / 长期记忆怎么做的？
- **短期**：LangGraph Checkpointer，thread 级状态持久化，框架拥有，支持断点恢复与人在回路。
- **长期**：`MemoryMiddleware` 排队对话 → 防抖 30s → 后台 LLM 抽取事实 → 原子写入 `memory.json`（每用户隔离）→ 下次注入 top15 事实 + 上下文到 `<memory>` 标签。

### Q5. 记忆置信度 ≥0.7 怎么判断？
- **不是独立打分模型**，是 LLM 在记忆更新 JSON 里自己产出的 `confidence`（0~1）字段。
- 入库闸门在 `updater.py`：`if confidence >= config.fact_confidence_threshold`（默认 0.7）才写盘/注入；低于被丢弃。
- LLM 漏写则默认 0.5（会被拦）；提示词把"用户纠正"推到 ≥0.95、"偏好强化"推到 ≥0.9；超 `max_facts`(100) 时按 confidence 降序裁剪。

---

## 5. 技术债 / 改进点（体现深度，必讲）

**最致命问题：DOE 业务层是主运行链的 fork 副本**
- `threads_runs_doe.py` + `services_doe.py` 近乎逐行复制主链路，只为多带一个 `user_id`（`set_current_user` 绕过路径鉴权）。
- **代价**：双份维护、易漂移、逻辑不同步。
- **更优解**：把 `user_id` 提为通用 run 上下文参数（如 ThreadDataMiddleware 已能解析 user_id），消除复制，而非另起一条链路。

---

## 6. 项目能做什么（功能清单）

- 通用 Agent 对话、工具调用、联网搜索/抓取、文件处理
- 多智能体委派（子 Agent）
- **CAX 领域**：调用 NCTI 草图内核**画草图**（13 类几何 + 12 类约束 API）、生成工程文档
- **DOE 领域**：实验设计工作流（专属 `/api/threads_doe` 路由）
- 长期用户记忆、追问建议、IM 渠道（飞书/Slack/企微等）接入

---

## 7. 面试话术模板（结尾收束）

> "这个项目让我理解到：做 Agent 平台，关键是**把'通用能力'和'领域业务'分层**，用图编排管决策、用中间件管横切，用插件化（Skill/工具）做扩展，用双层记忆做连续性。我也能指出当前 DOE 路由对主链路的 fork 复制是主要技术债，并给出收敛方案——这正是我作为实习生真正读懂这个项目的地方。"
