# 人机协同建模 API 需求分析报告

## 分析日期
2026-08-10

## 执行摘要

本报告基于对现有 Sketch API 和 NCTI Command API 的深度分析，评估当前 API 是否满足"人机协同建模"场景的需求。

**核心结论**：当前 API 能够支持**基础的 AI 辅助建模**，但在**AI 友好型接口**、**状态感知**、**智能交互**等方面存在明显缺口。

---

## 一、人机协同建模的场景定义

### 1.1 什么是"人机协同建模"

人机协同建模指人类设计师与 AI 代理协作完成 CAD 建模任务，典型场景包括：

| 场景 | 人类角色 | AI 角色 |
|------|----------|--------|
| **草图生成** | 提供概念/草图 | 生成精确参数化草图 |
| **约束添加** | 指定设计意图 | 自动添加合理约束 |
| **特征创建** | 选择特征类型 | 自动完成参数填充 |
| **设计修改** | 提出修改需求 | 执行修改并保证约束 |
| **设计优化** | 设定目标 | 提供优化建议 |
| **错误修复** | 发现问题 | 诊断并修复问题 |

### 1.2 核心能力需求

```
人机协同建模 = 建模能力 + AI 理解能力 + 智能交互能力
```

| 能力类别 | 具体需求 |
|----------|----------|
| **建模能力** | 草图绘制、3D 特征、布尔运算、参数化编辑 |
| **AI 理解能力** | 自然语言理解、设计意图识别、上下文感知 |
| **智能交互能力** | 智能推荐、自动补全、错误预防、渐进式交互 |

---

## 二、现有 API 能力评估

### 2.1 建模能力评估

#### ✅ 已满足的能力

| 能力 | Sketch API | NCTI API | 说明 |
|------|------------|----------|------|
| 2D 草图绘制 | ✅ 13 种几何 | - | 点/线/圆/弧/椭圆/样条等完整覆盖 |
| 2D 约束系统 | ✅ 12 种约束 | - | 尺寸约束 + 几何约束 |
| 3D 基础建模 | - | ✅ 338 命令 | 长方体/圆柱/圆锥/球体/圆环等 |
| 3D 特征操作 | - | ✅ 支持 | 拉伸/旋转/扫掠/放样/圆角/倒角 |
| 布尔运算 | - | ✅ 支持 | 并集/差集/交集 |
| 3D 约束系统 | - | ✅ DCM3 | 支持 3D 约束 |
| 几何查询 | - | ✅ 支持 | 体积/表面积/重心/惯性矩 |
| 特征识别 | - | ✅ 支持 | 查找圆角/孔/小特征 |

**结论**：基础建模能力**完整满足**人机协同建模需求。

#### ⚠️ 部分满足的能力

| 能力 | 现状 | 限制 |
|------|------|------|
| 参数化编辑 | Sketch 支持，NCTI 有限 | NCTI 缺少特征树管理 |
| 对象命名 | 支持 SetObjectName | AI 无法自动获取对象名称 |
| 脚本导出 | Sketch 支持 ExportPython | NCTI 无对应功能 |

### 2.2 AI 理解能力评估

#### ❌ 缺失的核心能力

| 能力 | 现状 | 影响 |
|------|------|------|
| **设计意图理解** | 无 | AI 无法理解"把圆移到中心"这类自然语言指令 |
| **上下文感知** | 无 | AI 不知道当前草图的状态（已约束/未约束） |
| **对象语义识别** | 无 | AI 无法区分"主轮廓"和"辅助线" |
| **设计历史理解** | 无 | AI 无法理解"像上次那样倒角" |

### 2.3 智能交互能力评估

#### ❌ 缺失的核心能力

| 能力 | 现状 | 影响 |
|------|------|------|
| **智能推荐** | 无 | AI 需手动分析应添加什么约束 |
| **自动补全** | 无 | AI 无法预测用户/下一步操作 |
| **错误预防** | 仅过约束查询 | AI 无法预判操作是否会导致问题 |
| **渐进式交互** | 无 | 无法支持"先大致画，再逐步细化" |

---

## 三、缺口分析与新增 API 需求

### 3.1 状态感知 API（优先级：高）

#### 3.1.1 草图状态分析

```python
# 需求描述
# AI 需要知道当前草图的状态
status = skt.AnalyzeStatus()
# 返回：{
#     "geometry_count": 10,
#     "constraint_count": 8,
#     "under_constrained": True,
#     "over_constrained": False,
#     "floating_objects": ["line_3", "arc_2"],
#     "suggested_constraints": [
#         {"type": "AddConsCoincide", "objects": ["line_3", "center_line"]},
#         {"type": "AddConsXpos", "objects": ["arc_2"]}
#     ]
# }

# 检查草图是否完整
is_complete = skt.IsFullyConstrained()

# 获取自由度信息
dof_info = skt.GetDegreesOfFreedom()
# 返回：{"total_dof": 12, "constrained_dof": 8, "remaining_dof": 4}
```

**原因**：
- AI 需要知道当前草图是否还需要添加约束
- 避免 AI 添加多余约束导致过约束
- 支持 AI 智能推荐下一步操作

#### 3.1.2 对象语义识别

```python
# 需求描述
# AI 识别对象的语义角色
semantic_info = skt.AnalyzeGeometry()
# 返回：[
#     {"object": "circle_1", "role": "main_profile", "confidence": 0.9},
#     {"object": "line_1", "role": "symmetry_axis", "confidence": 0.85},
#     {"object": "line_2", "role": "boundary", "confidence": 0.7}
# ]

# 查询特定类型的对象
profiles = skt.GetProfiles()  # 获取主轮廓
axes = skt.GetSymmetryAxes()  # 获取对称轴
dimensions = skt.GetDimensionalConstraints()  # 获取尺寸约束
```

**原因**：
- AI 需要理解"把主轮廓移到中心"中的"主轮廓"是哪个对象
- 支持自然语言指令的准确执行
- 减少 AI 的猜测

### 3.2 设计意图 API（优先级：高）

#### 3.2.1 意图识别

```python
# 需求描述
# AI 识别用户的设计意图
intent = skt.InferDesignIntent()
# 返回：{
#     "type": "symmetric_profile",
#     "confidence": 0.85,
#     "evidence": ["center_line_exists", "mirror_geometry_detected"],
#     "suggestions": [
#         "添加对称约束",
#         "添加相等约束到镜像几何"
#     ]
# }

# 识别常见设计模式
patterns = skt.DetectDesignPatterns()
# 返回：[
#     {"pattern": "symmetric_profile", "objects": [...]},
#     {"pattern": "hole_pattern", "objects": [...]},
#     {"pattern": "filleted_corner", "objects": [...]}
# ]
```

**原因**：
- AI 可以理解"这个设计是对称的"并自动添加对称约束
- 支持设计模式识别和复用
- 减少 AI 的误判

#### 3.2.2 意图表达

```python
# 需求描述
# AI 可以设置/查询设计意图
doc.SetDesignIntent("symmetry_axis", "center_line_1")
doc.SetDesignIntent("main_profile", ["circle_1", "line_1", "line_2"])

# 查询设计意图
intent = doc.GetDesignIntent("symmetry_axis")
# 返回："center_line_1"

# 获取所有意图
all_intents = doc.GetAllDesignIntents()
```

**原因**：
- AI 可以记录设计意图供后续操作使用
- 支持人类设计师标注设计意图
- 便于 AI 理解设计上下文

### 3.3 智能推荐 API（优先级：中）

#### 3.3.1 约束推荐

```python
# 需求描述
# AI 获取约束建议
recommendations = skt.RecommendConstraints()
# 返回：[
#     {"constraint": "AddConsCoincide", "objects": ["line_3", "center_line"], "priority": 1, "reason": "消除浮动"},
#     {"constraint": "AddConsXpos", "objects": ["arc_2"], "priority": 2, "reason": "固定水平位置"},
#     ...
# ]

# 获取特定类型的建议
fix_recommendations = skt.RecommendFixConstraints()  # 修复建议
optimize_recommendations = skt.RecommendOptimization()  # 优化建议
```

**原因**：
- AI 无需手动分析约束需求
- 提高约束添加的准确性
- 支持"最小约束"原则

#### 3.3.2 尺寸推荐

```python
# 需求描述
# AI 获取推荐尺寸值
suggestion = skt.SuggestDimensionValue(
    object="circle_1",
    constraint_type="radius",
    context={"similar_parts": [...], "design_rules": [...]}
)
# 返回：{"recommended": 25.0, "range": [20.0, 30.0], "reason": "符合标准尺寸系列"}

# 获取标准尺寸
standard_sizes = skt.GetStandardSizes("hole_diameter", standard="GB")
# 返回：[1.0, 1.2, 1.5, 2.0, 2.5, 3.0, ...]
```

**原因**：
- AI 可以推荐合理的尺寸值
- 支持标准件尺寸选择
- 减少人工输入

### 3.4 错误预防 API（优先级：中）

#### 3.4.1 操作预检查

```python
# 需求描述
# AI 在执行前预检查操作
preview = skt.PreviewOperation(
    operation="AddConsLength",
    params={"index": 0, "obj": "line_1"}
)
# 返回：{
#     "will_succeed": True,
#     "side_effects": ["line_1 will be fixed in X direction"],
#     "warnings": []
# }

# 检查是否会导致过约束
conflict = skt.CheckConflict(
    operation="AddConsParallel",
    params={"obj1": "line_1", "obj2": "line_2"}
)
# 返回：{"has_conflict": False, "conflicting_constraints": []}
```

**原因**：
- AI 可以避免执行会导致问题的操作
- 支持"沙盒"模式预览操作效果
- 减少错误和回滚

#### 3.4.2 设计验证

```python
# 需求描述
# AI 验证设计是否合理
validation = skt.ValidateDesign()
# 返回：{
#     "valid": True,
#     "issues": [
#         {"type": "warning", "message": "草图未封闭，可能无法拉伸", "object": "line_3"},
#         {"type": "info", "message": "建议添加对称约束以保持设计意图"}
#     ]
# }

# 检查封闭区域
closed_areas = skt.FindClosedAreas()
# 返回：[{"area": 1250.5, "boundary": ["line_1", "line_2", "arc_1"]}]
```

**原因**：
- AI 可以提前发现潜在问题
- 支持设计质量检查
- 减少返工

### 3.5 渐进式交互 API（优先级：中）

#### 3.5.1 草图细化

```python
# 需求描述
# AI 支持渐进式草图创建
# 第一步：创建粗略草图
skt.CreateRoughSketch()  # 允许未完全约束

# 第二步：逐步细化
skt.RefineSketch(
    stage="add_dimensions",  # 或 "add_geometric_constraints" 或 "fix_position"
    targets=["circle_1", "line_1"]
)

# 检查细化程度
refinement = skt.GetRefinementLevel()
# 返回：{
#     "stage": "dimensions_added",
#     "completion": 0.7,
#     "next_steps": ["add_geometric_constraints", "fix_position"]
# }
```

**原因**：
- 支持"先画大概，再逐步精确"的工作流
- AI 可以引导用户完成细化
- 降低使用门槛

#### 3.5.2 智能补全

```python
# 需求描述
# AI 智能补全草图
# 用户画了一半的矩形，AI 自动补全
skt.AutoCompleteSketch(
    incomplete_objects=["line_1", "line_2"],
    pattern="rectangle"  # 或 "circle", "symmetric_profile", ...
)

# AI 预测用户意图并建议
prediction = skt.PredictUserIntent(
    current_state=...,
    history=[...]
)
# 返回：{"likely_action": "add_symmetry_constraint", "confidence": 0.8}
```

**原因**：
- AI 可以辅助用户快速完成草图
- 支持智能预测和补全
- 提升用户体验

### 3.6 自然语言交互 API（优先级：低）

#### 3.6.1 指令执行

```python
# 需求描述
# AI 执行自然语言指令
result = skt.ExecuteIntent("把圆心移到原点")
# 返回：{"success": True, "operations": [...], "message": "已将 circle_1 的圆心移到原点"}

result = skt.ExecuteIntent("添加对称约束")
result = skt.ExecuteIntent("把所有圆角改成半径 5")

# 获取指令建议
suggestions = skt.GetIntentSuggestions()
# 返回：["添加对称约束", "固定草图位置", "添加尺寸约束"]
```

**原因**：
- 降低 AI 使用门槛
- 支持更自然的交互方式
- 减少脚本编写

### 3.7 特征树 API（优先级：中）

#### 3.7.1 特征管理（NCTI 需要补充）

```python
# 需求描述
# AI 需要理解设计历史
features = doc.GetFeatureTree()
# 返回：[
#     {"id": "sketch_1", "type": "sketch", "params": {...}, "children": ["extrude_1"]},
#     {"id": "extrude_1", "type": "extrude", "params": {"depth": 10}, "children": ["fillet_1"]},
#     {"id": "fillet_1", "type": "fillet", "params": {"radius": 2}}
# ]

# AI 编辑特征
doc.EditFeature("extrude_1", params={"depth": 20})

# AI 抑制/恢复特征
doc.SuppressFeature("fillet_1")
doc.ResumeFeature("fillet_1")

# AI 回滚到某一步
doc.RollbackTo("extrude_1")
```

**原因**：
- NCTI 当前缺少特征树管理
- AI 需要理解设计历史才能智能修改
- 支持参数化迭代

---

## 四、API 优先级矩阵

| API 类别 | 具体功能 | 优先级 | 影响范围 | 实现难度 |
|----------|----------|--------|----------|----------|
| **状态感知** | 草图状态分析 | 🔴 高 | 核心 | 低 |
| | 对象语义识别 | 🔴 高 | 核心 | 中 |
| **设计意图** | 意图识别 | 🔴 高 | 核心 | 高 |
| | 意图表达 | 🔴 高 | 核心 | 低 |
| **智能推荐** | 约束推荐 | 🟡 中 | 增强 | 中 |
| | 尺寸推荐 | 🟡 中 | 增强 | 中 |
| **错误预防** | 操作预检查 | 🟡 中 | 增强 | 中 |
| | 设计验证 | 🟡 中 | 增强 | 中 |
| **渐进交互** | 草图细化 | 🟡 中 | 体验 | 中 |
| | 智能补全 | 🟡 中 | 体验 | 高 |
| **自然语言** | 指令执行 | 🟢 低 | 体验 | 高 |
| **特征树** | 特征管理 | 🟡 中 | 增强 | 高 |

---

## 五、推荐实施路线图

### 阶段一：基础感知（1-2 个月）

**目标**：让 AI 能够感知和理解当前状态

- [ ] `skt.AnalyzeStatus()` - 草图状态分析
- [ ] `skt.IsFullyConstrained()` - 检查是否完全约束
- [ ] `skt.AnalyzeGeometry()` - 对象语义识别
- [ ] `doc.SetDesignIntent()` / `GetDesignIntent()` - 意图表达

**预期效果**：AI 可以判断草图状态，理解设计意图

### 阶段二：智能辅助（2-3 个月）

**目标**：增强 AI 的智能推荐能力

- [ ] `skt.RecommendConstraints()` - 约束推荐
- [ ] `skt.SuggestDimensionValue()` - 尺寸推荐
- [ ] `skt.PreviewOperation()` - 操作预检查
- [ ] `skt.ValidateDesign()` - 设计验证

**预期效果**：AI 可以智能推荐，避免错误

### 阶段三：高级交互（3-4 个月）

**目标**：完善交互体验

- [ ] `skt.InferDesignIntent()` - 意图识别
- [ ] `skt.ExecuteIntent()` - 自然语言指令
- [ ] `skt.AutoCompleteSketch()` - 智能补全
- [ ] NCTI 特征树 API

**预期效果**：支持更自然的交互方式

---

## 六、典型人机协同工作流

### 6.1 草图生成工作流

```
用户：画一个直径 50 的圆
AI:  创建圆 (center=(0,0,0), radius=25)
     添加半径约束
     返回：已创建圆，半径 25mm

用户：在圆的右边画一个矩形
AI:  分析草图状态 -> 圆已约束
     创建矩形 (位置在圆右侧)
     建议：是否添加圆与矩形的相切约束？
     用户确认 -> 添加相切约束

用户：让矩形对称于圆心
AI:  识别意图 -> 对称设计
     自动添加：对称约束 + 中心线
     验证：草图状态 -> 完全约束
```

### 6.2 设计修改工作流

```
用户：把圆的半径改成 30
AI:  预检查 -> 修改后不会过约束
     执行修改：radius = 30
     验证：草图仍然完全约束
     返回：修改成功

用户：给矩形加个圆角
AI:  分析矩形 -> 识别 4 个角
     建议：圆角半径设为多少？标准值：2, 3, 5, 8
     用户：5
     执行：添加圆角约束
     验证：草图仍然有效
```

---

## 七、总结

### 7.1 当前能力总结

| 能力维度 | 评分 | 说明 |
|----------|------|------|
| 基础建模 | ⭐⭐⭐⭐⭐ | 2D/3D 建模能力完整 |
| 约束系统 | ⭐⭐⭐⭐⭐ | 2D/3D 约束系统完善 |
| 状态感知 | ⭐ | 几乎空白 |
| 意图理解 | ⭐ | 几乎空白 |
| 智能交互 | ⭐⭐ | 基础能力有限 |

### 7.2 关键缺口

1. **状态感知**：AI 无法知道草图是否完全约束
2. **意图理解**：AI 无法理解设计意图
3. **智能推荐**：AI 无法推荐下一步操作
4. **错误预防**：AI 无法预判操作风险
5. **特征树**：NCTI 缺少特征树管理

### 7.3 与多 AI 协同的区别

| 维度 | 人机协同 | 多 AI 协同 |
|------|----------|----------|
| 核心需求 | 理解意图、智能辅助 | 会话管理、冲突检测 |
| 优先级 | 状态感知 > 协同管理 | 协同管理 > 状态感知 |
| 实现难度 | 相对较低 | 相对较高 |
| 用户价值 | 直接提升用户体验 | 间接提升效率 |

### 7.4 建议

1. **优先实施状态感知 API**：这是人机协同的基础
2. **逐步增强智能能力**：可结合 AI 模型实现
3. **NCTI 扩展特征树**：支持参数化设计
4. **保持 API 简洁**：避免过度设计

---

## 附录 A：API 对比表

### 现有 API vs 需求 API

| 功能 | 现有 API | 需求 API | 缺口 |
|------|---------|---------|------|
| 检查草图状态 | 无 | `AnalyzeStatus()` | 高 |
| 识别对象语义 | 无 | `AnalyzeGeometry()` | 高 |
| 理解设计意图 | 无 | `InferDesignIntent()` | 高 |
| 推荐约束 | 无 | `RecommendConstraints()` | 中 |
| 预检查操作 | 无 | `PreviewOperation()` | 中 |
| 验证设计 | 无 | `ValidateDesign()` | 中 |
| 特征树管理 | 无 | `GetFeatureTree()` | 中 |
| 自然语言指令 | 无 | `ExecuteIntent()` | 低 |

---

## 附录 B：参考文档

- [01-现有 API 盘点.md](./01-现有 API 盘点.md) - 现有 API 详细分析
- [02-AI 协同建模 API 需求分析.md](./02-AI 协同建模 API 需求分析.md) - 多 AI 协同分析（供参考）
- [skills/custom/sketch/SKILL.md](../../skills/custom/sketch/SKILL.md) - Sketch API 技能文档
- [skills/custom/ncti-commands/SKILL.md](../../skills/custom/ncti-commands/SKILL.md) - NCTI 命令技能文档

---

*文档生成时间：2026-08-10*
