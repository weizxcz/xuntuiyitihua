# Skill 与用户手册 API 出入核对

> 核对对象：
> - **项目 Skill**：`skills/custom/sketch/`（SKILL.md + `references/case-init.md`、`case-basic-geometry.md`、`case-constraint.md`、`case-edit-constraint.md`）
> - **用户手册**：`固体发动机参数化建模软件-用户手册V1.0.docx`（草图模块 §3、特征建模 §4）
> - 核对时间：2026-07-21
> - 方法：逐 API 比对签名、重载、参数与可编辑性描述。

## 1. 结论概览

| 类别 | 结论 |
|------|------|
| 核心草图 API（SketchWorkPlane / YHDocument / 13 种基础几何 / 12 种约束 / 编辑方法） | ✅ 基本一致，可放心调用 |
| **Skill 缺失、手册有定义的 API** | ⚠️ 6 类几何/约束辅助 API + 整套特征建模 API 未收录 |
| **同一 API 的签名/重载出入** | ⚠️ 圆角 `CurveRadius`（已修正：统一 3 参半径版）、中心线 `AddCenterLine`（第 2 重载不同）、倒角 `CurveChamfer`（点定位重载按规则有意不收录） |
| **手册自身笔误** | ⚠️ 3 处（Y 轴/中心线类型写错、GetOrigin 段误写） |
| **Skill 内部路径错误** | ⚠️ SKILL.md 引用的 references 路径与实际目录名不符，会导致 agent 读取失败 |

---

## 2. 详细出入

### 2.1 Skill 缺失、但手册已定义的 API（建议补进 skill）

| API | 手册定义（docx 行号） | Skill 现状 | Agent 影响 |
|-----|----------------------|-----------|-----------|
| `skt.SetRefData(name, value)` | 设置约束答案 / 参考尺寸数值（L338） | 未收录 | Agent 无法写参考尺寸值 |
| `skt.GetRefData(name)` | 获取约束答案 / 参考尺寸数值（L347） | 未收录 | Agent 无法读参考尺寸值 |
| `skt.AddCenterRect(center, length, width)` | 中心矩形（L720/L722） | 未收录 | 缺"中心矩形"绘制能力 |
| `skt.AddParallelogram(p1, p2, p3)` | 平行四边形（L731/L733） | 未收录 | 缺"平行四边形"绘制能力 |
| `skt.RegularPolygon(center, radius, sides)` | 正多边形（L742） | 未收录 | 缺"正多边形"绘制能力 |
| `skt.Partition(pt)` / `skt.Partition(pt1, pt2)` | 分割对象（L751/L755/L761） | 未收录 | 缺"曲线分割"能力 |
| `skt.RemovePointCons(pt)` | 移除点约束（L770/L778） | 未收录 | 缺"解除重合约束"能力 |

> 以上 7 个 API 均为手册"创建基本对象"章节明确列出的草图 API，但 skill 的 `case-basic-geometry.md` 仅覆盖 13 种（点/直线/中心线/样条/矩形/圆/圆弧/椭圆/椭圆弧/圆角/倒角/修剪/偏移），**未包含中心矩形、平行四边形、正多边形、分割、移除点约束**，也**未包含参考尺寸数值的 Set/Get**。

### 2.2 同一 API 的签名 / 重载出入（重点）

#### ① 圆角 `CurveRadius` —— 已修正（原 Skill 文本与示例自相矛盾）

| 来源 | 内容 |
|------|------|
| 手册 定义1（L644） | `skt.CurveRadius(pt1, a1, pt2, a2)` —— **点定位，4 参** |
| 手册 定义2（L652） | `skt.CurveRadius(1, a3, a4)` —— **半径定位，3 参** |
| 手册 定义3（L656） | `skt.CurveRadius()` —— 无参 |
| Skill 文本（case-basic-geometry.md L383） | "定义（距离定位）：`CurveRadius(r, objLine1, objLine2)`" —— **3 参**，对应手册定义2 |
| Skill 示例（L400、L493） | `skt.CurveRadius(NCTI.Point(15,15,0), l1, NCTI.Point(0,15,0), l2)` —— **4 参**，对应手册定义1 |

**出入**：Skill 在"定义"处写的是 3 参半径版，但所有示例代码用的是 4 参点定位版，且未把两种重载分开说明。手册明确区分了"点定位 4 参"与"半径定位 3 参"。Agent 若只按 Skill 文本 3 参调用会漏掉点定位重载；按示例 4 参调用则与文本签名不符。

> **状态：已修正（2026-07-21）**。`case-basic-geometry.md` 中两处示例已统一改为 3 参半径版 `skt.CurveRadius(10, l1, l2)`，与"定义（距离定位）"文本签名一致。手册的点定位 4 参重载仍作为独立重载保留在手册中，Skill 暂未单独收录（见 2.1 / 行动建议 P1）。

#### ② 中心线 `AddCenterLine` —— 第二重载不同

| 来源 | 第二重载 |
|------|---------|
| 手册 定义2（L499） | `skt.AddCenterLine()` —— **无参（GUI 手动选）** |
| Skill 定义2（case-basic-geometry.md L92） | `skt.AddCenterLine(sketchObject)` —— **将已有中心线对象设为有效中心线（参数化）** |

**出入**：二者第 2 重载语义不同。Skill 收录了手册没有的"参数化设有效中心线"重载；手册的第 2 重载是无参 GUI 版（Skill 明确禁用无参，故未收录）。建议 Skill 保留参数化重载并注明手册另有 GUI 无参版。

#### ③ 倒角 `CurveChamfer` —— 点定位重载按规则有意不收录

| 来源 | 内容 |
|------|------|
| 手册 定义1（L667） | `skt.CurveChamfer(pt1, a1, pt2, a2)` —— **点定位，4 参** |
| 手册 定义2（L675） | `skt.CurveChamfer(1, a3, 1, a4)` —— **距离定位，4 参** |
| 手册 定义3（L679） | `skt.CurveChamfer()` —— 无参 |
| Skill（case-basic-geometry.md L408） | 仅 `skt.CurveChamfer(distance1, line1, distance2, line2)` —— **距离定位，4 参** |

**结论（按 2026-07-21 规则）**：倒角不存在"半径定位 3 参"重载，故不适用"保留半径 3 参"规则；但依据"点定位重载的都不要"，手册定义1 的点定位 4 参版**有意不收录**，Skill 仅保留距离定位 4 参版（与手册定义2 一致）。此项不再作为待补缺口。

### 2.3 手册自身笔误（会误导 agent，需提醒内核团队修正）

| 位置 | 手册原文 | 问题 |
|------|---------|------|
| L179 | "获取草图基准 Y 轴 **SketchXAxis** 对象" | Y 轴类型应为 `SketchYAxis`，误写为 `SketchXAxis` |
| L192 | "获取草图基准 Y 轴 **SketchXAxis** 对象"（GetCenterLine 段） | 应为 `CenterLine` 对象 |
| L159 | "获取原点对象"段下写"获取草图内**全部几何约束对象**" | 复制粘贴错误，应为"获取草图原点对象" |

> 这些不是 Skill 的问题，但 agent 若严格照手册类型名调用会出错，建议在验收单中向内核团队提出。

### 2.4 Skill 内部路径错误（会导致 agent 读不到 references）

- SKILL.md（L118–121）引用的参考路径为 `/mnt/skills/custom/sketch-modeling/references/case-init.md` 等；
- 实际目录为 `skills/custom/sketch/references/`（目录名是 **`sketch`**，不是 **`sketch-modeling`**）。
- **影响**：agent 按 SKILL.md 的链接去读 `sketch-modeling/references/...` 会找不到文件，必须改为 `sketch/references/...`。这是 Skill 自身的硬 bug，与手册无关，但直接影响可用性，需优先修。

---

## 3. 特征建模 API（手册 §4 有、Skill 完全未覆盖）

手册 §4「特征建模」定义了一整套 `doc.RunCommand(...)` 命令，Skill（聚焦草图）**完全未涉及**。若后续要让 agent 做"草图→特征建模"端到端，这些是必须补充的 API：

- 基本实体：`cmd_ncti_create_box` / `cmd_ncti_create_cylinder` / `cmd_ncti_create_cone` / `cmd_ncti_create_sphere`
- 布尔运算：`cmd_ncti_boolean_unit` / `cmd_ncti_boolean_cut` / `cmd_ncti_boolean_common`
- 特征变换：`cmd_ncti_fillet` / `cmd_ncti_chamfer` / `cmd_ncti_pan` / `cmd_ncti_scale` / `cmd_ncti_rotate_body` / `cmd_ncti_prism`
- 草图相关命令：`cmd_ncti_create_circle` / `cmd_ncti_create_plane` / `cmd_ncti_delete`
- 辅助：`doc.FindEdgeByNearestPoint(name, pt)`

> 手册 §5「Web 端模型库」（RocketModel / 参数文件 / 建模脚本）属于参数化建模与部署范畴，与草图 Skill 不在同一层，本文不展开，但同样未被任何 Skill 覆盖。

---

## 4. 行动建议（按优先级）

1. **[P0] 修 Skill 路径 bug**：SKILL.md 中 `sketch-modeling` → `sketch`，否则 references 全部读不到。
2. **[P1] 补 6 类缺失草图 API**：`SetRefData/GetRefData`、`AddCenterRect`、`AddParallelogram`、`RegularPolygon`、`Partition`、`RemovePointCons` 写入 `case-basic-geometry.md`。
3. **[P1] 校正重载说明（按"点定位重载都不要、只留半径 3 参"规则）**：`CurveRadius` 已统一为半径定位 3 参 `skt.CurveRadius(10, l1, l2)`（SKILL.md 与 case-basic-geometry.md 均已改）；`CurveChamfer` 仅保留距离定位 4 参，点定位重载有意不收录；`AddCenterLine` 注明手册另有 GUI 无参版（非点定位/半径模式，单独处理）。
4. **[P2] 向内核团队提手册笔误**：L179/L192 的 `SketchXAxis` 误写、L159 复制粘贴错误。
5. **[P2] 评估是否新增 feature-modeling Skill**：覆盖 §4 的 `doc.RunCommand` 系列，支撑草图→特征端到端。

---

## 5. 一致的部分（确认无出入，可放心）

- `YH.SketchWorkPlane(doc[, origin, hDir, vDir])`、`Open/Close/GetObject/Delete/GetAllDisplayObjects/GetAllConsObjects/GetOrigin/GetXAxis/GetYAxis/GetCenterLine/RunSolve/RunCalCloseArea`
- `YH.YHDocument(doc)` 全套：`GetSketch/ExportPython/ArgumentAutoSnap/AutoSolve/AutoCalFreeCons/AutoCalCloseArea/CreatSketch/CreatCoordinateSystem/Clear`
- 13 种基础几何（点/直线/中心线/样条/矩形/圆/圆弧/椭圆/椭圆弧/圆角/倒角/修剪/偏移）的**参数化签名**与手册一致
- 12 种约束（Xpos/Ypos/Length/Radius/Angle/Parallel/Vertical/Tangent/Equal/XAxis/YAxis/Coincide）的创建签名、点索引规则与手册一致
- 可编辑性总表：尺寸类（Xpos/Ypos/Length/Radius/Angle/Parallel）支持 `EditSize/EditLocation/Size`，几何类仅 `ObjectName/ConsData` —— 与手册一致；平行约束需 `OpenSize/CloseSize` 也与手册一致
