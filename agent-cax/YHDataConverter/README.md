# GeoConv — 几何数据转换工具

GeoConv 是一款面向 CAD 三维模型的几何数据转换工具。导入 STEP/IGS 模型后，可将模型转换为多种机器学习数据格式（属性、Graph 拓扑、UV 网格、点云、多视图），用于几何深度学习模型的训练。

## 功能特点

- **模型导入**：支持 STEP（.step/.stp）、IGES（.igs）格式
- **3D 交互**：嵌入 NCTI 渲染引擎，支持旋转、缩放、面选择
- **5 种数据转换**：
  - **属性提取** — 13D 面属性 + 12D 边属性 → JSON
  - **拓扑提取** — 面邻接图 + 属性 + UV 网格 + 邻接矩阵 → JSON
  - **网格采样** — 面网格（5×5×7）+ 边网格（5×7，含二面角）→ JSON
  - **点云采样** — mesh 表面均匀采样 20000 点 → PLY
  - **多视图渲染** — 6 个视角渲染 PNG 图片
- **5 种可视化**：
  - **属性可视化** — 面/边属性表格展示，支持面类型动态过滤，导出 CSV
  - **拓扑可视化** — networkx 构建面邻接图，graphviz 渲染，支持缩放平移，导出 SVG + JSON
  - **网格可视化** — 嵌入 NCTI 3D 视图显示 UV 点，可保存 JSON
  - **点云可视化** — Open3D 独立窗口显示点云
  - **多视图可视化** — 6 方向离屏渲染，2×3 网格弹窗展示，导出 PNG

## 环境要求

- Windows 10 及以上
- Python 3.12+
- wxPython 4.2.1
- numpy
- open3d
- NCTI SDK（配置 `config/system_config.json` 中的 DLL 路径）

## 快速开始

```bash
conda create -n geoconv python=3.12
conda activate geoconv
pip install -r requirements.txt
python main.py
```

操作流程：

```text
创建零件 → 导入 STEP 模型 → 切换到"转换"选项卡 → 选择转换类型 → 保存结果
```

## 项目结构

```text
GeoConv/
├── config/                 # 配置
│   ├── config_load.py          # SDK 初始化，加载 DLL，创建全局 NCTI 实例
│   └── system_config.json      # SDK 路径配置
├── dialog/                 # 文件对话框
│   ├── import_file.py          # 导入 STP/STEP/IGS
│   ├── export_file.py          # 导出模型
│   └── ...
├── function/               # 核心逻辑
│   ├── mouse_event_delegate.py # 鼠标事件委托
│   ├── on_new_document.py      # 文档创建
│   └── on_category_file.py     # 3D 场景配色
├── scripts/                # 独立转换脚本
│   ├── extract_attributes.py       # 属性提取
│   ├── extract_graph_topology.py   # Graph 拓扑提取
│   ├── extract_uv_grid.py          # UV 网格提取
│   ├── extract_pointcloud.py       # 点云提取（子进程调用）
│   ├── step2point.py               # 点云批量转换
│   └── stp2images_ncti.py          # 多视图批量转换
├── ui/                     # 界面
│   ├── convert_main_window.py     # 主窗口，AUI 布局
│   ├── convert_tab.py             # 转换+可视化选项卡（5 转换 + 5 可视化工具栏按钮）
│   ├── viewer.py                  # 3D 视图面板，嵌入 NCTI 渲染
│   ├── file_tab.py                # 文件选项卡
│   └── general_tab.py             # 选择/显示选项卡
├── main.py                 # 入口
└── requirements.txt        # 依赖
```

## 工具栏按钮说明

### 转换按钮

| 按钮       | 输出格式   | 数据描述                                                                                     |
| ---------- | ---------- | -------------------------------------------------------------------------------------------- |
| 属性提取   | JSON       | 每个面 13 维属性（平面度、圆柱度、面积、质心等） + 每条边 12 维属性（凹凸、长度等） |
| 拓扑提取   | JSON       | 面邻接图结构 + 面/边属性 + 面 UV 网格（7x5x5）+ NxN 邻接矩阵                                |
| 网格采样   | JSON       | 面的 UV 参数空间网格（5x5x7：3坐标+3法向量+1标记）+ 边（5x7：3坐标+3切向量+1二面角） |
| 点云采样   | PLY        | 合并所有实体 mesh 后均匀采样 20000 个点，ASCII 格式                                        |
| 多视图渲染 | PNG（6张） | 从右前上、左后上、左前下、右后下、左前上、右后上 6 个方向渲染                              |

### 可视化按钮

| 按钮         | 展示方式                                                  | 导出格式   |
| ------------ | --------------------------------------------------------- | ---------- |
| 属性可视化   | wx.grid.Grid 表格弹窗，支持面类型动态过滤                 | CSV        |
| 拓扑可视化   | graphviz 渲染面邻接图，支持缩放平移，节点按面类型着色     | SVG + JSON |
| 网格可视化   | 嵌入 NCTI 3D 视图显示 UV 点                               | JSON       |
| 点云可视化   | Open3D 独立窗口显示点云                                   | -          |
| 多视图可视化 | 2x3 网格弹窗展示 6 方向离屏渲染                           | PNG        |

## 转换流程

```text
前3个按钮（属性/拓扑/网格）：
  _import_step() → AiModel 模式 → 提取面/边数据 → JSON

点云采样：
  子进程调用 extract_pointcloud.py → 装配模式导入 → RootGroup → GetMesh → 合并 → 采样 → PLY

多视图渲染：
  独立 doc/view → 6 个相机角度 → Straighten + SaveImage → PNG
```

## 输出数据格式

### 属性（_attributes.json）

```json
{
  "face": {
    "columns": ["faceid", "plane", "cylinder", ...],
    "data": [[1, 0.95, 0.02, ...], ...]
  },
  "edge": {
    "columns": ["fid", "eid", "concave", "convex", ...],
    "data": [[1, 2, 0, 1, ...], ...]
  }
}
```

### Graph（_graph.json）

```json
{
  "graph": {"edges": [[1,2], [1,3]], "num_nodes": 5},
  "graph_face_attr": [[...], ...],
  "graph_face_grid": [[[...], ...], ...],
  "graph_edge_attr": [[[...], ...], ...],
  "graph_edge_grid": [],
  "adjacency matrix": [[0,1,1], [1,0,1], [1,1,0]]
}
```

### 点云（_pointcloud.ply）

```text
ply
format ascii 1.0
element vertex 20000
property double x
property double y
property double z
end_header
11.0403 22.7118 -82.6
8.1849 -7 -34.382
...
```

## 配置

编辑 `config/system_config.json`：

- `dllPath` — NCTI SDK 目录路径
- `addKernelPath` — 附加内核路径（如 OCC）
- `loadDLL` — 启动时加载的 DLL 列表

## 许可证

内部工具，仅供内部使用。
