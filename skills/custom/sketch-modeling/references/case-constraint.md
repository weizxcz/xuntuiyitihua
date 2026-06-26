# 创建约束对象 (Constraints)

适用场景：为草图中的几何对象添加尺寸约束或几何约束。

**重要说明：**
- 仅使用参数化 API 版本。无参方法需配合 GUI 手动选中对象，agent 不可使用。
- `index`（控制点序号）：标识对象的第几个控制点。两份基准文档均未给出各几何类型具体的控制点编号规则，使用 index 前需实测确认具体编号对应的几何点。
- `SketchObjectN`：绘图对象实例变量（如 l1, c1 等通过绘制操作返回的对象）。

---

## 尺寸约束 (Dimension Constraints)

### 1. 水平尺寸约束 (Horizontal Dimension)

为给定对象添加水平尺寸约束。

**单对象：**
```python
cons1 = skt.AddConsXpos(0, l1)
```

**双对象：**
```python
cons1 = skt.AddConsXpos(0, l1, 1, l2)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| index | int | 对象控制点序号 |
| obj | SketchObject | 绘图对象变量 |
| index2 | int | 第二个对象控制点序号（可选） |
| obj2 | SketchObject | 第二个绘图对象变量（可选） |

### 2. 竖直尺寸约束 (Vertical Dimension)

为给定对象添加竖直尺寸约束。

**单对象：**
```python
cons1 = skt.AddConsYpos(0, l1)
```

**双对象：**
```python
cons1 = skt.AddConsYpos(0, l1, 1, l2)
```

参数同水平尺寸约束。

### 3. 长度尺寸约束 (Length Dimension)

为给定对象添加长度尺寸约束。

**单对象：**
```python
cons1 = skt.AddConsLength(0, l1)
```

**双对象：**
```python
cons1 = skt.AddConsLength(0, l1, 1, l2)
```

参数同水平尺寸约束。

### 4. 半径尺寸约束 (Radius Dimension)

为圆、圆弧添加半径尺寸约束。通过半径值和圆心定位目标对象。

```python
cons1 = skt.AddConsRadius(3.5, NCTI.Point(5, 20, 0))
```

| 参数 | 类型 | 说明 |
|------|------|------|
| radius | float | 半径值 |
| center | NCTI.Point | 圆心坐标 |

### 5. 角度尺寸约束 (Angle Dimension)

为给定对象添加角度尺寸约束。

**单对象：**
```python
cons1 = skt.AddConsAngle(l1)
```

**双对象：**
```python
cons1 = skt.AddConsAngle(l1, l2)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| obj1 | SketchObject | 第一个对象变量 |
| obj2 | SketchObject | 第二个对象变量（可选） |

注意：角度约束无 index 参数。基准 Python 方法表的示例形式：单对象版对一条直线调用 `skt.AddConsAngle(line1)`；双对象版将同一圆弧传两次 `skt.AddConsAngle(arc1, arc1)`。两种重载的具体几何语义基准未进一步说明。

---

## 几何约束 (Geometric Constraints)

### 6. 平行约束 (Parallel)

为两个绘图对象添加平行约束。

```python
skt.AddConsParallel(l1, l2)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| obj1 | SketchObject | 第一个对象 |
| obj2 | SketchObject | 第二个对象 |

### 7. 垂直约束 (Perpendicular — API: AddConsVertical)

为两个绘图对象添加垂直约束。

```python
skt.AddConsVertical(l1, l2)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| obj1 | SketchObject | 第一个对象 |
| obj2 | SketchObject | 第二个对象 |

注意：此处的"垂直"指两对象互相垂直（90°关系），对应英文 Perpendicular，但 API 命名为 `AddConsVertical`（沿用了 Vertical 字样）。与第 11 节的"竖直对齐"（沿 Y 轴方向，API 为 `AddConsYAxis`）是不同的约束类型，二者仅 API 名相似，语义不同，使用时以 API 名为准。

### 8. 相切约束 (Tangent)

为两个绘图对象添加相切约束。

```python
c1 = skt.AddCircle(NCTI.Point(0, 0, 0), 10)
l1 = skt.AddLine(NCTI.Point(-20, 10, 0), NCTI.Point(20, 10, 0))
skt.AddConsTangent(l1, c1)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| obj1 | SketchObject | 第一个对象 |
| obj2 | SketchObject | 第二个对象 |

### 9. 相等约束 (Equal)

为两个绘图对象添加相等约束。

**单对象：**
```python
skt.AddConsEqual(l1)
```

**双对象：**
```python
skt.AddConsEqual(l1, l2)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| obj1 | SketchObject | 第一个对象 |
| obj2 | SketchObject | 第二个对象，必须与 obj1 类型相同（可选） |

### 10. 水平约束 (Horizontal Alignment)

使线水平或使两个点沿水平方向对齐。

**单对象（传对象即可，无 index）：**
```python
skt.AddConsXAxis(l1)
```

**双对象（index + 对象配对）：**
```python
skt.AddConsXAxis(0, l1, 1, l2)
```

| 模式 | 参数 | 类型 | 说明 |
|------|------|------|------|
| 单对象 | obj | SketchObject | 线对象，使其水平 |
| 双对象 | index1 | int | 第一个对象控制点序号 |
| | obj1 | SketchObject | 第一个对象 |
| | index2 | int | 第二个对象控制点序号 |
| | obj2 | SketchObject | 第二个对象 |

### 11. 竖直约束 (Vertical Alignment)

使线竖直或使两个点沿竖直方向对齐。

**单对象：**
```python
skt.AddConsYAxis(l1)
```

**双对象：**
```python
skt.AddConsYAxis(0, l1, 1, l2)
```

参数模式同水平约束。

注意：此处的"竖直"指沿 Y 轴方向对齐，API 为 `AddConsYAxis`。与第 7 节的"垂直约束"（两对象 90°关系，API 为 `AddConsVertical`）是不同的约束类型。

### 12. 重合约束 (Coincide)

使两个点重合，或创建点线、线线共线约束。

**单对象：**
```python
skt.AddConsCoincide(0, l1)
```

**双对象：**
```python
skt.AddConsCoincide(0, l1, 1, l2)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| index1 | int | 第一个对象控制点序号 |
| obj1 | SketchObject | 第一个对象 |
| index2 | int | 第二个对象控制点序号（可选） |
| obj2 | SketchObject | 第二个对象（可选） |

---

## 完整代码示例

**示例：绘制直线并添加水平、竖直尺寸约束**

```python
skt = NCTI.SketchWorkPlane(doc)
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
skt = NCTI.SketchWorkPlane(doc)
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
- 尺寸约束（水平尺寸、竖直尺寸、长度尺寸）需要 index 参数指定控制点序号（基准 3.3.1–3.3.3 定义2/3）。
- 半径尺寸约束通过半径值 + 圆心定位，无 index（基准 3.3.4）；角度尺寸约束接收 SketchObject，无 index（基准 3.3.5）。
- 几何约束中：平行、垂直、相切接收两个 SketchObject，无 index（基准 3.3.6–3.3.8）；相等接收一个或两个 SketchObject，无 index（基准 3.3.9）；水平(XAxis)、竖直(YAxis)的单对象重载无 index，双对象重载为 (index, SketchObject, index, SketchObject) 带 index（基准 3.3.10–3.3.11）；重合(Coincide)的单对象与双对象重载均带 index，即 (index, SketchObject) 与 (index, SketchObject, index, SketchObject)（基准 3.3.12）。
- 尺寸约束类（水平/竖直/长度/半径/角度）的返回对象支持编辑方法（基准 3.4）；其余约束类型的返回值及可编辑性，两份基准未全部明示，详见 `case-edit-constraint.md`。
