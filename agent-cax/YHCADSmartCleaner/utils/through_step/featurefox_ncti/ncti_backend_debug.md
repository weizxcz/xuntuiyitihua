# ncti_backend.py 逐行 Debug 文档

> 对一个真实通槽件跑 `NctiPart`，逐行记录每个变量的**真实输出 + 类型**（watch 窗口风格）。
> 用途：快速理解 NCTI AiModel 原生数据（`FaceAttr`/`EdgeAttr`）如何被加工成 featurefox 用的邻接图 + 边表。

## 调试对象

| 项 | 值 |
|---|---|
| 测试件 | `20221121_154647_1.step` |
| 面数 | 25 |
| NCTI 边记录数 | 132 |
| 日期 | 2026-06-22 |
| 环境 | `yhcad_py312` + NCTI SDK |
| 复现命令 | 见文末「附录：debug 脚本」 |

## 文件总览（4 部分）

```
count_advanced_faces()  L30   数 STEP 文本 ADVANCED_FACE → int
class NctiPart          L44   一个零件的 NCTI 数据视图（核心）
class NctiFaceAttrs     L176  NctiPart 的缓存包装（给特征提取用）
load_part()             L221  导入 STEP → 返回 (NctiPart, doc)
```

---

## Part 1 — `count_advanced_faces`（[L30-41](ncti_backend.py#L30-L41)）

```python
content = f.read()                                  # → str,  整个 STEP 文本
re.findall(r"ADVANCED_FACE\s*\(", content)          # → list[str], 共 25 个匹配
return len(...)                                     # → 25,   int
```

**真实输出**：`count_advanced_faces(stp) → 25 (int)`

这就是「面数断言」的基准——和 `n_faces` 比对，验 `shell ADVANCED_FACE 顺序 == ai.FaceID 顺序` 假设有没有破裂（NCTI 合并共面会让两者不等）。

---

## Part 2 — `NctiPart.__init__`（[L51-70](ncti_backend.py#L51-L70)）

```python
ai = ncti.AiModel(doc, obj_name)      # → AiModel（NCTI native，这个件的面/边数据容器）
self.n_faces    = len(ai.FaceID)      # → 25,                int
self.face_attrs = ai.FaceAttr         # → list, len=25；每项 list[float/int] len=12
self.edge_attrs = ai.EdgeAttr         # → list, len=132；每项 list len=12
self.face_eids  = ai.FaceEID          # → list[int], len=132（边的"到"面位置索引）
self.face_fids  = ai.FaceFID          # → list[int], len=132（边的"从"面位置索引）
```

**真实 watch**：

- `face_attrs[0] = [1.0, 0.0, 0.0, 0.0, 0.0, 0.02095, 0.0, 0.270, 0.191, 0.0407, 1, 4]`
  - `[0]=1.0` → 是平面 ｜ `[1]=0.0` → 非圆柱 ｜ `[5]=0.02095` → 面积 ｜ `[10]=1,[11]=4` → 面类型码
- `edge_attrs[0] = [True, False, False, 0.05295, 0.0, 0,0,0,0, 1.0, 0, 0]`
  - `[0]=True` → 凹 ｜ `[1]=False` → 非凸 ｜ `[2]=False` → 非光顺 ｜ `[3]=0.05295` → 边长 ｜ `[4]=0.0` → 非圆弧 ｜ `[9]=1.0` → 是直线
- `edge_attrs[1] = [True, False, False, 0.2090, 1.0, 0, ...]` → 凹、**圆弧**、长 0.209
- `face_eids[:6] = [22, 21, 20, 19, 18, 9]`，`face_fids[:6] = [24, 24, 24, 24, 23, 23]`
  - 即第 0 条边连 `面22↔面24`，第 1 条 `面21↔面24` …（成对的「到/从」面）

衍生表初始化为空（[L64-68](ncti_backend.py#L64-L68)）：

```python
self.adjacency      = defaultdict(set)  # → {}（面 → {邻居面}）
self.edge_convexity = {}                # → {}（(min,max) → 'concave'/'convex'/'smooth'）
self.edge_dihedral  = {}                # → {}（(min,max) → +1.0/-1.0/0.0）
self.edge_type      = {}                # → {}（→ 'line'/'circle'/'other'）
self.edge_length_map= {}                # → {}（→ float 累加长度）
```

---

## Part 3 — `_build_edge_tables`（[L72-127](ncti_backend.py#L72-L127)）核心

**聚合桶**（[L80-81](ncti_backend.py#L80-L81)）：

```python
agg = defaultdict(lambda: {"conv":None,"len":0.0,"line":0,"circle":0,"other":0})
# → {}，每个新 key 自动生成这个 dict
```

**遍历 132 条边**（[L83-116](ncti_backend.py#L83-L116)），前几条 trace：

```
i=0: fa=22, fb=24
     adjacency[22].add(24); adjacency[24].add(22)    # → {22:{24}, 24:{22}, ...}
     key = (22, 24)                                   # → tuple
     ea = edge_attrs[0] = [True,False,False,0.05295,...,1.0,...]
     # 凸凹性: ea[1]=False(非凸), ea[0]=True → agg[key]["conv"]='concave'
     # 长度:   agg[key]["len"] += 0.05295  → 0.05295
     # 类型:   ea[9]=1.0 → agg[key]["line"] += 1  → 1

i=1: fa=21, fb=24, key=(21,24)
     ea = [True,...,0.209,1.0(circular),...] → conv='concave', len=0.209, circle=1
```

**注意聚合**：同一对面多条边会累加。例如 `(22,24)` 实际有 **2 条** NCTI 边记录（各长 0.05295），聚合后：

- `agg[(22,24)] = {"conv":"concave", "len":0.1058, "line":2, "circle":0, "other":0}`

**固化 4 表**（[L119-127](ncti_backend.py#L119-L127)）：

```python
self.edge_convexity[(22,24)]  = "concave"   # → str
self.edge_dihedral[(22,24)]   = 1.0         # +1 = 凹（concave）
self.edge_length_map[(22,24)] = 0.106       # 0.05295×2 累加 → float
self.edge_type[(22,24)]       = "line"      # line 计数最多 → str
```

**真实 4 表（前 6 项）**：

```
edge_convexity:  [((22,24),'concave'), ((21,24),'concave'), ((20,24),'concave'),
                  ((19,24),'concave'), ((18,23),'concave'), ((9,23),'convex')]
edge_dihedral:   [((22,24),1.0), ..., ((9,23),-1.0)]        # +凹 / -凸
edge_type:       [((22,24),'line'), ((21,24),'circle'), ((20,24),'line'),
                  ((19,24),'circle'), ((18,23),'circle'), ((9,23),'line')]
edge_length_map: [((22,24),0.106), ((21,24),0.418), ((20,24),0.106),
                  ((19,24),0.418), ((18,23),0.804), ((9,23),0.203)]
adjacency:       {22:[4,19,21,24], 24:[19,20,21,22], 21:[4,20,22,24], 20:[4,19,21,24]}
                  # → dict[int, list[int]]，每面 4 个邻居
```

> `(9,23)` 是 `'convex'`/`-1.0`——通槽外角的凸边，和内部凹边（+1.0）符号相反。这正是边特征 `dihedral_sign` 的区分力来源（占特征重要性 top1）。

---

## Part 4 — 几何查询方法（[L131-173](ncti_backend.py#L131-L173)）

```python
face_normal(0):    vec=doc.GetNormalByUV(obj,0,0.5,0.5) → return (vec.X,vec.Y,vec.Z)
                   # → (-1.0, -0.0, 0.0)    tuple[float×3]   面0法向 = -X 方向
face_centroid(0):  pt=doc.GetFacePointFromUV(obj,0,0.5,0.5) → (pt.X,pt.Y,pt.Z)
                   # → (0.0, 30.44, 24.81)   tuple[float×3]   UV 中心点
face_area(0):      attr=face_attrs[0]; return float(attr[5])
                   # → 0.02095              float            取 FaceAttr[5]
face_ftype(0):     attr[0]==1.0 → "PLANE" / attr[1]==1.0 → "CYL" / else "OTHER"
                   # → 'PLANE'              str
face_perimeter(0): sum(edge_length_map[(min(c,nb),max(c,nb))] for nb in adjacency[0])
                   # → 13.5158              float            面0 所有邻接边长度和
```

---

## Part 5 — `NctiFaceAttrs`（[L176-218](ncti_backend.py#L176-L218)）

缓存包装，第一次算完存进 `self._area[cell]` 等 dict，后续直接命中：

```python
fa = NctiFaceAttrs(part)        # → NctiFaceAttrs；_area/_perim/_centroid/_normal/_ftype 都是 {}
fa.area(0)                       # 第一次: 调 part.face_area(0) → 0.02095，存 _area[0]
                                 # → 0.02095    float
fa.total_perimeter()             # sum(part.edge_length_map.values())
                                 # → 85.1159    float（全件所有边总长，归一化用）
```

---

## Part 6 — `load_part`（[L221-253](ncti_backend.py#L221-L253)）

```python
doc = ncti.Document()                       # → Document（若没传 doc）
doc.New("OCC","DCM","GMSH")                 # → 重置文档，选引擎
doc.ResetCaseResult(); doc.SetCreateGeGeom(1); doc.SetImportAssemelFile(1)
                                            # → 约定B（批量稳定）
ok = doc.RunCommand("cmd_ncti_import_file", stp, "testbox")
                                            # → True；native 打印 "Imoprt file:33.47ms"
part = NctiPart(ncti, doc, "testbox")       # → NctiPart（触发 Part 2+3）
return part, doc                            # → (NctiPart, Document)
```

**真实输出**：`load_part → part: NctiPart | doc: Document`，导入耗时 `33.47ms`。

---

## 真实例子：通槽件 `20221121_154647_1` 完整解析

把这个件的真实数据串成一个完整例子：25 个面里有 **3 个通槽面**（`seg=9 = {2, 3, 10}`），看 NCTI 怎么解析、`_build_edge_tables` 怎么聚合、边分类器最后学到什么。

### 1. 通槽结构（3 个面）

| cell_id | 类型 | 法向 (X,Y,Z) | 面积 | 重心 | 角色 |
|---|---|---|---|---|---|
| 2  | PLANE | ( 0.00, 0.61, 0.79) | 0.036 | (6.8, 15.2, 37.9) | 倾斜平面壁 |
| 3  | CYL   | ( 0.00,-0.61, 0.79) | 0.142 | (6.8, 45.7, 37.9) | 圆柱壁 |
| 10 | PLANE | (-1.00, 0.00, 0.00) | 0.099 | (13.7, 30.4, 48.2) | 端壁（法向 -X） |

拓扑（3 面通过 3 条凹边两两相连，三角形）：

```
                 面10  (端壁 PLANE, 法向 -X)
                /    \
         凹边 /        \ 凹边
        (2,10)          (3,10)
            /              \
   面2(PLANE 倾斜壁) ──凹边(2,3)── 面3(CYL 圆柱壁)
```

这是个**混合通槽**：一个端壁（面10）+ 一个平面壁（面2）+ 一个圆柱壁（面3），3 条内部凹边围成通槽。

### 2. 通槽内部边（两端面都在 seg9，应凹为主）— 共 3 条，**全部 concave**

| 边 | 凸凹性 | dihedral | 类型 | 长度 |
|---|---|---|---|---|
| (2, 10) | concave | **+1.0** | line | 2.191 |
| (2, 3)  | concave | **+1.0** | line | 0.780 |
| (3, 10) | concave | **+1.0** | line | 2.191 |

→ 通槽内部边 **100% 凹（+1.0）**。这是 featurefox 边分类器的**正样本（y=1）**。

### 3. 通槽边界边（一面在 seg9、一面在外，应凸为主）— 共 7 条，**全部 convex**

| 边 | 凸凹性 | dihedral | 类型 | 长度 |
|---|---|---|---|---|
| (0, 2)  | convex | **-1.0** | line | 2.191 |
| (0, 3)  | convex | **-1.0** | line | 2.191 |
| (1, 2)  | convex | **-1.0** | line | 0.780 |
| (1, 10) | convex | **-1.0** | line | 1.170 |
| (3, 4)  | convex | **-1.0** | line | 0.780 |
| (4, 10) | convex | **-1.0** | line | 1.170 |
| (9, 10) | convex | **-1.0** | line | 3.473 |

→ 通槽外角边 **100% 凸（-1.0）**。这是**负样本（y=0）**。

### 4. 边分类器从这个件学到了什么

喂给 `_build_edge_tables` 后，边分类器拿到的训练信号：

- 3 条内部凹边 → `y=1`（通槽内部），`dihedral_sign = +1`
- 7 条边界凸边 → `y=0`（非通槽内部），`dihedral_sign = -1`

**核心区分维度就是 `dihedral_sign`（凹 vs 凸）** —— 这正是它占特征重要性 top1 的原因。通槽的几何本质：**内部连接是凹的**（材料被切掉形成的槽底-壁转角），**外角是凸的**（零件原本的外棱）。

预测时：边分类器给 3 条凹边高概率 → 剪枝保留 → 连通分量 `{2, 3, 10}` → 通槽实例识别成功。**零映射**：输出的 `{2, 3, 10}` 就是 cell_id，直接和 seg9 验证 → 完全匹配（EXACT）。

### 5. 这个件的数据流（端到端）

```
20221121_154647_1.step
  │
  ├─ count_advanced_faces → 25                 # 验对齐（== n_faces ✓）
  │
  ├─ load_part → NctiPart
  │    ai.FaceAttr[25] / EdgeAttr[132] / FaceEID·FaceFID[132]
  │    └─ _build_edge_tables 聚合 → adjacency + 4 边表
  │         └─ 通槽面 {2,3,10} 的内部边全 concave(+1.0)、边界边全 convex(-1.0)
  │
  ├─ build_face_graph → 132 条共享边，每条 30 维特征（dihedral_sign 是 top1）
  │
  └─ 边分类器 → 凹边高概率 → 连通分量 {2,3,10} = 通槽实例  ✓ 对 seg9 EXACT
```

---

## 数据流（一句话串起来）

```
STEP 文件 → count_advanced_faces = 25          (验对齐)
        → doc.RunCommand import → NctiPart
             ai.FaceAttr[25] / EdgeAttr[132] / FaceEID/FaceFID[132]    (native, 位置索引)
             → _build_edge_tables 聚合 → adjacency + 4 张边表          (纯 python dict, key=(min,max))
             → 几何查询 (GetNormalByUV / GetFacePointFromUV / FaceAttr[5])
        → build_face_graph 用这些表算 30 维边特征
```

## 关键类型记忆

- `face_attrs` / `edge_attrs` 是 NCTI 给的 **`list[list]`**（按位置索引，native 原始数据）
- `adjacency` / `edge_convexity` / `edge_dihedral` / `edge_type` / `edge_length_map` 是我们自己建的 **`dict`**（按 `(min,max)` 面对聚合，纯 Python）
- 前者是**输入**，后者是 `_build_edge_tables` 加工后的**产物**——特征提取（`edge_features._edge_feature_vector`）只读后者
- 所有面号都是 `ai.FaceID` 的**位置索引**（0..n-1），全程一套编号，闭环自洽（零映射）

---

## 附录：debug 脚本

存为 `featurefox_ncti/_debug_backend.py` 后，从 `utils/through_step/` 执行（yhcad_py312 环境）：

```bash
PYTHONUNBUFFERED=1 "D:/Anaconda3/envs/yhcad_py312/python.exe" -m featurefox_ncti._debug_backend
```

脚本内容（自动取第一个含 seg=9 的件，打印所有变量的 repr + type）：

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""逐行 debug：对一个真实通槽件打印 NctiPart 各数据结构的 repr + type。"""
import os, sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
UTILS_DIR = os.path.dirname(os.path.dirname(THIS_DIR))
TS_DIR = os.path.dirname(THIS_DIR)
PROJECT_ROOT = os.path.dirname(UTILS_DIR)
for _p in (THIS_DIR, UTILS_DIR, TS_DIR, PROJECT_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from ncti_backend import load_part, count_advanced_faces, NctiFaceAttrs  # noqa
from ncti_faceid_map import init_ncti_safe  # noqa
from featurefox_ncti.instance_data import list_step_files, load_label, STEPS_DIR  # noqa


def main():
    ncti = init_ncti_safe(PROJECT_ROOT)
    if ncti is None:
        sys.exit("NCTI 初始化失败")
    stp = name = None
    for f in list_step_files(0, 0)[:500]:
        nm = os.path.splitext(f)[0]
        s9, _, _ = load_label(nm)
        if s9:
            stp, name = os.path.join(STEPS_DIR, f), nm
            break
    print("件 =", name)
    print("count_advanced_faces ->", repr(count_advanced_faces(stp)),
          type(count_advanced_faces(stp)).__name__)

    part, doc = load_part(stp, ncti)
    print("part:", type(part).__name__, "| n_faces =", part.n_faces,
          type(part.n_faces).__name__)
    print("face_attrs:", type(part.face_attrs).__name__, "len", len(part.face_attrs),
          "| [0]=", list(part.face_attrs[0]))
    print("edge_attrs:", type(part.edge_attrs).__name__, "len", len(part.edge_attrs),
          "| [0]=", list(part.edge_attrs[0]), "| [1]=", list(part.edge_attrs[1]))
    print("face_eids:", type(part.face_eids).__name__, "len", len(part.face_eids),
          "| [:6]=", list(part.face_eids[:6]))
    print("face_fids:", type(part.face_fids).__name__, "| [:6]=", list(part.face_fids[:6]))
    print("adjacency(前4面):",
          {k: sorted(v) for k, v in list(part.adjacency.items())[:4]})
    print("edge_convexity(前6):", list(part.edge_convexity.items())[:6])
    print("edge_dihedral(前6):", list(part.edge_dihedral.items())[:6])
    print("edge_type(前6):", list(part.edge_type.items())[:6])
    print("edge_length_map(前6):",
          [(k, round(v, 3)) for k, v in list(part.edge_length_map.items())[:6]])
    print("face_normal(0)=", part.face_normal(0), type(part.face_normal(0)).__name__)
    print("face_centroid(0)=", part.face_centroid(0), type(part.face_centroid(0)).__name__)
    print("face_area(0)=", part.face_area(0), type(part.face_area(0)).__name__)
    print("face_ftype(0)=", repr(part.face_ftype(0)), type(part.face_ftype(0)).__name__)
    print("face_perimeter(0)=", round(part.face_perimeter(0), 4),
          type(part.face_perimeter(0)).__name__)
    fa = NctiFaceAttrs(part)
    print("NctiFaceAttrs.area(0)=", fa.area(0),
          "| total_perimeter=", round(fa.total_perimeter(), 4))
    os._exit(0)


if __name__ == "__main__":
    main()
```
