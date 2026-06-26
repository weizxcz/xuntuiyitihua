---
name: sketch-modeling
description: >
  Trigger: user requests any sketch modeling operation — create/open/close sketch,
  draw geometry (line, circle, arc, rect, spline, ellipse, etc.), add constraints,
  edit constraints, or any multi-step sketch workflow.
  Load this skill before generating NCTI sketch scripts.
allowed-tools:
  - write_file
  - read_file
  - str_replace
  - view_image
  - task
  - bash
  - present_files
  - ask_clarification
---

# NCTI 草图建模

## 概述

本技能覆盖 NCTI 草图建模的完整工作流：

- **草图初始化**：创建工作平面、打开、关闭、获取对象、删除
- **几何绘制**：11 种参数化操作 + 1 个仅 GUI 的 Trim
- **约束添加**：12 种类型，仅用参数化重载
- **约束编辑**：5 种类型

## 前置检查

任何草图绘制操作前，先确认草图状态：

1. **草图不存在** → 创建工作平面并打开：`skt = NCTI.SketchWorkPlane(doc)` → `skt.Open()`
2. **草图存在但未打开** → 打开：`skt.Open()`
3. **草图已打开** → 直接进行绘制/约束操作

## 工作流

### A. 单步操作

1. 前置检查（草图状态）
2. 调用一个工具执行对应操作
3. 组装完整脚本（必要时包含初始化）
4. 通过 `write_file` 保存到 `/mnt/user-data/outputs`

### B. 多步操作

1. 前置检查（草图状态）
2. 按序调用工具——确保跨步变量名一致
3. 将所有操作按正确顺序组装成完整脚本
4. 通过 `write_file` 保存

### C. 约束编辑

1. 获取约束对象：创建时捕获返回值（`cons1 = skt.AddConsLength(0, l1)`）或按名获取（`cons1 = skt.GetObject("name")`）
2. 应用编辑操作：`cons1.EditSize(50.0)`、`cons1.EditLocation(NCTI.Point(x, y, z))`
3. 组装并保存

### D. 修改已有脚本

**这是默认工作流。** 除非用户明确要求新建文件，否则始终走此流程：

1. 先通过 `read_file` 读取已有脚本
2. 用 `str_replace` 做精准修改（添加一行、调整尺寸、插入操作）：old_string 必须与现有代码精确匹配。如果需要改多处，执行多次 str_replace，每次针对一处变更
3. **不要用 `write_file` 整体重写已有脚本。** 即使改动很大，也用多次 str_replace 逐处完成——str_replace 只动该动的地方，write_file 会覆盖整个文件，有丢失已有代码的风险
4. 保持变量名一致

> `write_file` 仅在用户明确要求新建独立脚本文件时使用（见 SOUL.md「文件修改纪律」）。

## 跨步变量规则

- 圆角/倒角需要直线对象引用：`skt.CurveRadius(NCTI.Point(...), l1, NCTI.Point(...), l2)`
- 约束需要对象引用：`skt.AddConsLength(0, l1)`
- 约束编辑需要约束变量引用：`cons1.EditSize(50.0)`

## 参考目录

以下参考文件提供详细的 API 示例。需要细节时用 `read_file` 读取对应文件：

- `/mnt/skills/custom/sketch-modeling/references/case-init.md` — 草图初始化（创建、打开、关闭、获取/删除对象）
- `/mnt/skills/custom/sketch-modeling/references/case-basic-geometry.md` — 基本几何绘制（点、直线、圆弧、矩形、样条、椭圆、圆角、倒角）
- `/mnt/skills/custom/sketch-modeling/references/case-constraint.md` — 约束创建（12 种尺寸/几何约束）
- `/mnt/skills/custom/sketch-modeling/references/case-edit-constraint.md` — 约束编辑（EditSize/EditLocation/Size/ObjectName）
