# NTIC-CAX-Agent 项目业务逻辑与架构整理

> 目的：在修改代码前，先梳理清楚项目的整体架构、核心模块、关键数据流与代码入口，方便后续定位与改动。
>
> 整理时间：2026-07-16
> 项目本质：**基于 DeerFlow（LangGraph AI Agent 框架）的二次开发项目**，面向 CAX（CAD/CAE/CAM 等工程研发）领域，增加了 DOE（Design of Experiments，实验设计）等业务路由。

---

## 1. 项目总览

NTIC-CAX-Agent 是一个全栈 AI Agent 平台，后端基于 **DeerFlow**（LangGraph + FastAPI 的"超级 Agent"），并针对 CAX 领域做了定制（如 `threads_doe` 实验设计路由）。整体由三层组成：

| 层 | 端口 | 技术 | 职责 |
|----|------|------|------|
| Nginx | 2026 | Nginx | 统一反向代理入口 |
| Frontend | 3000 | Next.js 16 / React 19 / Tailwind 4 / Shadcn UI | Web 交互界面 |
| Gateway（后端） | 8001 | FastAPI + 内嵌 LangGraph 运行时 | REST API + Agent 运行时 |
| Provisioner（可选） | 8002 | Python | 仅 sandbox 配置为 provisioner/K8s 模式时启动 |

**请求路由（Nginx）**：
- `/api/langgraph/*` → Gateway 内嵌 LangGraph 兼容运行时（agent 交互、threads、流式）
- `/api/*`（其余）→ Gateway REST API（models、MCP、skills、memory、artifacts、uploads 等）
- `/`（非 API）→ Frontend（Next.js）

---

## 2. 后端分层架构

后端代码严格分为两层，**依赖方向单向**：

```
app/                         (应用层，import: app.*)
  ├── gateway/               FastAPI Gateway API + 路由
  └── channels/              IM 平台集成（飞书/Slack/Telegram/钉钉/企微/Discord/微信）

packages/harness/deerflow/   (框架层，import: deerflow.*)
  ├── agents/                 Agent 编排（lead_agent / middlewares / memory / thread_state）
  ├── sandbox/                沙箱执行系统
  ├── subagents/              子 Agent 委派
  ├── tools/                  工具系统
  ├── community/              社区工具（搜索/抓取/aio 沙箱）
  ├── mcp/                    MCP 协议集成
  ├── models/                 模型工厂
  ├── skills/                 Skill 发现与加载
  ├── config/                 配置系统
  ├── persistence/            数据库 / ORM / 迁移
  ├── reflection/             动态模块加载
  ├── runtime/                运行时（run 管理 / stream bridge / checkpointer / store）
  ├── tracing/                LangSmith / Langfuse 追踪
  └── uploads/                文件上传处理
```

**依赖铁律**：`app` 可以 import `deerflow`，但 `deerflow` **禁止** import `app`（由 `tests/test_harness_boundary.py` 在 CI 强制校验）。

---

## 3. 核心运行时：Agent 系统

### 3.1 Lead Agent（主 Agent）

入口：`packages/harness/deerflow/agents/lead_agent/agent.py`
- `make_lead_agent(config: RunnableConfig)` —— LangGraph 图工厂，注册在 `langgraph.json`
- `_make_lead_agent(...)` —— 实际构建逻辑：
  1. 解析模型（`_resolve_model_name`：请求 → agent 配置 → 全局默认）
  2. 根据 `thinking_enabled` / `is_plan_mode` / `subagent_enabled` / `agent_name` 决定能力
  3. 加载工具 `get_available_tools(...)`（沙箱 + 内置 + MCP + 社区 + 子 Agent）
  4. 按 skill 策略过滤工具 `filter_tools_by_skill_allowed_tools`
  5. 注入 tracing callback 到图根（**注意**：图内所有 `create_chat_model` 必须传 `attach_tracing=False`，否则会产生重复 span 且 `session_id/user_id` 无法传播）
  6. `create_agent(...)` 组装 model + tools + middleware + system_prompt + `ThreadState`

### 3.2 中间件链（Middleware Chain）

中间件在 `build_middlewares()` 中按**严格顺序**追加，关键顺序约束见 `agent.py` 注释。完整 20 个中间件（按执行顺序）：

| # | 中间件 | 作用 |
|---|--------|------|
| 1 | ThreadDataMiddleware | 创建每线程隔离目录（workspace/uploads/outputs），解析 user_id |
| 2 | UploadsMiddleware | 注入新上传文件到对话上下文 |
| 3 | SandboxMiddleware | 获取沙箱，存储 sandbox_id 到 state |
| 4 | DanglingToolCallMiddleware | 为缺失响应的 tool_calls 补占位 ToolMessage |
| 5 | LLMErrorHandlingMiddleware | 规范化模型调用失败为可恢复错误 |
| 6 | GuardrailMiddleware | 工具调用前鉴权（可选，guardrails.enabled） |
| 7 | SandboxAuditMiddleware | 审计沙箱 shell/文件操作 |
| 8 | ToolErrorHandlingMiddleware | 工具异常转 ToolMessage，避免中断 run |
| 9 | SkillActivationMiddleware | `/skill-name task` 语法激活指定 skill |
| 10 | SummarizationMiddleware | 接近 token 上限时压缩上下文（可选） |
| 11 | TodoListMiddleware | plan mode 下任务跟踪（可选） |
| 12 | TokenUsageMiddleware | token 用量统计（可选） |
| 13 | TitleMiddleware | 首次交互后自动生成标题 |
| 14 | MemoryMiddleware | 排队对话用于异步记忆提取 |
| 15 | ViewImageMiddleware | 注入图片 base64（仅 vision 模型） |
| 16 | DeferredToolFilterMiddleware | tool_search 时隐藏延迟 MCP 工具 schema（可选） |
| 17 | SystemMessageCoalescingMiddleware | 合并多个 SystemMessage 为单个前置 |
| 18 | SubagentLimitMiddleware | 截断超额 `task` 调用（可选） |
| 19 | LoopDetectionMiddleware | 检测并打断重复工具调用循环 |
| 20 | ClarificationMiddleware | 拦截 ask_clarification，**必须最后**（中断执行 goto END） |

### 3.3 ThreadState

`packages/harness/deerflow/agents/thread_state.py` —— 扩展 `AgentState`，含 `sandbox`、`thread_data`、`title`、`artifacts`、`todos`、`uploaded_files`、`viewed_images`，使用自定义 reducer。

---

## 4. 工具系统（Tools）

`packages/harness/deerflow/tools/` 中 `get_available_tools(groups, include_mcp, model_name, subagent_enabled)` 组装：

1. **配置定义工具** —— 从 `config.yaml` 经 `resolve_variable()` 解析
2. **MCP 工具** —— 已启用 MCP server（懒加载 + mtime 缓存失效）
3. **内置工具**（`tools/builtins/`）：
   - `present_files` —— 输出文件对用户可见（仅 `/mnt/user-data/outputs`）
   - `ask_clarification` —— 请求澄清（被 ClarificationMiddleware 拦截中断）
   - `view_image` —— 图片转 base64（仅 vision 模型）
   - `setup_agent` —— 仅 bootstrap：创建自定义 Agent 的 SOUL.md/config
   - `update_agent` —— 仅自定义 Agent：运行时自更新
   - `task` —— 委派子 Agent（需启用）
   - `tool_search` —— 延迟工具检索
4. **社区工具**（`community/`）：tavily（搜索）、jina_ai（抓取）、firecrawl（爬取）、ddg/serper/exa/brave/searxng（搜索）、image_search（图片搜索）、aio_sandbox（Docker 沙箱）
5. **ACP Agent 工具**：`invoke_acp_agent` —— 调用外部 ACP 兼容 Agent

---

## 5. 沙箱系统（Sandbox）

`packages/harness/deerflow/sandbox/`：
- **抽象接口** `Sandbox`：`execute_command` / `read_file` / `write_file` / `list_dir`
- **Provider 模式** `SandboxProvider`：`acquire` / `acquire_async` / `get` / `release`
  - `LocalSandboxProvider`（`sandbox/local/`）—— 本地文件系统，每线程 `local:{thread_id}`，LRU 缓存（默认 256）
  - `AioSandboxProvider`（`community/aio_sandbox/`）—— Docker 隔离，活跃缓存 + 预热池
- **虚拟路径**：Agent 看到 `/mnt/user-data/{workspace,uploads,outputs}` 和 `/mnt/skills`，物理映射到 `backend/.deer-flow/users/{user_id}/threads/{thread_id}/user-data/...`
- **沙箱工具**（`sandbox/tools.py`）：`bash`、`ls`、`read_file`、`write_file`、`str_replace`

---

## 6. 子 Agent 系统（Subagent）

`packages/harness/deerflow/subagents/`：
- 内置 Agent：`general-purpose`（全工具，除 task）、`bash`（命令专家）
- 执行：`SubagentExecutor` 后台线程池（调度池 3 + 执行池 3），`MAX_CONCURRENT_SUBAGENTS=3`
- 默认超时 `subagents.timeout_seconds=1800`（30 分钟），`max_turns=150`
- 流程：`task()` 工具 → executor 后台 → 轮询 5s → SSE 事件 → 结果
- 子图编译 `checkpointer=False`（一次性，不恢复）

---

## 7. 记忆系统（Memory）

`packages/harness/deerflow/agents/memory/`：
- `updater.py`：LLM 提取上下文 + 事实，`memory.json` 原子写入
- `queue.py`：防抖队列（默认 30s，每线程去重）
- `storage.py`：每用户隔离 `{base_dir}/users/{user_id}/memory.json`（及每 Agent 每用户布局）
- 数据结构：User Context（work/personal/topOfMind）、History、Facts（带 confidence 评分）
- 下次交互注入 top 15 事实 + 上下文到 system prompt `<memory>` 标签

---

## 8. Gateway API（app/gateway/）

FastAPI 应用入口 `app/gateway/app.py`（`create_app()`），端口 8001，健康检查 `GET /health`。

启动流程（`lifespan`）：
1. 加载配置、设置日志级别、tiktoken 预热
2. `langgraph_runtime(app, startup_config)` 初始化运行时（StreamBridge / RunManager / checkpointer / store）
3. `_ensure_admin_user`：首启提示访问 `/setup`；后续启动迁移无主线程到 admin
4. 启动 IM channel service

中间件栈：`AuthMiddleware`（fail-closed）→ `CSRFMiddleware`（Double Submit Cookie）→ `CORSMiddleware`

### 8.1 路由模块（routers/）

| Router | 前缀 | 职责 |
|--------|------|------|
| models | `/api/models` | 列出/查询 LLM 模型 |
| mcp | `/api/mcp` | MCP server 配置管理 |
| memory | `/api/memory` | 记忆读取/重载/配置 |
| skills | `/api/skills` | skill 列表/启停/安装 |
| artifacts | `/api/threads/{id}/artifacts` | 产物文件服务 |
| uploads | `/api/threads/{id}/uploads` | 文件上传（markitdown 自动转 Markdown） |
| threads | `/api/threads/{id}` | 线程本地数据清理 |
| agents | `/api/agents` | 自定义 Agent 管理 |
| suggestions | `/api/suggestions` | 追问建议生成 |
| channel_connections | `/api/channels` | 用户 IM 连接管理 |
| channels | `/api/channels` | IM 渠道集成 |
| assistants_compat | — | LangGraph Platform 兼容 stub |
| auth | `/api/v1/auth` | 认证 |
| feedback | `/api/threads/{id}/runs/{rid}/feedback` | 反馈 |
| thread_runs | `/api/threads/{id}/runs` | 线程内 run 生命周期（stream/wait/cancel） |
| **threads_runs_doe** | **`/api/threads_doe`** | **CAX 定制：DOE 实验设计 run 路由** |
| runs | `/api/runs` | 无状态 run（stream/wait） |
| sessions | — | session_id ↔ thread_id 映射 |

### 8.2 CAX 定制：DOE 路由

`app/gateway/routers/threads_runs_doe.py` + `app/gateway/services_doe.py` 是本项目的**领域定制层**：
- 新增前缀 `/api/threads_doe`，提供 `POST /{thread_id}/runs/stream`（SSE 流式）
- `services_doe.start_run()` 复用 `app/gateway/services.py` 的 `resolve_agent_factory` / `normalize_input` / `build_run_config` / `sse_consumer` / `wait_for_run_completion` 等通用服务
- 关键差异：请求体 `RunCreateRequestDoe` 额外携带 `user_id` 字段，用于指定 run 归属用户（`set_current_user`），绕过基于路径参数的 `@require_permission` 鉴权（因为无状态 run 的 thread_id 在 body 中）
- 这是 CAX 业务（如实验设计/DOE 工作流）的入口，后续改 CAX 相关逻辑应优先看这里

---

## 9. IM 渠道系统（app/channels/）

桥接飞书/Slack/Telegram/Discord/钉钉/企微/微信到 Gateway LangGraph 兼容 API。
- `message_bus.py`：异步 pub/sub
- `store.py`：JSON 持久化 `channel:chat[:topic]` → `thread_id`
- `manager.py`：核心分发器（Feishu/Telegram 用 `runs.stream` 增量更新，Slack/Discord 用 `runs.wait`）
- `service.py`：从 `config.yaml` 管理所有渠道生命周期
- 渠道 worker 通过 `langgraph-sdk` HTTP 客户端 + 内部认证调用 Gateway

---

## 10. 配置系统（config/）

- **主配置** `config.yaml`（项目根）：`config_version`（当前 15）、`models[]`、`tools[]`、`tool_groups[]`、`sandbox`、`skills`、`title`、`summarization`、`subagents`、`memory`、`token_budget`、`channels` 等
- **扩展配置** `extensions_config.json`：`mcpServers` + `skills` 状态
- `get_app_config()` 缓存 + 内容签名热重载（per-run 字段改完即生效；`database`/`checkpointer`/`sandbox` 等 `STARTUP_ONLY_FIELDS` 需重启）
- 配置值以 `$` 开头解析为环境变量
- 模型通过反射 `use: package.module:ClassName` 实例化

---

## 11. 持久化（persistence/）

- ORM 表：`runs`、`threads_meta`、`feedback`、`users`、`run_events`、`channel_*`
- 迁移：alembic **混合引导**（`bootstrap_schema`），Gateway 启动时自动 `alembic upgrade head`
- 数据库：SQLite（默认，开发）/ Postgres（生产多实例，用 advisory lock 串行化）
- LangGraph checkpointer 表（`checkpoints` 等）由 LangGraph 拥有，alembic 通过 `include_object` 过滤排除

---

## 12. 前端（frontend/）

Next.js 16 App Router，站点地图：`/`、`/chats`、`/chats/new`、`/chats/[thread_id]`。
- `src/core/`：业务逻辑（api、agents、threads、messages、skills、mcp、memory、todos、uploads、auth 等）
- `src/components/`：UI（ui / workspace / landing / ai-elements）
- `src/hooks/`：自定义 React hooks
- `src/server/better-auth/`：认证
- 通过 LangGraph SDK + nginx 代理与后端通信

---

## 13. 改代码前的快速定位指南

| 我想改… | 看哪里 |
|---------|--------|
| Agent 行为 / 系统提示词 | `agents/lead_agent/prompt.py`、`agent.py` |
| 新增/调整中间件 | `agents/middlewares/` + `agent.py::build_middlewares` |
| 工具逻辑 | `tools/`、`tools/builtins/`、`community/` |
| 沙箱执行 | `sandbox/`、`community/aio_sandbox/` |
| 子 Agent | `subagents/` |
| 记忆 | `agents/memory/` |
| REST 接口 | `app/gateway/routers/` |
| **CAX/DOE 业务** | **`app/gateway/routers/threads_runs_doe.py`、`services_doe.py`** |
| IM 渠道 | `app/channels/` |
| 配置项 | `config/`、`config.example.yaml` |
| 数据库表 | `persistence/models/`、`persistence/migrations/versions/` |
| 前端交互 | `frontend/src/core/`、`frontend/src/components/workspace/` |

---

## 14. 关键约定与坑点

1. **Tracing 铁律**：图内 `create_chat_model` 必须 `attach_tracing=False`（见 `agent.py` 顶部 docstring），否则重复 span + `session_id/user_id` 丢失。
2. **分层边界**：`deerflow` 不得 import `app`（CI 校验）。
3. **中间件顺序**：`ClarificationMiddleware` 必须最后；`ThreadDataMiddleware` 必须在 `SandboxMiddleware` 前（需 thread_id）。
4. **配置热重载边界**：改 `STARTUP_ONLY_FIELDS`（`database`/`checkpointer`/`sandbox`/`log_level`/`channels` 等）需重启。
5. **TDD 强制**：每个改动必须配单测（`backend/tests/test_<feature>.py`），改完跑 `make test`。
6. **文档同步**：改代码后需同步更新 `README.md` / `CLAUDE.md`（项目约定）。
7. **DOE 路由鉴权**：`threads_doe` 通过 body 中的 `user_id` + `set_current_user` 指定归属，而非路径参数鉴权。
8. **阻塞 IO 检测**：业务代码中的同步阻塞 IO 必须 offload 到 `asyncio.to_thread`（由 `tests/blocking_io/` 运行时门禁校验）。
