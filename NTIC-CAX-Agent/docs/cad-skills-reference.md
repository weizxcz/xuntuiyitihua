# CAD 相关高星 Skill 仓库参考清单

> 用途：为本项目 `skills/custom/sketch/SKILL.md` 的后续升级（规格化转译 + 求解验证）提供业界 skill 写法与验证清单范本。
> 调研时间：2026-07-20
> 重要前提：以下仓库**均不使用 NCTI 内核**，借鉴的是"skill 怎么组织、怎么写验证/检查、怎么参数化"的方法论，不是代码本身。

---

## 1. 仓库清单（按 Star 高 → 低）

| 仓库 | Star | 格式 | CAD 后端 | 核心 skill | 对咱们 sketch skill 的借鉴点 |
|------|------|------|----------|-----------|------------------------------|
| **earthtojake/text-to-cad** | ⭐ 8.4k | SKILL.md（三级渐进加载） | build123d / OpenCascade（开源） | `CAD`(自然语言→STEP)、`CAD Viewer`、`DXF`、`step.parts`(标准件库)、`G-code`、`URDF` 等 11 个 | **最值得看**。它的 `CAD` skill 就是"自然语言→模型→本地求解→预览"闭环，和我们的"转译+验证"思路同构；`CAD Viewer` 验证了"渲染回灌视觉核对"可行 |
| **Soljourner/claude-engineering-skills** | ⭐ 37 | SKILL.md（三级加载） | SolidWorks / ANSYS / COMSOL / OpenFOAM | `solidworks-cad`(参数化泵设计)、`ansys-simulation`、`structural-analysis`、`material-properties-db` | **参数化设计**思路（泵设计用参数驱动）+ **材料/标准件数据库** skill，可借鉴到我们的"参数化驱动接口"和"长期记忆沉淀领域知识" |
| **delancy827/cad-skills** | ⭐ 16 | SKILL.md（834+466 行） | AutoCAD / 中望 / 浩辰（COM 接口） | `cad-automation`(写代码画图)、`cad-designer`(设计方法论) | **`cad-designer` 最有价值**：内含"国标制图规范(GB/T)、设计检查清单、图纸审查"——这正是我们 `verify_sketch` 缺的"验证该查什么"的范本 |
| **anthropics/skills**（官方规范库） | 高星（需核实） | SKILL.md 标准 | 通用 | 17 个示例 skill | 不是 CAD 专用，但它是 **SKILL.md 写法的权威参考**——我们写 sketch skill 应照它的 frontmatter/渐进披露规范 |

> 补充：`cadskills.xyz` 是 `earthtojake/text-to-cad` 的官网，确认 100% 开源、本地运行、支持 Claude Code / Codex。

---

## 2. 各仓库详情

### 2.1 earthtojake/text-to-cad（⭐ 8.4k）
- **定位**：面向 CAD / 机器人 / 硬件设计的 agent skills 库，最新版本 0.3.9（2026-07-10），962 forks。
- **11 个 skill**：
  - `CAD`：从自然语言或图像创建/编辑 CAD 模型，主输出 STEP，可选 STL/3MF/GLB。
  - `CAD Viewer`：本地浏览器预览 CAD、G-code、机器人文件。
  - `step.parts`：查找现成离线 STEP 标准件（螺丝、轴承、电机、连接器）。
  - `DXF`：从 Python 源或 CAD 几何创建 2D DXF 图纸。
  - `URDF` / `SRDF` / `SDF`：机器人结构/规划/仿真文件。
  - `SendCutSend`：上传加工服务前检查 DXF/STEP。
  - `G-code`：网格切片为校验过的 FDM `.gcode`（真实切片器 CLI）。
  - `Bambu Labs`：本地打印任务管理。
  - `Implicit CAD`：GLSL SDF 浏览器原生隐式 CAD（实验性）。
- **CAD 后端**：build123d（基于 OpenCascade，与 CadQuery 同源）。
- **可本地运行**：`npx skills install earthtojake/text-to-cad` 或 Codex/Claude Code 插件安装。
- **借鉴**：`CAD` skill 的"生成→本地求解→预览"闭环结构；`CAD Viewer` 的"渲染回灌视觉核对"验证方式。

### 2.2 Soljourner/claude-engineering-skills（⭐ 37）
- **定位**：100+ 工程技能，MIT 许可，分 Databases / Packages / Integrations / Helpers / Thinking 五类。
- **CAD/机械/航天相关**：
  - `solidworks-cad`：参数化泵设计自动化（需商业许可，Python/API 脚本指导）。
  - `ansys-simulation` / `openfoam-cfd` / `comsol-multiphysics`：仿真自动化。
  - `structural-analysis`、`pump-design`、`material-properties-db` 等。
- **SKILL.md 三级加载**：L1 自动识别名称→L2 加载完整 SKILL.md→L3 按需加载参考/代码。
- **借鉴**：参数化设计驱动模型；材料/标准件数据库 skill（对应我们的长期记忆沉淀领域知识）。

### 2.3 delancy827/cad-skills（⭐ 16）
- **定位**：让 AI Agent 学会用 AutoCAD（含中望/浩辰国产 CAD，COM 接口），MIT 许可。
- **两个 skill**：
  - `cad-automation/SKILL.md`（834 行）：Python pyautocad/win32com 连接、绘图/编辑/图层/标注/块、AutoLISP、三维建模、批量处理、国产 CAD 兼容。
  - `cad-designer/SKILL.md`（466 行）：**国标制图规范(GB/T)、图层管理、标注标准与公差、块设计规范、模板系统(DWT)、打印出图、性能优化、设计检查清单**。
- **借鉴**：`cad-designer` 的"设计检查清单 / 图纸审查"是 `verify_sketch` 缺的"验证该查什么"范本——可照其思路把"过约束/欠约束/退化几何/国标"列成检查项。

### 2.4 anthropics/skills（官方规范库）
- **定位**：Anthropic 官方 Agent Skills 标准仓库，SKILL.md 写法的权威参考（17 个示例 skill）。
- **借鉴**：写 sketch skill 时遵循其 frontmatter（name/description/allowed-tools）+ 渐进披露（SKILL.md 仅概述，细节放 references/）规范。

---

## 3. 三个最该借鉴的点（落到本项目）

1. **earthtojake 的 CAD skill 闭环结构** → 对标"SketchSpec → 转译 → verify → 预览"。其 `CAD Viewer` 证明"渲染成图回灌模型做视觉核对"可行（补上我们之前想做但没做的视觉自校验）。
2. **delancy827 的 `cad-designer` 检查清单** → 把"图纸对不对"拆成 GB/T 规范、图层、尺寸链封闭性等可勾选项；我们 `verify_sketch` 可照此把"过约束/欠约束/退化几何/国标"列成检查项。
3. **Soljourner 的参数化 + 数据库 skill** → `solidworks-cad` 用参数驱动模型、`material-properties-db` 沉淀领域知识，对应我们的"参数化驱动接口"和"长期记忆存材料库/公司标准"。

---

## 4. 提醒（避免踩坑）

- **没有一个是 NCTI 内核**，拉下来接不上 `YH.SketchWorkPlane`，别指望直接复用代码。
- 这些 skill 的验证都依赖各自 CAD 内核 API（build123d / SolidWorks API），我们的验证卡在"内核 API 文档未冻结"（见 `sketch-transpile-verify-design.md` §5.1 阻塞项）——现在只能学**写法**，不能学**验证实现**。
- `delancy827` / `Soljourner` 的 skill 是给通用 Claude/Codex 用的 SKILL.md，格式与 DeerFlow 的 `SKILL.md`（frontmatter + 工作流）基本兼容，可参考结构。

---

## 5. 参考链接

- earthtojake/text-to-cad: https://github.com/earthtojake/text-to-cad （官网 https://www.cadskills.xyz/）
- Soljourner/claude-engineering-skills: https://github.com/Soljourner/claude-engineering-skills
- delancy827/cad-skills: https://github.com/delancy827/cad-skills
- anthropics/skills（官方规范）: https://github.com/anthropics/skills
