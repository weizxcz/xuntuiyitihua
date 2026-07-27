# 草图初始化与文档管理 (Initialization & Document)

适用场景：创建草图工作平面、打开/关闭、获取与删除对象、获取基准对象、求解、文档级管理。

> 入口类：`YH.SketchWorkPlane`（草图工作平面，绘图入口）与 `YH.YHDocument`（文档管理实例，文档级操作入口）。几何基元仍为 `NCTI.Point` / `NCTI.Vector`。

---

## 一、草图工作平面 (SketchWorkPlane)

### 1. 创建草图工作平面

`skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))` — 默认平面
`skt = YH.SketchWorkPlane(doc, origin, hDir, vDir)` — 自定义平面

| 参数 | 类型 | 说明 |
|------|------|------|
| doc | 文档类型 | 实例化的文档对象（预注入） |
| origin | NCTI.Point | 原点，可省略，默认 (0,0,0) |
| hDir | NCTI.Vector | 水平方向，可省略，默认 (1,0,0) |
| vDir | NCTI.Vector | 竖直方向，可省略，默认 (0,1,0) |
| 返回值 | SketchWorkPlane | 实例化的草图工作平面对象 |

```python
# 默认平面
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))

# 自定义平面（原点 (5,0,0)，水平方向 (0,1,0)，竖直方向 (0,0,1)）
origin = NCTI.Point(5, 0, 0)
hDir = NCTI.Vector(0, 1, 0)
vDir = NCTI.Vector(0, 0, 1)
skt = YH.SketchWorkPlane(doc, origin, hDir, vDir)
```

### 2. 打开草图

`skt.Open()` — 无参数。进入草图绘制模式，所有绘制操作前必须先调用。

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
skt.Close()   # 先关闭（演示）
skt.Open()    # 再打开
```

### 3. 关闭草图

`skt.Close()` — 无参数。退出草图绘制模式。

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
skt.Close()
```

### 4. 获取草图对象

`obj = skt.GetObject(objName)` — 按名称获取任意草图对象（基本对象、约束对象、基准对象）。

| 参数 | 类型 | 说明 |
|------|------|------|
| objName | str | 对象名称；绘制后可从左侧对象树查看，或鼠标悬停在图形上查看 |

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
skt.AddCircle(NCTI.Point(0, 0, 0), 10)
# 根据实际对象名获取（对象名来自对象树）
c1 = skt.GetObject("yhd23")
print(c1.ObjectName())
```

### 5. 删除草图对象

`skt.Delete(strObjNameList)` — 按名称列表删除。

| 参数 | 类型 | 说明 |
|------|------|------|
| strObjNameList | list[str] | 草图对象名称列表 |

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
skt.AddCircle(NCTI.Point(0, 0, 0), 10)
skt.AddLine(NCTI.Point(10, 0, 0), NCTI.Point(5, 20, 0))
# 根据实际对象名删除
skt.Delete(["yhd23", "yhd33"])
```

### 6. 获取所有几何对象

`skt.GetAllDisplayObjects()` — 无参数。返回草图内全部绘图几何图元对象。

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
skt.AddCircle(NCTI.Point(0, 0, 0), 10)
allGeo = skt.GetAllDisplayObjects()
```

### 7. 获取所有约束对象

`skt.GetAllConsObjects()` — 无参数。返回草图内全部几何约束对象。

```python
allCons = skt.GetAllConsObjects()
```

### 8. 获取原点对象

`skt.GetOrigin()` — 无参数。返回草图原点 SketchOrigin 对象。

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
org = skt.GetOrigin()
pos = org.Point()          # 获取原点坐标
print(pos)
```

### 9. 获取 X 轴对象

`skt.GetXAxis()` — 无参数。返回草图基准 X 轴 SketchXAxis 对象。

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
xAxis = skt.GetXAxis()
name = xAxis.ObjectName()  # 获取名称
vec = xAxis.Direct()       # 获取方向向量
print(name, vec)
```

### 10. 获取 Y 轴对象

`skt.GetYAxis()` — 无参数。返回草图基准 Y 轴 SketchYAxis 对象。

```python
yAxis = skt.GetYAxis()
name = yAxis.ObjectName()
vec = yAxis.Direct()
```

### 11. 获取中心线对象

`skt.GetCenterLine()` — 无参数。返回草图基准中心线 CenterLine 对象。

```python
centerLine = skt.GetCenterLine()
name = centerLine.ObjectName()        # 获取名称
startPt = centerLine.StartPoint()     # 获取起点
endPt = centerLine.EndPoint()         # 获取终点
```

### 12. 求解

`skt.RunSolve()` — 无参数。执行草图约束求解，更新几何图元位置尺寸。

```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
yh_doc = YH.YHDocument(doc)
yh_doc.AutoSolve(False)          # 先关闭自动求解
l1 = skt.AddLine(NCTI.Point(0, 0, 0), NCTI.Point(10, 0, 0))
cons1 = skt.AddConsLength(0, l1)
cons1.EditSize(50)
skt.RunSolve()                   # 手动求解一次
```

### 13. 计算封闭区域

`skt.RunCalCloseArea()` — 无参数。计算草图封闭图形的面积。

```python
skt.RunCalCloseArea()
```

---

## 二、文档管理实例 (YHDocument)

文档级操作的顶层入口。需要文档级控制（求解开关、导出、清空、按名获取平面、创建基准坐标系等）时使用。

### 1. 创建实例化对象

`yh_doc = YH.YHDocument(doc)`

| 参数 | 类型 | 说明 |
|------|------|------|
| doc | 文档类型 | 底层文档对象（预注入） |
| 返回值 | YHDocument | 实例化的文档管理对象 |

```python
yh_doc = YH.YHDocument(doc)
```

### 2. 根据对象名获取草图工作平面

`skt = yh_doc.GetSketch(sketchWorkPlaneNameStr)`

| 参数 | 类型 | 说明 |
|------|------|------|
| sketchWorkPlaneNameStr | str | 草图工作平面对象名（左侧对象树可见） |
| 返回值 | SketchWorkPlane | 实例化的草图工作平面 |

```python
yh_doc = YH.YHDocument(doc)
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
# 对象名来自左侧对象树
skt0 = yh_doc.GetSketch("yh_sketch_work_plane_14")
```

### 3. 创建草图工作平面

`skt = yh_doc.CreatSketch()` — 默认平面
`skt = yh_doc.CreatSketch(origin, hDir, vDir)` — 自定义平面

| 参数 | 类型 | 说明 |
|------|------|------|
| origin | NCTI.Point | 原点，可省略，默认 (0,0,0) |
| hDir | NCTI.Vector | 水平方向，可省略，默认 (1,0,0) |
| vDir | NCTI.Vector | 竖直方向，可省略，默认 (0,1,0) |

```python
yh_doc = YH.YHDocument(doc)
skt = yh_doc.CreatSketch()
# skt = yh_doc.CreatSketch(NCTI.Point(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
```

### 4. 创建基准坐标系

`yh_doc.CreatCoordinateSystem(origin, hDir, vDir)` — 三个参数均必填。

| 参数 | 类型 | 说明 |
|------|------|------|
| origin | NCTI.Point | 原点 |
| hDir | NCTI.Vector | 水平方向 |
| vDir | NCTI.Vector | 竖直方向 |

```python
yh_doc = YH.YHDocument(doc)
yh_doc.CreatCoordinateSystem(NCTI.Point(0, 20, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
```

### 5. 导出草图 Python

`yh_doc.ExportPython(exPathStr, exportMode)` — 将草图几何与约束导出为本地 Python 脚本。

| 参数 | 类型 | 说明 |
|------|------|------|
| exPathStr | str | 导出的 py 文件路径 |
| exportMode | int | 导出模式：0 = 仅导出约束；1 = 全导出 |

```python
yh_doc = YH.YHDocument(doc)
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
skt.AddCircle(NCTI.Point(0, 0, 0), 50)
skt.AddLine(NCTI.Point(50, 0, 0), NCTI.Point(80, 90, 0))
yh_doc.ExportPython("D:/test.py", 1)
```

### 6. 自动求解开关

`yh_doc.AutoSolve(opOrClose)`

| 参数 | 类型 | 说明 |
|------|------|------|
| opOrClose | bool | True 开启，False 关闭 |

```python
yh_doc = YH.YHDocument(doc)
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
yh_doc.AutoSolve(False)         # 关闭自动求解
c1 = skt.AddCircle(NCTI.Point(0, 0, 0), 50)
consR = skt.AddConsRadius(c1)
consR.EditSize(200)             # 关闭后修改约束不立即求解
skt.RunSolve()                  # 需手动求解
```

### 7. Python 捕捉开关

`yh_doc.ArgumentAutoSnap(opOrClose)`

| 参数 | 类型 | 说明 |
|------|------|------|
| opOrClose | bool | True 开启，False 关闭 |

```python
yh_doc = YH.YHDocument(doc)
yh_doc.ArgumentAutoSnap(True)
skt = YH.SketchWorkPlane(doc, NCTI.Point(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
skt.AddLine(NCTI.Point(0, 0, 0), NCTI.Point(50, 50, 0))
```

### 8. 自动计算弱约束开关

`yh_doc.AutoCalFreeCons(opOrClose)`

| 参数 | 类型 | 说明 |
|------|------|------|
| opOrClose | bool | True 开启，False 关闭 |

```python
yh_doc = YH.YHDocument(doc)
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
yh_doc.AutoCalFreeCons(False)
skt.AddCircle(NCTI.Point(0, 0, 0), 50)
```

### 9. 自动计算闭合区域开关

`yh_doc.AutoCalCloseArea(opOrClose)`

| 参数 | 类型 | 说明 |
|------|------|------|
| opOrClose | bool | True 开启，False 关闭 |

```python
yh_doc = YH.YHDocument(doc)
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
yh_doc.AutoCalCloseArea(False)
skt.AddCircle(NCTI.Point(0, 0, 0), 50)
```

### 10. 清除

`yh_doc.Clear()` — 无参数。清空当前文档内全部草图、约束、坐标系等所有数据。

```python
yh_doc = YH.YHDocument(doc)
skt = yh_doc.CreatSketch()
skt.AddCircle(NCTI.Point(0, 0, 0), 50)
skt.AddLine(NCTI.Point(50, 0, 0), NCTI.Point(80, 70, 0))
yh_doc.Clear()
```

---

## 三、基准对象通用查询方法

以下方法均挂在 `skt.GetXAxis()` / `skt.GetYAxis()` / `skt.GetOrigin()` / `skt.GetCenterLine()` 返回的对象上，无参数。

### 坐标轴对象（SketchXAxis / SketchYAxis）

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `.ObjectName()` | str | 获取名称 |
| `.SetObjectName(name)` | — | 设置名称（name 为 str） |
| `.ObjectType()` | str | 获取类型名称 |
| `.Direct()` | NCTI.Vector | 获取方向向量 |

X 轴（获取名称/类型/方向、设置名称）：
```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
xAxis = skt.GetXAxis()
print(xAxis.ObjectName())             # 获取名称
xAxis.SetObjectName('nameTest')       # 设置名称
print(xAxis.ObjectType())             # 获取类型名称
print(xAxis.Direct())                 # 获取方向向量
```

Y 轴（获取名称/类型/方向、设置名称）：
```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
yAxis = skt.GetYAxis()
print(yAxis.ObjectName())             # 获取名称
yAxis.SetObjectName('nameTest')       # 设置名称
print(yAxis.ObjectType())             # 获取类型名称
print(yAxis.Direct())                 # 获取方向向量
```

### 原点对象（SketchOrigin）

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `.ObjectName()` | str | 获取名称 |
| `.SetObjectName(name)` | — | 设置名称（name 为 str） |
| `.ObjectType()` | str | 获取类型名称 |
| `.Point()` | NCTI.Point | 获取原点坐标 |

获取原点坐标、名称/类型、设置名称：
```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
org = skt.GetOrigin()
print(org.Point())                    # 获取原点坐标
print(org.ObjectName())               # 获取名称
org.SetObjectName('nameTest')         # 设置名称
print(org.ObjectType())               # 获取类型名称
```

### 中心线对象（CenterLine）

> 说明：通过 `skt.GetCenterLine()` 获取的是草图基准中心线对象。

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `.ObjectName()` | str | 获取名称 |
| `.SetObjectName(name)` | — | 设置名称（name 为 str） |
| `.ObjectType()` | str | 获取类型名称 |
| `.StartPoint()` | NCTI.Point | 获取起点坐标 |
| `.EndPoint()` | NCTI.Point | 获取终点坐标 |

获取起点/终点坐标、名称/类型、设置名称：
```python
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
centerLine = skt.GetCenterLine()
print(centerLine.StartPoint())        # 获取起点坐标
print(centerLine.EndPoint())          # 获取终点坐标
print(centerLine.ObjectName())        # 获取名称
centerLine.SetObjectName('nameTest')  # 设置名称
print(centerLine.ObjectType())        # 获取类型名称
```

---

## 完整代码示例

**示例：创建草图、绘图、求解、导出**

```python
# 文档管理入口
yh_doc = YH.YHDocument(doc)
yh_doc.AutoCalFreeCons(False)        # 关闭自动弱约束，便于精确控制

# 草图入口
skt = YH.SketchWorkPlane(doc, NCTI.Vector(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
skt.Open()

# 绘图
l1 = skt.AddLine(NCTI.Point(0, 0, 0), NCTI.Point(50, 0, 0))
cons1 = skt.AddConsLength(0, l1)
cons1.EditSize(80)

# 求解并导出
skt.RunSolve()
yh_doc.ExportPython("D:/test.py", 1)

skt.Close()
```

## 注意事项

- 绘图前必须确保草图已打开（`skt.Open()`）。
- `skt` 变量是所有草图操作的入口，必须保持一致的变量名。
- `YHDocument` 的方法（AutoSolve / ExportPython / Clear 等）挂在 `yh_doc` 上，不是 `skt` 上。
- 精确控制约束时，常配合 `yh_doc.AutoSolve(False)` + `yh_doc.AutoCalFreeCons(False)`，最后再 `skt.RunSolve()`。
- `GetObject` / `Delete` 的对象名来自左侧对象树或鼠标悬停查看，不是变量名。
