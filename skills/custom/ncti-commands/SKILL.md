---
name: ncti-commands
description: >
  触发：用户请求任何 NCTI CAD 命令操作 - 创建/修改/执行命令脚本，
  包括建模、约束、曲线/曲面、修复、文档管理等。
  在生成或修改 CAD 脚本前加载此技能。
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

# NCTI 命令 Skill

## 概述

本技能覆盖 NCTI CAD 系统的完整命令集：

- **文档管理** - 保存、加载、导出、清空等
- **建模命令** - 几何体创建、布尔运算、扫掠等
- **约束命令** - DCM 约束系统、尺寸约束、几何约束
- **曲线/曲面** - B 样条、NURBS、贝塞尔曲线等
- **修复命令** - 几何修复、容差处理、网格修复
- **其他命令** - 相机、选择、颜色、输出等

> **入口对象：** `doc` (NCTI.Document), `NCTI` (几何基元模块)

## 前置检查

执行任何命令前，确认：
1. 文档已打开或创建
2. 必要的几何对象已存在
3. 约束系统已初始化（如需要）

## 工作流

### A. 单步操作

1. 确认用户需求
2. 查找对应命令文档
3. 组装完整脚本
4. 调用执行工具执行脚本

### B. 多步操作

1. 分解任务为多个步骤
2. 按序调用工具
3. 确保跨步变量名一致
4. 组装完整脚本并执行

### C. 修改已有脚本

1. 读取已有脚本
2. 用 str_replace 做精准修改
3. 保持变量名一致
4. 重新执行

## 脚本格式

> **脚本格式规范详见 [cad-script-exec](../cad-script-exec/SKILL.md#脚本格式规范) 公共技能文档。**

**NCTI 命令脚本特点**：
- 只使用 `NCTI` 模块和 `doc` 对象
- 设置 `need_yh: false`
- 不需要 `YH` 模块

**标准脚本模板**：
```python
# 建模脚本示例
doc.RunCommand("cmd_ncti_create_box", "box1", NCTI.Point(0, 0, 0), 10, 20, 30)
```

## 执行方式

> **执行流程详见 [cad-script-exec](../cad-script-exec/SKILL.md#标准执行流程) 公共技能文档。**

**简要流程**：
1. 生成/修改脚本
2. 调用 `cad_script_run_scripts` 执行（`need_yh: false`）
3. 获取文件 URL（如未返回）
4. 使用 `present_model` 展示模型

## 参考目录

以下参考文件提供详细的命令文档。需要细节时用 `read_file` 读取对应文件：

- `references/执行命令类型.md` — 执行命令类型 (342 个命令)
- `references/文档类型.md` — 文档类型 (207 个命令)
- `references/视图类型.md` — 视图类型 (33 个命令)
- `references/场景类型.md` — 场景类型 (26 个命令)
- `references/选择集类型.md` — 选择集类型 (17 个命令)
- `references/矩阵变换类型.md` — 矩阵变换类型 (15 个命令)
- `references/网格类型.md` — 网格类型 (9 个命令)
- `references/分组类型.md` — 分组类型 (7 个命令)
- `references/单元类型.md` — 单元类型 (8 个命令)
- `references/AI 模型类型.md` — AI 模型类型 (5 个命令)
- `references/对象类型.md` — 对象类型 (4 个命令)
- `references/方法.md` — 方法 (3 个命令)
- `references/AI 属性类型.md` — AI 属性类型 (3 个命令)
- `references/中点约束结构体类型.md` — 中点约束结构体类型 (3 个命令)
- `references/退化点信息类型.md` — 退化点信息类型 (2 个命令)
- `references/AI 对象类型.md` — AI 对象类型 (2 个命令)
- `references/向量类型.md` — 向量类型 (2 个命令)
- `references/约束类型.md` — 约束类型 (1 个命令)
- `references/几何属性类型.md` — 几何属性类型 (1 个命令)
- `references/几何边界类型.md` — 几何边界类型 (1 个命令)
- `references/回调进度类型.md` — 回调进度类型 (1 个命令)
- `references/圆锥曲线结构体类型.md` — 圆锥曲线结构体类型 (1 个命令)
- `references/点类型.md` — 点类型 (1 个命令)
- `references/颜色类型.md` — 颜色类型 (1 个命令)
- `references/样条曲线结构体类型.md` — 样条曲线结构体类型 (1 个命令)
- `references/未分类.md` — 未分类 (4 个命令)

## 常用命令模式

### 1. RunCommand 模式

```python
doc.RunCommand("cmd_ncti_xxx", param1, param2, ...)
```

### 2. 直接方法调用

```python
doc.Save(path)
doc.Open(path)
```

### 3. 几何基元

```python
NCTI.Point(x, y, z)
NCTI.Vector(x, y, z)
NCTI.Vector3(x, y, z)
```

## 注意事项

1. 脚本不需要 import 语句，doc 和 NCTI 已全局可用
2. 脚本直接执行，不需要 def main()
3. 对象名称在创建时指定，用于后续引用
4. 约束系统需要先创建再使用
5. 执行前确保依赖的对象已存在

## 类别统计

| 类别 | 命令数 |
|------|--------|
| 建模命令 | 338 |
| 基础命令 | 227 |
| 约束命令 | 133 |
| AI 属性类 | 2 |


## 备选方式：保存后执行（不推荐）

仅在 MCP 服务器不可时使用：

1. 用 `write_file` 保存脚本到 `/mnt/user-data/outputs/xxx.py`
2. 用 `bash` 执行：`python /mnt/user-data/outputs/xxx.py`

> **注意**：使用前需确保 `extensions_config.json` 中已启用 `cad_script` MCP 服务器（HTTP 模式，端口 8310）。
