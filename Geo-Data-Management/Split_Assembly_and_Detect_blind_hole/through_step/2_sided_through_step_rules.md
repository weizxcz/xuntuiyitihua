# 双侧通槽台阶 (2-sided through step) STEP 几何识别规则

> 基于 1000 个标注样本（`D:\wyg\data\data\通槽`）的统计归纳。
> 生成日期：2026-06-09

---

## 1. 特征定义

**双侧通槽台阶**：在基础体上，由 3 个平面组成的台阶形凹槽，沿槽长度方向两端贯通。

几何形态为 Π 形截面（倒 U 形）沿一个方向拉伸：

```
    ┌──────────────────┐
    │  基面 (不属于特征)  │
    ├──┐            ┌──┤
    │  │  侧壁 A     │  │  ← PLANE，法线朝槽内
    │  │            │  │
    │  └────────────┘  │
    │    底面          │  ← PLANE，法线与两侧壁都垂直
    └──────────────────┘
         ↕ 开放端        ↕ 开放端
```

---

## 2. 纯 STEP 拓扑/几何识别规则

以下规则仅依赖 STEP 文件文本中的实体和引用关系，**不依赖任何标注标签**。

### 必要条件（所有条件必须同时满足）

#### 条件 1：3 个 ADVANCED_FACE 底面均为 PLANE

```
遍历 CLOSED_SHELL 中所有 ADVANCED_FACE，
候选面 F 的底层曲面实体类型必须为 PLANE。
```

提取方式：
- `ADVANCED_FACE` → 引用 `#surface_id`
- `#surface_id = PLANE(...)` → 类型为 PLANE

#### 条件 2：3 个面两两通过共享 EDGE_CURVE 邻接

```
对于候选三元组 {A, B, C}：
  A 和 B 共享至少 1 条 EDGE_CURVE
  A 和 C 共享至少 1 条 EDGE_CURVE
  B 和 C 共享至少 1 条 EDGE_CURVE
```

即 3 个面在 STEP 拓扑中形成**三角形邻接关系**。

提取方式：
- `ADVANCED_FACE` → `FACE_BOUND` → `EDGE_LOOP` → `ORIENTED_EDGE` → `EDGE_CURVE`
- 通过 `EDGE_CURVE` 被两个不同面引用来判断共享

#### 条件 3：法向量角度 — 至少 2 对近似垂直（75°-105°）

```
提取 3 个 PLANE 面的法向量 N_a, N_b, N_c：
  计算 3 对夹角：angle(N_a,N_b), angle(N_a,N_c), angle(N_b,N_c)
  其中至少 2 对夹角在 [75°, 105°] 范围内
```

提取方式：
- `PLANE` → `AXIS2_PLACEMENT_3D` → `DIRECTION` → 法向量 (dx, dy, dz)
- 夹角 = arccos(|dot(N_i, N_j)|)

#### 条件 4：存在唯一底面 — 其法向量与两侧壁都近似垂直

```
在 3 个面中找到满足以下条件的唯一面 F_bottom：
  angle(N_bottom, N_wall_A) ∈ [75°, 105°]
  angle(N_bottom, N_wall_B) ∈ [75°, 105°]
```

若不存在或存在多个，则该三元组不构成通槽。

#### 条件 5：两侧壁法向量在底面切平面上的分量方向相反

```
将两侧壁法向量投影到底面切平面上：
  proj_A = N_wall_A - dot(N_wall_A, N_bottom) × N_bottom
  proj_B = N_wall_B - dot(N_wall_B, N_bottom) × N_bottom

通槽特征：dot(proj_A, proj_B) < 0
  （两侧壁法向量在底面平面内朝向对方 → 指向槽内）
```

这是区分通槽台阶与普通直角/角台的关键条件：
- **通槽**：两侧壁法向量在底面平面内的分量朝向对方（负点积）
- **直角**：两侧壁法向量在底面平面内的分量朝向相近方向（正点积或接近零）

#### 条件 6：共享边底层曲线类型主要为 LINE

```
3 个面之间共享的 EDGE_CURVE，其底层几何曲线类型
应主要为 LINE（直线段），不是 CIRCLE 或 B_SPLINE。
```

提取方式：
- `EDGE_CURVE` → `curve_geom_ref`
- 若为 `SURFACE_CURVE`，则再引用 → 底层 `LINE` / `CIRCLE`

---

## 3. 统计依据

| 统计项 | 结果 |
|--------|------|
| 曲面类型 | 100% PLANE（3778 面，0 个曲面） |
| 典型面数/实例 | 3 面（71%），4 面（11%），6 面（9%） |
| 面边数 | 53% 为 4 条边，26% 为 5 条边 |
| 边类型 | >99% LINE |
| 法向量角度模式 | OVV 77%, PVV 15%, VVV 6% |
| 底面 bottom=1 | 100%（非平行面始终是底面） |

> P = 平行 (<10°), V = 垂直 (80-100°), O = 其他角度

---

## 4. 识别局限性

上述纯几何规则存在以下局限性：

1. **误检率较高**：CAD 模型中存在大量满足上述条件的 3 面组合（如直角台阶、棱边组合），统计上约 30% 的候选为误检。

2. **开放端检测困难**：仅从 STEP 面级拓扑难以可靠判断槽的两端是否开放（非盲端），这需要更高级的体积/边界分析。

3. **建议**：纯 STEP 几何规则适合作为**候选生成器**，生成候选后结合以下方式进一步过滤：
   - AI 模型（AAGNet 面分割）做二次验证
   - 体积分析判断是否为凹特征
   - 用户交互确认

---

## 5. 伪代码

```python
def detect_2sided_through_step(step_parser):
    # 1. 收集所有 PLANE 面及其法向量
    plane_faces = [(fid, get_plane_normal(fid))
                   for fid in all_advanced_faces
                   if surface_type(fid) == "PLANE" and get_plane_normal(fid)]

    # 2. 构建邻接图（通过共享 EDGE_CURVE）
    adjacency = build_adjacency_from_shared_edges(plane_faces)

    # 3. 枚举所有互相邻接的三元组
    candidates = []
    for a, b, c in find_triangles(adjacency):
        na, nb, nc = normals[a], normals[b], normals[c]

        # 4. 角度检查：至少 2 对垂直
        angles = [angle(na,nb), angle(na,nc), angle(nb,nc)]
        if sum(1 for a in angles if 75 <= a <= 105) < 2:
            continue

        # 5. 识别底面
        bottom = find_face_perp_to_both(a, b, c, na, nb, nc)
        if bottom is None:
            continue
        walls = [f for f in (a,b,c) if f != bottom]

        # 6. 切平面投影方向相反
        proj_a = na - dot(na, n_bottom) * n_bottom  # 去掉底面法线分量
        proj_b = nb - dot(nb, n_bottom) * n_bottom
        if dot(proj_a, proj_b) >= 0:
            continue  # 不是通槽，是直角

        candidates.append({
            faces: [a, b, c],
            bottom: bottom,
            side_walls: walls,
        })

    return candidates
```
