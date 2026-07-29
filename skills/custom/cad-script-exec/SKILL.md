---
name: cad-script-exec
description: >
  公共技能：CAD script MCP 执行流程 - 提供脚本格式规范、执行流程、URL 获取、模型展示的标准流程。
  其他 skill 需要执行 CAD 脚本时加载此技能并引用其文档。
allowed-tools:
  - write_file
  - read_file
  - str_replace
  - bash
  - task
  - cad_script_run_scripts
  - cad_script_get_file_url
  - get_session_id
  - present_model
---

# CAD Script MCP 执行公共技能

## 概述

本技能提供 CAD 脚本执行的标准化流程，包括：
- **脚本格式规范** - 脚本编写规则和全局变量说明
- 脚本执行（通过 `cad_script_run_scripts`）
- 文件 URL 获取（通过 `cad_script_get_file_url`）
- 模型展示（通过 `present_model`）
- 会话隔离（通过 `get_session_id`）

其他 skill 需要执行 CAD 脚本时，应引用本技能的文档，而不是重复编写执行流程。

---

## 脚本格式规范

### 执行环境

脚本是直接 `exec()` 执行的 Python 代码，**不需要** `import` 语句或函数定义。脚本可以直接访问以下全局变量：

| 变量 | 类型 | 说明 |
|------|------|------|
| `NCTI` | module | NCTI Python 模块，提供点、向量、选择管理等基础功能 |
| `doc` | NCTI.Document | NCTI 文档对象，用于打开/保存/下载 CAD 文件 |
| `YH` | module | YH Python 模块，提供文档、草图工作平面等核心功能（需要时可用） |
| `yh_doc` | YH.YHDocument | YH 文档对象，用于创建/打开草图、管理求解开关等（需要时可用） |

### 脚本编写规则

1. **不需要 import 语句** - `NCTI`、`YH`、`doc` 等已全局可用
2. **不需要 `def main()`** - 直接执行代码
3. **不需要 `doc.New()`/`doc.Open()`/`doc.Save()`** - MCP 会自动处理文档
4. **捕获返回值** - 几何对象和约束的返回值需要捕获，用于后续操作
5. **使用几何基元** - `NCTI.Point(x, y, z)` 或 `NCTI.Vector(x, y, z)`

### 脚本模板

#### 建模脚本模板（need_yh: false）

```python
# 直接使用 NCTI 模块和 doc 对象
doc.RunCommand("cmd_ncti_xxx", "obj_name", NCTI.Point(0, 0, 0), param1, param2)
```

#### 草图脚本模板（need_yh: true）

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

### 可选：文档级控制（草图脚本）

如需关闭自动求解等文档级控制：

```python
yh_doc = YH.YHDocument(doc)
yh_doc.AutoSolve(False)          # 关闭自动求解
yh_doc.AutoCalFreeCons(False)    # 关闭自动弱约束
yh_doc.AutoCalCloseArea(False)   # 关闭自动闭合区域计算
# ... 绘图与约束编辑 ...
skt.RunSolve()                   # 手动求解
```

---

## MCP 服务器工具

该 MCP 服务器提供以下工具（已通过 `cad_script_*` 通配符授权）：

| 工具名称 | 功能 |
|---------|------|
| `cad_script_run_scripts` | 执行 CAD 操作脚本 |
| `cad_script_get_file_url` | 获取 CAD 文件的下载 URL |
| `get_session_id` | 获取或生成会话 UUID |
| `present_model` | 展示 3D 模型 |

---

## 标准执行流程

### 步骤 1：生成/修改脚本

编写或修改 CAD 脚本代码，例如：

```python
# 示例脚本（具体内容由调用 skill 决定）
doc.RunCommand("cmd_ncti_xxx", "obj1", param1, param2)
```

### 步骤 2：展示脚本

**在执行前，必须先输出完整脚本内容给用户查看**：

```
我将执行以下脚本：

```python
doc.RunCommand("cmd_ncti_create_box", "box1", NCTI.Point(0, 0, 0), 10, 20, 30)
```
```

然后继续执行下一步。

### 步骤 3：调用 `cad_script_run_scripts` 执行脚本

```json
{
  "scripts": [
    {
      "script_type": "xxx",
      "script_content": "脚本内容",
      "should_execute": true
    }
  ],
  "model_path": "{uuid}/{filename}.yha",
  "need_yh": true/false
}
```

**参数说明**：
- `scripts`: 脚本数组，每个脚本包含类型、内容和执行标志
- `model_path`: 模型文件路径（**相对路径，不要包含 `/mnt/user-data/outputs/` 前缀**），格式为 `{uuid}/{filename}.yha`
- `need_yh`: 是否需要 YH 模块（草图脚本为 `true`，建模脚本为 `false`）

**重要**：`model_path` 只需要传递相对路径，例如 `a1b2c3d4-e5f6-7890-abcd-ef1234567890/model.yha`，**不要**写成 `/mnt/user-data/outputs/a1b2c3d4-e5f6-7890-abcd-ef1234567890/model.yha`。

### 步骤 4：获取文件 URL

检查步骤 3 的返回结果：
- **如果返回了 `file_url`**：直接使用返回的 URL
- **如果未返回 `file_url`**：调用 `cad_script_get_file_url` 获取

```json
{
  "file_path": "{uuid}/{filename}.yha"
}
```

### 步骤 5：展示模型

使用 `present_model` 工具展示 3D 模型：

```json
{
  "filepath": "http://127.0.0.1:8310/files/{uuid}/{filename}.yha"
}
```

### 完整执行结果示例

**成功执行（返回 file_url）**：
```json
{
  "success": true,
  "file_url": "http://127.0.0.1:8310/files/a1b2c3d4-e5f6-7890-abcd-ef1234567890/model.yha",
  "message": "脚本执行成功"
}
```
→ 直接使用 `file_url` 调用 `present_model`

**成功执行（未返回 file_url）**：
```json
{
  "success": true,
  "message": "脚本执行成功"
}
```
→ 需调用 `cad_script_get_file_url` 获取 URL

**执行失败**：
```json
{
  "success": false,
  "error": "脚本执行失败：NameError: name 'NCTI' is not defined",
  "message": "执行错误：第 3 行语法错误"
}
```
→ 立即报告错误，询问用户是否修改脚本

---

## 会话隔离规则

### UUID 管理

1. **为新会话生成 UUID**：调用 `get_session_id(generate=True)` 获取随机 UUID
2. **复用 UUID**：同一个会话中始终使用相同的 UUID 前缀
3. **会话隔离**：不同会话使用不同的 UUID 文件夹实现隔离

示例：
- 会话 A：`a1b2c3d4-e5f6-7890-abcd-ef1234567890/model.yha`
- 会话 B：`b2c3d4e5-f6a7-8901-bcde-f23456789012/model.yha`

### model_path 格式

```
{uuid}/{filename}.yha
```

例如：
- `a1b2c3d4-e5f6-7890-abcd-ef1234567890/model.yha`
- `b2c3d4e5-f6a7-8901-bcde-f23456789012/commands.yha`

---

## 执行纪律

**必须遵守的执行规则**：

1. **生成脚本后立即执行** - 禁止只生成脚本而不执行
2. **执行前必须展示脚本** - 调用 `cad_script_run_scripts` 前，必须先输出完整脚本内容给用户查看
3. **使用会话隔离路径** - 每次使用 `get_session_id` 获取 UUID，模型路径格式：`{uuid}/{filename}.yha`
4. **正确传递 model_path 参数** - 调用 `cad_script_run_scripts` 时必须传入 `model_path`，格式为 `{uuid}/{filename}.yha`
5. **执行成功后必须展示模型** - 使用 `present_model` 工具展示结果
6. **失败时立即报告** - 执行失败时，报告错误信息并询问用户是否修改脚本
7. **禁止跳过执行步骤** - 即使脚本简单，也必须执行并展示结果

### 错误处理

如果执行失败：

1. 检查错误信息，定位问题
2. 修正脚本代码
3. 重新执行步骤 3-5

示例错误响应：
```json
{
  "success": false,
  "error": "脚本执行失败：..."
}
```

---

## 备选方式：保存后执行（不推荐）

仅在 MCP 服务器不可时使用：

1. 用 `write_file` 保存脚本到 `/mnt/user-data/outputs/xxx.py`
2. 用 `bash` 执行：`python /mnt/user-data/outputs/xxx.py`

> **注意**：优先使用 MCP 服务器执行方式。

---

## 使用示例

### 示例 1：建模脚本执行

```python
# 步骤 1：生成脚本
doc.RunCommand("cmd_ncti_create_box", "box1", NCTI.Point(0, 0, 0), 10, 20, 30)

# 步骤 2：执行（need_yh: false，因为只使用 NCTI 模块）
{
  "scripts": [{"script_type": "create_box", "script_content": "...", "should_execute": true}],
  "model_path": "{uuid}/model.yha",
  "need_yh": false
}
```

### 示例 2：草图脚本执行

```python
# 步骤 1：生成脚本
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
skt.Open()
circle = skt.AddCircle(NCTI.Point(0, 0, 0), 20)
skt.Close()

# 步骤 2：执行（need_yh: true，因为使用 YH 模块）
{
  "scripts": [{"script_type": "sketch", "script_content": "...", "should_execute": true}],
  "model_path": "{uuid}/sketch.yha",
  "need_yh": true
}
```

---

## 引用此技能

其他 skill 在需要执行 CAD 脚本时，应：
1. 在 `allowed-tools` 中包含 `cad_script_*` 相关工具
2. 引用本技能的执行流程和脚本格式文档，而不是重复编写
3. 仅在本技能文档中描述特定领域的命令和 API，在公共 skill 中描述通用流程
