---
name: cad-script-exec
description: >
  公共技能：CAD script 执行流程 - 提供脚本格式规范、执行流程、模型展示的标准流程。
  其他 skill 需要执行 CAD 脚本时加载此技能并引用其文档。
allowed-tools:
  - write_file
  - read_file
  - str_replace
  - bash
  - task
  - exec_script
---

# CAD Script MCP 执行公共技能

## 概述

本技能提供 CAD 脚本执行的标准化流程，包括：
- **脚本格式规范** - 脚本编写规则和全局变量说明
- **脚本执行** - 通过 `exec_script` 工具返回脚本给用户自行处理脚本执行

其他 skill 需要执行 CAD 脚本时，应引用本技能的文档，而不是重复编写执行流程。

---

## 脚本格式规范

### 执行环境

脚本是直接 `exec()` 执行的 Python 代码，**不需要** `import` 语句或函数定义。脚本可以直接访问以下全局变量：

| 变量 | 类型 | 说明 |
|------|------|------|
| `NCTI` | module | NCTI Python 模块，提供点、向量、选择管理等基础功能 |
| `doc` | NCTI.Document | NCTI 文档对象，用于打开/保存/下载 CAD 文件 |
| `YH` | module | YH Python 模块，提供文档、草图工作平面等核心功能（need_yh=true 时可用） |

### 脚本编写规则

1. **不需要 import 语句** - `NCTI`、`YH`、`doc` 等已全局可用
2. **不需要 `def main()`** - 直接执行代码
3. **不需要 `doc.New()`/`doc.Open()`/`doc.Save()`** - MCP 会自动处理文档
4. **不需要询问认为问题** - 按你的理解直接生成脚本
5. **不需要询问用户参数** - 如果需要用户输入参数，在脚本中使用`doc.ReturnDialogData`
6. **捕获返回值** - 几何对象和约束的返回值需要捕获，用于后续操作
7. **使用几何基元** - `NCTI.Point(x, y, z)` 或 `NCTI.Vector(x, y, z)`

### 脚本模板

#### 建模脚本模板（need_yh: false）

```python
# 直接使用 NCTI 模块和 doc 对象
doc.RunCommand("cmd_ncti_xxx", "obj_name", NCTI.Point(0, 0, 0), param1, param2)
```

#### 草图脚本模板（need_yh: true）

```python
# 草图初始化（需要自行创建 yh_doc）
yh_doc = YH.YHDocument(doc)
skt = yh_doc.GetActivitySketch()
if skt is None:
  skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
# 绘制几何
skt.Open()
circle = skt.AddCircle(NCTI.Point(0, 0, 0), 20)
line = skt.AddLine(NCTI.Point(-10, 0, 0), NCTI.Point(10, 0, 0))

# 添加约束
cons = skt.AddConsRadius(circle)
cons.EditSize(30.0)

# 关闭草图
skt.Close()
```

#### 参数输入模板

```python
# 根据用户提供的长方体长、宽、高等参数创建一个长方体

doc.ResetCaseResult()
length = 10.0
width = 20.0
height = 30.0
pt = NCTI.Point(0, 0, 0)

res = doc.ReturnDialogData(-1, "创建长方体参数", "长", length, "宽", width, "高", height, "顶点坐标", pt)
if len(res) == 0 : 
    print("用户取消了操作")
elif res[0] <= 0.0 or res[1] <= 0.0 or res[2] <= 0.0 :
    print("请输入合理的长方体的长、宽和高")
else :
    length = res[0]
    width = res[1]
    height = res[2]
    pt = res[3]
    doc.RunCommand("cmd_ncti_create_box", "box", pt, length, width, height)
    doc.Zoom()
```


---

## 执行工具

使用 `exec_script` 工具执行脚本：

| 参数 | 类型 | 说明 |
|------|------|------|
| `script` | string | 脚本内容（Python 代码） |
| `description` | string | 脚本描述 |
| `need_yh` | boolean | 是否需要 YH 模块（草图脚本为 `true`，建模脚本为 `false`） |

**执行流程**：
1. LLM 调用 `exec_script(script, description, need_yh)` 返回脚本
2. 前端识别 `exec_script` 工具调用（通过 `hasExecScript()` 函数）
3. 前端按需处理脚本

---

## 标准执行流程

### 步骤 1：生成/修改脚本

编写或修改 CAD 脚本代码，例如：

```python
# 示例脚本（具体内容由调用 skill 决定）
doc.RunCommand("cmd_ncti_xxx", "obj1", param1, param2)
```

### 步骤 2：调用 `exec_script` 执行脚本

```json
{
  "script": "脚本内容",
  "description": "脚本描述",
  "need_yh": true/false
}
```

**参数说明**：
- `script`: 脚本内容（Python 代码）
- `description`: 脚本描述
- `need_yh`: 是否需要 YH 模块（草图脚本为 `true`，建模脚本为 `false`）

**重要**：
- Frontend 会自动调用 MCP 服务器执行脚本
- Frontend 会自动加载并展示模型文件
- 不需要手动调用 `present_model` 或 `get_file_url`

---

## 执行纪律

**必须遵守的执行规则**：

1. **生成脚本后立即执行** - 禁止只生成脚本而不执行
2. **执行前必须展示脚本** - 调用 `exec_script` 前，必须先输出完整脚本内容给用户查看
3. **正确设置 need_yh 参数** - 草图脚本设为 `true`，建模脚本设为 `false`
4. **禁止跳过执行步骤** - 即使脚本简单，也必须执行并展示结果

### 错误处理

如果用户反馈执行失败：

1. 检查错误信息，定位问题
2. 修正脚本代码
3. 重新执行步骤 2-3

---

## 注意事项

1. **need_yh 参数设置**：
   - `true`：草图脚本（需要 YH 模块）
   - `false`：建模脚本（只使用 NCTI 模块）
2. **脚本格式**：脚本是直接 `exec()` 执行的 Python 代码，不需要 `import` 或 `def main()`

---

## 使用示例

### 示例 1：建模脚本执行

```python
# 步骤 1：生成脚本
doc.RunCommand("cmd_ncti_create_box", "box1", NCTI.Point(0, 0, 0), 10, 20, 30)

# 步骤 2：执行（need_yh: false，因为只使用 NCTI 模块）
exec_script(
    script="doc.RunCommand(\"cmd_ncti_create_box\", \"box1\", NCTI.Point(0, 0, 0), 10, 20, 30)",
    description="创建一个 10x20x30 的立方体",
    need_yh=false
)
```

### 示例 2：草图脚本执行

```python
# 步骤 1：生成脚本（需要自行创建 yh_doc）
yh_doc = YH.YHDocument(doc)
skt = yh_doc.GetActivitySketch()
if skt is None:
  skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
skt.Open()
circle = skt.AddCircle(NCTI.Point(0, 0, 0), 20)
skt.Close()

# 步骤 2：执行（need_yh: true，因为使用 YH 模块）
exec_script(
    script="yh_doc = YH.YHDocument(doc)\nsk = yh_doc.GetActivitySketch()\nif skt is None:\n  skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))\nsk.Open()\ncircle = skt.AddCircle(NCTI.Point(0, 0, 0), 20)\nsk.Close()",
    description="创建一个半径为 20 的圆",
    need_yh=true
)
```

---

## 引用此技能

其他 skill 在需要执行 CAD 脚本时，应：
1. 在 `allowed-tools` 中包含 `exec_script` 工具
2. 引用本技能的执行流程和脚本格式文档，而不是重复编写
3. 仅在本技能文档中描述特定领域的命令和 API，在公共 skill 中描述通用流程
