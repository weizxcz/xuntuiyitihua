# 创建基本对象 (Basic Geometry Drawing)

适用场景：在草图中绘制点、直线、中心线、样条、矩形、圆、圆弧、椭圆、椭圆弧、圆角、倒角、修剪、偏移等几何对象。

> **重要：仅使用带显式参数的 API。** 各方法的无参版本（形如 `AddLine()`）需在 GUI 中手动选择对象才能落地，agent 不可使用，本文件不收录。

---

## 1. 点 (Point)

`p1 = skt.AddPoint(pt)`

| 参数 | 类型 | 说明 |
|------|------|------|
| pt | NCTI.Point | 创建点的位置 |
| 返回值 | SketchPoint | 点对象 |

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
p2 = skt.AddPoint(NCTI.Point(0, 1, 0))
```

**点对象查询方法（均无参数）：**

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `.Point()` | NCTI.Point | 获取点坐标 |
| `.ObjectName()` | str | 获取名称 |
| `.ObjectType()` | str | 获取类型名称 |
| `.SetObjectName(name)` | — | 设置名称（name 为 str） |

获取点坐标：
```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
point = skt.AddPoint(NCTI.Point(10, 10, 0))
pos = point.Point()
print(pos)
```

获取/设置名称、获取类型：
```python
name = point.ObjectName()       # 获取名称
print(name)
point.SetObjectName('nameTest') # 设置名称
print(point.ObjectType())       # 获取类型名称
```

## 2. 直线 (Line)

`l1 = skt.AddLine(ptStart, ptEnd)`

| 参数 | 类型 | 说明 |
|------|------|------|
| ptStart | NCTI.Point | 直线端点一 |
| ptEnd | NCTI.Point | 直线端点二 |
| 返回值 | SketchLine | 直线对象 |

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
l2 = skt.AddLine(NCTI.Point(10, 0, 0), NCTI.Point(5, 20, 0))
```

**直线对象查询方法（均无参数）：**

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `.StartPoint()` | NCTI.Point | 获取起点坐标 |
| `.EndPoint()` | NCTI.Point | 获取终点坐标 |
| `.ObjectName()` | str | 获取名称 |
| `.ObjectType()` | str | 获取类型名称 |
| `.SetObjectName(name)` | — | 设置名称（name 为 str） |

获取起点/终点坐标：
```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
line = skt.AddLine(NCTI.Point(0, 0, 0), NCTI.Point(10, 10, 0))
print(line.StartPoint())
print(line.EndPoint())
```

获取/设置名称、获取类型：
```python
name = line.ObjectName()        # 获取名称
print(name)
line.SetObjectName('nameTest')  # 设置名称
print(line.ObjectType())        # 获取类型名称
```

## 3. 中心线 (CenterLine)

`cl1 = skt.AddCenterLine(pt1, pt2)` — 过给定两点创建中心线，会无限延伸
`skt.AddCenterLine(sketchObject)` — 将已有的中心线对象设为有效中心线

| 参数 | 类型 | 说明 |
|------|------|------|
| pt1 | NCTI.Point | 中心线过的坐标点一 |
| pt2 | NCTI.Point | 中心线过的坐标点二 |
| sketchObject | SketchCenterLine | 实例化的中心线对象（用于设置为有效中心线） |

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
# 过给定两点创建中心线
cl2 = skt.AddCenterLine(NCTI.Point(10, 0, 0), NCTI.Point(5, 20, 0))
# 设置 cl2 为有效中心线
skt.AddCenterLine(cl2)
```

**中心线对象查询方法（均无参数）：**

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `.StartPoint()` | NCTI.Point | 获取起点坐标 |
| `.EndPoint()` | NCTI.Point | 获取终点坐标 |
| `.ObjectName()` | str | 获取名称 |
| `.ObjectType()` | str | 获取类型名称 |
| `.SetObjectName(name)` | — | 设置名称（name 为 str） |

获取起点/终点坐标：
```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
centerLine = skt.AddCenterLine(NCTI.Point(10, 0, 0), NCTI.Point(5, 20, 0))
print(centerLine.StartPoint())
print(centerLine.EndPoint())
```

获取/设置名称、获取类型：
```python
print(centerLine.ObjectName())             # 获取名称
centerLine.SetObjectName('nameTest')       # 设置名称
print(centerLine.ObjectType())             # 获取类型名称
```

## 4. 样条 (Spline)

`sp1 = skt.AddSpline(controlPtList)` — 依次连接控制点绘制样条曲线

| 参数 | 类型 | 说明 |
|------|------|------|
| controlPtList | list[NCTI.Point] | 样条控制点列表 |
| 返回值 | SketchSpline | 样条对象 |

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
sl2 = skt.AddSpline([NCTI.Point(0, 0, 0), NCTI.Point(6, -3, 0), NCTI.Point(-4, -2, 0), NCTI.Point(2, -5, 0)])
```

**样条对象查询方法（均无参数）：**

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `.ControlPoints()` | list[NCTI.Point] | 获取控制点集 |
| `.ObjectName()` | str | 获取名称 |
| `.ObjectType()` | str | 获取类型名称 |
| `.SetObjectName(name)` | — | 设置名称（name 为 str） |

获取控制点集：
```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
spline = skt.AddSpline([NCTI.Point(0, 0, 0), NCTI.Point(6, -3, 0)])
for pos in spline.ControlPoints():
    print(pos)
```

获取/设置名称、获取类型：
```python
print(spline.ObjectName())             # 获取名称
spline.SetObjectName('testTest')       # 设置名称
print(spline.ObjectType())             # 获取类型名称
```

## 5. 矩形 (Rectangle)

`r1 = skt.AddRect(ptStart, ptEnd)` — 以起点和对角点创建矩形

| 参数 | 类型 | 说明 |
|------|------|------|
| ptStart | NCTI.Point | 起点（第一个顶点） |
| ptEnd | NCTI.Point | 对角点 |
| 返回值 | 矩形对象 | — |

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
rect2 = skt.AddRect(NCTI.Point(0, 0, 0), NCTI.Point(20, 20, 0))
```

## 6. 圆 (Circle)

`c1 = skt.AddCircle(centerPt, radius)`

| 参数 | 类型 | 说明 |
|------|------|------|
| centerPt | NCTI.Point | 圆心点坐标 |
| radius | float | 半径 |
| 返回值 | SketchCircle | 圆对象 |

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
c2 = skt.AddCircle(NCTI.Point(0, 0, 0), 10)
```

**圆对象方法：**

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `.Center()` | NCTI.Point | 获取圆心坐标 |
| `.Radius()` | float | 获取半径 |
| `.EditCenter(pos)` | — | 编辑圆的圆心坐标（pos 为 NCTI.Point） |
| `.ObjectName()` | str | 获取名称 |
| `.ObjectType()` | str | 获取类型名称 |
| `.SetObjectName(name)` | — | 设置名称（name 为 str） |

获取圆心/半径、编辑圆心：
```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
circle = skt.AddCircle(NCTI.Point(0, 0, 0), 10)
print(circle.Center())
print(circle.Radius())
circle.EditCenter(NCTI.Point(10, 0, 0))   # 修改圆心
```

获取/设置名称、获取类型：
```python
print(circle.ObjectName())             # 获取名称
circle.SetObjectName('nameTest')       # 设置名称
print(circle.ObjectType())             # 获取类型名称
```

## 7. 圆弧 (Arc)

**方式一：起点、终点、弧上点**
`a1 = skt.AddArc(startPt, endPt, pt)`

| 参数 | 类型 | 说明 |
|------|------|------|
| startPt | NCTI.Point | 圆弧起始点 |
| endPt | NCTI.Point | 圆弧终点 |
| pt | NCTI.Point | 圆弧上一点 |

**方式二：半径、起始角、终止角、圆心**
`a1 = skt.AddArc(r, startAngle, endAngle, centerPt)`

| 参数 | 类型 | 说明 |
|------|------|------|
| r | float | 圆弧半径 |
| startAngle | float | 圆弧起始角度 |
| endAngle | float | 圆弧终止角度 |
| centerPt | NCTI.Point | 圆弧圆心点 |

> 两种方式根据已知条件选择。

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
# 起点、终点、弧上点
arc2 = skt.AddArc(NCTI.Point(10, 0, 0), NCTI.Point(0, 0, 0), NCTI.Point(5, 5, 0))
# 半径、起始角、终止角、圆心
arc3 = skt.AddArc(5, 0, 60, NCTI.Point(0, 0, 0))
```

**圆弧对象查询方法（均无参数）：**

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `.Center()` | NCTI.Point | 获取圆心坐标 |
| `.Radius()` | float | 获取半径 |
| `.StartAngle()` | float | 获取起始角度 |
| `.EndAngle()` | float | 获取终止角度 |
| `.ObjectName()` | str | 获取名称 |
| `.ObjectType()` | str | 获取类型名称 |
| `.SetObjectName(name)` | — | 设置名称（name 为 str） |

获取圆心/半径/角度：
```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
arc = skt.AddArc(5, 0, 60, NCTI.Point(0, 0, 0))
print(arc.Center())
print(arc.Radius())
print(arc.StartAngle())
print(arc.EndAngle())
```

获取/设置名称、获取类型：
```python
print(arc.ObjectName())             # 获取名称
arc.SetObjectName('testName')       # 设置名称
print(arc.ObjectType())             # 获取类型名称
```

## 8. 椭圆 (Ellipse)

`e1 = skt.AddEllipse(centerPt, majVec, minVec)`

| 参数 | 类型 | 说明 |
|------|------|------|
| centerPt | NCTI.Point | 椭圆圆心 |
| majVec | NCTI.Vector | 椭圆长半轴向量 |
| minVec | NCTI.Vector | 椭圆短半轴向量 |
| 返回值 | SketchEllipse | 椭圆对象 |

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
ell2 = skt.AddEllipse(NCTI.Point(0, 0, 0), NCTI.Vector(2, 0, 0), NCTI.Vector(0, 1, 0))
```

**椭圆对象查询方法（均无参数）：**

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `.Center()` | NCTI.Point | 获取圆心坐标 |
| `.MajorAxis()` | NCTI.Vector | 获取长半轴向量 |
| `.MinorAxis()` | NCTI.Vector | 获取短半轴向量 |
| `.ObjectName()` | str | 获取名称 |
| `.ObjectType()` | str | 获取类型名称 |
| `.SetObjectName(name)` | — | 设置名称（name 为 str） |

获取圆心/长半轴/短半轴：
```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
ellipse = skt.AddEllipse(NCTI.Point(0, 0, 0), NCTI.Vector(2, 0, 0), NCTI.Vector(0, 1, 0))
print(ellipse.Center())
print(ellipse.MajorAxis())
print(ellipse.MinorAxis())
```

获取/设置名称、获取类型：
```python
print(ellipse.ObjectName())             # 获取名称
ellipse.SetObjectName('nameTest')       # 设置名称
print(ellipse.ObjectType())             # 获取类型名称
```

## 9. 椭圆弧 (Ellipse Arc)

`e1 = skt.AddEllipseArc(centerPt, majVec, minVec, dStartAngle, dEndAngle)`

| 参数 | 类型 | 说明 |
|------|------|------|
| centerPt | NCTI.Point | 椭圆弧圆心 |
| majVec | NCTI.Vector | 椭圆弧长半轴向量 |
| minVec | NCTI.Vector | 椭圆弧短半轴向量 |
| dStartAngle | float | 椭圆弧起始角度 |
| dEndAngle | float | 椭圆弧终止角度 |

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
p1 = skt.AddEllipseArc(NCTI.Point(0, 0, 0), NCTI.Vector(10, 0, 0), NCTI.Vector(0, 5, 0), 10, 90)
```

**椭圆弧对象查询方法（均无参数）：**

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `.Center()` | NCTI.Point | 获取圆心坐标 |
| `.MajorAxis()` | NCTI.Vector | 获取长半轴向量 |
| `.MinorAxis()` | NCTI.Vector | 获取短半轴向量 |
| `.StartAngle()` | float | 获取起始角度 |
| `.EndAngle()` | float | 获取终止角度 |
| `.ObjectName()` | str | 获取名称 |
| `.ObjectType()` | str | 获取类型名称 |
| `.SetObjectName(name)` | — | 设置名称（name 为 str） |

获取圆心/长短半轴/角度：
```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
ellipseArc = skt.AddEllipseArc(NCTI.Point(0, 0, 0), NCTI.Vector(10, 0, 0), NCTI.Vector(0, 5, 0), 10, 90)
print(ellipseArc.Center())
print(ellipseArc.MajorAxis())
print(ellipseArc.MinorAxis())
print(ellipseArc.StartAngle())
print(ellipseArc.EndAngle())
```

获取/设置名称、获取类型：
```python
print(ellipseArc.ObjectName())              # 获取名称
ellipseArc.SetObjectName('nameTest')        # 设置名称
print(ellipseArc.ObjectType())              # 获取类型名称
```

## 10. 圆角 (Fillet)

根据两条直线及上面其中各一点创建圆角。

**定义（距离定位）：** `SketchWorkPlane.CurveRadius(r, objLine1, objLine2)` — 距离方式定位圆角。

| 参数 | 类型         | 说明 |
|------|------------|------|
| r | float      | ,圆角半径 |
| line1 | SketchLine | 第 1 个线段对象（已创建的直线变量） |
| line2 | SketchLine | 第 2 个线段对象（已创建的直线变量） |

> **关键：line1、line2 必须是之前通过 `skt.AddLine()` 创建并赋值的直线对象。**

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
skt.Open()
l1 = skt.AddLine(NCTI.Point(0, 0, 0), NCTI.Point(30, 0, 0))
l2 = skt.AddLine(NCTI.Point(30, 0, 0), NCTI.Point(30, 20, 0))

# 定义：距离定位
skt.CurveRadius(NCTI.Point(15, 15, 0), l1, NCTI.Point(0, 15, 0), l2)
skt.Close()
```

## 11. 倒角 (Chamfer)

根据两条直线及上面其中各一点创建倒角。

**定义（距离定位）：** `SketchWorkPlane.CurveChamfer(distance1, lineObject1, distance2, lineObject2)` — 以距离方式定位倒角。

| 参数 | 类型         | 说明 |
|------|------------|------|
| distance1 | float      | 倒角在直线对象一这边的长度 |
| line1 | SketchLine | 第 1 个线段对象（已创建的直线变量） |
| distance2 | float      | 倒角在直线对象二这边的长度 |
| line2 | SketchLine | 第 2 个线段对象（已创建的直线变量） |

> **关键：line1、line2 必须是之前通过 `skt.AddLine()` 创建并赋值的直线对象。**

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
skt.Open()
l1 = skt.AddLine(NCTI.Point(0, 0, 0), NCTI.Point(30, 0, 0))
l2 = skt.AddLine(NCTI.Point(30, 0, 0), NCTI.Point(30, 20, 0))

# 定义：距离定位
skt.CurveChamfer(3, l1, 4, l2)
skt.Close()
```

## 12. 修剪 (Trim)

修剪给定的绘图对象，有两种参数化方式：

**方式一：指定修剪位置点**
`skt.CurveTrimming(pt)` — 修剪该坐标点位置对应的图元

**方式二：指定修剪位置点 + 一组草图对象**
`skt.CurveTrimming(pt, [obj1, obj2])` — 仅在给定对象列表中修剪该坐标点位置

| 参数 | 类型 | 说明 |
|------|------|------|
| pt | NCTI.Point | 要修剪位置对应的坐标点 |
| objList | list[SketchObject] | 一组草图对象（方式二使用） |

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
skt.Open()
circle1 = skt.AddCircle(NCTI.Point(5, 0, 0), 10)
line1 = skt.AddLine(NCTI.Point(-10, 5, 0), NCTI.Point(20, 5, 0))

# 方式一：指定修剪位置点
skt.CurveTrimming(NCTI.Point(5, 10, 0))

# 方式二：修剪位置点 + 一组对象
skt.CurveTrimming(NCTI.Point(5, 10, 0), [circle1, line1])
skt.Close()
```

## 13. 偏移 (Offset)

对草图曲线执行偏移复制生成新图元：

`skt.CurveOffset([obj], distance)` — 对一组草图对象按距离偏移

| 参数 | 类型 | 说明 |
|------|------|------|
| objList | list[SketchObject] | 草图对象数组 |
| distance | float | 偏移距离 |

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
line1 = skt.AddLine(NCTI.Point(10, 10, 0), NCTI.Point(20, 20, 0))
skt.CurveOffset([line1], 2)
```

> 偏移另有 `CurveOffset(type)` 形式（type 为偏移类型：1 单一偏移 / 2 链条偏移 / 3 环偏移），该形式配合 GUI 选择使用，agent 不可用，本文件不收录。

---

## 完整代码示例

**示例：绘制两条直线并在交点处创建圆角**

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
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
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
skt.Open()

# 绘制矩形
r1 = skt.AddRect(NCTI.Point(0, 0, 0), NCTI.Point(20, 20, 0))

# 绘制圆（圆心 (10,10,0)，半径 10）
c1 = skt.AddCircle(NCTI.Point(10, 10, 0), 10)

skt.Close()
```

## 注意事项

- 所有绘制操作前必须确保草图已打开（`skt.Open()`）。
- 圆角和倒角操作的 `line1`、`line2` 必须是之前通过 `skt.AddLine()` 创建并赋值的直线对象，务必使用一致的变量名。
- 圆弧有两种参数化方式，根据用户已知条件选择：三点版（起点、终点、弧上点）或半径角度版（半径、起始角、终止角、圆心）。
- 修剪（CurveTrimming）支持脚本调用，传入修剪位置点（可附带一组对象）。
- 偏移（CurveOffset）的脚本形式为「对象数组 + 偏移距离」。
