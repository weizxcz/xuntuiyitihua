---
name: sketch
description: >
  Trigger: user requests any sketch modeling operation — create/open/close sketch,
  draw geometry (point, line, centerline, spline, rect, circle, arc, ellipse,
  ellipse arc, fillet, chamfer, trim, offset), add constraints, edit constraints,
  control constraint display/property, or any multi-step sketch workflow.
  Load this skill before generating model sketch scripts.
allowed-tools:
  - write_file
  - read_file
  - str_replace
  - view_image
  - task
  - bash
  - present_files
  - ask_clarification
  - get_session_id
  - exec_script
---

# 草图建模 Skill

## 概述

本技能覆盖模型草图建模的完整工作流：

- **文档管理与草图初始化**：`YH.YHDocument(doc)` 文档入口；`YH.SketchWorkPlane` 创建/打开/关闭草图、获取与删除对象、获取基准对象（原点/坐标轴/中心线）、求解、封闭区域计算；文档级开关（自动求解、弱约束、闭合区域、Python 捕捉）、导出 Python、创建基准坐标系、清空
- **几何绘制**：13 种参数化操作——点、直线、中心线、样条、矩形、圆、圆弧、椭圆、椭圆弧、圆角、倒角、修剪、偏移
- **约束添加**：12 种类型——水平/竖直/长度/半径/角度尺寸约束，平行/垂直/相切/相等/水平 (XAxis)/竖直 (YAxis)/重合几何约束
- **约束显示与属性控制**：显示隐藏、半径互切直径、固定约束、构造线、固定尺寸、参考尺寸、显示模式、约束类型
- **约束编辑**：尺寸类约束可 EditSize/EditLocation/Size；平行约束额外 OpenSize/CloseSize；所有约束可查询 ObjectName/ConsData

> **入口类**：草图工作平面 `YH.SketchWorkPlane`、文档管理 `YH.YHDocument`。几何基元为 `NCTI.Point` / `NCTI.Vector`。
> **无参方法禁用**：所有需要 GUI 手动选对象的无参重载（如 `AddLine()`、`AddCircle()`、`AddConsXpos()`、`AddConsParallel()` 等）agent 不可使用，只调用带显式参数的版本。
>**注意入参**：所有使调用的方法都要查看skill，使用准确的入参格式。
> **设置名称**：所有几何对象和约束都要设置唯一名称，便于跨步引用(如`circle = skt.AddCircle(NCTI.Point(0,0,0), 10)\nname = 'nameTest'
type = circle.SetObjectName(name)`)

## 前置检查

任何草图绘制操作前，先确认草图状态：
1. **获取激活草图工作平面** -> `skt = yh_doc.GetActivitySketch()`，若返回 `None` 则草图不存在

2. **激活草图工作平面不存在** → 创建工作平面并打开：
   ```python
   skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
   ```
3. **草图存在但未打开** → 打开：`skt.Open()`
4. **草图已打开** → 直接进行绘制/约束操作

需要文档级控制（求解开关、导出、按名获取已有平面等）时，额外创建文档入口：
```python
yh_doc = YH.YHDocument(doc)
```

## 工作流

### A. 单步操作

1. 前置检查（草图状态）
2. 调用一个工具执行对应操作
3. 组装完整脚本（必要时包含初始化）
4. 调用执行工具返回脚本给用户

### B. 多步操作

1. 前置检查（草图状态）
2. 按序调用工具——确保跨步变量名一致
3. 将所有操作按正确顺序组装成完整脚本
4. 调用执行工具返回脚本给用户

### C. 添加约束

1. 先绘制几何对象并捕获返回值：`l1 = skt.AddLine(...)`
2. 用对象变量添加约束并捕获约束变量：`cons1 = skt.AddConsLength(0, l1)`
3. 需要时编辑约束：`cons1.EditSize(50.0)`；平行约束需先 `cons1.OpenSize()` 再 `EditSize`
4. 组装并保存执行

### D. 约束编辑

1. 获取约束对象：创建时捕获返回值（`cons1 = skt.AddConsLength(0, l1)`）或按名获取（`cons1 = skt.GetObject("name")`）
2. 应用编辑操作：`cons1.EditSize(50.0)`、`cons1.EditLocation(NCTI.Point(x, y, z))`
3. 组装并保存执行

### E. 修改已有脚本

**这是默认工作流。** 除非用户明确要求新建文件，否则始终走此流程：

1. 先通过 `read_file` 读取已有脚本
2. 用 `str_replace` 做精准修改（添加一行、调整尺寸、插入操作）：old_string 必须与现有代码精确匹配。如果需要改多处，执行多次 str_replace，每次针对一处变更
3. **不要用 `write_file` 整体重写已有脚本。** 即使改动很大，也用多次 str_replace 逐处完成——str_replace 只动该动的地方，write_file 会覆盖整个文件，有丢失已有代码的风险
4. 保持变量名一致

> `write_file` 仅在用户明确要求新建独立脚本文件时使用（见 SOUL.md「文件修改纪律」）。

## 跨步变量规则

- 圆角/倒角需要直线对象引用：`skt.CurveRadius(NCTI.Point(...), l1, NCTI.Point(...), l2)`
- 修剪可传位置点（可选附带对象列表）：`skt.CurveTrimming(NCTI.Point(...))` 或 `skt.CurveTrimming(NCTI.Point(...), [c1, l1])`
- 偏移需要对象数组 + 距离：`skt.CurveOffset([line1], 2)`
- 约束需要对象引用：`skt.AddConsLength(0, l1)`
- 约束编辑需要约束变量引用：`cons1.EditSize(50.0)`
- 平行约束编辑尺寸前必须先打开：`cons1.OpenSize()` → `EditSize` → `cons1.CloseSize()`

## 常用控制开关

精确控制约束、避免自动求解干扰时，常用文档级开关配合手动求解：

```python
yh_doc = YH.YHDocument(doc)
yh_doc.AutoSolve(False)          # 关闭自动求解
yh_doc.AutoCalFreeCons(False)    # 关闭自动弱约束
yh_doc.AutoCalCloseArea(False)   # 关闭自动闭合区域计算
# ... 绘图与约束编辑 ...
skt.RunSolve()                   # 手动求解
```

## 参考目录

以下参考文件提供详细的 API 示例。需要细节时用 `read_file` 读取对应文件：

- `/mnt/skills/custom/sketch-modeling/references/case-init.md` — 草图初始化与文档管理（YH.SketchWorkPlane 创建/打开/关闭/获取删除对象、基准对象查询、求解；YH.YHDocument 文档管理全套：求解开关、导出 Python、按名获取平面、创建基准坐标系、清空）
- `/mnt/skills/custom/sketch-modeling/references/case-basic-geometry.md` — 基本几何绘制（点、直线、中心线、样条、矩形、圆、圆弧、椭圆、椭圆弧、圆角、倒角、修剪、偏移）+ 几何对象查询方法
- `/mnt/skills/custom/sketch-modeling/references/case-constraint.md` — 约束创建（12 种尺寸/几何约束）+ 约束显示与属性控制（显示隐藏、构造线、固定尺寸、参考尺寸、约束类型等）
- `/mnt/skills/custom/sketch-modeling/references/case-edit-constraint.md` — 约束编辑与查询（EditSize/EditLocation/Size；平行约束 OpenSize/CloseSize；ObjectName/ConsData；可编辑性总表）

## 脚本格式

> **脚本格式规范详见 [cad-script-exec](../cad-script-exec/SKILL.md#脚本格式规范) 公共技能文档。**

**草图脚本特点**：
- 使用 `YH` 模块和 `yh_doc` 对象
- 设置 `need_yh: true`

**标准脚本模板**：
```python
skt = yh_doc.GetActivitySketch()
if None == skt:
    skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))

# 绘制几何
circle = skt.AddCircle(NCTI.Point(0, 0, 0), 20)
line = skt.AddLine(NCTI.Point(-10, 0, 0), NCTI.Point(10, 0, 0))

# 添加约束
cons = skt.AddConsRadius(0, circle)
cons.EditSize(30.0)

```

## 执行方式

> **执行流程详见 [cad-script-exec](../cad-script-exec/SKILL.md#标准执行流程) 公共技能文档。**

**简要流程**：
1. 生成/修改脚本
2. 调用 `exec_script(script, description, need_yh=true)` 执行脚本
3. Frontend 通过 `hasExecScript()` 识别工具调用
4. Frontend 创建 `assistant:exec-script` 消息分组
5. 模型查看器接收 `script` 和 `needYh` 参数
6. 模型查看器自动调用 MCP 执行并展示模型

**注意**：`need_yh` 参数必须设为 `true`，因为草图脚本需要使用 YH 模块。
