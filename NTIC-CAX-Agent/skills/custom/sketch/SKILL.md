---
name: sketch
description: >
  Trigger: user requests any sketch modeling operation — create/open/close sketch,
  draw geometry (point, line, centerline, spline, rect, circle, arc, ellipse,
  ellipse arc, fillet, chamfer, trim, offset), add constraints, edit constraints,
  control constraint display/property, or any multi-step sketch workflow.
  Load this skill. You emit a structured SketchSpec (JSON); deterministic tools
  transpile it to NCTI Python and verify it — you never hand-write kernel API calls.
allowed-tools:
  - transpile_sketch
  - verify_sketch
  - run_sketch_pipeline
  - write_file
  - read_file
  - str_replace
  - view_image
  - task
  - bash
  - present_files
  - ask_clarification
---

# NCTI 草图建模（结构化转译 + 验证闭环）

## 核心思想

你**不再手写 NCTI Python**。你负责理解意图、产出**结构化草图规格 `SketchSpec`（JSON）**，
由确定性工具完成内核代码生成与正确性验证：

- `transpile_sketch` — Spec → NCTI Python（确定性，零语法/API/命名错误）
- `verify_sketch` — Spec 浅层静态验证（退化几何 / 悬空引用 / 类型不匹配 / 缺值）
- `run_sketch_pipeline` — 验证 → 转译 → 有界自动修复闭环（**优先用**）

> 设计依据：`docs/sketch-transpile-verify-design.md`（对标 CADSmith 双循环 + Draw2Think 每动作验证）。
> 内核 API 由 `transpiler` 按冻结的 `api_catalog` 机械映射，你无需记忆 `YH.SketchWorkPlane` 签名。

## 渲染与确认（部署边界 · 重要）

生成的 NCTI Python 脚本**不会在 Agent 后端直接求解/渲染**——它由人工**复制到团队的 NCTI 内核软件里执行并渲染**。因此：

- Agent 侧只做 **浅层静态验证**（`verify_sketch` / `run_sketch_pipeline` 的 `report.issues`），不保证几何完全可解。
- `run_sketch_pipeline` 返回的 `kernel` 字段恒为 `{"skipped": true, ...}`——这是**预期行为**（独立 `ncti_python` 绑定无法 headless 执行，且本架构就是「脚本外送渲染」），**不是 bug**，不要尝试在此环境跑求解器。
- 最终的「是否过/欠约束、能否渲染」由**人工在 NCTI 软件内确认**。若软件报约束冲突/退化几何，把报错贴回，你据 `report.issues` 的语义对应修补 Spec 后重新生成。

## 工作流

### A. 标准闭环（推荐，默认走这条）

1. **理解意图**，规划图元与约束，给每个图元分配稳定 `id`（变量名，避开保留字 `doc/skt/yh_doc/YH/NCTI`）。
2. **组装 `SketchSpec` JSON**（字段见下方「Spec 字段」）。
3. 调用 `run_sketch_pipeline(spec_json)`。
4. **解析返回**：
   - `ok: true` → 取 `script`（确定性 NCTI Python），用 `write_file` 写入 `/mnt/user-data/outputs/sketch.py`，再 `present_files` 呈现。**该脚本供人工复制到 NCTI 软件内渲染确认**（见「渲染与确认」）。
   - `ok: false` → 读 `report.issues`，按 `code` 修补 Spec（`DANGLING_REF` 补图元 / `DEGENERATE` 修退化几何 / `TYPE_MISMATCH` 换约束类型 / `MISSING_VALUE` 补尺寸），重新调用（**≤3 轮**）。
5. 若多轮仍 `unfixable`（几何/数值冲突），用 `ask_clarification` 向用户澄清模糊或冲突需求，不要瞎猜。

### B. 分步转译 + 验证（需精细控制时）

1. `verify_sketch(spec_json)` 先验证，拿到 `issues` 提前修；
2. `transpile_sketch(spec_json)` 生成脚本；
3. 同 A.4 落盘 / 呈现。

### C. 修改已有脚本

优先改 **Spec** 而非脚本：读取旧 Spec（或旧脚本反推），用 `str_replace` 改 Spec JSON，再走 A。
若只能改脚本，用 `str_replace` 精准修改（old_string 精确匹配），**不要整体用 `write_file` 重写**——避免丢失已有代码。

## Spec 字段

```json
{
  "plane": "XY",            // 可选: "XY" | "XZ" | "YZ"，默认 "XY"
  "auto_solve": true,       // 可选，默认 true
  "primitives": [ { "id": "l1", "type": "line", "start": [0,0,0], "end": [50,0,0] } ],
  "constraints": [ { "type": "length", "target": "l1", "value": 50.0 } ]
}
```

**几何 primitive.type（13 种）与必填参数：**

| type | 必填字段 |
|------|----------|
| point | `at:[x,y,z]` |
| line | `start:[x,y,z]`, `end:[x,y,z]` |
| centerline | `start`, `end` |
| spline | `points:[[x,y,z],...]` |
| rect | `start`, `end` |
| circle | `center:[x,y,z]`, `radius:>0` |
| arc | 三选一：`start,end,point_on_arc` 或 `radius:>0,start_angle,end_angle,center` |
| ellipse | `center`, `major:[x,y,z]`, `minor:[x,y,z]` |
| ellipse_arc | `center`, `major`, `minor`, `start_angle`, `end_angle` |
| fillet | `radius:>0`, `line_a`, `line_b`（须为 line 的 id） |
| chamfer | `dist_a:>0`, `line_a`, `dist_b:>0`, `line_b` |
| trim | `at:[x,y,z]`, `objects?:[id,...]` |
| offset | `objects:[id,...]`, `distance` |

**约束 constraint.type（12 种）与必填字段：**

| type | 目标 | 必填 |
|------|------|------|
| length / angle / xpos / ypos | 1–2 个图元 | `target`(+`target2`) + `value` |
| radius | circle / arc | `target` + `value` |
| parallel / perpendicular / horizontal / vertical | line | `target`(+`target2`) |
| tangent / equal / coincide | 任意 | `target`(+`target2`) |

> 注：API 名与语义——`horizontal`=`AddConsXAxis`、`vertical`=`AddConsYAxis`、`perpendicular`=`AddConsVertical`（API 名 Vertical，语义垂直）。`id` 提供稳定引用，解决"左边那个孔"类指代。

## 参考目录

以下参考文件提供内核 API 细节（你一般无需直接调用，转译器已封装）。需要细节时用 `read_file` 读取：

- `skills/custom/sketch/references/case-init.md` — 草图初始化与文档管理
- `skills/custom/sketch/references/case-basic-geometry.md` — 基本几何绘制
- `skills/custom/sketch/references/case-constraint.md` — 约束创建与显示属性
- `skills/custom/sketch/references/case-edit-constraint.md` — 约束编辑与查询
