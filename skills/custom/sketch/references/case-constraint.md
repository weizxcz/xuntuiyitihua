# 创建约束对象 (Constraints)

适用场景：为草图中的几何对象添加尺寸约束或几何约束。

> **重要：仅使用参数化 API 版本。** 各约束的无参方法（形如 `AddConsXpos()`）需配合 GUI 手动选中对象，agent 不可使用，本文件不收录。
>
> 约束对象创建后通常需要赋变量名（如 `cons1 = skt.AddConsXpos(...)`），以便后续编辑（见 `case-edit-constraint.md`）。
>
> `index` / `indexN`：绘图对象的整型点索引（控制点序号）。`SketchObject` / `SketchObjectN`：绘图对象实例变量（如 l1、c1）。

---

## 尺寸约束 (Dimension Constraints)

### 1. 水平尺寸约束 (Horizontal Dimension)

为对象添加水平尺寸约束（计算某点与原点、或两点之间的水平距离）。

**单对象（该对象点与原点的水平距离）：**
`cons1 = skt.AddConsXpos(index, sketchObject)`

**双对象（两个对象点之间的水平距离）：**
`cons1 = skt.AddConsXpos(index1, sketchObject1, index2, sketchObject2)`

| 参数 | 类型 | 说明 |
|------|------|------|
| index | int | 要添加水平尺寸约束的对象的点索引 |
| sketchObject | SketchObject | 草图对象 |
| index1/index2 | int | 两对象之间约束时，对象一/对象二的点索引 |
| sketchObject1/sketchObject2 | SketchObject | 两对象之间约束时的对象一/对象二 |

```python
yh_doc = YH.YHDocument(doc)
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
yh_doc.AutoSolve(False)
yh_doc.AutoCalFreeCons(False)
c1 = skt.AddCircle(NCTI.Point(0, 0, 0), 10)
l1 = skt.AddLine(NCTI.Point(10, 0, 0), NCTI.Point(5, 20, 0))

# 单对象：c1 的点 0 与原点的水平距离
skt.AddConsXpos(0, c1)

# 双对象：c1 的点 0 与 l1 的点 1 之间的水平距离
skt.AddConsXpos(0, c1, 1, l1)
```

### 2. 竖直尺寸约束 (Vertical Dimension)

为对象添加竖直尺寸约束。参数与水平尺寸约束完全一致。

**单对象：** `cons1 = skt.AddConsYpos(index, sketchObject)`
**双对象：** `cons1 = skt.AddConsYpos(index1, sketchObject1, index2, sketchObject2)`

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
l1 = skt.AddLine(NCTI.Point(10, 10, 0), NCTI.Point(20, 20, 0))
cons1 = skt.AddConsYpos(0, l1, 1, l1)
```

### 3. 长度尺寸约束 (Length Dimension)

为直线对象添加长度尺寸约束，或为两点之间、点与线之间添加长度约束。

**单对象：** `cons1 = skt.AddConsLength(index, sketchObject)`
**双对象：** `cons1 = skt.AddConsLength(index1, sketchObject1, index2, sketchObject2)`

参数同水平尺寸约束。

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
l1 = skt.AddLine(NCTI.Point(10, 10, 0), NCTI.Point(20, 20, 0))
cons1 = skt.AddConsLength(0, l1, 1, l1)
```

### 4. 半径尺寸约束 (Radius Dimension)

为圆、圆弧添加半径尺寸约束。

**方式一（推荐）：传入圆/圆弧对象**
`cons1 = skt.AddConsRadius(sketchObject)`

| 参数 | 类型 | 说明 |
|------|------|------|
| sketchObject | SketchObject | 圆或者圆弧对象 |

**方式二：通过半径值与圆心定位**
`cons1 = skt.AddConsRadius(radius, center)`

| 参数 | 类型 | 说明 |
|------|------|------|
| radius | float | 半径值 |
| center | NCTI.Point | 圆心坐标 |

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
c1 = skt.AddCircle(NCTI.Point(0, 0, 0), 10)

# 方式一：传入圆/圆弧对象
cons1 = skt.AddConsRadius(c1)

# 方式二：半径值 + 圆心
# cons2 = skt.AddConsRadius(15, NCTI.Point(0, 0, 0))
```

### 5. 角度尺寸约束 (Angle Dimension)

为对象添加角度尺寸约束。

**单对象（该直线与 X 轴的夹角）：**
`cons1 = skt.AddConsAngle(sketchObject)`

**双对象（两条直线之间的夹角）：**
`cons1 = skt.AddConsAngle(sketchObject1, sketchObject2)`

| 参数 | 类型 | 说明 |
|------|------|------|
| sketchObject | SketchObject | 直线对象（单对象版：与 X 轴夹角） |
| sketchObject1/sketchObject2 | SketchObject | 两条直线对象（双对象版：两线夹角） |

> 单对象版默认是该直线与 X 轴的角度；也可传入直线对象与坐标轴对象（如 `skt.GetXAxis()`）。

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
l1 = skt.AddLine(NCTI.Point(10, 0, 0), NCTI.Point(5, 20, 0))
l2 = skt.AddLine(NCTI.Point(10, 30, 0), NCTI.Point(40, 20, 0))

# 单对象：l1 与 X 轴的夹角
skt.AddConsAngle(l1)

# 直线与坐标轴
skt.AddConsAngle(l1, skt.GetXAxis())

# 两条直线之间的夹角
skt.AddConsAngle(l1, l2)
```

---

## 几何约束 (Geometric Constraints)

### 6. 平行约束 (Parallel)

为两个绘图对象添加平行约束。

`cons1 = skt.AddConsParallel(sketchObject1, sketchObject2)`

| 参数 | 类型 | 说明 |
|------|------|------|
| sketchObject1 | SketchObject | 对象一 |
| sketchObject2 | SketchObject | 对象二 |

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
a1 = skt.AddLine(NCTI.Point(5, 5, 0), NCTI.Point(15, 15, 0))
a2 = skt.AddLine(NCTI.Point(20, 5, 0), NCTI.Point(20, 15, 0))
cons1 = skt.AddConsParallel(a1, a2)
```

> 平行约束支持 `EditSize` 编辑两线夹角（平行 = 180°），编辑前需先 `OpenSize()`，详见 `case-edit-constraint.md`。

### 7. 垂直约束 (Perpendicular — API: AddConsVertical)

为两个直线对象添加垂直约束（两线互相垂直，即 90° 关系）。

`cons1 = skt.AddConsVertical(sketchObject1, sketchObject2)`

| 参数 | 类型 | 说明 |
|------|------|------|
| sketchObject1 | SketchObject | 直线对象一 |
| sketchObject2 | SketchObject | 直线对象二 |

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
l1 = skt.AddLine(NCTI.Point(10, 0, 0), NCTI.Point(5, 20, 0))
l2 = skt.AddLine(NCTI.Point(10, 30, 0), NCTI.Point(30, 20, 0))
cons1 = skt.AddConsVertical(l1, l2)
```

> 注意：此处的「垂直」指两对象互相垂直（Perpendicular），API 名为 `AddConsVertical`。与第 11 节的「竖直约束」（沿 Y 轴对齐，API 为 `AddConsYAxis`）是不同类型，仅 API 名相似，以 API 名为准。

### 8. 相切约束 (Tangent)

为两个绘图对象添加相切约束。

`cons1 = skt.AddConsTangent(sketchObject1, sketchObject2)`

| 参数 | 类型 | 说明 |
|------|------|------|
| sketchObject1 | SketchObject | 对象一 |
| sketchObject2 | SketchObject | 对象二（可为直线对象） |

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
c1 = skt.AddCircle(NCTI.Point(0, 0, 0), 10)
l2 = skt.AddLine(NCTI.Point(10, 30, 0), NCTI.Point(40, 20, 0))
cons1 = skt.AddConsTangent(c1, l2)
```

### 9. 相等约束 (Equal)

为绘图对象添加相等约束。

**单对象：** `skt.AddConsEqual(sketchObject1)`
**双对象：** `cons1 = skt.AddConsEqual(sketchObject1, sketchObject2)`

| 参数 | 类型 | 说明 |
|------|------|------|
| sketchObject1 | SketchObject | 对象一 |
| sketchObject2 | SketchObject | 对象二，须与对象一类型相同（可选） |

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
a1 = skt.AddLine(NCTI.Point(10, 10, 0), NCTI.Point(20, 20, 0))
a2 = skt.AddLine(NCTI.Point(21, 20, 0), NCTI.Point(40, 10, 0))
cons1 = skt.AddConsEqual(a1, a2)
```

### 10. 水平约束 (Horizontal Alignment — API: AddConsXAxis)

使直线水平，或使两个点沿水平方向对齐。

**单对象（使该线水平）：** `cons1 = skt.AddConsXAxis(sketchObject1)`

**双对象（两个点沿水平方向对齐）：** `cons1 = skt.AddConsXAxis(index1, sketchObject1, index2, sketchObject2)`

| 参数 | 类型 | 说明 |
|------|------|------|
| sketchObject1 | SketchObject | 单对象模式：使其水平的线对象 |
| index1/index2 | int | 双对象模式：对象一/对象二的点索引 |
| sketchObject1/sketchObject2 | SketchObject | 双对象模式：两个对象 |

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
a1 = skt.AddLine(NCTI.Point(10, 10, 0), NCTI.Point(20, 20, 0))
# 单对象：使 a1 水平
cons1 = skt.AddConsXAxis(a1)
```

双对象（两个点沿水平方向对齐）：
```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
a1 = skt.AddLine(NCTI.Point(10, 10, 0), NCTI.Point(20, 20, 0))
a2 = skt.AddLine(NCTI.Point(30, 10, 0), NCTI.Point(40, 20, 0))
# a1 的点 0 与 a2 的点 1 沿水平方向对齐
cons2 = skt.AddConsXAxis(0, a1, 1, a2)
```

### 11. 竖直约束 (Vertical Alignment — API: AddConsYAxis)

使直线竖直，或使两个点沿竖直方向对齐。

**单对象：** `cons1 = skt.AddConsYAxis(sketchObject1)`
**双对象：** `cons1 = skt.AddConsYAxis(index1, sketchObject1, index2, sketchObject2)`

参数模式同水平约束。

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
a1 = skt.AddLine(NCTI.Point(10, 10, 0), NCTI.Point(20, 20, 0))
# 单对象：使 a1 竖直
cons1 = skt.AddConsYAxis(a1)
```

双对象（两个点沿竖直方向对齐）：
```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
a1 = skt.AddLine(NCTI.Point(10, 10, 0), NCTI.Point(20, 20, 0))
a2 = skt.AddLine(NCTI.Point(30, 10, 0), NCTI.Point(40, 20, 0))
# a1 的点 0 与 a2 的点 1 沿竖直方向对齐
cons2 = skt.AddConsYAxis(0, a1, 1, a2)
```

> 注意：此处的「竖直」指沿 Y 轴方向对齐，API 为 `AddConsYAxis`。与第 7 节的「垂直约束」（两对象 90° 关系，API 为 `AddConsVertical`）是不同类型。

### 12. 重合约束 (Coincide)

使两个点重合，或在点与线、线与线之间创建共线约束（两点重合、点线重合、线线重合）。

**单对象：** `cons1 = skt.AddConsCoincide(index1, sketchObject1)`
**双对象：** `cons1 = skt.AddConsCoincide(index1, sketchObject1, index2, sketchObject2)`

| 参数 | 类型 | 说明 |
|------|------|------|
| index1 | int | 对象一的点索引 |
| sketchObject1 | SketchObject | 对象一 |
| index2 | int | 对象二的点索引（可选） |
| sketchObject2 | SketchObject | 对象二（可选） |

单对象（与基准共点）：
```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
a1 = skt.AddLine(NCTI.Point(10, 10, 0), NCTI.Point(20, 20, 0))
# a1 的点 0 重合约束
cons1 = skt.AddConsCoincide(0, a1)
```

双对象（两点重合 / 共线）：
```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
a1 = skt.AddLine(NCTI.Point(10, 10, 0), NCTI.Point(20, 20, 0))
a2 = skt.AddLine(NCTI.Point(21, 20, 0), NCTI.Point(30, 10, 0))
# a1 的点 1 与 a2 的点 0 重合
cons2 = skt.AddConsCoincide(1, a1, 0, a2)
```

---

## 约束显示与属性控制 (Display & Property Control)

以下方法用于控制约束的显示状态与属性，挂在 `skt` 上。涉及「名称列表」参数时，对象名来自左侧对象树或 `skt.GetObject()`。

### 13. 切换约束对象显示

`skt.SwitchConsDisplay()` — 无参数。切换草图约束图形的显示 / 隐藏状态。

```python
skt.SwitchConsDisplay()
```

### 14. 显示 / 隐藏约束

全局控制所有约束显示隐藏，或单独控制指定约束列表显示隐藏。

**全局：** `skt.ShowCons(mode)` — mode 为 1 显示全部约束 / 0 隐藏全部约束
**指定约束：** `skt.ShowCons(mode, consList)` — 控制给定约束对象列表

| 参数 | 类型 | 说明 |
|------|------|------|
| mode | int | 1 显示 / 0 隐藏 |
| consList | list | 约束对象列表（可选） |

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
consAngle = skt.GetObject("yhc...")     # 通过对象名获取约束对象
skt.ShowCons(1, [consAngle])            # 显示该约束
skt.ShowCons(0)                         # 隐藏全部约束
```

### 15. 半径尺寸互切直径

切换半径尺寸约束为直径尺寸、或直径切换为半径。

**按名称：** `skt.SwitchConsRadius("yhc...")` — 参数：约束对象名称
**按对象：** `skt.SwitchConsRadius(consRadius)` — 参数：约束对象

```python
consRadius = skt.GetObject("yhc..")
skt.SwitchConsRadius(consRadius)
```

### 16. 固定约束

给草图图元添加固定约束，锁定图元位置不可拖动。

`skt.FixedCons(sketchObject)`

| 参数 | 类型 | 说明 |
|------|------|------|
| sketchObject | SketchObject | 需要固定的草图几何对象 |

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
c1 = skt.AddCircle(NCTI.Point(0, 0, 0), 10)
skt.FixedCons(c1)
```

### 17. 设置为构造线

将几何图元切换为构造线 / 普通实线。

`skt.Tectonicline(mode, nameList)`

| 参数 | 类型 | 说明 |
|------|------|------|
| mode | int | 1 构造线 / 0 非构造线 |
| nameList | list[str] | 几何对象名称列表 |

```python
skt.Tectonicline(1, ["yhdxxx"])
```

### 18. 固定尺寸

锁定 / 解锁尺寸约束，锁定后尺寸不可修改。

`skt.LockSize(mode, nameList)`

| 参数 | 类型 | 说明 |
|------|------|------|
| mode | int | 1 锁定 / 0 解锁 |
| nameList | list[str] | 尺寸约束名称列表 |

```python
skt.LockSize(1, ["yhdxxx"])
```

### 19. 参考尺寸

将尺寸约束切换为参考尺寸 / 驱动尺寸。

`skt.ConsRef(mode, nameList)`

| 参数 | 类型 | 说明 |
|------|------|------|
| mode | int | 1 参考 / 0 非参考 |
| nameList | list[str] | 尺寸约束名称列表 |

```python
skt.ConsRef(1, ["yhdxxx"])
```

### 20. 长度尺寸约束切换显示模式

切换长度尺寸约束显示样式。

`skt.SwitchConsLength(consL)`

| 参数 | 类型 | 说明 |
|------|------|------|
| consL | 长度尺寸约束对象 | 长度尺寸约束对象 |

```python
consL = skt.GetObject("yhc..")
skt.SwitchConsLength(consL)
```

### 21. 设置约束类型

将约束切换为强约束 / 弱约束。

`skt.ConsType(mode, nameList)`

| 参数 | 类型 | 说明 |
|------|------|------|
| mode | int | 1 强约束 / 0 弱约束 |
| nameList | list[str] | 约束名称列表 |

```python
skt.ConsType(1, ["yhcxxx"])
```

---

## 完整代码示例

**示例：绘制直线并添加水平、竖直尺寸约束**

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
skt.Open()

# 绘制一条直线
l1 = skt.AddLine(NCTI.Point(0, 0, 0), NCTI.Point(20, 30, 0))

# 添加水平尺寸约束
cons1 = skt.AddConsXpos(0, l1)

# 添加竖直尺寸约束
cons2 = skt.AddConsYpos(0, l1)

skt.Close()
```

**示例：绘制直线并添加平行和长度约束**

```python
yh_doc = YH.YHDocument(doc)
yh_doc.AutoSolve(False)
yh_doc.AutoCalFreeCons(False)

skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
skt.Open()

# 绘制两条直线
l1 = skt.AddLine(NCTI.Point(0, 0, 0), NCTI.Point(20, 0, 0))
l2 = skt.AddLine(NCTI.Point(0, 10, 0), NCTI.Point(20, 10, 0))

# 添加平行约束
skt.AddConsParallel(l1, l2)

# 添加长度约束
cons1 = skt.AddConsLength(0, l1)

skt.Close()
```

## 注意事项

- 约束操作前必须有已创建的几何对象（通过绘制操作返回的变量）。
- 尺寸约束（水平 / 竖直 / 长度）的单/双对象重载均带 `index` 点索引。
- 半径尺寸约束优先使用对象重载 `AddConsRadius(sketchObject)`；半径值 + 圆心的重载用于按值定位。
- 角度尺寸约束：单对象 = 该直线与 X 轴夹角；双对象 = 两直线夹角；无 `index`。
- 几何约束中：平行、垂直、相切接收两个 SketchObject，无 `index`；相等接收一个或两个 SketchObject；水平(XAxis)、竖直(YAxis)的单对象重载无 `index`，双对象重载为 `(index, SketchObject, index, SketchObject)`；重合(Coincide)的单/双对象重载均带 `index`。
- 创建约束后建议立即赋变量名，便于后续编辑与查询。
- 约束的编辑/查询方法见 `case-edit-constraint.md`。
