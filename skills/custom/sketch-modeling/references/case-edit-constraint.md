# 编辑约束对象 (Edit Constraints)

适用场景：修改已创建约束的尺寸值或位置。

## 通用编辑方法

基准 3.4 为水平、竖直、角度、半径、长度 5 种尺寸约束给出以下 4 个编辑方法：

| 方法 | 参数 | 说明 |
|------|------|------|
| `EditSize(dSize)` | float | 编辑尺寸（dSize 为浮点尺寸值） |
| `EditLocation(pt)` | NCTI.Point | 编辑位置（pt 为位置点坐标，基准未进一步说明其语义） |
| `Size()` | — | 获取尺寸 |
| `ObjectName()` | — | 获取对象名 |

## 获取约束对象

```python
# 方式一：创建时捕获返回值
cons1 = skt.AddConsLength(0, l1)

# 方式二：通过名称获取
cons1 = skt.GetObject("constraint_name")
```

## 各约束类型的创建方式

| 约束类型 | 创建语句 |
|----------|----------|
| 水平尺寸 | `cons1 = skt.AddConsXpos(0, l1)` |
| 竖直尺寸 | `cons1 = skt.AddConsYpos(0, l1)` |
| 长度尺寸 | `cons1 = skt.AddConsLength(0, l1)` |
| 半径尺寸 | `cons1 = skt.AddConsRadius(10, NCTI.Point(0, 0, 0))` |
| 角度尺寸 | `cons1 = skt.AddConsAngle(l1)` |

获取对象后，统一调用编辑方法：

```python
cons1.EditSize(50.0)                     # 编辑尺寸
cons1.EditLocation(NCTI.Point(10, 5, 0)) # 编辑位置
current = cons1.Size()                   # 获取尺寸
name = cons1.ObjectName()                # 获取对象名
```

---

## 完整代码示例

**示例：绘制直线 → 添加长度约束 → 编辑约束值**

```python
skt = NCTI.SketchWorkPlane(doc)
skt.Open()

# 绘制直线
l1 = skt.AddLine(NCTI.Point(0, 0, 0), NCTI.Point(20, 0, 0))

# 添加长度约束
cons1 = skt.AddConsLength(0, l1)

# 编辑约束值
cons1.EditSize(50.0)

# 获取尺寸
print(cons1.Size())

skt.Close()
```

**示例：绘制圆 → 添加半径约束 → 编辑半径值**

```python
skt = NCTI.SketchWorkPlane(doc)
skt.Open()

# 绘制圆
c1 = skt.AddCircle(NCTI.Point(0, 0, 0), 10)

# 添加半径约束（约束半径 15，与圆半径 10 不同）
cons1 = skt.AddConsRadius(15, NCTI.Point(0, 0, 0))

# 修改半径
cons1.EditSize(15.0)

skt.Close()
```

## 注意事项

- 编辑约束前必须先获取约束对象（创建时捕获或 GetObject）。
- `EditSize(dSize)`：dSize 为浮点尺寸值（基准 3.4 标注 dSize 为"浮点类型的数值"）。
- `EditLocation(pt)`：pt 为位置点坐标（基准 3.4 标注 pt 为"位置点坐标"，未进一步说明其几何语义）。
- 建议在创建约束后立即赋变量名，方便后续编辑引用。
- **各约束类型对编辑方法的支持范围以炎核文档为准**：API 文档（用户手册 3.4）明示水平、竖直、长度、半径、角度 5 种尺寸约束支持 `EditSize`/`EditLocation`/`Size`/`ObjectName`；Python 方法表额外显示平行约束（`SketchConsParallel`）也支持 `EditSize`/`EditLocation`/`Size`/`ObjectName`（以及 `OpenSize`/`CloseSize`）。其余约束类型是否可编辑，两份文档均未明示，使用前需实测确认。
