# StepParser 可提取的 STEP 信息清单

> 整理 `YHCADSmartCleaner\utils\detect_blind_holes_and_export_stp_v15_22.py:StepParser`
> 加上 `featurefox/edge_features.py:FaceAttrs`、`detect_through_step.py:_face_*` 等
> 辅助函数后，**从 STEP 文本（ISO 10303-21 / AP214）能拿到 / 算出的所有几何信息**。

---

## 1. `StepParser` 数据字典（parse 完直接读）

`StepParser.parse()` 后会产生以下字典/集合结构，按 STEP 实体分类：

### 1.1 实体层

| 属性 | 类型 | 内容 |
| --- | --- | --- |
| `parser.entities` | `dict[int, {"type", "params", "raw"}]` | **所有 STEP 实体的原始解析结果**。key = entity id（整数），value = 类型名 + 参数文本 + 原始字符串 |
| `parser.advanced_faces` | `dict[int, {"bounds", "surface", "same_sense"}]` | 每个 ADVANCED_FACE 的边界 ref 列表、引用的 surface id、`same_sense`（`.T.`/`.F.`） |
| `parser.face_bounds` | `dict[int, {"type", "loop", "is_outer"}]` | FACE_OUTER_BOUND / FACE_BOUND 实体，type/loop ref/是否外边界 |
| `parser.edge_loops` | `dict[int, list[int]]` | EDGE_LOOP → ORIENTED_EDGE id 列表 |
| `parser.oriented_edges` | `dict[int, {"curve"}]` | ORIENTED_EDGE → EDGE_CURVE ref（**注意：未存方向**）|
| `parser.edge_curves` | `dict[int, {"v1", "v2", "curve"}]` | EDGE_CURVE → 起止 vertex ref + 底层 curve 实体 ref |

### 1.2 几何层

| 属性 | 类型 | 内容 |
| --- | --- | --- |
| `parser.points` | `dict[int, (x, y, z)]` | **所有 CARTESIAN_POINT**——直接给 3D 坐标 |
| `parser.directions` | `dict[int, (dx, dy, dz)]` | 所有 DIRECTION——单位向量（不归一化） |
| `parser.vertex_points` | `dict[int, int]` | VERTEX_POINT → CARTESIAN_POINT ref |
| `parser.axis2` | `dict[int, {"point_ref", "axis_ref", "ref_direction_ref"}]` | AXIS2_PLACEMENT_3D → 三个 ref（原点/Z方向/X方向） |
| `parser.surfaces` | `dict[int, {"type", "axis_ref", "radius", "semi_angle", "major_radius", "minor_radius"}]` | 各类曲面参数（PLANE/CYL/CONE/SPHERE/TORUS/B_SPLINE） |

**曲面 type → 字段映射**：

| etype | radius | semi_angle | major_radius | minor_radius |
| --- | --- | --- | --- | --- |
| `PLANE` / `B_SPLINE_SURFACE_WITH_KNOTS` | — | — | — | — |
| `CYLINDRICAL_SURFACE` | ✅ 半径 | — | — | — |
| `SPHERICAL_SURFACE` | ✅ 半径 | — | — | — |
| `CONICAL_SURFACE` | ✅ 底部半径 | ✅ 半角 | — | — |
| `TOROIDAL_SURFACE` | = minor_radius | — | ✅ 主半径 | ✅ 小半径 |

### 1.3 拓扑索引（`_build_topology_indexes` 生成）

| 属性 | 类型 | 内容 |
| --- | --- | --- |
| `parser.surface_to_faces` | `defaultdict[list]` | surface id → 引用它的所有 face id（**多个 face 可共享一个曲面**）|
| `parser.edge_curve_to_faces` | `defaultdict[set]` | EDGE_CURVE id → 共享它的所有 face id（用于求邻接面）|
| `parser.face_to_edge_curves` | `defaultdict[set]` | face id → 该面所有 EDGE_CURVE id |
| `parser.face_to_edges_by_bound` | `defaultdict[list]` | face id → 各边界（外/内）的详细结构（loop ref + curve 列表）|

---

## 2. `StepParser` 内置辅助方法

| 方法 | 返回 | 说明 |
| --- | --- | --- |
| `face_surface_type(face_id)` | str | `"PLANE" / "CYLINDRICAL_SURFACE" / "CONICAL_SURFACE" / "SPHERICAL_SURFACE" / "TOROIDAL_SURFACE" / "B_SPLINE_SURFACE_WITH_KNOTS" / "UNKNOWN"` |
| `face_surface_id(face_id)` | int 或 None | 该面引用的 surface 实体 id |
| `axis_info(surface_id)` | `{"point", "direction", "ref_direction"}` | 曲面的轴线（原点 + Z 方向 + X 方向） |
| `face_bound_count(face_id)` | `(outer, inner, total)` | 外边界数、内边界数、总边界数 |
| `face_loop_curve_counts(face_id)` | `list[int]` | 每个 loop 的不重复 EDGE_CURVE 数 |
| `face_total_curve_count(face_id)` | int | 所有 loop 的 EDGE_CURVE 总数 |
| `vertex_xyz(vertex_id)` | `(x, y, z)` 或 None | 顶点的 3D 坐标 |
| `edge_vertices_xyz(edge_curve_id)` | `[(x,y,z), (x,y,z)]` | 边的两端点坐标（顺序对应 v1, v2）|
| `edge_base_curve_type(edge_curve_id)` | str | 边底层曲线类型：`"LINE" / "CIRCLE" / "B_SPLINE_CURVE" / "SURFACE_CURVE" / ...` |
| `edge_vertex_refs(edge_curve_id)` | `[v1, v2]` | 边的 vertex 实体 id |
| `cylindrical_face_axial_span(surface_id, face_id)` | float 或 None | 圆柱面所有顶点沿轴线方向的投影范围（**轴向跨度**，不是半径）|

---

## 3. 几何计算层（`detect_through_step.py` + `edge_features.py`）

### 3.1 面级几何

| 函数 | 签名 | 说明 |
| --- | --- | --- |
| `_face_normal(parser, fid)` | `(nx, ny, nz)` 或 None | **面法向原始**（来自 AXIS2_PLACEMENT_3D.Z），**未做 same_sense 修正** |
| `_face_normal_effective(parser, fid)` | `(nx, ny, nz)` 或 None | **面有效外法向**（已 same_sense 修正）—— PLANE/CYL/CONE/SPHERE/TORUS 都用这个 |
| `_cyl_surface_normal_at_point(parser, fid, point)` | `(nx, ny, nz)` 或 None | **圆柱面在指定点的径向法向**（已 same_sense 修正）—— 关键，单点精确 |
| `_face_normal_at_edge(parser, fid, edge_midpoint)` | `(nx, ny, nz)` 或 None | **统一接口**：PLANE 用 effective；CYL 用径向（边中点） |
| `_face_centroid(parser, fid)` | `(x, y, z)` 或 None | **面顶点集凸包重心**（顶点的算术平均） |
| `_face_vertices(parser, fid)` | `[(x, y, z), ...]` | 面的所有顶点坐标（去重） |
| `_face_area_approx(parser, fid, normal=None)` | float | **PLANE 近似面积**：顶点投到面平面 + 角度排序 + 鞋带公式。**对曲面（CYL/CONE）无效**——返回 0 或垃圾 |
| `FaceAttrs.area(fid)` | float | 同上，带缓存 |
| `FaceAttrs.normal(fid)` | `(nx, ny, nz)` | **按 ftype 分支**：PLANE → `_face_normal_effective`；CYL → `_cyl_surface_normal_at_point(centroid)`；其他 → `_face_normal_effective` |
| `FaceAttrs.centroid(fid)` | `(x, y, z)` | 同 `_face_centroid`，带缓存 |
| `FaceAttrs.ftype(fid)` | `"PLANE" / "CYL" / "OTHER"` | 3 分类简版 |
| `FaceAttrs.perimeter(fid)` | float | 面周长 = 各边长度之和 |
| `FaceAttrs.total_perimeter()` | float | 整个零件的所有边总长 |

### 3.2 边级几何

| 函数 | 签名 | 说明 |
| --- | --- | --- |
| `edge_length(parser, ec_id)` | float | **LINE: 端点距离**；**CIRCLE: 弧长**（`r * 2*asin(chord/2r)`）；其他曲线：端点距离近似 |
| `_circle_radius_center(parser, ec_id)` | `(radius, center_xyz)` 或 `(None, None)` | CIRCLE 边的半径和圆心 |
| `_compute_edge_convexity(parser, face_a, face_b)` | `(label, sign)` | **质心偏移法**：计算共享边的凸凹性。`label ∈ {"concave", "convex", "smooth", "unknown"}`；`sign` 是连续值 `[-1, +1]`（+1=强凹，-1=强凸） |
| `_unwrap_curve_entity(parser, ec_id)` | int 或 None | 拆开 SURFACE_CURVE 包装，返回底层几何实体 id |

### 3.3 几何关系

| 函数 | 签名 | 说明 |
| --- | --- | --- |
| `_face_edge_ids(parser, fid)` | set | 该面所有 EDGE_CURVE id |
| `_shared_edge_ids(parser, fa, fb)` | set | 两面共享的 EDGE_CURVE id |
| `_adjacent_faces_of_face(parser, fid)` | list | 共享 ≥1 条边的所有邻接面 id |
| `edge_curve_to_faces[ec_id]` | set | 直接查表：共享某条 EDGE_CURVE 的所有面 id |
| `surface_to_faces[surface_id]` | list | 共享同一曲面的所有面 id（**共面/共轴检测基础**）|
| `_plane_basis_for_face(parser, fid)` | `(origin, u_vec, v_vec)` | PLANE 面的 2D 基（参数矩形） |
| `_project_to_plane_2d(point, basis)` | `(u, v)` | 3D 点投到 PLANE 基的 2D 坐标 |
| `_point_in_bbox_2d(pt, bbox, tol)` | bool | 2D 点是否在 bbox 内 |

### 3.4 点/曲线几何

| 函数 | 签名 | 说明 |
| --- | --- | --- |
| `_circle_axis_center_radius(parser, ec_id)` | `(axis_dir, center, radius)` | CIRCLE 的轴线方向、圆心、半径 |
| `_circle_edge_center_radius(parser, ec_id)` | `(center, radius)` | CIRCLE 的圆心和半径 |
| `_edge_circle_center_radius_axis(parser, ec_id)` | 三元组 | 同上（detect_through_step.py:1687）|
| `_point_line_distance(point, line_point, line_dir)` | float | 点到直线距离 |
| `_edge_is_circle(parser, ec_id)` | bool | 边的底层曲线是否为 CIRCLE |
| `_circle_edge_nonpartial(parser, ec_id)` | bool | CIRCLE 边是否完整（端点重合 → 整圆）|
| `_circle_group_is_closed(parser, edges)` | bool | 圆边组是否构成闭环 |

---

## 4. 衍生特征（用于通槽识别）

| 函数 | 用途 |
| --- | --- |
| `_plane_shared_ring_score(parser, fid)` | PLANE 是否被多个相邻 CYL 围成环 |
| `_cylinder_adjacent_to_plane_by_circle(parser, cyl_face, plane_face)` | CYL 和 PLANE 是否被圆边相邻 |
| `_axis_group_signature(parser, cyl_faces)` | 多 CYL 共轴签名（axis + 半径）|
| `_shared_plane_circle_coverage(parser, plane_face, circle_center, circle_radius, samples)` | 圆被 PLANE 覆盖比例 |
| `_shared_bottom_disk_local_integrity(...)` | 共享底面完整性（局部覆盖检查）|
| `_shared_plane_is_rectangular_strip(parser, plane_face, min_aspect)` | PLANE 是否矩形/带状 |
| `_shared_rect_candidate_from_cylinder(...)` | 从 CYL 生成矩形共享底候选 |
| `_classify_complete_cylindrical_wall(parser, fid)` | CYL 完整/部分判定 |
| `_is_clean_two_circle_cyl_wall(parser, fid)` | CYL 上下两圆口判定 |
| `find_shared_multi_ring_plane_holes(...)` | 寻找多环平面通孔（**通槽入口识别**）|
| `find_partial_mouth_sector_blind_holes(...)` | 部分圆口盲孔识别 |
| `find_variable_depth_truncated_blind_holes(...)` | 变深度截断盲孔识别 |
| `find_split_cyl_wall_blind_holes(...)` | 分割圆柱壁盲孔识别 |
| `find_double_chamfer_slit_blind_holes(...)` | 双倒角缝盲孔识别 |

---

## 5. 数据语义陷阱（已知）

### 5.1 STEP 文本**不含**的字段

| 缺失字段 | 原因 | 现有近似 |
| --- | --- | --- |
| **曲面（CYL/CONE/SPHERE/TORUS）的真实面积** | STEP 不存，必须做曲线积分 | **当前无实现**——`_face_area_approx` 对曲面无效 |
| **UV 参数化网格采样（5×5 等）** | STEP 不存网格采样点 | **当前无**——需自己造（PLANE 容易，CYL 需从几何参数反推）|
| **NURBS 曲面的几何中心** | 控制点 ≠ 实际重心 | 无现成 |
| **ORIENTED_EDGE 方向（forward/reverse）** | parser 未存 `parts[3]` | `_compute_edge_convexity` 用"去除边方向分量"规避 |

### 5.2 `_face_area_approx` 的根上限制

- **圆弧/曲面边被弦化**：弧边只取起止两个端点
- **按角度排序假设凸多边形**：实际面可能非凸或带洞
- 详细诊断见 `step_parser_extracted_info.md` 之外，更详细的面积语义差异在 CLAUDE.md 的"已知数据语义差异"小节

### 5.3 `fa.normal(fid)` 对 CYL 的语义陷阱

| ftype | `FaceAttrs.normal(fid)` 实际返回 |
| --- | --- |
| `PLANE` | 整面恒定法向 ✅ |
| `CYL` | **轴线方向**（不是面法向）—— `_cyl_surface_normal_at_point(centroid)` 算的径向法向 ✅ |
| `OTHER` | surface 基础方向（不一定指向有效体外）|

**正确用法**：CYL 应当**单点计算**，调用 `_cyl_surface_normal_at_point(parser, fid, point)`，不能用 `fa.normal(fid)`。

### 5.4 `same_sense` 翻转未对齐

- `_face_normal_effective` 已 same_sense 修正 ✅
- `_cyl_surface_normal_at_point` 已 same_sense 修正 ✅
- `_compute_edge_convexity` 已 same_sense 修正（通过 `_face_normal_at_edge`）✅
- **未做修正的**：原始 `_face_normal`（不推荐使用）

---

## 6. 与 NCTI 数据的语义差异（对照参考）

> 详见 `through_step/CLAUDE.md` 的"已知数据语义差异"小节。

| 量 | STEP 侧 | NCTI 侧 |
| --- | --- | --- |
| **面法向（单点）** | `_cyl_surface_normal_at_point(parser, fid, centroid)` | `doc.GetNormalByUV(obj, i, 0.5, 0.5)` |
| **面中心** | `_face_centroid(parser, fid)`（顶点凸包重心）| `doc.GetFaceMidPoint(obj, i)`（OCC 几何中心）|
| **面顶点** | `_face_vertices(parser, fid)`（精确）| `doc.GetPointFromUV(obj, i, u, v)` 采样 |
| **面边界点集** | ✅ 精确（EDGE_LOOP 全顶点）| ⚠️ `GetAllPointsOfFace` 类接口**不存在** |
| **5×5 UV 网格点/法向** | ❌ 不存，需自造 | ✅ `ai_data_info.FacePoints` / `FaceNormals` |
| **面积** | ⚠️ PLANE 近似（凸包鞋带，n_verts=4 精确）/ 曲面无 | ✅ OCC 引擎精确积分（`FaceAttr[5]`，但 PLANE 不可信 p50=0.001）|
| **归一化坐标** | ❌ | ✅ `FaceAttr[7..9]`（bbox min-max → [-1, 1]）|

---

## 7. 用法示例

```python
from detect_blind_holes_and_export_stp_v15_22 import StepParser
from featurefox.edge_features import FaceAttrs

parser = StepParser("path/to/file.step")
parser.parse()

# 1. 遍历所有面
for fid in parser.advanced_faces:
    print(f"face {fid}: type={parser.face_surface_type(fid)}, same_sense={parser.advanced_faces[fid]['same_sense']}")

# 2. 取所有 3D 点
all_pts = [pt for pt in parser.points.values() if pt is not None and len(pt) >= 3]
print(f"total CARTESIAN_POINT: {len(all_pts)}")

# 3. 面级几何（用 FaceAttrs 缓存包装）
fa = FaceAttrs(parser)
for fid in parser.advanced_faces:
    print(f"face {fid}: ftype={fa.ftype(fid)}, normal={fa.normal(fid)}, centroid={fa.centroid(fid)}, area={fa.area(fid)}")

# 4. 邻接面
for fid in parser.advanced_faces:
    adj = _adjacent_faces_of_face(parser, fid)  # 需 import
    print(f"face {fid} adjacent to {len(adj)} faces")

# 5. 边凸凹性
label, sign = _compute_edge_convexity(parser, fa, fb)
# label ∈ {"concave", "convex", "smooth", "unknown"}
```

---

## 8. 当前实现缺什么（如有需要可补）

| 缺的量 | 用途 | 实现难度 |
| --- | --- | --- |
| CYL/CONE 面真实面积 | STEP vs NCTI 面积匹配 | ⭐⭐（曲线积分）|
| UV 参数化网格点（PLANE/CYL）| 与 NCTI `FacePoints[i][u][v]` 点对点匹配 | ⭐⭐ |
| 5×5 UV 网格采样（曲面）| 同上（曲面复杂）| ⭐⭐⭐⭐ |
| NURBS 曲面法向/面积 | 完整 STEP 几何支持 | ⭐⭐⭐⭐⭐ |
| `parser.oriented_edges` 存方向 | 严格 half-edge 数据结构 | ⭐ |
| 面真实中心（边长加权）| 比凸包重心更准 | ⭐⭐ |

---

## 9. 相关文件

| 文件 | 角色 |
| --- | --- |
| `detect_blind_holes_and_export_stp_v15_22.py` | StepParser 类本体（4491 行）|
| `detect_through_step.py` | `_face_normal*` / `_face_centroid` / `_face_area_approx` / `_compute_edge_convexity` 等几何辅助 |
| `featurefox/edge_features.py` | `FaceAttrs` 缓存包装 + `edge_length` + `_circle_radius_center` 等边级几何 |
| `featurefox/ncti_faceid_map.py` | **NCTI 侧几何指纹映射**——对比用 |
| `check_order_assumption.py` | STEP/NCTI 顺序假设验证（用这里的接口） |
| `through_step/CLAUDE.md` | 整体模块说明 + 已知数据语义差异 |