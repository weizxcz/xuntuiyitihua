# lib/ — 核心库

NCTI 数据后端 + 特征提取 + 标签处理。所有模块使用相对导入，无环形依赖。

## 模块清单

### `ncti_backend.py`
NCTI 数据后端，封装炎核 SDK。

| 导出 | 说明 |
|------|------|
| `NctiPart` | 轻量代理，提供 `n_faces` / `edge_convexity` / `faces` |
| `NctiFaceAttrs` | 面属性查询：`ftype(cell_id)` → `"PLANE"` / `"CYLINDER"` / `"CONE"` 等 |
| `load_part(step_path, ncti, ...)` | 导入 STEP → NctiPart（约定A：OCC 对象名 + face 序列） |
| `count_advanced_faces(step_path)` | 正则统计 STEP 文件中 ADVANCED_FACE 数量 |

### `ncti_faceid_map.py`
NCTI 初始化 + STEP ↔ NCTI 面 ID 映射。

| 导出 | 说明 |
|------|------|
| `init_ncti_safe(project_root)` | 通过 `config/config_load` 初始化 NCTI SDK |
| `build_step_face_to_ncti_pos_map(...)` | 建立 STEP face_id → ai.FaceID 位置索引的双射映射 |

### `edge_features.py`
边特征提取器（FeatureFox 论文 30 维特征）。

| 导出 | 说明 |
|------|------|
| `FEATURE_NAMES` | 30 维特征名称列表 |
| `build_face_graph(part)` | 构建 AAG，返回 `(edges, NctiFaceAttrs)` |

每条边特征包含：二面角符号、夹角弧度、边长度/凹凸性、邻面类型/面积/包围盒等。

### `instance_features.py`
实例级特征提取器（26 维），用于第二级分类器区分真盲孔与硬负样本。

| 导出 | 说明 |
|------|------|
| `INSTANCE_FEATURE_NAMES` | 26 维特征名称 |
| `extract_instance_features(part, fa, conv_map, cells, edge_probs)` | 提取连通分量的实例特征 |

### `instance_data.py`
标签加载 + 训练数据生成（多进程 chunk 隔离）。

| 导出 | 说明 |
|------|------|
| `load_label(name)` | 加载 JSON 标签 → `(seg, inst, n)` |
| `list_step_files(max, offset)` | 列出 STEP 文件 |
| `collect_dataset()` | 子进程分 chunk 收集训练数据 |
| `build_training_sample()` | 构建单件训练样本 |
| `STEPS_DIR` / `LABELS_DIR` | 数据路径 |

### `geom_helpers.py`
纯几何工具函数，无外部依赖。

- `_dot(a, b)` — 点积
- `_vec_len(v)` — 向量长度
- `_angle_between_normals(n1, n2)` — 法向量夹角
- `_project_to_plane(pt, origin, normal)` — 点投影到平面

### `face_registration.py`
STEP ↔ NCTI 面几何配准（双射验证）。

用于验证 NCTI 导入后面 ID 映射的正确性，通过质心位置 + 面积 + 法向量等几何属性进行最近邻匹配。
