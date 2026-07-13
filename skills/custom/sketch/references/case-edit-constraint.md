# 编辑约束对象 (Edit Constraints)

适用场景：修改已创建约束的尺寸数值、尺寸显示位置，或查询约束的尺寸值、名称、关联对象。

> 关键结论：约束按可编辑性分两类。
> - **尺寸类约束**（水平 Xpos / 竖直 Ypos / 长度 Length / 半径 Radius / 角度 Angle / 平行 Parallel）支持完整编辑：`EditSize` / `EditLocation` / `Size`。
> - **几何类约束**（垂直 Vertical / 相切 Tangent / 相等 Equal / 水平 XAxis / 竖直 YAxis / 重合 Coincide）仅支持查询：`ObjectName` / `ConsData`，**不支持** `EditSize`。

---

## 一、获取约束对象

编辑或查询前，必须先拿到约束对象。两种方式：

```python
# 方式一：创建约束时捕获返回值
cons1 = skt.AddConsLength(0, l1)

# 方式二：通过对象名获取（对象名来自左侧对象树）
cons1 = skt.GetObject("constraint_name")
```

---

## 二、通用编辑/查询方法

适用于 6 种可编辑的尺寸类约束（Xpos / Ypos / Length / Radius / Angle / Parallel）：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `.EditSize(dSizeValue)` | float | — | 编辑约束的**尺寸数值**大小 |
| `.EditLocation(ptPosition)` | NCTI.Point | — | 编辑约束的**尺寸显示位置**（尺寸标注的显示位置，非几何位置） |
| `.Size()` | — | float | 获取约束的尺寸数值 |
| `.ObjectName()` | — | str | 获取约束对象名 |
| `.ConsData()` | — | list | 获取约束关联的对象列表 |

> 特别注意：`EditLocation(pt)` 编辑的是**尺寸标注的显示位置**（即尺寸数字显示在哪里），不是修改几何本身。

---

## 三、各类尺寸约束的编辑示例

### 1. 水平尺寸约束 (SketchConsXPos)

```python
skt = YH.SketchWorkPlane(doc)
a1 = skt.AddLine(NCTI.Point(10, 10, 0), NCTI.Point(20, 20, 0))
cons1 = skt.AddConsXpos(0, a1, 1, a1)

cons1.EditSize(60)                          # 编辑尺寸数值
cons1.EditLocation(NCTI.Point(20, 30, 0))   # 编辑尺寸显示位置
print(cons1.Size())                         # 获取尺寸数值
print(cons1.ObjectName())                   # 获取对象名
print(cons1.ConsData())                     # 获取关联对象列表
```

### 2. 竖直尺寸约束 (SketchConsYPos)

```python
skt = YH.SketchWorkPlane(doc)
a1 = skt.AddLine(NCTI.Point(10, 10, 0), NCTI.Point(20, 20, 0))
cons1 = skt.AddConsYpos(0, a1, 1, a1)
cons1.EditSize(60)
```

### 3. 长度尺寸约束 (SketchConsLength)

```python
skt = YH.SketchWorkPlane(doc)
l1 = skt.AddLine(NCTI.Point(0, 0, 0), NCTI.Point(20, 0, 0))
cons1 = skt.AddConsLength(0, l1)
cons1.EditSize(50)        # 修改长度为 50
print(cons1.Size())
```

### 4. 半径尺寸约束 (SketchConsRadius)

```python
skt = YH.SketchWorkPlane(doc)
c1 = skt.AddCircle(NCTI.Point(0, 0, 0), 10)
cons1 = skt.AddConsRadius(c1)
cons1.EditSize(60)        # 修改半径约束值为 60
```

### 5. 角度尺寸约束 (SketchConsAngle)

```python
skt = YH.SketchWorkPlane(doc)
line1 = skt.AddLine(NCTI.Point(0, 0, 0), NCTI.Point(10, 10, 0))
angle1 = skt.AddConsAngle(line1, skt.GetXAxis())   # line1 与 X 轴的夹角
angle1.EditSize(60)                                 # 修改角度为 60°
print(angle1.Size())
```

### 6. 平行约束 (SketchConsParallel) — 特殊：需先 OpenSize

平行约束的 `EditSize` 实为设置**两条直线的夹角**（平行时为 180°）。编辑前**必须先调用 `OpenSize()`** 打开尺寸显示与编辑功能，编辑后可用 `CloseSize()` 关闭。

| 方法 | 参数 | 说明 |
|------|------|------|
| `.OpenSize()` | — | 打开平行约束的平行尺寸显示和编辑功能 |
| `.CloseSize()` | — | 关闭平行约束的平行尺寸显示和编辑功能 |
| `.EditSize(dSizeValue)` | float | 编辑两线夹角数值 |
| `.EditLocation(ptPosition)` | NCTI.Point | 编辑平行尺寸显示位置 |
| `.Size()` | — | 获取平行尺寸数值 |
| `.ObjectName()` | — | 获取对象名 |
| `.ConsData()` | — | 获取关联对象列表 |

```python
skt = YH.SketchWorkPlane(doc)
a1 = skt.AddLine(NCTI.Point(5, 5, 0), NCTI.Point(15, 15, 0))
a2 = skt.AddLine(NCTI.Point(20, 5, 0), NCTI.Point(20, 15, 0))
cons1 = skt.AddConsParallel(a1, a2)

cons1.OpenSize()                              # 先打开尺寸编辑功能
cons1.EditSize(20)                            # 编辑夹角为 20°
cons1.EditLocation(NCTI.Point(20, 30, 0))     # 编辑尺寸显示位置
print(cons1.Size())                           # 获取尺寸数值
cons1.CloseSize()                             # 关闭尺寸编辑功能
```

---

## 四、几何类约束的查询（不可 EditSize）

垂直 / 相切 / 相等 / 水平 / 竖直 / 重合 这 6 类约束只能查询，不能编辑尺寸数值：

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `.ObjectName()` | str | 获取约束对象名 |
| `.ConsData()` | list | 获取约束关联的对象列表 |

垂直约束查询：
```python
skt = YH.SketchWorkPlane(doc)
l1 = skt.AddLine(NCTI.Point(0, 0, 0), NCTI.Point(10, 20, 0))
l2 = skt.AddLine(NCTI.Point(0, 0, 0), NCTI.Point(-20, 20, 0))
cons1 = skt.AddConsVertical(l1, l2)
print(cons1.ObjectName())
print(cons1.ConsData())
```

相切约束查询：
```python
skt = YH.SketchWorkPlane(doc)
c1 = skt.AddCircle(NCTI.Point(0, 0, 0), 10)
l1 = skt.AddLine(NCTI.Point(10, 30, 0), NCTI.Point(40, 20, 0))
cons1 = skt.AddConsTangent(c1, l1)
print(cons1.ObjectName())
print(cons1.ConsData())
```

相等约束查询：
```python
skt = YH.SketchWorkPlane(doc)
a1 = skt.AddLine(NCTI.Point(10, 10, 0), NCTI.Point(20, 20, 0))
a2 = skt.AddLine(NCTI.Point(21, 20, 0), NCTI.Point(40, 10, 0))
cons1 = skt.AddConsEqual(a1, a2)
print(cons1.ObjectName())
print(cons1.ConsData())
```

水平约束查询：
```python
skt = YH.SketchWorkPlane(doc)
a1 = skt.AddLine(NCTI.Point(10, 10, 0), NCTI.Point(20, 20, 0))
cons1 = skt.AddConsXAxis(a1)
print(cons1.ObjectName())
print(cons1.ConsData())
```

竖直约束查询：
```python
skt = YH.SketchWorkPlane(doc)
a1 = skt.AddLine(NCTI.Point(10, 10, 0), NCTI.Point(20, 20, 0))
cons1 = skt.AddConsYAxis(a1)
print(cons1.ObjectName())
print(cons1.ConsData())
```

重合约束查询：
```python
skt = YH.SketchWorkPlane(doc)
a1 = skt.AddLine(NCTI.Point(10, 10, 0), NCTI.Point(20, 20, 0))
a2 = skt.AddLine(NCTI.Point(21, 20, 0), NCTI.Point(30, 10, 0))
cons1 = skt.AddConsCoincide(1, a1, 0, a2)
print(cons1.ObjectName())
print(cons1.ConsData())
```

---

## 五、约束可编辑性总表

| 约束类型 | 创建 API | EditSize | EditLocation | Size | ObjectName/ConsData |
|----------|----------|----------|--------------|------|---------------------|
| 水平尺寸 | `AddConsXpos` | ✓ | ✓ | ✓ | ✓ |
| 竖直尺寸 | `AddConsYpos` | ✓ | ✓ | ✓ | ✓ |
| 长度尺寸 | `AddConsLength` | ✓ | ✓ | ✓ | ✓ |
| 半径尺寸 | `AddConsRadius` | ✓ | ✓ | ✓ | ✓ |
| 角度尺寸 | `AddConsAngle` | ✓ | ✓ | ✓ | ✓ |
| 平行 | `AddConsParallel` | ✓（需 OpenSize） | ✓（需 OpenSize） | ✓（需 OpenSize） | ✓ |
| 垂直 | `AddConsVertical` | ✗ | ✗ | ✗ | ✓ |
| 相切 | `AddConsTangent` | ✗ | ✗ | ✗ | ✓ |
| 相等 | `AddConsEqual` | ✗ | ✗ | ✗ | ✓ |
| 水平(对齐) | `AddConsXAxis` | ✗ | ✗ | ✗ | ✓ |
| 竖直(对齐) | `AddConsYAxis` | ✗ | ✗ | ✗ | ✓ |
| 重合 | `AddConsCoincide` | ✗ | ✗ | ✗ | ✓ |

---

## 完整代码示例

**示例：绘制直线 → 添加长度约束 → 编辑约束值 → 查询**

```python
skt = YH.SketchWorkPlane(doc)
skt.Open()

# 绘制直线
l1 = skt.AddLine(NCTI.Point(0, 0, 0), NCTI.Point(20, 0, 0))

# 添加长度约束
cons1 = skt.AddConsLength(0, l1)

# 编辑约束值
cons1.EditSize(50.0)

# 查询
print(cons1.Size())
print(cons1.ObjectName())

skt.Close()
```

**示例：绘制圆 → 添加半径约束 → 编辑半径值**

```python
yh_doc = YH.YHDocument(doc)
skt = YH.SketchWorkPlane(doc)
skt.Open()

yh_doc.AutoSolve(False)        # 关闭自动求解，便于观察编辑效果

# 绘制圆
c1 = skt.AddCircle(NCTI.Point(0, 0, 0), 10)

# 添加半径约束并修改
cons1 = skt.AddConsRadius(c1)
cons1.EditSize(15.0)

skt.RunSolve()                 # 手动求解
skt.Close()
```

## 注意事项

- 编辑或查询约束前，必须先获取约束对象（创建时捕获返回值，或通过 `skt.GetObject(name)` 按名获取）。
- `EditSize(dSizeValue)`：dSizeValue 为浮点尺寸数值。
- `EditLocation(pt)`：编辑的是**尺寸标注的显示位置**，不是几何本身的位置。
- 平行约束的 `EditSize` 是两线夹角，且**必须先 `OpenSize()`** 才能编辑/查询尺寸，编辑后可 `CloseSize()`。
- 几何类约束（垂直/相切/相等/水平对齐/竖直对齐/重合）**不支持** `EditSize`/`EditLocation`/`Size`，只能 `ObjectName`/`ConsData` 查询。
- 建议创建约束后立即赋变量名，方便后续编辑引用。
