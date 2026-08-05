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
> **⚠️ 强制命名规则**：**所有生成的对象（几何对象 + 约束对象）必须设置唯一名称**
> - 几何对象创建后立即命名：`circle = skt.AddCircle(NCTI.Point(0,0,0), 10); circle.SetObjectName("circle_1")`
> - 约束对象创建后立即命名：`cons = skt.AddConsRadius(circle); cons.SetObjectName("radius_cons_1")`
> - 名称应语义化且唯一，便于后续通过 `GetObject("name")` 获取编辑
> **⚠️ 返回值检查**：如果调用方法本该返回对象（如 `AddLine()`、`AddCircle()`、`AddConsRadius()` 等），但返回了 `None` / `init` / `0`，代表方法调用内部执行失败。此时应检查：
> 1. 参数格式是否正确
> 2. 前置条件是否满足（如草图是否已打开）
> 3. 对象引用是否有效（如圆角/倒角需要有效的直线对象）
> **⚠️ 严禁臆造方法**：所有方法调用必须以参考文档为准。**不要根据方法名推测功能**。例如：
> - 圆对象有 `EditCenter()` 编辑圆心，但**没有 `EditRadius()`** 方法
> - 修改圆的半径需要通过 `AddConsRadius(circle)` + `cons.EditSize(20)` 实现
> - 调用任何方法前，先查阅参考文档确认该方法是否存在

## 约束创建快速指引

**⚠️ 高频错误：不同约束的 `AddCons*` 方法参数模式不同，调用前务必确认！**

### 带 index 参数的约束（需要指定点索引）

| 约束 | API 签名 | 示例 |
|------|---------|------|
| 水平尺寸 | `AddConsXpos(index, obj)` 或 `AddConsXpos(index1, obj1, index2, obj2)` | `skt.AddConsXpos(0, c1)` |
| 竖直尺寸 | `AddConsYpos(index, obj)` 或 `AddConsYpos(index1, obj1, index2, obj2)` | `skt.AddConsYpos(0, l1)` |
| 长度尺寸 | `AddConsLength(index, obj)` 或 `AddConsLength(index1, obj1, index2, obj2)` | `skt.AddConsLength(0, l1)` |
| 重合 | `AddConsCoincide(index1, obj1)` 或 `AddConsCoincide(index1, obj1, index2, obj2)` | `skt.AddConsCoincide(0, l1)` |

### 只传对象的约束（**不需要** index 参数）

| 约束 | API 签名 | 示例 | ⚠️ 常见错误 |
|------|---------|------|------------|
| **半径尺寸** | `AddConsRadius(obj)` | `skt.AddConsRadius(c1)` | ❌ `AddConsRadius(0, c1)` — 没有 index！ |
| 角度尺寸 | `AddConsAngle(obj)` 或 `AddConsAngle(obj1, obj2)` | `skt.AddConsAngle(l1)` | ❌ `AddConsAngle(0, l1)` |
| 平行 | `AddConsParallel(obj1, obj2)` | `skt.AddConsParallel(l1, l2)` | — |
| 垂直 | `AddConsVertical(obj1, obj2)` | `skt.AddConsVertical(l1, l2)` | — |
| 相切 | `AddConsTangent(obj1, obj2)` | `skt.AddConsTangent(c1, l1)` | — |
| 相等 | `AddConsEqual(obj)` 或 `AddConsEqual(obj1, obj2)` | `skt.AddConsEqual(l1)` | — |
| 水平对齐 | `AddConsXAxis(obj)` **或** `AddConsXAxis(idx1, obj1, idx2, obj2)` | `skt.AddConsXAxis(l1)` | ⚠️ 单对象模式不需要 index，双对象模式需要！ |
| 竖直对齐 | `AddConsYAxis(obj)` **或** `AddConsYAxis(idx1, obj1, idx2, obj2)` | `skt.AddConsYAxis(l1)` | ⚠️ 单对象模式不需要 index，双对象模式需要！ |

### ⚠️ 特殊注意事项

#### 1. `AddConsXAxis` / `AddConsYAxis` 的双重模式

这两个约束有**两种完全不同的调用方式**：

```python
# ✅ 单对象模式：使直线水平/竖直（不需要 index）
skt.AddConsXAxis(l1)   # 使 l1 水平
skt.AddConsYAxis(l1)   # 使 l1 竖直

# ✅ 双对象模式：两点水平/竖直对齐（需要 index）
skt.AddConsXAxis(0, l1, 1, l2)  # l1 的点 0 与 l2 的点 1 水平对齐
skt.AddConsYAxis(0, l1, 1, l2)  # l1 的点 0 与 l2 的点 1 竖直对齐

# ❌ 错误：单对象模式误加 index
skt.AddConsXAxis(0, l1)  # 错误！单对象模式不需要 index
```

#### 2. `AddConsAngle` — 没有 index 参数

```python
# ✅ 正确
skt.AddConsAngle(l1)              # 直线与 X 轴夹角
skt.AddConsAngle(l1, l2)          # 两直线夹角
skt.AddConsAngle(l1, skt.GetXAxis())  # 直线与坐标轴

# ❌ 错误：没有 index 参数！
skt.AddConsAngle(0, l1)  # 错误！
```

#### 3. 平行约束编辑特殊规则

平行约束调用 `EditSize()` 前**必须先调用 `OpenSize()`**：
```python
cons = skt.AddConsParallel(l1, l2)
cons.OpenSize()      # ⚠️ 必须先调用
cons.EditSize(30.0)  # 编辑夹角（单位：度）
cons.CloseSize()     # 可选：关闭尺寸显示
```

### 几何类约束不可编辑尺寸

以下约束**不支持** `EditSize()`/`EditLocation()`/`Size()`，只能查询：
- 垂直 (`AddConsVertical`)
- 相切 (`AddConsTangent`)
- 相等 (`AddConsEqual`)
- 水平对齐 (`AddConsXAxis`)
- 竖直对齐 (`AddConsYAxis`)
- 重合 (`AddConsCoincide`)

---

## ⚠️ 几何绘制操作易错点

### 1. `AddArc` — 两种参数模式

```python
# 方式一：三点（起点、终点、弧上点）
skt.AddArc(NCTI.Point(10, 0, 0), NCTI.Point(0, 0, 0), NCTI.Point(5, 5, 0))

# 方式二：半径 + 起始角 + 终止角 + 圆心
skt.AddArc(5, 0, 60, NCTI.Point(0, 0, 0))  # r, startAngle, endAngle, center

# ❌ 错误：混用两种模式
skt.AddArc(5, NCTI.Point(0, 0, 0), 60, NCTI.Point(0, 0, 0))  # 错误！
```

### 2. `AddCenterLine` — 两种模式

```python
# 方式一：两点创建中心线
skt.AddCenterLine(NCTI.Point(10, 0, 0), NCTI.Point(5, 20, 0))

# 方式二：设置已有中心线为有效（只传对象）
skt.AddCenterLine(cl2)

# ❌ 错误：混用
skt.AddCenterLine(0, cl2)  # 错误！
```

### 3. `CurveRadius` / `CurveChamfer` — 参数顺序

```python
# CurveRadius: (pt1, line1, pt2, line2) — 点 - 线-点 - 线 交替
skt.CurveRadius(NCTI.Point(15, 15, 0), l1, NCTI.Point(0, 15, 0), l2)

# CurveChamfer: (dist1, line1, dist2, line2) — 距离 - 线-距离 - 线 交替
skt.CurveChamfer(3, l1, 4, l2)

# ❌ 错误：参数顺序搞混
skt.CurveRadius(l1, NCTI.Point(15, 15, 0), l2, NCTI.Point(0, 15, 0))  # 错误！
```

### 4. `CurveOffset` — 第一个参数必须是数组

```python
# ✅ 正确
skt.CurveOffset([line1], 2)
skt.CurveOffset([line1, line2], 5)

# ❌ 错误：直接传对象
skt.CurveOffset(line1, 2)  # 错误！必须用数组
```

### 5. `CurveTrimming` — 第二个参数必须是数组（如果提供）

```python
# 方式一：只传点
skt.CurveTrimming(NCTI.Point(5, 10, 0))

# 方式二：点 + 对象数组
skt.CurveTrimming(NCTI.Point(5, 10, 0), [circle1, line1])

# ❌ 错误：直接传单个对象
skt.CurveTrimming(NCTI.Point(5, 10, 0), circle1)  # 错误！必须用数组
```

---

## 前置检查

任何草图绘制操作前，先确认草图状态：
1. **创建 yh_doc** -> `yh_doc = YH.YHDocument(doc)`

2. **获取激活草图工作平面** -> `skt = yh_doc.GetActivitySketch()`，若返回 `None` 则草图不存在

3. **激活草图工作平面不存在** → 创建工作平面并打开：
   ```python
   skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
   ```
4. **草图存在但未打开** → 打开：`skt.Open()`
5. **草图已打开** → 直接进行绘制/约束操作

需要文档级控制（求解开关、导出、按名获取已有平面等）时，使用已创建的 `yh_doc`：
```python
yh_doc.AutoSolve(False)          # 关闭自动求解
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
3. **立即为几何对象和约束对象设置唯一名称**：`l1.SetObjectName("line_1")`、`cons1.SetObjectName("length_cons_1")`
4. **⚠️ 禁止重复添加约束**：如果对象已添加过约束，**不能**再次添加相同类型的约束，必须通过名称获取已有约束对象进行编辑
5. 需要时编辑约束：`cons1.EditSize(50.0)`；平行约束需先 `cons1.OpenSize()` 再 `EditSize`
6. 组装并保存执行

**约束添加示例**：
```python
# ✅ 首次添加：创建半径约束
circle = skt.AddCircle(NCTI.Point(0,0,0), 10)
circle.SetObjectName("circle_1")
cons = skt.AddConsRadius(circle)
cons.SetObjectName("radius_cons_1")
cons.EditSize(20)

# ✅ 编辑已有约束：通过名称获取
circle = skt.GetObject("circle_1")
cons = skt.GetObject("radius_cons_1")  # 通过名称获取已有约束
cons.EditSize(30)  # 修改半径

# ❌ 错误：重复添加约束
circle = skt.GetObject("circle_1")
cons = skt.AddConsRadius(circle)  # 错误！该圆已有半径约束，不能再次添加
```

### D. 约束编辑

1. 获取约束对象：创建时捕获返回值（`cons1 = skt.AddConsLength(0, l1)`）或按名获取（`cons1 = skt.GetObject("name")`）
2. 应用编辑操作：`cons1.EditSize(50.0)`、`cons1.EditLocation(NCTI.Point(x, y, z))`
3. 组装并保存执行

### ⚠️ 增量脚本规则（重要）

**当前执行方式：累积执行**

每次生成的脚本会追加到已有脚本后面执行。因此：
- **首次创建**：生成完整的创建脚本
- **后续编辑**：只生成编辑部分的脚本，**不要重复创建已存在的对象**

**核心规则**：编辑已有对象时，使用 `GetObject("对象名")` 获取对象，而不是重新创建。

**场景对比**：

| 用户请求 | 脚本内容 | 说明 |
|---------|---------|------|
| "画一个圆" | `circle = skt.AddCircle(NCTI.Point(0,0,0), 10); circle.SetObjectName("my_circle")` | 首次创建：需要设置对象名 |
| "把圆半径改成 20" | `circle = skt.GetObject("my_circle"); cons = skt.AddConsRadius(circle); cons.EditSize(20)` | 增量编辑：通过约束修改半径 |
| "把圆心移到 (10,0,0)" | `circle = skt.GetObject("my_circle"); circle.EditCenter(NCTI.Point(10,0,0))` | 增量编辑：直接调用 EditCenter |
| "在圆旁边画一个直线" | `line = skt.AddLine(NCTI.Point(10,0,0), NCTI.Point(20,0,0))` | 增量添加：只创建新对象 |

**错误示例**（会重复创建）：
```python
# ❌ 错误：用户说"把圆半径改成 20"，模型却生成了完整脚本
circle = skt.AddCircle(NCTI.Point(0, 0, 0), 10)  # 重复创建了！
# 错误：圆没有 EditRadius 方法
```

**正确示例**：
```python
# ✅ 正确：用 GetObject 获取已有对象，通过约束修改半径
circle = skt.GetObject("my_circle")  # 按名称获取已有对象
cons = skt.AddConsRadius(circle)     # 添加半径约束
cons.EditSize(20)                    # 通过约束修改半径
```

**重要提示**：
1. **必须**在创建对象时立即调用 `SetObjectName("unique_name")` 设置唯一名称（几何对象和约束对象都要命名）
2. 编辑对象时，使用 `GetObject("unique_name")` 按名称获取
3. 对象名来自左侧对象树或鼠标悬停查看，不是变量名
4. **圆没有 `EditRadius()` 方法**，修改半径需要通过 `AddConsRadius()` + `EditSize()` 实现

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
- 使用 `YH` 模块，脚本需要自行创建 `yh_doc` 对象
- 设置 `need_yh: true`
- **⚠️ 弱约束控制**：脚本开头必须调用 `yh_doc.InitPythonScritp(False)` 禁用软件自动弱约束，由脚本控制；脚本最后恢复 `yh_doc.InitPythonScritp(True)`

**标准脚本模板**：
```python
# 自行创建 yh_doc（执行环境不再注入）
yh_doc = YH.YHDocument(doc)

# ⚠️ 禁用自动弱约束，由脚本控制
yh_doc.InitPythonScritp(False)

# ... 草图绘制与约束操作 ...

# ⚠️ 脚本最后恢复自动弱约束
yh_doc.InitPythonScritp(True)

skt = yh_doc.GetActivitySketch()
if None == skt:
    skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))

# 绘制几何
circle = skt.AddCircle(NCTI.Point(0, 0, 0), 20)
line = skt.AddLine(NCTI.Point(-10, 0, 0), NCTI.Point(10, 0, 0))

# 添加约束（注意：AddConsRadius 只传对象，不需要 index！）
cons = skt.AddConsRadius(circle)  # ✅ 正确
# cons = skt.AddConsRadius(0, circle)  # ❌ 错误！
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
