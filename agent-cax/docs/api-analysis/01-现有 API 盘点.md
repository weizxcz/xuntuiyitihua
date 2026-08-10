# 自动化建模 API 分析 - 现有 API 盘点

## 分析日期
2026-08-10

## 1. Sketch API 能力盘点

### 1.1 文档与草图管理
| 类别 | 方法 | 说明 |
|------|------|------|
| YHDocument | `YH.YHDocument(doc)` | 文档入口实例化 |
| YHDocument | `GetActivitySketch()` | 获取激活草图 |
| YHDocument | `GetSketch(name)` | 按名称获取草图 |
| YHDocument | `CreatSketch()` | 创建草图工作平面 |
| YHDocument | `CreatCoordinateSystem()` | 创建基准坐标系 |
| YHDocument | `ExportPython()` | 导出 Python 脚本 |
| YHDocument | `AutoSolve()` | 自动求解开关 |
| YHDocument | `AutoCalFreeCons()` | 自动弱约束开关 |
| YHDocument | `AutoCalCloseArea()` | 自动闭合区域计算开关 |
| YHDocument | `ArgumentAutoSnap()` | Python 捕捉开关 |
| YHDocument | `Clear()` | 清空文档 |

### 1.2 草图工作平面操作
| 类别 | 方法 | 说明 |
|------|------|------|
| SketchWorkPlane | `YH.SketchWorkPlane(doc, origin, hDir, vDir)` | 创建草图平面 |
| SketchWorkPlane | `Open()` | 打开草图 |
| SketchWorkPlane | `Close()` | 关闭草图 |
| SketchWorkPlane | `GetObject(name)` | 按名称获取对象 |
| SketchWorkPlane | `Delete(nameList)` | 按名称删除对象 |
| SketchWorkPlane | `GetAllDisplayObjects()` | 获取所有几何对象 |
| SketchWorkPlane | `GetAllConsObjects()` | 获取所有约束对象 |
| SketchWorkPlane | `GetOrigin()` | 获取原点 |
| SketchWorkPlane | `GetXAxis()` | 获取 X 轴 |
| SketchWorkPlane | `GetYAxis()` | 获取 Y 轴 |
| SketchWorkPlane | `GetCenterLine()` | 获取基准中心线 |
| SketchWorkPlane | `RunSolve()` | 手动求解 |
| SketchWorkPlane | `RunCalCloseArea()` | 计算封闭区域面积 |

### 1.3 几何绘制 (13 种)
| 类型 | 方法 | 参数 | 返回值 |
|------|------|------|--------|
| 点 | `AddPoint(pt)` | NCTI.Point | SketchPoint |
| 直线 | `AddLine(ptStart, ptEnd)` | NCTI.Point, NCTI.Point | SketchLine |
| 中心线 | `AddCenterLine(pt1, pt2)` | NCTI.Point, NCTI.Point | SketchCenterLine |
| 样条 | `AddSpline(controlPtList)` | list[NCTI.Point] | SketchSpline |
| 矩形 | `AddRect(ptStart, ptEnd)` | NCTI.Point, NCTI.Point | SketchRect |
| 圆 | `AddCircle(centerPt, radius)` | NCTI.Point, float | SketchCircle |
| 圆弧 | `AddArc(startPt, endPt, pt)` 或 `AddArc(r, startAngle, endAngle, centerPt)` | 三种模式 | SketchArc |
| 椭圆 | `AddEllipse(centerPt, majVec, minVec)` | NCTI.Point, NCTI.Vector, NCTI.Vector | SketchEllipse |
| 椭圆弧 | `AddEllipseArc(centerPt, majVec, minVec, dStartAngle, dEndAngle)` | 5 参数 | SketchEllipseArc |
| 圆角 | `CurveRadius(pt1, line1, pt2, line2)` | 点 - 线-点 - 线交替 | SketchFillet |
| 倒角 | `CurveChamfer(dist1, line1, dist2, line2)` | 距离 - 线-距离 - 线 | SketchChamfer |
| 修剪 | `CurveTrimming(pt, [objList])` | NCTI.Point + 可选对象数组 | - |
| 偏移 | `CurveOffset([objList], distance)` | 对象数组 + 距离 | - |

### 1.4 对象查询方法
| 对象类型 | 查询方法 |
|----------|----------|
| 点 | `Point()`, `ObjectName()`, `ObjectType()`, `SetObjectName(name)` |
| 直线 | `StartPoint()`, `EndPoint()`, `ObjectName()`, `ObjectType()`, `SetObjectName(name)` |
| 圆 | `Center()`, `Radius()`, `EditCenter(pos)`, `ObjectName()`, `ObjectType()`, `SetObjectName(name)` |
| 圆弧 | `Center()`, `Radius()`, `StartAngle()`, `EndAngle()`, `ObjectName()`, `SetObjectName(name)` |
| 椭圆 | `Center()`, `MajorAxis()`, `MinorAxis()`, `ObjectName()`, `SetObjectName(name)` |
| 中心线 | `StartPoint()`, `EndPoint()`, `ObjectName()`, `SetObjectName(name)` |
| 样条 | `ControlPoints()`, `ObjectName()`, `SetObjectName(name)` |

### 1.5 约束添加 (12 种)
| 类型 | 方法 | 参数模式 |
|------|------|----------|
| 水平尺寸 | `AddConsXpos(index, obj)` 或 `AddConsXpos(index1, obj1, index2, obj2)` | 需要 index |
| 竖直尺寸 | `AddConsYpos(index, obj)` 或 `AddConsYpos(index1, obj1, index2, obj2)` | 需要 index |
| 长度尺寸 | `AddConsLength(index, obj)` 或 `AddConsLength(index1, obj1, index2, obj2)` | 需要 index |
| 半径尺寸 | `AddConsRadius(obj)` 或 `AddConsRadius(radius, center)` | **不需要 index** |
| 角度尺寸 | `AddConsAngle(obj)` 或 `AddConsAngle(obj1, obj2)` | **不需要 index** |
| 平行 | `AddConsParallel(obj1, obj2)` | 两对象 |
| 垂直 | `AddConsVertical(obj1, obj2)` | 两对象 |
| 相切 | `AddConsTangent(obj1, obj2)` | 两对象 |
| 相等 | `AddConsEqual(obj)` 或 `AddConsEqual(obj1, obj2)` | 单/双对象 |
| 水平对齐 | `AddConsXAxis(obj)` 或 `AddConsXAxis(idx1, obj1, idx2, obj2)` | 双重模式 |
| 竖直对齐 | `AddConsYAxis(obj)` 或 `AddConsYAxis(idx1, obj1, idx2, obj2)` | 双重模式 |
| 重合 | `AddConsCoincide(index1, obj1)` 或 `AddConsCoincide(index1, obj1, index2, obj2)` | 需要 index |

### 1.6 约束编辑与显示控制
| 方法 | 说明 |
|------|------|
| `ShowCons(mode, [consList])` | 显示/隐藏约束 |
| `SwitchConsDisplay()` | 切换约束显示 |
| `SwitchConsRadius(cons)` | 半径/直径切换 |
| `FixedCons(obj)` | 添加固定约束 |
| `Tectonicline(mode, nameList)` | 构造线切换 |
| `LockSize(mode, nameList)` | 锁定尺寸 |
| `ConsRef(mode, nameList)` | 参考尺寸切换 |
| `SwitchConsLength(cons)` | 长度显示模式切换 |
| `ConsType(mode, nameList)` | 强/弱约束切换 |

### 1.7 约束编辑方法
| 方法 | 适用约束 | 说明 |
|------|----------|------|
| `EditSize(value)` | 尺寸类约束 | 修改尺寸值 |
| `EditLocation(pt)` | 尺寸类约束 | 修改位置 |
| `Size()` | 尺寸类约束 | 查询尺寸值 |
| `OpenSize()` | 平行约束 | 打开尺寸编辑 (必须先调用) |
| `CloseSize()` | 平行约束 | 关闭尺寸显示 |
| `ObjectName()` | 所有约束 | 查询名称 |
| `ConsData()` | 所有约束 | 查询约束数据 |

---

## 2. NCTI 命令 API 能力盘点

### 2.1 命令分类统计
| 类别 | 命令数 | 说明 |
|------|--------|------|
| 建模命令 | 338 | 几何体创建、布尔运算、扫掠等 |
| 基础命令 | 227 | 文档管理、视图、文件操作等 |
| 约束命令 | 133 | DCM 约束系统 |

### 2.2 文档管理
| 方法 | 说明 |
|------|------|
| `NCTI.Document()` | 实例化文档对象 |
| `doc.New(strGeom, strCons, strGrid)` | 创建内核文档 |
| `doc.Save(path)` | 保存文档 |
| `doc.Open(path)` | 打开 NCTI 文件 |
| `doc.Close()` | 关闭文档 |
| `doc.Delete()` | 删除文档 |
| `doc.Clear()` | 清空几何实体 |
| `doc.ExportFile(path, objName)` | 导出文件 |
| `doc.DataExchange(inPath, outPath)` | 文件格式转换 |
| `doc.DownloadFile(path)` | 下载导出文件 |

### 2.3 基础几何创建
| 命令 | 示例 |
|------|------|
| 长方体 | `doc.RunCommand("cmd_ncti_create_box", "name", pt, w, h, d)` |
| 圆柱 | `doc.RunCommand("cmd_ncti_create_cylinder", "name", r, h, pt, n)` |
| 圆锥 | `doc.RunCommand("cmd_ncti_create_cone", "name", r1, r2, h, pt, n, u)` |
| 球体 | `doc.RunCommand("cmd_ncti_create_sphere", "name", r, pt, n)` |
| 圆环 | `doc.RunCommand("cmd_ncti_create_torus", "name", majR, minR, pt, n)` |
| 平面 | `doc.RunCommand("cmd_ncti_create_plane", "name", pt, n)` |
| 直线 | `doc.RunCommand("cmd_ncti_create_line", "name", pt, vec)` |
| 顶点 | `doc.RunCommand("cmd_ncti_create_vertex", "name", pt)` |

### 2.4 布尔运算
| 命令 | 说明 |
|------|------|
| `cmd_ncti_boolean_unit` | 并集 |
| `cmd_ncti_boolean_cut` | 差集 |
| `cmd_ncti_boolean_intersect` | 交集 |

### 2.5 特征操作
| 命令 | 说明 |
|------|------|
| `cmd_ncti_fillet` | 圆角 |
| `cmd_ncti_chamfer` | 倒角 |
| `cmd_ncti_extrude` | 拉伸 |
| `cmd_ncti_revolve` | 旋转 |
| `cmd_ncti_sweep` | 扫掠 |
| `cmd_ncti_loft` | 放样 |

### 2.6 曲线/曲面
| 命令 | 说明 |
|------|------|
| `cmd_ncti_bspline_curve` | B 样条曲线 |
| `cmd_ncti_create_bezier_curve` | 贝塞尔曲线 |
| `cmd_ncti_create_bspline_surf` | B 样条曲面 |
| `cmd_ncti_make_helical_curve_by_point` | 螺旋线 |
| `cmd_ncti_make_helical_surface_by_curve` | 螺旋面 |

### 2.7 DCM 约束系统 (3D)
| 命令 | 说明 |
|------|------|
| `cmd_ncti_create_dcm3_dim_sys` | 创建约束系统 |
| `cmd_ncti_create_dcm3_point/line/circle/ellipse/cylinder` | 创建 DCM 几何 |
| `cmd_ncti_dcm3_fix` | 固定约束 |
| `cmd_ncti_dcm3_addd` | 添加约束 |
| `cmd_ncti_dcm3_evaluate` | 求解约束 |
| `cmd_ncti_dcm3_check` | 检查过约束 |
| `cmd_ncti_dcm3_get_overdefined_constraints` | 获取过约束集合 |

### 2.8 查询与分析
| 方法 | 说明 |
|------|------|
| `doc.GetTopoNb(obj)` | 获取拓扑数量 |
| `doc.FindFaceByNearestPoint(obj, pt)` | 根据点找面 |
| `doc.FindEdgeByNearestPoint(obj, pt)` | 根据点找边 |
| `doc.FindVertexByNearestPoint(obj, pt)` | 根据点找顶点 |
| `doc.FindGeomByNearestPoint(obj, pts)` | 查找最近几何 |
| `doc.GetBoundingBox(objs)` | 获取外包盒 |
| `doc.GetObbBoungdingBox(objs)` | 获取 OBB 包围盒 |
| `NCTI.BodyProp(doc, obj)` | 获取几何属性 (体积、表面积、重心、惯性矩) |
| `doc.FindFillets(objs, minR, maxR, type)` | 查找圆角 |
| `doc.FindHoles(objs, minD, maxD)` | 查找孔 |
| `doc.FindSmallFeatures(objs, type, tol)` | 查找小特征 |

### 2.9 视图与相机
| 方法 | 说明 |
|------|------|
| `doc.TopView()` | 俯视图 |
| `doc.FrontView()` | 前视图 |
| `doc.RightView()` | 右视图 |
| `doc.Zoom()` | 窗口最大化 |
| `doc.GetCamera()` | 获取相机信息 |
| `doc.SaveImage(path)` | 保存图片 |

### 2.10 选择集管理
| 方法 | 说明 |
|------|------|
| `NCTI.SelectionManager(doc)` | 创建选择管理器 |
| `sel.ClearSelected()` | 清除选择 |
| `sel.SetSelected()` | 设置选择 |
| `sel.ObjectNames` | 设置对象名称 |
| `sel.CellIDs` | 设置单元格 ID |
| `sel.SelectScreen()` | 屏幕框选 |

---

## 3. API 能力评估

### 3.1 Sketch API 优势
1. **完整的 2D 草图绘制能力** - 13 种几何绘制操作
2. **参数化约束系统** - 12 种尺寸/几何约束
3. **对象命名与查询** - 支持按名称获取和编辑对象
4. **增量编辑** - 支持通过 GetObject 获取已有对象进行编辑
5. **求解控制** - 支持自动/手动求解开关

### 3.2 Sketch API 局限
1. **无 3D 直接建模能力** - 仅限 2D 草图
2. **无装配功能** - 缺少多部件装配 API
3. **无参数化特征历史** - 缺少特征树管理
4. **无配置/设计表支持** - 缺少批量配置管理

### 3.3 NCTI API 优势
1. **丰富的 3D 建模命令** - 338 个建模命令
2. **完整的 DCM 约束系统** - 支持 3D 约束
3. **强大的查询能力** - 拓扑查询、特征识别
4. **文件互操作** - 支持 STEP/IGES 等格式
5. **几何分析** - 体积、表面积、惯性矩等

### 3.4 NCTI API 局限
1. **命令式 API** - 缺少参数化/特征树管理
2. **约束系统复杂** - DCM 约束需要手动管理
3. **缺少高级自动化接口** - 如模板化建模、配置驱动

---

## 4. 待分析的问题

1. 自动化建模需要哪些核心能力？
2. 现有 API 是否覆盖了这些能力？
3. 哪些场景下 API 不足？
4. 需要新增哪些 API 来支持自动化建模？

---

*此文档为阶段性分析文档，待工作流完成后更新*
