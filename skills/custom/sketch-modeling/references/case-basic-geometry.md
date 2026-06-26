# 创建基本对象 (Basic Geometry Drawing)

适用场景：在草图中绘制点、直线、圆弧、矩形等几何对象。

**重要：仅使用带显式坐标参数的 API。无参数版本需 GUI 手动交互，agent 不可使用。**

## API 参考

### 1. 点 (Point)

```python
skt.AddPoint(NCTI.Point(0, 1, 0))
```

| 参数 | 类型 | 说明 |
|------|------|------|
| point | NCTI.Point | 点坐标 |

如需后续约束引用该点，可赋变量名：`p1 = skt.AddPoint(...)`。

### 2. 直线 (Line)

```python
l1 = skt.AddLine(NCTI.Point(10, 0, 0), NCTI.Point(5, 20, 0))
```

| 参数 | 类型 | 说明 |
|------|------|------|
| start | NCTI.Point | 起点 |
| end | NCTI.Point | 终点 |

返回直线对象。必须赋变量名（l1, l2, ...），后续圆角、倒角、约束操作会引用。

### 3. 中心线 (CenterLine)

```python
cl1 = skt.AddCenterLine(NCTI.Point(10, 0, 0), NCTI.Point(5, 20, 0))
```

| 参数 | 类型 | 说明 |
|------|------|------|
| start | NCTI.Point | 起点 |
| end | NCTI.Point | 终点 |

中心线会无限延伸。返回中心线对象。

### 4. 样条 (Spline)

```python
sp1 = skt.AddSpline([NCTI.Point(0, 0, 0), NCTI.Point(6, -3, 0), NCTI.Point(-4, -2, 0), NCTI.Point(2, -5, 0)])
```

| 参数 | 类型 | 说明 |
|------|------|------|
| points | list[NCTI.Point] | 依次连接的控制点列表 |

返回样条曲线对象。

### 5. 矩形 (Rectangle)

```python
r1 = skt.AddRect(NCTI.Point(10, 10, 0), NCTI.Point(20, 20, 0))
```

| 参数 | 类型 | 说明 |
|------|------|------|
| corner1 | NCTI.Point | 第一个对角顶点 |
| corner2 | NCTI.Point | 第二个对角顶点 |

返回矩形对象。

### 6. 圆 (Circle)

```python
c1 = skt.AddCircle(NCTI.Point(0, 0, 0), 10)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| center | NCTI.Point | 圆心 |
| radius | float | 半径 |

返回圆对象。

### 7. 圆弧 (Arc)

**方式一：半径 + 起止角 + 圆心**
```python
a1 = skt.AddArc(5, 0, 60, NCTI.Point(0, 0, 0))
```

| 参数 | 类型 | 说明 |
|------|------|------|
| radius | float | 半径 |
| startAngle | float | 起始角度 |
| endAngle | float | 终止角度 |
| center | NCTI.Point | 圆弧圆心 |

**方式二：三点定弧**
```python
a1 = skt.AddArc(NCTI.Point(10, 0, 0), NCTI.Point(0, 0, 0), NCTI.Point(5, 5, 0))
```

| 参数 | 类型 | 说明 |
|------|------|------|
| start | NCTI.Point | 圆弧起点 |
| end | NCTI.Point | 圆弧终点 |
| pointOnArc | NCTI.Point | 圆弧上的一点 |

返回圆弧对象。两种方式根据已知条件选择。

> 三点版参数顺序为「起点 → 终点 → 弧上点」，依据 Python 方法表（开发计划）的参数列标注；该行列对齐经方式一（半径版 `5,0,60`）的数值交叉验证无误，可信。注：API 用户手册 3.2.7 的文字描述为「起点→弧上点→终点」，与 Python 方法表冲突；二者相较，Python 方法表为开发计划、参数语义更精确，故本 skill 采信 Python 方法表。

### 8. 椭圆 (Ellipse)

```python
e1 = skt.AddEllipse(NCTI.Point(0, 0, 0), NCTI.Vector(2, 0, 0), NCTI.Vector(0, 1, 0))
```

| 参数 | 类型 | 说明 |
|------|------|------|
| center | NCTI.Point | 椭圆中心 |
| majorAxis | NCTI.Vector | 长半轴向量 |
| minorAxis | NCTI.Vector | 短半轴向量 |

返回椭圆对象。

注意：`AddEllipse(...)` 必须通过 `skt.` 调用：`skt.AddEllipse(...)`。

### 9. 椭圆弧 (Ellipse Arc)

```python
e1 = skt.AddEllipseArc(NCTI.Point(0, 0, 0), NCTI.Vector(10, 0, 0), NCTI.Vector(0, 5, 0), 10, 90)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| center | NCTI.Point | 椭圆中心 |
| majorAxis | NCTI.Vector | 长半轴向量 |
| minorAxis | NCTI.Vector | 短半轴向量 |
| startAngle | float | 起始角度 |
| endAngle | float | 终止角度 |

返回椭圆弧对象。

### 10. 圆角 (Fillet)

```python
skt.CurveRadius(NCTI.Point(15, 15, 0), l1, NCTI.Point(0, 15, 0), l2)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| point1 | NCTI.Point | 第一条线上的点 |
| line1 | Line object | 已创建的直线对象变量名 |
| point2 | NCTI.Point | 第二条线上的点 |
| line2 | Line object | 已创建的直线对象变量名 |

**关键：l1、l2 必须是之前通过 `skt.AddLine()` 创建并赋值的直线对象（基准说明"l1、l2均指代直线对象"）。**

### 11. 倒角 (Chamfer)

```python
skt.CurveChamfer(NCTI.Point(15, 15, 0), l1, NCTI.Point(0, 15, 0), l2)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| point1 | NCTI.Point | 第一条线上的点 |
| line1 | Line object | 已创建的直线对象变量名 |
| point2 | NCTI.Point | 第二条线上的点 |
| line2 | Line object | 已创建的直线对象变量名 |

**关键：l1、l2 必须是之前通过 `skt.AddLine()` 创建并赋值的直线对象（基准说明"l1、l2均指代直线对象"）。**

### 12. 修剪 (Trim) — ⚠️ GUI 专用

```python
skt.CurveTrimming()
```

**此操作仅有无参版本，需要在 GUI 中手动选择要修剪的对象。Agent 无法在脚本中使用此操作。**

如果用户请求修剪操作，向用户说明：修剪功能当前仅支持 GUI 交互模式，脚本模式下不可用。

## 完整代码示例

**示例：绘制两条直线并在交点处创建圆角**

```python
# 创建草图
skt = NCTI.SketchWorkPlane(doc)
skt.Open()

# 绘制两条相交直线
l1 = skt.AddLine(NCTI.Point(0, 0, 0), NCTI.Point(30, 0, 0))
l2 = skt.AddLine(NCTI.Point(30, 0, 0), NCTI.Point(30, 20, 0))

# 在交点处创建圆角
skt.CurveRadius(NCTI.Point(15, 0, 0), l1, NCTI.Point(30, 10, 0), l2)

skt.Close()
```

**示例：绘制矩形和圆**

```python
skt = NCTI.SketchWorkPlane(doc)
skt.Open()

# 绘制矩形
r1 = skt.AddRect(NCTI.Point(0, 0, 0), NCTI.Point(20, 20, 0))

# 绘制圆（圆心 (10,10,0)，半径 10）
c1 = skt.AddCircle(NCTI.Point(10, 10, 0), 10)

skt.Close()
```

## 注意事项

- 所有绘制操作前必须确保草图已打开（`skt.Open()`）。
- 圆角和倒角操作依赖之前创建的直线对象，务必使用一致的变量名。
- 圆弧有两种参数化方式，根据用户已知条件选择。
- 修剪操作（CurveTrimming）仅支持 GUI，脚本中不可用。
