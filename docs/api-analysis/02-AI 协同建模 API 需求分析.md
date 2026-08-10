# AI 协同建模 API 需求分析报告

## 分析日期
2026-08-10

## 执行摘要

本报告基于对现有 Sketch API 和 NCTI Command API 的深度分析，评估当前 API 是否满足"AI 协同建模"场景的需求，并识别出需要补充的 API 能力。

**核心结论**：当前 API 能够支持**基础的 AI 辅助建模**，但在**多 AI 协同**、**智能理解**、**状态管理**等关键能力上存在明显缺口。

---

## 一、AI 协同建模的场景定义

### 1.1 什么是"AI 协同建模"

AI 协同建模指多个 AI 代理协作完成 CAD 建模任务，典型场景包括：

| 场景 | 描述 |
|------|------|
| 分工协作 | 不同 AI 负责不同部件/特征，最后组装 |
| 迭代优化 | AI 生成设计 → AI 评估 → AI 修改 → 循环 |
| 约束协调 | 多个 AI 添加约束时避免冲突 |
| 知识共享 | AI 间传递设计意图、参数、经验 |
| 冲突解决 | 检测并解决多 AI 操作产生的冲突 |

### 1.2 核心能力需求

```
AI 协同建模 = 建模能力 + 协同能力 + 智能能力
```

| 能力类别 | 具体需求 |
|----------|----------|
| **建模能力** | 草图绘制、3D 特征、布尔运算、参数化编辑 |
| **协同能力** | 状态同步、冲突检测、版本管理、协作协议 |
| **智能能力** | 意图理解、约束推荐、冲突预测、设计优化 |

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

**结论**：基础建模能力**基本满足**AI 协同建模需求。

#### ⚠️ 部分满足的能力

| 能力 | 现状 | 限制 |
|------|------|------|
| 参数化编辑 | Sketch 支持，NCTI 有限 | NCTI 缺少特征树管理 |
| 命名与查询 | 对象可命名 | 缺少批量查询/过滤 |
| 脚本导出 | Sketch 支持 ExportPython | NCTI 无对应功能 |

### 2.2 协同能力评估

#### ❌ 缺失的核心能力

| 能力 | 现状 | 影响 |
|------|------|------|
| **多 AI 会话管理** | 无 | 无法区分不同 AI 的操作来源 |
| **操作日志/审计** | 无 | 无法追溯谁做了什么修改 |
| **冲突检测** | 仅过约束查询 | 无法检测多 AI 间的语义冲突 |
| **版本管理** | 无 | 无法回滚/对比/分支 |
| **状态同步** | 无 | AI 间无法感知彼此的状态变化 |
| **协作锁机制** | 无 | 无法防止并发修改冲突 |

### 2.3 智能能力评估

#### ❌ 缺失的核心能力

| 能力 | 现状 | 影响 |
|------|------|------|
| **设计意图理解** | 无 | AI 无法理解"为什么这样设计" |
| **约束推荐** | 无 | AI 需手动判断添加什么约束 |
| **冲突预测** | 无 | 无法预判操作是否会导致冲突 |
| **设计验证** | 仅几何查询 | 无法验证设计是否符合规范 |
| **优化建议** | 无 | AI 无法获得改进建议 |

---

## 三、缺口分析与新增 API 需求

### 3.1 协同管理 API（优先级：高）

#### 3.1.1 AI 会话管理

```python
# 需求描述
# 为每个 AI 代理创建独立的会话上下文
session = doc.CreateAISession(agent_id="ai_001", name="草图设计助手")

# 获取当前会话
session = doc.GetCurrentSession()

# 查询所有活跃会话
sessions = doc.ListAISessions()

# 会话间传递数据
session.SetData("design_intent", {"type": "symmetric", "axis": "center_line"})
other_session = doc.GetSession("ai_002")
intent = other_session.GetData("design_intent")

# 结束会话
session.Close()
```

**原因**：
- 需要区分不同 AI 的操作来源
- 支持 AI 间的数据共享和意图传递
- 便于审计和追溯

#### 3.1.2 操作日志与审计

```python
# 需求描述
# 记录当前 AI 的操作
session.LogOperation("AddCircle", params={"center": (0,0,0), "radius": 10})

# 查询操作历史
history = session.GetOperationHistory(since="2026-08-10T10:00:00")

# 查询某 AI 的所有操作
ai_history = doc.GetAIHistory(agent_id="ai_001")

# 回滚到指定操作
doc.RollbackTo(operation_id="op_12345")

# 获取操作差异
diff = doc.GetDiff(before="op_123", after="op_125")
```

**原因**：
- 支持版本管理和回滚
- 便于问题定位和审计
- 支持"时间旅行"式的设计探索

#### 3.1.3 协作锁机制

```python
# 需求描述
# 获取对象锁
lock = doc.AcquireLock("sketch_1", session_id="ai_001", timeout=30)

# 释放锁
lock.Release()

# 检查对象是否被锁定
is_locked = doc.IsLocked("sketch_1")

# 获取锁信息
lock_info = doc.GetLockInfo("sketch_1")
# 返回：{"owner": "ai_002", "locked_at": "2026-08-10T10:30:00", ...}

# 强制释放（管理员）
doc.ForceReleaseLock("sketch_1")
```

**原因**：
- 防止并发修改冲突
- 支持"谁在编辑"的可视化提示
- 避免覆盖他人工作

### 3.2 冲突检测 API（优先级：高）

#### 3.2.1 语义冲突检测

```python
# 需求描述
# 预检查：在执行前检测潜在冲突
conflicts = doc.PredictConflicts(
    operation="AddConsLength",
    params={"obj": "line_1", "value": 50},
    check_scope=["ai_001", "ai_002"]  # 检查与这些 AI 的操作是否冲突
)
# 返回：{"has_conflict": True, "conflicts": [...]}

# 检测过约束
overconstraints = doc.CheckOverconstraints()

# 检测设计冲突（跨 AI）
design_conflicts = doc.CheckDesignConflicts(
    rules=["symmetry_must_match", "tolerance_compatible"]
)
```

**原因**：
- 避免 AI 间添加冲突约束
- 提前预警而非事后修复
- 支持自定义冲突规则

#### 3.2.2 约束兼容性分析

```python
# 需求描述
# 分析约束系统的完整性
analysis = doc.AnalyzeConstraints()
# 返回：{
#     "under_constrained": [...],
#     "fully_constrained": [...],
#     "over_constrained": [...],
#     "redundant": [...]
# }

# 建议移除的约束
suggestions = doc.GetRedundantConstraints()

# 检查约束冲突
conflicts = doc.GetConstraintConflicts()
```

**原因**：
- 帮助 AI 理解约束系统状态
- 避免添加冗余约束
- 辅助冲突解决

### 3.3 智能辅助 API（优先级：中）

#### 3.3.1 设计意图识别

```python
# 需求描述
# 识别当前草图的设计意图
intent = doc.InferDesignIntent(
    sketch="sketch_1",
    context={"previous_operations": [...]}
)
# 返回：{
#     "type": "symmetric_profile",
#     "confidence": 0.85,
#     "evidence": ["center_line_exists", "mirror_geometry_detected"],
#     "suggestions": ["add_symmetry_constraint", "add_equal_constraints"]
# }

# 批量识别
intents = doc.InferDesignIntentAll()
```

**原因**：
- AI 可理解设计意图而非仅几何
- 支持智能约束推荐
- 减少 AI 的猜测

#### 3.3.2 约束推荐

```python
# 需求描述
# 推荐应添加的约束
recommendations = doc.RecommendConstraints(
    sketch="sketch_1",
    goal="fully_constrained"  # 或 "minimal_constrained"
)
# 返回：[
#     {"constraint": "AddConsCoincide", "objects": ["line_1", "center_line"], "priority": 1},
#     {"constraint": "AddConsXpos", "objects": ["line_1"], "priority": 2},
#     ...
# ]

# 推荐约束值
value_suggestion = doc.SuggestConstraintValue(
    constraint_type="length",
    context={"similar_parts": [...], "design_rules": [...]}
)
```

**原因**：
- AI 无需手动分析约束需求
- 提高约束添加的准确性
- 支持设计规则集成

#### 3.3.3 设计验证

```python
# 需求描述
# 验证设计是否符合规范
validation = doc.ValidateDesign(
    rules=["manufacturing", "assembly", "tolerance"],
    options={"tolerance_level": "standard"}
)
# 返回：{
#     "valid": False,
#     "issues": [
#         {"rule": "min_wall_thickness", "severity": "warning", "location": "face_123"},
#         ...
#     ]
# }

# 检查可制造性
dfm_result = doc.CheckDFM("part_1", manufacturing_process="cnc_milling")

# 检查装配干涉
interference = doc.CheckInterference(["part_1", "part_2"])
```

**原因**：
- AI 可验证设计质量
- 支持 DFM/DFA 规则检查
- 减少返工

### 3.4 参数化与配置 API（优先级：中）

#### 3.4.1 参数管理

```python
# 需求描述
# 定义参数
doc.AddParameter("main_length", value=100.0, unit="mm", group="主尺寸")
doc.AddParameter("wall_thickness", value=5.0, unit="mm", group="壁厚")

# 查询参数
params = doc.GetParameters(group="主尺寸")
value = doc.GetParameter("main_length")

# 批量设置参数
doc.SetParameters({"main_length": 120.0, "wall_thickness": 6.0})

# 参数关联/表达式
doc.SetParameterExpression("inner_diameter", "main_length - 2 * wall_thickness")
```

**原因**：
- 支持参数化设计
- AI 可通过修改参数快速迭代
- 支持参数间的关联关系

#### 3.4.2 配置管理

```python
# 需求参数
# 保存当前配置
doc.SaveConfiguration("config_v1", description="初始设计")

# 加载配置
doc.LoadConfiguration("config_v1")

# 比较配置
diff = doc.CompareConfigurations("config_v1", "config_v2")

# 列出所有配置
configs = doc.ListConfigurations()

# 批量生成变体
variants = doc.GenerateVariants(
    base_config="config_v1",
    parameters={"main_length": [100, 120, 150], "wall_thickness": [5, 6, 7]}
)
```

**原因**：
- 支持设计变体管理
- AI 可探索不同配置
- 支持配置对比

### 3.5 特征树 API（优先级：中）

#### 3.5.1 特征管理

```python
# 需求描述
# 获取特征树
features = doc.GetFeatureTree()

# 获取特征信息
feature = doc.GetFeature("extrude_1")
# 返回：{"type": "extrude", "parent": "sketch_1", "params": {...}, ...}

# 编辑特征参数
doc.EditFeature("extrude_1", params={"depth": 50.0})

# 抑制/恢复特征
doc.SuppressFeature("fillet_1")
doc.ResumeFeature("fillet_1")

# 删除特征
doc.DeleteFeature("feature_1")

# 重排序特征
doc.ReorderFeatures(["sketch_1", "extrude_1", "fillet_1"])
```

**原因**：
- NCTI 当前缺少特征树管理
- AI 需要理解设计历史
- 支持特征级别的编辑

### 3.6 装配 API（优先级：低）

#### 3.6.1 多部件装配

```python
# 需求描述
# 创建装配
assembly = doc.CreateAssembly("assembly_1")

# 添加部件
assembly.AddComponent("part_1", transform=...)
assembly.AddComponent("part_2", transform=...)

# 添加装配约束
assembly.AddConstraint("mate", "part_1.face_1", "part_2.face_1")
assembly.AddConstraint("align", "part_1.axis_1", "part_2.axis_1")

# 干涉检查
interference = assembly.CheckInterference()

# 获取装配关系
relationships = assembly.GetAssemblyRelationships()
```

**原因**：
- 当前 NCTI 缺少装配 API
- AI 协同建模常涉及多部件
- 支持装配级别的约束管理

### 3.7 数据交换 API（优先级：低）

#### 3.7.1 AI 间数据交换

```python
# 需求描述
# 导出 AI 设计数据
export_data = doc.ExportAIData(
    format="json",  # 或 "xml", "protobuf"
    scope={"sketches": True, "features": True, "parameters": True}
)

# 导入 AI 设计数据
import_result = doc.ImportAIData(export_data, merge_mode="merge")

# 订阅设计变更
subscription = doc.SubscribeChanges(
    topics=["sketch_modified", "parameter_changed"],
    callback="http://ai-service/webhook"
)
```

**原因**：
- AI 间需要共享设计数据
- 支持事件驱动的协同
- 支持外部系统集成

---

## 四、API 优先级矩阵

| API 类别 | 具体功能 | 优先级 | 影响范围 | 实现难度 |
|----------|----------|--------|----------|----------|
| **协同管理** | AI 会话管理 | 🔴 高 | 核心 | 中 |
| | 操作日志 | 🔴 高 | 核心 | 中 |
| | 协作锁 | 🔴 高 | 核心 | 中 |
| **冲突检测** | 语义冲突检测 | 🔴 高 | 核心 | 高 |
| | 约束兼容性 | 🔴 高 | 核心 | 中 |
| **智能辅助** | 设计意图识别 | 🟡 中 | 增强 | 高 |
| | 约束推荐 | 🟡 中 | 增强 | 高 |
| | 设计验证 | 🟡 中 | 增强 | 中 |
| **参数化** | 参数管理 | 🟡 中 | 增强 | 低 |
| | 配置管理 | 🟡 中 | 增强 | 中 |
| **特征树** | 特征管理 | 🟡 中 | 增强 | 高 |
| **装配** | 多部件装配 | 🟢 低 | 扩展 | 高 |
| **数据交换** | AI 数据交换 | 🟢 低 | 扩展 | 中 |

---

## 五、推荐实施路线图

### 阶段一：基础协同（1-2 个月）

**目标**：实现基本的多 AI 协同能力

- [ ] AI 会话管理 API
- [ ] 操作日志 API
- [ ] 协作锁机制
- [ ] 约束兼容性分析

**预期效果**：多个 AI 可以安全地协作，避免冲突

### 阶段二：智能辅助（2-3 个月）

**目标**：增强 AI 的智能化能力

- [ ] 设计意图识别
- [ ] 约束推荐
- [ ] 参数管理
- [ ] 配置管理

**预期效果**：AI 可以更智能地理解设计意图，减少人工干预

### 阶段三：高级功能（3-6 个月）

**目标**：完善高级协同能力

- [ ] 语义冲突检测
- [ ] 设计验证
- [ ] 特征树 API
- [ ] 装配 API

**预期效果**：支持复杂的协同建模场景

---

## 六、总结

### 6.1 当前能力总结

| 能力维度 | 评分 | 说明 |
|----------|------|------|
| 基础建模 | ⭐⭐⭐⭐ | 2D/3D 建模能力完整 |
| 约束系统 | ⭐⭐⭐⭐ | 2D/3D 约束系统完善 |
| 查询分析 | ⭐⭐⭐ | 几何查询完善，语义分析缺失 |
| 协同能力 | ⭐ | 几乎空白 |
| 智能能力 | ⭐⭐ | 基础能力有限 |

### 6.2 关键缺口

1. **协同管理**：缺少 AI 会话、操作日志、协作锁
2. **冲突检测**：缺少语义级冲突预测
3. **智能辅助**：缺少意图理解、约束推荐
4. **参数化**：缺少参数管理和配置管理
5. **特征树**：NCTI 缺少特征树管理

### 6.3 建议

1. **优先实施协同管理 API**：这是 AI 协同的基础
2. **逐步增强智能能力**：可结合 AI 模型实现
3. **考虑扩展 NCTI 内核**：特征树管理需要内核支持
4. **建立 API 版本管理**：确保向后兼容

---

## 附录 A：参考文档

- [01-现有 API 盘点.md](./01-现有 API 盘点.md) - 现有 API 详细分析
- [skills/custom/sketch/SKILL.md](../../skills/custom/sketch/SKILL.md) - Sketch API 技能文档
- [skills/custom/ncti-commands/SKILL.md](../../skills/custom/ncti-commands/SKILL.md) - NCTI 命令技能文档

---

*文档生成时间：2026-08-10*
