# 草图 Agent「结构化转译 + 验证闭环」设计方案

> 目标：把当前"LLM 直接生成 NCTI Python 脚本"的脆弱链路，升级为"LLM 产出结构化草图规格 → 确定性转译器生成内核脚本 → 求解器验证闭环自修正"的工业级链路。
> 本文先汇总开源 CAD/Sketch Agent 与最新论文的做法，再给出落地到本项目（NCTI 内核 + DeerFlow harness）的具体设计。
> 调研时间：2026-07-20

---

## 1. 为什么需要"结构化转译 + 验证闭环"

当前 `skills/custom/sketch/SKILL.md` 的本质是：**LLM 直接写 Python → `write_file` → bash 沙箱 → `import YH` 调 NCTI 内核 → `RunSolve()`**。问题：

- LLM 既要"理解意图"又要"写对内核 API + 参数"，两步错误叠加；
- 工作流里**没有"画完检查"步骤**（A–E 都是生成/编辑，无验证）；
- 几何合法性（约束冲突、过/欠约束、退化几何）只能靠内核求解器判定，模型本身保证不了。

业界共识（见下文调研）：**把"生成"和"正确性"解耦——用结构化中间表示承接意图，用确定性代码生成承接内核，用求解器做验证闭环。**

---

## 2. 开源项目与论文调研

### 2.1 标杆：CADSmith（2026, arXiv:2603.26512）
- **做法**：多智能体管道，从自然语言生成 **CadQuery** 代码；**不用微调**，而是用 **RAG 查 CadQuery API 文档**（内核演进时知识库不失效）。
- **双嵌套纠错循环**（直接对应"验证闭环"）：
  - **内循环**：解决**执行错误**（语法/API/运行时异常）——对应"脚本能不能跑"。
  - **外循环**：**程序化几何验证**——直接调 OpenCASCADE 内核取精确数值：边界框尺寸、体积、**实体有效性(solid validity)**；再引入一个独立 **VLM Judge** 做整体视觉评估。
- **效果**：Chamfer Distance 从 28.37 降到 0.74。
- **对我们的启示**：① 验证要分"能跑"和"几何对"两层；② 几何正确性靠**内核数值提取**，不是模型；③ API 知识用 RAG 而非微调（与上一轮"不建议微调 API"一致）。

### 2.2 Draw2Think（2026, arXiv:2605.20743）——"每动作验证"范式
- **做法**：把冻结的 VLM 包在 **GeoGebra 约束引擎**外，通过**类型化工具规范（Typed ToolSpecs）**通信；画布即"工作记忆"。
- **Propose-Draw-Verify 闭环**：VLM 提议类型化构造动作 → 引擎以代数方式执行 → **无效/退化配置作为 engine error 直接返回** → 结构化观察（错误、精确长度/角度/交点）回灌模型自修正。
- **Per-action verification**：验证点从"生成后"提前到"每动作后"，避免"最终对但中间错"。
- **对我们的启示**：① "类型化工具"= 结构化转译的雏形；② 验证应**尽早、尽量细粒度**；③ 引擎报错要结构化回灌，而非静默近似。

### 2.3 CADDesigner（2026, CAD 期刊 vol.198）
- **做法**：ReAct 工作流；先做**交互式需求分析**把模糊输入细化；用 **ECIP（显式上下文命令范式）** 让建模上下文/操作状态显式化以降低歧义；执行后检查**符号日志 + 渲染视觉反馈**自动修订；成功案例存入**结构化知识库**持续积累。
- **对我们的启示**：① 模糊输入先"澄清"再生成（对应本项目 `ClarificationMiddleware`）；② "显式上下文"≈ 结构化中间表示；③ 用知识库沉淀成功草图（对应长期记忆）。

### 2.4 cad-agents-platform（2026, GitHub 新鲜项目）—— 架构同构验证
- **做法**：**LangGraph** 编排 O2C 十阶段制造流水线；为 NX / SolidWorks / FreeCAD **各建独立 Agent**（各自 system prompt + 示例 + **validation**）；`designer` 用 RAG 从真实轮廓库检索；`assembler` 输出带几何约束的 URDF；用 `interrupt()`/`Command(resume)` 做**人在回路**，用 `AsyncPostgresSaver` 做检查点恢复。
- **对我们的启示**：它的架构（LangGraph + 每平台验证 + 人在回路 + Checkpointer）**与本项目高度同构**——证明"harness + 验证 + 人在回路"是业界主流路线，我们的分层方向是对的。

### 2.5 微调路线参考（作对比，非推荐）
- **CAD-Coder（2025）**：专为 CAD 代码生成**微调的开源 VLM**，可从图像直接出 CAD 代码。证明"微调识别"可行，但代价是数据标注 + 权重随内核演进过期。
- **Sketch2CAD（SIGGRAPH Asia 2020）**：手绘草图 → 可编辑 CAD，序列建模 + 分割 + 几何优化。草图识别的经典范式。
- **DeepCAD**：178,238 个模型的 CAD 构造序列数据集——可用于**合成训练数据**启动识别模型。

> 结论：识别侧微调有先例（CAD-Coder / Sketch2CAD），但**生成侧应走"结构化 + 验证"而非微调**（CADSmith 用 RAG 已证伪微调必要性）。

---

## 3. 跨项目共性模式（提炼）

| 模式 | 出处 | 本项目对应 |
|------|------|-----------|
| 结构化/显式中间表示 | Draw2Think Typed ToolSpecs, CADDesigner ECIP | 本文 SketchSpec |
| 确定性代码生成（非 LLM 裸写） | 全部 | 本文 Transpiler |
| 双层验证（执行错误 + 几何合法性） | CADSmith 双循环 | verify_sketch |
| 每动作/尽早验证 | Draw2Think per-action | 转译后即时 solve |
| 内核数值提取做判定 | CADSmith solid validity | NCTI RunSolve 状态读取 |
| API 知识用 RAG 不用微调 | CADSmith | Skill/references |
| 成功案例沉淀 | CADDesigner 知识库 | 长期记忆 |
| 人在回路 + 检查点 | cad-agents-platform | ClarificationMiddleware + Checkpointer |

---

## 4. 本项目落地设计

### 4.1 结构化中间表示：SketchSpec（JSON Schema）
LLM 不再输出 Python，而是输出**与内核解耦的草图规格**（字段严格对应 NCTI 的 13 几何 + 12 约束类型）：

```json
{
  "plane": "XY",
  "auto_solve": true,
  "primitives": [
    {"id":"l1","type":"line","start":[0,0,0],"end":[50,0,0]},
    {"id":"c1","type":"circle","center":[25,25,0],"radius":10.0}
  ],
  "constraints": [
    {"type":"length","target":"l1","value":50.0},
    {"type":"tangent","a":"c1","b":"l1"}
  ]
}
```
- `id` 提供**稳定对象引用**（解决"左边那个孔"类指代问题）；
- 类型/参数与 `SKILL.md` 中 13 几何 + 12 约束一一映射，可被 schema 校验。

### 4.2 确定性转译器：Spec → NCTI Python
一段**不依赖 LLM**的代码，把 SketchSpec 编译为 `YH.SketchWorkPlane` / `YH.YHDocument` 调用：
- 遍历 primitives → 生成 `skt.AddLine(...)` 等，按 `id` 绑定变量；
- 遍历 constraints → 生成 `skt.AddConsLength(0, l1)` 等，用 `id` 解析对象引用；
- 处理 `auto_solve` → `yh_doc.AutoSolve(False)` + 末尾 `skt.RunSolve()`。
- **收益**：彻底消灭 LLM 的语法错误、API 误用、变量名错配——这是比微调更便宜且可靠的"脚本更准"。

### 4.3 验证闭环：verify_sketch（对应 CADSmith 外循环 + Draw2Think 每动作验证）
新增领域工具 `verify_sketch`，在 `RunSolve()` 后读取 NCTI 内核状态：
- **约束状态**：过约束 / 欠约束（自由度 DOF 数）/ 冲突约束列表；
- **退化几何**：零长线、重合点、自交；
- **实体有效性**：草图是否闭合、是否可拉伸。
- 把上述**结构化结果**回灌 LLM，触发 Spec 补丁（改尺寸/加约束/删退化图元）→ 重新转译 → 重新验证，**有界重试**（如 ≤3 轮）。
- 内循环（执行错误）由转译器确定性生成天然规避，外循环（几何合法性）由 verify_sketch 兜底——与 CADSmith 双循环同构。

### 4.4 与现有架构的集成点
| 改动点 | 落点 | 说明 |
|--------|------|------|
| Skill 改写 | `skills/custom/sketch/SKILL.md` | 工作流改为"输出 SketchSpec → 调 transpiler → 调 verify_sketch"，删除"裸写 Python" |
| 新增工具 | `deerflow/tools/` 或 `sketch` Skill 的 allowed-tools | `emit_sketch_spec`、`verify_sketch`（确定性转译器作为内部函数） |
| 人在回路 | `ClarificationMiddleware` | 模糊/冲突时 `ask_clarification` 澄清而非瞎猜（CADDesigner 需求分析） |
| 连续性 | Checkpointer + 长期记忆 | Spec 作为 state 保存可断点续跑；成功 Spec 存入记忆当知识库（CADDesigner） |
| 识别（感知层，前置补充） | **图像 → SketchSpec 的 CV/几何感知方案见 `sketch-perception-design.md`** | 当前瓶颈在识别段，已前移为确定性 CV/几何 + OCR（非微调）；VLM 仅兜底语义 |

---

## 5. 实施路线图（分阶段，性价比递增）

1. **P0 结构化转译**：定义 SketchSpec + 转译器，Skill 改为输出 Spec。→ 消灭语法/API 错误，几乎零成本。
2. **P1 验证闭环**：`verify_sketch` 读内核状态 + 有界重试。→ 几何合法性兜底。
3. **P2 澄清 + 知识沉淀**：模糊输入走 Clarification；成功 Spec 入长期记忆。
4. **P3 识别微调（仅若 M0–M2 后仍卡识别）**：只微调"草图图 → SketchSpec"的 VLM，用合成数据启动 + 少量人工标注；**不微调代码生成**。（图像→SketchSpec 的感知层具体设计见 `sketch-perception-design.md`，已前移为 M0–M2 的确定性 CV/几何方案。）

> 与领导对齐要点：微调只该出现在 P3 且只针对"识别"，P0–P2 用架构手段把下限拉起，不依赖训练数据。

---

## 5.1 前置依赖：需内核团队冻结的 API 文档清单（阻塞项）

> 当前 `skills/custom/sketch/references/case-*.md` 中的签名**可能过期**，且验证闭环依赖的"读回"能力在现有文档中**完全缺失**。
> 在同事的内核 API 文档冻结前，**不启动任何代码实现**（避免基于会变的假设返工）。
> 以下清单即为与内核团队对齐的"文档需求"，逐项确认后才能解除阻塞。

### 阻塞项 A：运行时前提（决定代码能否跑起来）
| 需求项 | 为什么必须 | 当前状态 |
|--------|-----------|----------|
| 沙箱内 `YH` / `NCTI` 的 import 方式（包名、路径、是否预装） | 转译器生成的脚本第一句就是 `import YH`，import 不了全盘皆输 | 文档仅写"预注入"，未说明如何获得 |
| 预注入文档/草图句柄的获取 API（如 `doc` / `skt` 从哪来、怎么创建新的） | 当前 case 文档假设 `doc` 已存在，但新建会话需要显式创建 | 未文档化 |
| `YHDocument` / `SketchWorkPlane` 的最小可运行构造示例 | 验证"骨架能立" | 仅有 Add 系列，缺顶层的建文档/建平面 |

### 阻塞项 B：求解器反馈语义（决定 verify_sketch 能否做"深层验证"）
> **2026-07-21 探针结论（重要，推翻原"无 API 文档"判断）**：DOF/冲突/状态接口**在本地安装的内核里确实存在**，只是名字与我们预测的 `GetDOF`/`GetConflictCons` 不同——真实接口是 `doc.dcm_constraint_balance(sys)`（`[1]`=自由度/[2]`=约束度/`[3]`=刚性体自由度）、`doc.dcm_status(sys, node)`（枚举：`3`=OVER_DEFINED/`5`=NOT_CONSISTENT/`10`=WELL_DEFINED/`11`=UNDER_DEFINED），另有新一代 `dcm3_*` 引擎（`dcm3_constraint_balance`/`dcm3_status`/`dcm3_overdefined_status`/`dcm3_underdefined_dof`/`dcm3_get_overdefined_constraints`）。**但**这些接口在独立的 `ncti_python` 绑定里**无法 headless 执行**（见 §5.3），故"深层验证"的真正阻塞项从"缺接口"转为"缺宿主应用执行环境"。

| 需求项 | 为什么必须 | 当前状态 |
|--------|-----------|----------|
| `RunSolve()` 的返回值类型与异常类型（过约束 / 欠约束 / 退化几何分别怎么反馈：抛异常？返回错误码？静默不求解？） | 验证闭环的核心输入——没有它就只能做"浅层验证" | 只写"执行约束求解"，无返回值/异常说明（仍待内核团队补） |
| 自由度（DOF）查询接口 | 判断"欠约束"必须的数值依据 | ✅ 已找到真实接口：`doc.dcm_constraint_balance(sys)[1]`（见上） |
| 约束冲突查询接口 / 求解器状态枚举 | 判断"过约束/哪条冲突"必须 | ✅ 已找到真实接口：`doc.dcm_status(sys, node)` + `dcm3_get_overdefined_constraints` |
| 退化几何检测接口（零长线、重合点、自交） | 浅层验证也依赖 | ⚠️ 仍待内核团队补（独立绑定下无法验证） |

### 阻塞项 C：最终 API 签名（决定转译器映射表是否正确）
| 需求项 | 为什么必须 | 当前状态 |
|--------|-----------|----------|
| 13 几何 + 12 约束 API 的**最终签名**（参数类型、返回值、是否含 no-arg GUI 版本） | 转译器是机械映射，签名一变映射全变 | `case-*.md` 疑似过期，需内核团队确认冻结版 |
| `AutoSolve(True/False)` 与 `RunSolve()` 的精确时序约束 | 批量加约束时是否需先关自动求解 | 文档有提及但时序未严格定义 |

### 文档冻结前的可执行动作（不写业务代码）
- 与内核团队开一次对齐会，把上表作为"API 文档交付验收单"；
- 内部先冻结 **SketchSpec JSON Schema**（第 4.1 节，与内核无关，可现在定）；
- 梳理"浅层验证"兜底方案：若 B 类接口最终不提供，verify_sketch 退化为"读回已建图元坐标 + 约束值，比对 Spec 落实度 + 零长线/重合点检测"，仍能挡住大部分明显错误。

---

### 5.2 实现状态（2026-07-21，API 已冻结）

内核 API 文档冻结后，已解除 §5.1 阻塞并实现 **P0 转译器 + P1 浅层验证闭环**，代码落于 `backend/app/sketch/`：

| 模块 | 文件 | 说明 |
|------|------|------|
| API 目录（单一事实源） | `app/sketch/api_catalog.py` | 冻结的 13 几何 + 12 约束 API 名、约束目标类型、保留字 |
| 结构化规格 | `app/sketch/spec.py` | `SketchSpec` pydantic 模型（判别联合），schema 即校验 |
| 确定性转译器 | `app/sketch/transpiler.py` | `transpile(spec)` → NCTI Python，变量名取自 `id` |
| 验证器 | `app/sketch/verify.py` | `verify_spec`（浅层：重复/保留字、退化几何、悬空引用、类型不匹配、缺值）+ `verify_kernel`（深验钩子，`run_solver` 抛错时降级为 skipped） |
| 内核深验接缝 | `app/sketch/kernel.py` | `KernelRuntime` 协议 + `make_ncti_run_solver(rt, *, dcm_system, status_nodes)`（exec 脚本→读真实 DCM 接口 `dcm_constraint_balance`/`dcm_status`/`dcm3_*`）+ `set_kernel_runtime`/`get_kernel_runtime` 注册表 |
| 闭环编排 | `app/sketch/pipeline.py` | `SketchPipeline.run`：转译→验证→有界自动修复（仅悬空引用约束可安全剔除）→重试；**始终**调 `verify_kernel` 填充 `kernel` 字段 |
| Skill 工具封装 | `app/sketch/tools.py` | 三个 LangChain 工具：`transpile_sketch` / `verify_sketch` / `run_sketch_pipeline`（Spec JSON → 结构化结果），`run_sketch_pipeline` 的 `kernel` 字段已接入深验；注册于 `config.yaml` 的 `tools` 段 |
| 测试 | `tests/test_sketch_pipeline.py` | 9 个用例全过；`python -m app.sketch.demo` 演示 4 场景 |

> **Skill 接线（2026-07-21）**：转译器/验证器已封装为 Skill 工具并接入 harness——`config.yaml` 的 `tools` 段新增 `transpile_sketch`/`verify_sketch`/`run_sketch_pipeline`（`use: app.sketch.tools:*`），`skills/custom/sketch/SKILL.md` 的 `allowed-tools` 白名单同步加入这三个工具，工作流改为「LLM 产出 SketchSpec(JSON) → 调 `run_sketch_pipeline`（或 `transpile_sketch`+`verify_sketch`）→ 按 `report.issues` 修补重试（≤3 轮）」。注意 `tool_policy` 按 `allowed-tools` 过滤全局工具，故 SKILL.md 必须同时列出 write_file/read_file/bash/present_files/ask_clarification 等所需工具。
> **深验接缝已接通（2026-07-21）**：`run_sketch_pipeline` 的 `kernel` 字段现已接入 `verify_kernel` 深验——无内核运行时返回 `{"skipped": true, "reason": "..."}`（修复了此前返回 `null` 的不一致）。**但 option (c) 探针（2026-07-21）证明：独立的 `ncti_python` 绑定（`ncti_python312.pyd`，license `dcubed.lic`/`gmde.lic` 在位，`Init(KERNEL_DIR)` 返回 1）虽暴露完整 DCM 接口，却无法 headless 执行——`doc.RunCommand(...)` 是 no-op（`AllNames()` 前后均 `None`），`doc.ActivateDoc()` 会挂起等待宿主应用的文档管理器/消息循环；`YH`/`SketchWorkPlane` 也不可独立 import。** 因此真实深验的真正阻塞项是"缺宿主 NCTI 应用的执行环境"，而非"接口未找到"。接缝仍保留 `set_kernel_runtime` 作为正确集成点——但注册的运行时必须能在**宿主应用内**（脚本宿主/批处理/自动化 API）执行转译脚本，而非裸 `Document()`。宿主应用就绪前，`kernel` 字段维持 `skipped`。详见 §5.3。

### 5.3 内核探针结论（option (c)，2026-07-21）

**目标**：一锤定音确认 ① `YH` 是否可独立 import；② 草图 `RunSolve` 后如何拿到 DCM 系统名，使 `run_sketch_pipeline` 能接真实 DOF/冲突深验。

**环境**：后端 venv Python `3.12.13`，恰好匹配 `D:\软件\biaozhuruanjian\ncti_python312.pyd`；license `dcubed.lic`/`gmde.lic` 均在该目录。

**实测结果**（探针 `backend/app/sketch/_probe_c*.py`，已清理）：

| 检查项 | 结果 |
|--------|------|
| `import ncti_python` / `Init(KERNEL_DIR)` | ✅ 成功（加载 `ncti_python312.pyd`，`Init` 返回 1，license 找到） |
| 暴露的 API 表面 | ✅ 完整：`Document`/`Point`/`Vector`/`AiFunction` + 全套 `dcm_*` 与 `dcm3_*`（含 `dcm_constraint_balance`/`dcm_status`/`dcm3_overdefined_status`/`dcm3_underdefined_dof`/`dcm3_get_overdefined_constraints`） |
| `doc.RunCommand("cmd_ncti_create_*", ...)` | ❌ **no-op**，返回 `None`；`doc.AllNames()` 执行前后均为 `None`（图元未创建、约束引擎未跑） |
| `doc.dcm_constraint_balance` / `doc.dcm_status` | ❌ 返回 `None`（因上面没真正求解） |
| `doc.ActivateDoc()` | ❌ **挂起**（阻塞等待宿主应用的文档管理器/消息循环） |
| `import YH` / `YH.SketchWorkPlane` | ❌ 独立模块**不可导入**（仅 `Document`/`Point`/`Vector`/`AiFunction`） |

**结论（一锤定音）**：

1. **`YH` 不可独立 import** —— 转译器发的 `YH.SketchWorkPlane`/`skt.AddLine`/`skt.RunSolve` OOP 风格**只能在完整 NCTI 应用的脚本宿主内运行**，独立后端进程里跑不起来。
2. **DCM 读回接口已确认真实存在且名称已校准**（`dcm_constraint_balance`/`dcm_status`/`dcm3_*`），但**无法在后端 headless 执行**——独立的 `ncti_python` 绑定只是"接口暴露壳"，命令分发器、文档管理器、消息循环都由**宿主 NCTI 应用**提供。
3. 因此 `run_sketch_pipeline` 当前**无法**获得真实 DOF/冲突深验；`kernel` 字段维持 `skipped` 是正确行为，不是 bug。

**通往真实深验的两条路径（需宿主应用，超出本次探针范围）**：

- **路径 A（推荐先问内核团队）**：内核是否提供**无 GUI 的 headless 引擎入口**（注册命令表 + 文档管理器、无需消息循环）。若有，`set_kernel_runtime` 注册的运行时即可在后端直接 exec 转译脚本并读 DCM 状态——我们已写好的 `kernel.py` 接缝**零改动即可激活**。
- **路径 B（应用内脚本宿主）**：后端经 NCTI 应用的脚本宿主/批处理/自动化（COM/CLI）接口喂入转译脚本、取回求解状态。需内核团队给出"外部触发脚本执行 + 读取结果"的接口。

**对当前代码的影响**：`backend/app/sketch/kernel.py` 的 docstring 已据上述结论改写（休眠原因从"运行时未注册"纠正为"独立绑定需宿主应用"）；`transpiler.py` 维持 OOP 风格（与用户手册冻结 API 一致，且宿主应用内可用）；`SKILL.md` 已新增「渲染与确认（部署边界）」小节，明确工作流收尾为「脚本外送 → 人工在 NCTI 软件内渲染确认」。

### 5.4 已确定的 MVP 边界（2026-07-22，用户确认）

> **部署架构（用户口述，根因）**：AI 生成的草图脚本需**复制到团队另外的内核软件里才能渲染**。因此独立 `ncti_python` 绑定无法 headless 执行是**架构使然**，不是临时坑。

据此把当前产品边界**明确写死**为：

- **Agent 侧 = 浅层静态验证**：`verify_sketch` / `run_sketch_pipeline` 的 `report.issues` 只查退化几何 / 悬空引用 / 类型不匹配 / 缺值；不保证几何完全可解。
- **`kernel` 字段恒为 `{"skipped": true, ...}`**：这是**预期行为，非 bug**。不要尝试在后端跑求解器或读 DOF/冲突。
- **最终确认 = 人工在 NCTI 软件内渲染**：过/欠约束、能否渲染由人工在软件里确认；报错贴回后 Agent 据 `report.issues` 语义对应修补 Spec 重生成。

**真实深验（DOF/冲突读回）仍为「待解锁」能力**，解锁条件只有一条：内核团队提供**无 GUI 的 headless 引擎入口**（§5.3 路径 A）。一旦提供，`set_kernel_runtime` 接缝零改动激活，MVP 边界即可升级为「浅层 + 内核深验」双保险。在此之前，按上述边界交付即可。

## 6. 度量指标

| 层 | 指标 |
|----|------|
| 转译 | Spec→脚本 一次通过率（语法/API 错误率） |
| 验证 | **MVP 阶段为人工确认率**：人工在 NCTI 软件内渲染一次通过率（浅层静态验证只能兜底退化/悬空引用，几何可解性由人确认）；headless 引擎入口（§5.4）就绪后可升级为「过求解器一次通过率 pass@1」 |
| 识别（若做） | 图元 F1 / 约束 F1（参考 Sketch2CAD） |
| 业务 | 端到端任务成功率、人工返工率 |

---

## 7. 参考链接

- CADSmith: https://arxiv.org/abs/2603.26512 （多智能体 + 程序化几何验证 + 双循环，RAG 非微调）
- Draw2Think: https://draw2think.github.io/ （Constraint-Agentic Harness，Typed ToolSpecs，每动作验证）
- CADDesigner: https://562590763.github.io/CADDesigner/ （ReAct + ECIP 显式上下文 + 知识库）
- cad-agents-platform: https://github.com/Juanespape/cad-agents-platform （LangGraph 编排 + 每平台验证 + 人在回路）
- CAD-Coder (2025): 微调 VLM 出 CAD 代码（识别微调先例）
- Sketch2CAD: https://github.com/Enigma-li/Sketch2CAD （手绘草图→可编辑 CAD）
- DeepCAD: https://github.com/ChrisWu1997/DeepCAD （178k CAD 构造序列数据集，合成数据）
- CQAsk: https://github.com/OpenOrion/CQAsk （LLM CAD 生成，CadQuery）
- llmcad: https://llmcad.org/ （LLM 友好的 CAD 库，OpenCASCADE 封装）
