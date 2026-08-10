# CAD 自动化建模 API 能力评估报告

**分析日期**: 2026-08-10  
**分析范围**: Sketch API (2D 草图) + NCTI API (3D 建模)

---

## 执行摘要

| 评估维度 | 评分 | 说明 |
|---------|------|------|
| 2D 草图绘制能力 | ⭐⭐⭐⭐⭐ | 完整，13 种几何 +12 种约束 |
| 3D 建模能力 | ⭐⭐⭐⭐ | 完整，338 个建模命令 |
| 参数化特征管理 | ⭐ | **严重缺失** |
| 装配约束系统 | ⭐⭐ | 基础 DCM 约束存在，但缺少装配级 API |
| 配置驱动建模 | ⭐ | **严重缺失** |
| 智能约束推荐 | ⭐ | **严重缺失** |
| 错误诊断与恢复 | ⭐⭐ | 基础查询存在，缺乏失败诊断 |

**总体结论**: 现有 API **满足基础建模需求**，但**不满足高效自动化建模需求**。

---

## 1. 现有 API 能力盘点

### 1.1 Sketch API (2D 草图)

| 能力类别 | 覆盖情况 | 详细能力 |
|---------|---------|---------|
| 几何绘制 | ✅ 完整 | 13 种：点、直线、中心线、样条、矩形、圆、圆弧、椭圆、椭圆弧、圆角、倒角、修剪、偏移 |
| 约束添加 | ✅ 完整 | 12 种：水平/竖直/长度/半径/角度尺寸 + 平行/垂直/相切/相等/水平对齐/竖直对齐/重合 |
| 约束编辑 | ✅ 完整 | 尺寸类可编辑 (EditSize/EditLocation)，几何类仅查询 |
| 对象管理 | ✅ 完整 | 命名 (SetObjectName)、按名获取 (GetObject)、删除 (Delete) |
| 求解控制 | ✅ 完整 | 自动求解开关、手动求解、弱约束开关 |

**优势**:
- API 设计清晰，参数化程度高
- 支持对象命名和增量编辑
- 约束系统完整

**局限**:
- 仅限 2D 草图，无 3D 直接能力
- 无特征树管理

### 1.2 NCTI API (3D 建模)

| 能力类别 | 命令数 | 详细能力 |
|---------|--------|---------|
| 基本体创建 | ✅ | 长方体、圆柱、圆锥、球体、圆环、平面、直线、顶点 |
| 布尔运算 | ✅ | 并集、差集、交集 |
| 特征操作 | ✅ | 圆角、倒角、拉伸、旋转、扫掠、放样 |
| 曲线/曲面 | ✅ | B 样条、贝塞尔、螺旋线/面 |
| DCM 约束 | ✅ | 3D 约束系统 (fix/add/evaluate/check) |
| 查询分析 | ✅ | 拓扑查询、特征识别、几何属性 |
| 文件操作 | ✅ | 保存、打开、导出、格式转换 |

**优势**:
- 建模命令丰富 (338 个)
- 支持多种文件格式互操作
- 有基础的特征识别能力

**局限**:
- **命令式 API**，缺少参数化特征历史
- DCM 约束系统复杂，需要手动管理
- 无装配约束 API

---

## 2. 自动化建模核心需求分析

### 2.1 典型自动化建模场景

| 场景 | 描述 | 所需 API 能力 |
|------|------|-------------|
| **参数化设计** | 通过修改参数驱动模型变化 | 特征参数查询/修改 |
| **系列化建模** | 批量生成不同规格的模型 | 配置/参数表管理 |
| **装配体建模** | 多部件装配与约束 | 装配约束 API |
| **模板复用** | 基于模板快速建模 | 模板实例化 API |
| **智能设计** | 自动添加约束/优化 | 约束推荐 API |
| **错误恢复** | 建模失败后诊断修复 | 失败诊断 API |

### 2.2 需求优先级排序

| 优先级 | 需求 | 影响范围 |
|-------|------|---------|
| 🔴 高 | 特征参数管理 | 所有参数化建模 |
| 🔴 高 | 配置驱动建模 | 系列化产品 |
| 🟡 中 | 装配约束系统 | 装配体设计 |
| 🟡 中 | 约束推荐 | 草图建模效率 |
| 🟢 低 | 模板化建模 | 快速原型 |
| 🟢 低 | 错误诊断 | 用户体验 |

---

## 3. API 缺口分析

### 3.1 严重缺口 (影响核心能力)

#### 缺口 1: 特征参数管理缺失

**问题**: 现有 API 只有命令式建模，没有参数化特征树管理。

**影响**:
- 无法查询已有特征的参数
- 无法修改已有特征的参数
- 每次修改需要重新建模

**示例对比**:
```python
# ❌ 现有方式：无法修改已有特征
box = NCTI.Primitive.Box(10, 10, 10)  # 创建后无法修改尺寸

# ✅ 期望方式：参数化特征管理
feature = doc.GetFeature("box_1")      # 获取特征
feature.SetParam("width", 20)          # 修改参数
feature.Rebuild()                      # 重新生成
```

#### 缺口 2: 配置/参数表管理缺失

**问题**: 无配置驱动机制，无法批量生成系列化模型。

**影响**:
- 无法从 Excel/CSV 批量导入参数
- 无法管理多配置版本
- 系列化建模需要重复编写脚本

**期望 API**:
```python
# 期望的配置驱动 API
config = doc.LoadConfig("config.xlsx")  # 加载配置表
for params in config.Rows:              # 遍历配置
    model = Template.Build("bracket", params)
    model.Save(f"bracket_{params['size']}.yha")
```

### 3.2 中度缺口 (影响效率)

#### 缺口 3: 装配约束系统不完整

**问题**: DCM 约束主要用于草图，缺少部件级装配约束。

**影响**:
- 无法定义部件间的装配关系
- 无法进行装配体参数化设计
- 装配需要手动对齐

**期望 API**:
```python
# 期望的装配约束 API
asm = doc.GetAssembly()
asm.AddPart("shaft", "shaft.yha")
asm.AddPart("bearing", "bearing.yha")
asm.AddConstraint("coaxial", "shaft.axis", "bearing.hole")
asm.AddConstraint("mate", "shaft.step", "bearing.face")
```

#### 缺口 4: 智能约束推荐缺失

**问题**: 添加约束需要手动分析，无法自动推荐。

**影响**:
- 草图约束依赖人工判断
- 容易过约束或欠约束
- 自动化程度低

**期望 API**:
```python
# 期望的智能约束 API
skt = yh_doc.GetActivitySketch()
recommendations = skt.AnalyzeGeometry()  # 分析几何
for cons in recommendations:             # 获取推荐约束
    if cons.Type == "parallel":
        skt.AddConsParallel(cons.Obj1, cons.Obj2)
```

### 3.3 轻度缺口 (影响体验)

#### 缺口 5: 模板化建模支持不足

**问题**: 无模板实例化机制。

**期望 API**:
```python
# 期望的模板 API
template = doc.LoadTemplate("bracket_template.yha")
model = template.Instantiate({
    "length": 100,
    "width": 50,
    "hole_diameter": 10
})
```

#### 缺口 6: 错误诊断能力弱

**问题**: 建模失败后缺乏诊断信息。

**期望 API**:
```python
# 期望的诊断 API
try:
    skt.RunSolve()
except SolveError as e:
    diag = e.Diagnose()  # 获取诊断信息
    print(f"过约束对象：{diag.OverdefinedObjects}")
    print(f"建议：{diag.Recommendations}")
```

---

## 4. 新增 API 建议

### 4.1 高优先级 API

#### API 1: 特征参数管理

| 项目 | 内容 |
|------|------|
| **API 名称** | `FeatureManager` |
| **功能** | 查询/修改特征参数，触发重新生成 |
| **核心方法** | `GetFeature(name)`, `SetParam(feature, param, value)`, `Rebuild(feature)` |
| **优先级** | 🔴 高 |
| **理由** | 参数化建模的核心能力 |

**接口设计**:
```python
class FeatureManager:
    def GetFeature(self, name: str) -> Feature:
        """获取指定名称的特征"""
        pass
    
    def GetFeatureList(self) -> List[Feature]:
        """获取所有特征列表"""
        pass
    
    def SetParam(self, feature: Feature, param: str, value: float) -> bool:
        """设置特征参数"""
        pass
    
    def Rebuild(self, feature: Feature = None) -> bool:
        """重新生成特征，None 表示重建全部"""
        pass
    
    def GetParam(self, feature: Feature, param: str) -> float:
        """获取特征参数值"""
        pass
```

#### API 2: 配置驱动建模

| 项目 | 内容 |
|------|------|
| **API 名称** | `ConfigManager` |
| **功能** | 加载配置表，批量生成模型 |
| **核心方法** | `LoadConfig(path)`, `GetConfig(key)`, `BuildSeries(template, config)` |
| **优先级** | 🔴 高 |
| **理由** | 系列化产品建模的核心需求 |

**接口设计**:
```python
class ConfigManager:
    def LoadConfig(self, path: str, format: str = "xlsx") -> Config:
        """从文件加载配置 (支持 xlsx/csv/json)"""
        pass
    
    def GetRowCount(self) -> int:
        """获取配置行数"""
        pass
    
    def GetRow(self, index: int) -> Dict[str, Any]:
        """获取指定行的参数"""
        pass
    
    def BuildSeries(self, template: str, output_dir: str) -> List[str]:
        """批量生成系列化模型，返回生成的文件列表"""
        pass
```

### 4.2 中优先级 API

#### API 3: 装配约束系统

| 项目 | 内容 |
|------|------|
| **API 名称** | `AssemblyManager` |
| **功能** | 管理装配体，添加装配约束 |
| **核心方法** | `AddPart()`, `AddConstraint()`, `SolveAssembly()` |
| **优先级** | 🟡 中 |
| **理由** | 装配体设计必需 |

**接口设计**:
```python
class AssemblyManager:
    def AddPart(self, path: str, name: str, position: Point = None) -> Part:
        """添加部件到装配体"""
        pass
    
    def AddConstraint(self, type: str, obj1: str, obj2: str, 
                      param: float = None) -> Constraint:
        """添加装配约束 (coaxial/mate/angle/offset 等)"""
        pass
    
    def SolveAssembly(self) -> bool:
        """求解装配约束"""
        pass
    
    def GetSubAssembly(self) -> List[SubAssembly]:
        """获取子装配结构"""
        pass
```

#### API 4: 智能约束推荐

| 项目 | 内容 |
|------|------|
| **API 名称** | `ConstraintAdvisor` |
| **功能** | 分析草图几何，推荐约束 |
| **核心方法** | `AnalyzeGeometry()`, `GetRecommendations()`, `ApplyRecommended()` |
| **优先级** | 🟡 中 |
| **理由** | 提升草图建模效率 |

**接口设计**:
```python
class ConstraintAdvisor:
    def AnalyzeGeometry(self, sketch: SketchWorkPlane) -> AnalysisResult:
        """分析草图几何，识别潜在约束"""
        pass
    
    def GetRecommendations(self) -> List[Recommendation]:
        """获取推荐约束列表"""
        pass
    
    def ApplyRecommended(self, sketch: SketchWorkPlane, 
                         filter: str = None) -> List[Constraint]:
        """应用推荐约束，可选过滤类型"""
        pass
```

### 4.3 低优先级 API

#### API 5: 模板化建模

| 项目 | 内容 |
|------|------|
| **API 名称** | `TemplateManager` |
| **功能** | 加载模板，实例化参数化模型 |
| **优先级** | 🟢 低 |

#### API 6: 错误诊断

| 项目 | 内容 |
|------|------|
| **API 名称** | `ErrorDiagnoser` |
| **功能** | 诊断建模失败原因，提供修复建议 |
| **优先级** | 🟢 低 |

---

## 5. 实施建议

### 5.1 分阶段实施

| 阶段 | 内容 | 预期周期 |
|------|------|---------|
| **第一阶段** | 实现 FeatureManager 特征参数管理 | 2-3 周 |
| **第二阶段** | 实现 ConfigManager 配置驱动建模 | 1-2 周 |
| **第三阶段** | 实现 AssemblyManager 装配约束 | 2-3 周 |
| **第四阶段** | 实现 ConstraintAdvisor 智能约束 | 2-3 周 |
| **第五阶段** | 实现 TemplateManager 和 ErrorDiagnoser | 1-2 周 |

### 5.2 技术路线

1. **特征参数管理**: 需要与 NCTI 内核深度集成，获取特征参数化信息
2. **配置驱动**: 可在现有 API 之上封装，实现配置解析和批量生成
3. **装配约束**: 需要扩展 DCM 约束系统到部件级
4. **智能约束**: 可考虑引入规则引擎或轻量 ML 模型

### 5.3 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| NCTI 内核不支持特征参数查询 | 高 | 与 NCTI 厂商沟通，或实现特征重放机制 |
| 装配约束复杂度高 | 中 | 先实现基本约束类型，逐步扩展 |
| 智能约束准确率低 | 低 | 先实现规则-based，逐步引入 ML |

---

## 6. 结论

1. **现有 API 基础能力完整** - 2D 草图和 3D 建模命令覆盖充分
2. **自动化能力严重不足** - 缺少参数化特征管理、配置驱动等核心能力
3. **建议优先实施特征参数管理 API** - 这是参数化建模的基础
4. **配置驱动建模次之** - 对系列化产品至关重要
5. **装配和智能约束作为后续增强** - 提升整体自动化水平

---

*报告生成时间：2026-08-10*  
*分析工具：Sketch API + NCTI API 文档分析*
