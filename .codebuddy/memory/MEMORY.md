# 长期记忆（跨会话稳定事实）

## 用户协作偏好
- **每次代码修改都必须记到 memory**：用户要求每次改动（含 bug 修复）都追加到当天日志 `YYYY-MM-DD.md`，以便换 agent 时也能通过记忆恢复上下文。
- 沟通语言：中文（简体）。

## 项目：YHCADLabeller-platfrom（炎核几何特征标注工具）
- 技术栈：wxPython（AUI 布局）、OCC/Kernel 3D 查看器、matplotlib 训练曲线。
- 主窗口 `ui/main_window.py` 的 `CAEPlatform` 是唯一状态栏出口 `self.status_bar`，所有面板/function 的报错都经 `self.main_window.status_bar.SetStatusText(...)`。
- 状态栏已改为 `LoggingStatusBar` 子类：命中报错关键字时额外 `print(..., file=sys.stderr)`（前缀 `[状态栏报错]`），方便在终端看一闪而过的错误。
- 训练页（tab index=3）中央区为内嵌 `TrainDashboardPanel`（曲线+日志），非弹窗；切到训练 tab 时隐藏 `cad_view`(STP 查看器)。tab 顺序：文件(0)/选择显示(1)/标注(2)/训练(3)/识别(4)。

## 项目：NTIC-CAX-Agent（DeerFlow 二次开发的 CAX AI Agent 平台）
- 同构集成先例 `backend/app/sketch/`：把 NCTI 内核能力封成确定性 `@tool`（transpile_sketch/verify_sketch/run_sketch_pipeline），在 `config.yaml` 的 `tools:` 注册，KernelRuntime 桥（`app/sketch/kernel.py` 的 `set_kernel_runtime`）。
- **NCTI 内核无头限制（关键，2026-07-23 修正）**：独立 `ncti_python` 绑定暴露完整 API，但**必须做 DLL 降级加载**——只加载 `ncti_command/occ_plugin/doc_occ`（geom 级），跳过 `ncti_window.dll`/`ncti_render_vulkan.dll`，否则纯无头挂起。实测结论（wygcleaner Python 3.11 + geom DLL）：
  - ✅ **可用（无头真实生效）**：`doc.New("OCC","DCM",0)` + `RunCommand("cmd_ncti_import_file",path,name)` 导入；`FindAllFaces`/`FindFillets`/`SelectionManager` 识别；`RunCommand("cmd_ncti_remove_features",obj,[cell_id])` 清理（圆角被真删，面数下降）；`RunCommand("cmd_ncti_export_file",path,obj)` 导出。即 **YHCADSmartCleaner 识别/清理走架构 A（无头独立进程直跑），无需宿主 NCTI 应用**。
  - ❌ **不可用**：`doc.Open(stp)` 无头**挂起**（必须用 New+RunCommand 导入替代）；草图求解类命令 / 依赖宿主文档管理器消息循环的 API 仍受限（`app/sketch/kernel.py` 的 `kernel` 字段仍 `skipped`）。
  - 调用 RunCommand 的**铁律**：每次命令前 `doc.ResetCaseResult()`；返回值可能是 PyCapsule 需强转 bool；进程末尾 `os._exit(0)` 规避 NCTI 拆卸段错误（0xC0000005）。
- 自定义子 Agent 在 `config.yaml` 的 `subagents.custom_agents:` 声明，主 Agent 经 `task` 工具委派。
- 集成 CAX 能力时：后端环境（可能 Linux/Docker）与 NCTI 原生环境（Windows + DLL + torch/dgl）隔离，必须进程外调用。
- YHCADSmartCleaner 识别/清理集成计划：`NTIC-CAX-Agent/docs/cad-feature-cleaner-integration-plan.md`（先跑 Phase 0 可行性 spike 决定架构 A/B）。
- **cad_feature 代码已自包含于 NTIC-CAX-Agent（2026-07-23 迁移）**：识别/清理 CLI 在 `backend/app/cad_feature/cli/`（`recognition_cli.py` + `recognition_core.py`，几何识别核心已内化，**实际第三方依赖仅 numpy + scikit-learn**，scipy 未被 import），**不再 import YHCADSmartCleaner**，可独立仓库部署。依赖清单见 `backend/app/cad_feature/cli/requirements.txt`（仅装在 wygcleaner 子进程环境，**不写进主 backend/pyproject.toml** 以维持隔离）。NCTI SDK 路径经 `NCTI_SDK_PATH` / `--sdk` 注入（`kernel.CadFeatureConfig.sdk_path` → runner 透传子进程 env `NCTI_SDK_PATH`）。旧脚本 `YHCADSmartCleaner/recognition_cli.py` 与 `spike_headless.py` 已删除。
- **前后端启动（本机实测，2026-07-23）**：本机**没有 `make`、没有 git-bash 的 `bash.exe`、没有 `lsof`**，所以 `make dev` / `scripts/serve.sh`（bash 脚本强依赖 lsof/pgrep/nginx）跑不了。手动分进程后台启动（PowerShell `Start-Process cmd -WindowStyle Hidden`）：后端 `cd backend && set PYTHONPATH=. && uv run uvicorn app.gateway.app:app --host 0.0.0.0 --port 8001`（日志 `logs/gateway.log`）；前端 `cd frontend && pnpm run dev`（日志 `logs/frontend.log`，Next.js 16 监听 3000）。**跳过 nginx（2026 反代）**。依赖已就绪（`.venv` / `node_modules` / `.env` / `uv.lock` 均在）。`/api/*` 需登录鉴权（better-auth，401＝未登录，非故障）。后端启动警告 `No 'checkpointer' section` → InMemoryStore（重启丢线程历史），非致命。**集成代码已全部完成（2026-07-23）**：M0 可行性 + M1 CLI（实测通过）+ M2 后端工具层 + M3 子 Agent 注册 + M4 单测（`backend/tests/test_cad_feature.py` 16 用例全绿）。剩余仅端到端联调（`make dev` + 前端上传 STP）。
- **recognition_cli.py（M1）关键约束**：① `load_ncti_geom()` 解析 `system_config.json` 的 `dllPath` 相对路径时，基准必须是 `config/` 目录（与 `config_load.py` 一致），不能是 `recognition_cli.py` 所在目录，否则 `../SDK` 错解；② 默认 `method=ai` 走内核 `doc.FindFillets`（最准，spike 验证），`method=geometry` 走逐面采样法作 fallback（会漏检）；③ **clean 导入名必须与 recognition 一致**——从 `recognition_json` 的 `features[0].object_name` 取导入名，否则 `cmd_ncti_remove_features` 报 "variable name does not exist"；④ clean 删多个圆角时部分会报 `geometry function error`（删除顺序的拓扑依赖，NCTI 特性可接受）。

## 工具/环境提示
- 搜索工具 `search_content` 的 `path` 参数在本工作区偶尔失效（会搜到同级仓库 YHCADLabeller-web / YHDataConverter 等）。排查本工程代码时优先用 `read_file` 直接读目标文件，或确认返回结果所属工程。
- 训练管线在独立 conda 环境 `yhcad_env` 运行（装 dgl/torch），GUI 在另环境运行。
- 合并同事代码后需检查 `YHCADLabeller-platfrom/config/system_config.json`：同事（用户名 12290）的个人路径（如 `C:\Users\12290\...`）可能覆盖 `dllPath`(NCTI SDK路径)/`trainEnvPython`(训练conda python)，需改回本机路径。2026-07-22 已发生一次：dllPath 被改成 `C:\Users\12290\AppData\Local\Programs\YHPreCAE`，已改回 `D:/软件/biaozhuruanjian`。
