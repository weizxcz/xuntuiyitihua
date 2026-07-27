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
  - present_model
  - ask_clarification
  - get_session_id
  - cad_script_*
---

# 脚本格式说明

脚本是直接 `exec()` 执行的 Python 代码，不需要 `import` 语句或函数定义。脚本可以访问以下全局变量：

| 变量 | 类型 | 说明 |
|------|------|------|
| `NCTI` | module | NCTI Python 模块，提供点、向量、选择管理等基础功能 |
| `YH` | module | YH Python 模块，提供文档、草图工作平面等核心功能 |
| `doc` | NCTI.Document | NCTI 文档对象，用于打开/保存/下载 CAD 文件 |
| `yh_doc` | YH.YHDocument | YH 文档对象，用于创建/打开草图、管理求解开关等 |

**标准脚本模板**：
```python
# 草图初始化（如需要）
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
skt.Open()

# 绘制几何
circle = skt.AddCircle(NCTI.Point(0, 0, 0), 20)
line = skt.AddLine(NCTI.Point(-10, 0, 0), NCTI.Point(10, 0, 0))

# 添加约束
cons = skt.AddConsRadius(0, circle)
cons.EditSize(30.0)

# 关闭草图
skt.Close()
```

**注意事项**：
1. 脚本不需要 `import` 语句，`NCTI` 和 `YH` 已全局可用
2. 脚本不需要 `def main()`，直接执行代码
3. 使用 `NCTI.Point(x, y, z)` 或 `NCTI.Vector(x, y, z)` 创建几何基元
4. 使用 `YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))` 创建草图工作平面
5. 几何对象和约束的返回值需要捕获，用于后续操作（如 `l1 = skt.AddLine(...)`）
6. **脚本执行环境会自动处理文档**：
   - MCP 会自动新建或打开模型文件（`doc` 和 `yh_doc` 已准备好）
   - 脚本执行后，MCP 会自动保存文件并返回下载 URL
   - **脚本中不需要调用 `doc.New()`、`doc.Open()` 或 `doc.Save()`**
7. 如需关闭自动求解，使用 `yh_doc.AutoSolve(False)`，然后手动调用 `skt.RunSolve()`

# 草图建模

## 概述

本技能覆盖模型草图建模的完整工作流：

- **文档管理与草图初始化**：`YH.YHDocument(doc)` 文档入口；`YH.SketchWorkPlane` 创建/打开/关闭草图、获取与删除对象、获取基准对象（原点/坐标轴/中心线）、求解、封闭区域计算；文档级开关（自动求解、弱约束、闭合区域、Python 捕捉）、导出 Python、创建基准坐标系、清空
- **几何绘制**：13 种参数化操作——点、直线、中心线、样条、矩形、圆、圆弧、椭圆、椭圆弧、圆角、倒角、修剪、偏移
- **约束添加**：12 种类型——水平/竖直/长度/半径/角度尺寸约束，平行/垂直/相切/相等/水平 (XAxis)/竖直 (YAxis)/重合几何约束
- **约束显示与属性控制**：显示隐藏、半径互切直径、固定约束、构造线、固定尺寸、参考尺寸、显示模式、约束类型
- **约束编辑**：尺寸类约束可 EditSize/EditLocation/Size；平行约束额外 OpenSize/CloseSize；所有约束可查询 ObjectName/ConsData

> **入口类**：草图工作平面 `YH.SketchWorkPlane`、文档管理 `YH.YHDocument`。几何基元为 `NCTI.Point` / `NCTI.Vector`。
> **无参方法禁用**：所有需要 GUI 手动选对象的无参重载（如 `AddLine()`、`AddCircle()`、`AddConsXpos()`、`AddConsParallel()` 等）agent 不可使用，只调用带显式参数的版本。

## 前置检查

任何草图绘制操作前，先确认草图状态：

1. **草图不存在** → 创建工作平面并打开：
   ```python
   skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
   skt.Open()
   ```
2. **草图存在但未打开** → 打开：`skt.Open()`
3. **草图已打开** → 直接进行绘制/约束操作

需要文档级控制（求解开关、导出、按名获取已有平面等）时，额外创建文档入口：
```python
yh_doc = YH.YHDocument(doc)
```

## 工作流

### A. 单步操作

1. 前置检查（草图状态）
2. 调用一个工具执行对应操作
3. 组装完整脚本（必要时包含初始化）
4. 保存到 `/mnt/user-data/outputs` 并执行

### B. 多步操作

1. 前置检查（草图状态）
2. 按序调用工具——确保跨步变量名一致
3. 将所有操作按正确顺序组装成完整脚本
4. 保存到 `/mnt/user-data/outputs` 并执行

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
- 平行约束编辑尺寸前必须先打开：`cons1.OpenSize()` → `cons1.EditSize(20)` → `cons1.CloseSize()`

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

---

## 执行方式（推荐：MCP 自动执行）

**每次生成或修改脚本后，必须立即执行，如果执行成功结果返回了模型URL,使用 present_model 工具返回给前端加载, 没有返回URL则先URL。**

### MCP 服务器工具

该 MCP 服务器提供以下工具（已通过 `cad_script_*` 通配符授权）：

| 工具名称 | 功能 |
|---------|------|
| `cad_script_run_scripts` | 执行 CAD 操作脚本 |
| `cad_script_get_file_url` | 获取 CAD 文件的下载 URL |

### 标准执行流程

**步骤 1：生成/修改脚本**

```python
# 示例脚本
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
skt.Open()
circle = skt.AddCircle(NCTI.Point(0, 0, 0), 20)
skt.Close()
```

**步骤 2：调用 `cad_script_run_scripts` 执行脚本**

```json
{
  "scripts": [
    {
      "script_type": "create_circle",
      "script_content": "skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))\nskt.Open()\ncircle = skt.AddCircle(NCTI.Point(0, 0, 0), 20)\nskt.Close()",
      "should_execute": true
    }
  ],
  "model_path": "sketch.yha"
}
```

**步骤 3：如果步骤2返回了file_url,使用返回的file_url,否则调用 `cad_script_get_file_url` 获取下载 URL**

```json
{
  "file_path": "sketch.yha"
}
```

**步骤 4：使用 `present_model` 工具向用户展示 3D 模型**

执行完成后，调用 `present_model` 工具，传入 MCP 返回的完整 URL：

```json
{
  "filepath": "http://127.0.0.1:8310/files/sketch.yha"
}
```

> **重要**：
> 1. 每次脚本生成或修改后禁止使用sk命名变量，**必须**立即调用 `cad_script_run_scripts` 执行
> 2. 执行成功后，**必须**调用 `cad_script_get_file_url` 获取下载 URL
> 3. 将完整 URL 通过 `present_model` 工具传递给前端，供前端在 3D 查看器中加载 CAD 文件
> 4. `present_model` 工具专门用于展示 3D 模型文件（.yha, .yhp 等格式），支持：
>    - 完整 URL：`http://127.0.0.1:8310/files/uuid/example.yha`（从 MCP 服务器获取）
> 5. **模型路径隔离规则**：
>    - 为每个新会话生成一个随机的 UUID 作为文件夹名称（例如：`a1b2c3d4-e5f6-7890-abcd-ef1234567890/sketch.yha`）
>    - **使用 `get_session_id` 工具生成 UUID**：调用 `get_session_id(generate=True)` 返回一个随机 UUID
>    - 同一个会话中始终复用该 UUID 路径，确保前端能正确更新场景而非创建新实例
>    - 不同会话使用不同的 UUID 文件夹实现隔离
>    - 例如：会话 A 使用 `a1b2c3d4-e5f6-7890-abcd-ef1234567890/sketch.yha`，会话 B 使用 `b2c3d4e5-f6a7-8901-bcde-f23456789012/sketch.yha`

### 错误处理

如果执行失败：

1. 检查错误信息，定位问题
2. 修正脚本代码
3. 重新执行步骤 2-4

示例错误响应：
```json
{
  "success": false,
  "error": "脚本执行失败：..."
}
```

---

### 备选方式：保存后执行（不推荐）

仅在 MCP 服务器不可时使用：

1. 用 `write_file` 保存脚本到 `/mnt/user-data/outputs/xxx.py`
2. 用 `bash` 执行：`python /mnt/user-data/outputs/xxx.py`

> **注意**：使用前需确保 `extensions_config.json` 中已启用 `cad_script` MCP 服务器（HTTP 模式，端口 8310）。
