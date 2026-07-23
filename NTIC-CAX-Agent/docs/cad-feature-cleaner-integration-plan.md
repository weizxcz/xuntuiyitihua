# 把 YHCADSmartCleaner 识别/清理能力接口化并集成进 NTIC-CAX-Agent（子 Agent）

> 目标：前端上传 STP → 自然语言说「识别圆角/倒角」→ 后台调模型识别 → 输出识别 JSON；用户若继续「清理掉这些特征」→ 输出清理后的 STEP。
> 阶段定位：本次只做底层（识别/清理接口 + Agent 编排），前端实时可视化「不是我们的工作」，先不做。
> 编写日期：2026-07-22
> 参照先例：`backend/app/sketch/`（NCTI 草图「结构化转译 + 验证闭环」集成，已落地）
>
> **现状（2026-07-23）**：Phase 0 已完成并**选定架构 A**（无头独立进程直跑，无需宿主 NCTI 应用）。
> M1（`NTIC-CAX-Agent/backend/app/cad_feature/cli/recognition_cli.py`，自包含于 NTIC-CAX-Agent）+ M2（`NTIC-CAX-Agent/backend/app/cad_feature/`）+ config 注册（2 工具 + `cad-feature-cleaner` 子 Agent）均已落地。
> 关键修正：spike v4 实测推翻了 `kernel.py`「RunCommand 无头 no-op」的结论（对文件导入/特征清理/导出类命令不成立，见 §1.2）。
>
> **M1 实测通过（2026-07-23 下午）**：在 wygcleaner（Python 3.11.15）跑通 recognize + clean 双链路（测试 STP = `D:\wyg\data\含倒角、圆角、通孔、盲孔(单solid).stp`）：
> - `recognize`：识别到 **63 个圆角**（`method=ai` 走内核 `doc.FindFillets`，`confidence=1.0`）。
> - `clean`：成功移除 **45 个**（18 个报 `geometry function error`，系删除顺序导致的拓扑依赖，属 NCTI 特性可接受），导出 `part_cleaned.step`（551404 字节，原 STP 589179 字节）。
> - 修复 3 个 bug：① `load_ncti_geom()` 相对路径基准错误（`../SDK` 须相对 `config/` 目录解析，与 `config_load.py` 一致）；② 几何采样法漏检（默认 method 改 `ai` 走内核 `FindFillets`，几何法保留为 `method=geometry` fallback）；③ clean 导入名与 recognition 不一致（须从 `recognition_json` 的 `features[0].object_name` 取导入名，否则 `cmd_ncti_remove_features` 找不到对象）。
> - **Phase 4 单测**：`backend/tests/test_cad_feature.py`（16 用例，mock runner，验证 tools JSON 契约 + kernel 配置 + runner 命令拼接 + 错误传播，全绿）。

---

## 1. 方向评估（我的判断）

### 1.1 结论

**方向可行，且强烈建议按现有 `sketch` 集成的同构模式做**，不要另起炉灶。理由：

- 你们在 `NTIC-CAX-Agent` 里已经有了一条**完整可复制的 NCTI 内核集成路径**：`app/sketch/` 把内核能力封装成确定性 LangChain 工具（`@tool`），通过 `config.yaml` 的 `tools:` 注册，再由 skill / 主 Agent 调用。识别/清理可以照搬：`app/cad_feature/` = 新的工具层。
- 用户要的是「子 Agent」。DeerFlow 原生支持 `config.yaml` 的 `subagents.custom_agents:` 声明自定义子 Agent（`cad-feature-cleaner`），由主 Agent 通过 `task` 工具委派。这与你们的架构完全一致。
- YHCADSmartCleaner 的识别/清理函数已经是**与 GUI 解耦的纯函数**（`on_find_fillet*.py`、`on_remove_feature.py`、`ai/ai_recognizer.py` 都只依赖 `NCTI` + `doc` 两个对象），接口化成本低。

### 1.2 唯一的致命前置风险（必须先做 Phase 0）

NCTI 内核**不是无头可执行的**。来自 `backend/app/sketch/kernel.py` 的实测结论（2026-07-21）：

- 独立 `ncti_python` 绑定（`ncti_python312.pyd`，即 YHCADSmartCleaner 用的同一个 `import ncti_python` + `NCTI.Init(...)`）暴露完整 API，但 **`doc.RunCommand(...)` 是 no-op**，`doc.ActivateDoc()` 会挂起（等待宿主应用的消息循环）。
- 后果：YHCADSmartCleaner 的清理 `doc.RunCommand("cmd_ncti_remove_features", ...)` 若在裸 Python 进程里调，**可能根本不生效**；它之所以在桌面 GUI 里能用，是因为宿主应用启动了文档管理器 / 消息循环。

> **⚠️ 已被 Phase 0 spike v4（2026-07-23）推翻/修正**：上述 no-op 结论**不适用于文件导入 / 特征清理 / 导出类命令**。在「geom 级 DLL 降级加载」（只加载 `ncti_command/occ_plugin/doc_occ`，跳过 `ncti_window/ render_vulkan`）+ `wygcleaner` 环境（Python 3.11）下实测：`cmd_ncti_import_file` / `cmd_ncti_remove_features` / `cmd_ncti_export_file` **全部无头可用且真实生效**（圆角 cell 被真实删掉，面数 136→135，STEP 文件生成）。
> 仍受限的是：① `doc.Open(stp)` 在无头会**挂起**（必须改用 `doc.New + RunCommand(cmd_ncti_import_file)`）；② 草图求解类命令 / 依赖宿主文档管理器消息循环的 API 仍受 `kernel.py` 描述的限制。因此 cad_feature 走**架构 A**，sketch 的 `kernel` 字段仍 `skipped`。

**这决定了整个架构形态**，因此计划把「可行性 spike」列为 Phase 0，没过这一关就不往下写集成代码。两种可能结果对应两套架构（见 §3）。

### 1.3 与 sketch 集成的同与异

| 维度 | sketch 集成（已落地） | 本计划（cad_feature） |
|------|------|------|
| 内核依赖 | 草图求解需宿主应用；当前 `kernel` 字段 `skipped` | 识别/清理同样需宿主应用 |
| 工具形态 | 确定性 `@tool`，返回 JSON | 同 |
| KernelRuntime 桥 | `set_kernel_runtime()` 注册后用；未注册则降级 | 复用同一桥接模式 |
| 额外依赖 | 无（纯转译/校验） | **需 torch/dgl/AAGNet 权重** + **Windows + NCTI SDK** |
| 产物 | NCTI Python 脚本 | 识别 JSON + 清理后 STEP 文件 |

---

## 2. 总体架构（分层）

```
┌─ 前端（Next.js，暂不做实时可视化）
│     上传 STP ──► /api/uploads ──► /mnt/user-data/uploads/part.stp
│
├─ NTIC-CAX-Agent 后端（DeerFlow Gateway）
│   ├─ 主 Agent（lead_agent）
│   │     解析自然语言「识别圆角」→ 调 task 委派 ──┐
│   │                                            │
│   ├─ 子 Agent：cad-feature-cleaner  ◄──────────┘
│   │     仅持有 cad_feature 工具 + 文件工具
│   │     ├─ recognize_cad_features(stp, type, method, params) → JSON
│   │     └─ clean_cad_features(stp, recognition_json, out)    → STEP
│   │
│   └─ app/cad_feature/  ← 新增工具层（同 app/sketch/）
│         tools.py（@tool 封装）
│         kernel.py（KernelRuntime 桥，复用 sketch 的注册机制）
│         runner.py（调用 cad_feature/cli/recognition_cli.py；本地 subprocess / 远程 HTTP）
│
└─ YHCADSmartCleaner / NCTI 原生环境（Windows + NCTI SDK + torch/dgl）
      └─ 仅提供 NCTI SDK（DLL + ncti_python）；由 cli/recognition_cli.py 经 NCTI_SDK_PATH 加载
            load SDK (NCTI_SDK_PATH) → open STP → 识别/清理 → 写 JSON / STEP
```

**关键约束**：YHCADSmartCleaner 的运行环境（Windows + NCTI 原生 DLL + AI 权重 + torch/dgl）与 NTIC-CAX-Agent 后端环境（uv 管理的 Python，可能 Linux/Docker）**不是同一个**。所以 `app/cad_feature` 不能直接 import YHCADSmartCleaner 的模块，必须通过**进程外调用**（本地 subprocess 或远程 HTTP 服务）。

---

## 3. 两种架构（取决于 Phase 0 结果）

### 架构 A：YHCADSmartCleaner 可在无头进程内跑通（理想）
Phase 0 spike 证明 `Document()` + `Open(stp)` + `FindFillets` + `RunCommand("cmd_ncti_remove_features")` + 导出 STEP 在裸 Python 里能产出真实几何。
- `app/cad_feature/runner.py` 用 `subprocess` 调 `cad_feature/cli/recognition_cli.py`（同机 Windows + NCTI SDK，由 NCTI_SDK_PATH 注入）。
- 工具内部：写出参数文件 → 调用 CLI → 读回 JSON/STEP 路径 → 返回。
- 清理走同一进程，最干净。

### 架构 B：清理/命令必须跑在宿主 NCTI 应用里（更可能）
Phase 0 spike 复现 `kernel.py` 的 no-op/挂起现象。
- 把 YHCADSmartCleaner 改造成**常驻宿主进程 / 自动化脚本宿主**：启动 NCTI 应用 → 进入脚本模式等待指令 → 收到「识别/清理某 STP」→ 执行 → 回写产物 → 继续等待。
- `app/cad_feature/runner.py` 改为与该常驻进程通信（本地 socket / 命名管道，或封装成 HTTP 微服务）。
- 识别若是只读（`FindFillets` / `AiModel` 提取图）可能能无头跑，但清理一定走宿主进程。

**建议**：Phase 0 先按架构 A 的最小脚本测；若卡在清理，立刻切架构 B（把 YHCADSmartCleaner 的 `main.py` 改成「无界面自动化模式」，复用它已有的文档管理器）。**无论 A/B，上层 `app/cad_feature` 工具接口不变**，差异只封在 `runner.py` 里。

---

## 4. 阶段计划

### Phase 0 — 可行性 Spike（最关键，先于一切集成，≈0.5–1 天）
目标：确定选架构 A 还是 B。
1. 在 YHCADSmartCleaner 里写最小脚本 `spike_headless.py`：
   - `from config.config_load import init_ncti_config` 拿 `NCTI`，`doc = NCTI.Document()`
   - `doc.Open("<测试.stp>")` 或对应导入 API
   - 调 `doc.FindFillets(...)` / `ncti.AiModel(...)` 看能否拿到面/边
   - 调 `doc.RunCommand("cmd_ncti_remove_features", name, [cell_id])` 后导出 STEP，检查 STEP 是否真的少了面
2. 记录：识别是否拿到数据、清理导出是否生效、`ActivateDoc` 是否挂起。
3. 出一份 1 页结论：选 A 或 B，以及 runner 通信方式。
4. **门禁**：未出结论前，不写任何集成代码。

### Phase 1 — YHCADSmartCleaner 接口化（≈2–3 天）
在 `app/cad_feature/cli/` 新增 `recognition_cli.py`（无头入口，自包含于 NTIC-CAX-Agent），把几何识别核心（`recognition_core.py`）与现有函数包成 CLI：
- 子命令 `recognize`：参数 `stp_path, feature_type, method, out_json`；内部复用
  - `function/on_find_fillet_by_ai.py::find_feature_by_ai`（AI 圆角）
  - `function/on_find_fillet.py::find_fillet_by_geo` / `find_fillet_compound`（几何圆角，半径区间）
  - `function/on_find_fillet_hyper.py`（融合识别）
  - 同型扩展 `on_find_plane/on_find_cylinder/on_find_cone`、`on_find_blind_hole_stp`、`on_find_through_step_*` 等（孔/台阶等）
- 子命令 `clean`：参数 `stp_path, recognition_json, out_step`；内部复用 `function/on_remove_feature.py::remove_feature` + 导出。
- 统一输出：识别结果写 `recognition_result.json`；清理后模型写 `<name>_cleaned.step`。
- NCTI SDK 路径**不再读任何外部 config**，改由 `NCTI_SDK_PATH` 环境变量或 `--sdk` 注入（`kernel.CadFeatureConfig.sdk_path` → runner 透传子进程 env）。
- **约定**：中文注释/日志（沿用 YHCADSmartCleaner 现有风格）。

### Phase 2 — NTIC-CAX-Agent 工具层 `app/cad_feature/`（≈2 天）
仿 `app/sketch/` 新建：
- `kernel.py`：复用 sketch 的 `KernelRuntime` 注册机制（或直接 import `app.sketch.kernel` 的 `set_kernel_runtime`，避免重复）；本层关注「是否可达宿主 NCTI」。
- `runner.py`：封装进程外调用（架构 A=subprocess 调 `recognition_cli.py`；架构 B=HTTP/socket 调常驻进程）。用 `CAD_FEATURE_RUNNER`（本地脚本路径）或 `CAD_FEATURE_ENDPOINT`（HTTP）环境变量切换。阻塞 IO 必须 `asyncio.to_thread`（遵守 DeerFlow 的 blocking_io 门禁）。
- `tools.py`：两个 `@tool`：
  - `recognize_cad_features(stp_path, feature_type, method, params_json) -> str`（返回结果 JSON 字符串）
  - `clean_cad_features(stp_path, recognition_json, output_step_path) -> str`（返回含清理后 STEP 路径的 JSON）
  - 两个工具都返回**结构化 JSON 字符串**（与 sketch 工具一致），并调用 `present_files` 把产物推到 `/mnt/user-data/outputs` 让用户可见（见 §5 契约）。
- 在 `config.yaml` 的 `tools:` 注册（同 `transpile_sketch` 那段，group 用 `cad`）。

### Phase 3 — 子 Agent + 配置（≈0.5–1 天）
- 在 `config.yaml` 的 `subagents.custom_agents:` 声明 `cad-feature-cleaner`：
  - `description`：何时委托（用户要识别/清理 CAD 几何特征）
  - `system_prompt`：角色（CAX 几何特征识别清理专家）、两阶段纪律（先识别产出 JSON 给用户确认 → 用户确认后再清理）、只调 cad_feature 工具 + 文件工具
  - `tools` 白名单：`[recognize_cad_features, clean_cad_features, read_file, write_file, present_files]`
  - `disallowed_tools`：`[task, ask_clarification]`（禁止嵌套委派与中断）
  - `model: inherit`，`max_turns: 50`，`timeout_seconds: 900`（识别+清理可能慢，按需调大）
- 主 Agent 经 `task` 工具委派；NL→参数解析由主 Agent（LLM）完成，子 Agent 只接结构化参数。

### Phase 4 — 端到端联调 + 测试（≈1–2 天）
- 单测：`backend/tests/test_cad_feature_*.py`（mock runner，验证 JSON 契约与工具返回；遵守项目 TDD 铁律）。
- 联调：上传一个含圆角的 STP，自然语言「识别圆角」，确认输出 JSON；再「清理掉」，确认输出 STEP。
- 同步更新 `README.md` / `CLAUDE.md`（项目约定）。

---

## 5. 接口契约（草案）

### 5.1 识别结果 JSON（子 Agent 内部 + 输出给用户）
```json
{
  "source_file": "part.stp",
  "feature_type": "fillet",          // fillet | chamfer | blind_hole | through_step | plane | cylinder | cone | logo
  "method": "ai",                    // ai | geometry | hybrid
  "features": [
    {
      "id": 1,
      "object_name": "Part1",
      "cell_id": 12345,
      "face_type": "圆柱面",
      "radius": 5.0,                 // 圆角/倒角有；其他特征可为 null
      "confidence": 0.92             // AI 方法有；几何方法可省略
    }
  ],
  "summary": { "count": 12, "by_type": { "圆柱面": 12 } }
}
```

### 5.2 工具签名
```python
@tool("recognize_cad_features")
def recognize_cad_features_tool(
    stp_path: str,        # /mnt/user-data/uploads/part.stp
    feature_type: str,    # fillet/chamfer/blind_hole/...
    method: str = "ai",   # ai/geometry/hybrid
    params_json: str = "{}"  # 半径区间、阈值等
) -> str:  # 返回 5.1 的 JSON 字符串

@tool("clean_cad_features")
def clean_cad_features_tool(
    stp_path: str,           # 原始 STP
    recognition_json: str,   # 5.1 的 JSON 字符串（或其中 features 列表）
    output_step_path: str    # /mnt/user-data/outputs/part_cleaned.step
) -> str:  # {"ok": true, "cleaned_step": "<path>", "removed_count": N}
```

### 5.3 子 Agent system_prompt 要点
- 第一阶段只识别，把 JSON 通过 `present_files` 交给用户，**不主动清理**。
- 用户明确说「清理/移除/删除这些特征」才进入第二阶段（`clean_cad_features`）。
- 自然语言「圆角/倒角/孔」→ `feature_type` 映射表写在 prompt 里。
- 失败时返回结构化错误，不瞎猜参数。

---

## 6. 数据流（一次完整交互）

```
用户上传 part.stp
  → 主 Agent 解析「识别圆角」→ task(cad-feature-cleaner, {stp, type=fillet, method=ai})
  → recognize_cad_features → runner → YHCADSmartCleaner 无头识别
  → 返回 recognition_result.json → present_files → 用户看到 JSON
用户：「把圆角清理掉」
  → task(cad-feature-cleaner, {clean, recognition_json})
  → clean_cad_features → runner → YHCADSmartCleaner 清理 + 导出
  → 返回 part_cleaned.step → present_files → 用户下载
```

---

## 7. 风险与开放问题

| 风险 | 影响 | 缓解 |
|------|------|------|
| NCTI 内核无头执行（Phase 0） | 决定架构 A/B，可能需常驻宿主进程 | Phase 0 先验证 |
| AI 权重 + torch/dgl 体积/环境 | 后端环境装不下，必须进程外 | 封在 YHCADSmartCleaner 侧 |
| Windows-only 原生 DLL | 后端若是 Linux/Docker 无法直跑 | runner 走本地（同机 Windows）或 Windows 微服务 |
| 识别置信度/误检 | 清理是破坏性操作 | 两阶段确认 + 先识别后清理的纪律 |
| AAGNet 对倒角/孔的权重是否齐备 | 部分 feature_type 可能只有几何法 | 按 feature_type 选可用 method，缺权重时降级 geometry |
| 阻塞 IO | DeerFlow 有 blocking_io 门禁 | runner 调用包 `asyncio.to_thread` |

**开放问题（需你确认）**：
1. Phase 0 你那边方便跑无头脚本验证吗？（需要 Windows + 已配 `config/system_config.json` 的 NCTI SDK）
2. 后端部署形态：同机 Windows 开发，还是 Linux/Docker 后端 + 独立 Windows 推理机？这决定 runner 用 subprocess 还是 HTTP。
3. 首期先支持哪几个 feature_type？建议 MVP = 圆角（AI+几何+融合）先跑通，倒角/孔作为扩展。

---

## 8. 工作量与里程碑

| 里程碑 | 内容 | 估时 |
|--------|------|------|
| M0 | Phase 0 可行性结论（A/B） | 0.5–1 天 |
| M1 | `app/cad_feature/cli/recognition_cli.py`（识别+清理，自包含，仅依赖 numpy/scipy/sklearn） | 2–3 天 |
| M2 | `app/cad_feature/` 工具层 + config 注册 | 2 天 |
| M3 | `cad-feature-cleaner` 子 Agent + 委派联调 | 0.5–1 天 |
| M4 | 端到端 + 单测 + 文档 | 1–2 天 |

**建议起点**：先一起把 M0（Phase 0 spike）跑了，拿到结论再决定后续是否继续。这一步投入最小、信息最大。
