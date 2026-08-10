# YHCADLabeller — 炎核几何特征识别标注工具

YHCADLabeller 是一款面向 CAD 三维模型的几何特征标注工具。支持从本地或远程服务器导入 STEP/IGS 模型，在 3D 视图中点选几何面标注特征类型（圆角、倒角、盲孔、通孔等），导出 seg/inst/bottom 格式的 JSON 训练数据集。

## 功能特点

- **模型导入**：支持 STEP（.step/.stp）、IGES（.igs）格式，本地文件或远程服务器下载
- **标注工作台**：独立工作台窗口，按行业/产品类型/几何特征筛选零件，6 点完成度指示
- **3D 交互**：嵌入 NCTI 渲染引擎，支持旋转、缩放、面选择
- **特征标注**：6 种标注操作（标注、批量标注、标注底面、批量标注底面、高亮、移除）+ [+] 追加面
- **实例追踪**：自动区分同一特征的不同实例，生成 N×N 实例矩阵
- **撤销**：Ctrl+Z 最多撤销 50 步
- **自动保存**：每 2 分钟自动保存标注进度
- **JSON 导入/导出**：输出 seg（语义分割）、inst（实例分割）、bottom（底面标记）格式数据，支持导入已标注 JSON 恢复标注

## 环境要求

- Windows 10 及以上
- Python 3.8+
- wxPython 4.2.1
- requests >= 2.28.0
- NCTI SDK（配置 `config/system_config.json` 中的 DLL 路径）

## 快速开始

```bash
pip install -r requirements.txt
python main.py
```

### 本地文件标注流程

```
创建零件 → 导入 STEP 模型 → 切换到标注选项卡 → 添加特征名称 → 选择面并标注 → 导出 JSON
```

### 服务器工作台流程

1. 在 `config/system_config.json` 中配置 `apiServerUrl` 为 Flask API 地址
2. 点击文件选项卡中的"导入"按钮 → 打开标注工作台
3. 按行业、产品类型、几何特征筛选零件
4. 双击零件行或选中后点击导入 → 自动下载并加载模型
5. 切换到标注选项卡进行标注 → 导出 JSON

## 项目结构

```
YHCADLabeller/
├── config/                 # 配置
│   ├── config_load.py          # SDK 初始化，加载 DLL，创建全局 NCTI 实例
│   └── system_config.json      # SDK 路径 + API 服务器地址
├── core/                   # 核心服务
│   └── api_client.py           # Flask API HTTP 客户端（零件列表、筛选、下载）
├── workspace/              # 标注工作台
│   └── workspace_window.py     # 独立工作台窗口（筛选、翻页、完成度指示、下载导入）
├── dialog/                 # 文件对话框
│   ├── import_file.py          # 导入 STP/STEP/IGS
│   ├── import_from_server.py   # 服务器零件选择对话框（旧版，未使用）
│   ├── export_file.py          # 导出模型
│   ├── new_document.py         # 新建零件对话框
│   └── ...
├── function/               # 核心逻辑
│   ├── mouse_event_delegate.py # 鼠标事件委托（单击/双击/右键）
│   ├── on_new_document.py      # 文档创建
│   └── on_category_file.py     # 3D 场景配色
├── ui/                     # 界面
│   ├── main_window.py          # 主窗口（CAEPlatform），AUI 布局，状态管理
│   ├── viewer.py               # 3D 视图面板，嵌入 NCTI 渲染
│   ├── label_feature_panel.py  # 标注面板（按钮、列表、撤销）
│   ├── label_name_panel.py     # 特征名称管理面板
│   ├── label_tab.py            # 标注选项卡（导入/导出 JSON）
│   ├── file_tab.py             # 文件选项卡（导入按钮打开工作台）
│   └── general_tab.py          # 选择/显示选项卡
├── utils/                  # 工具
│   └── file_finder.py          # JSON 标注路径 → STEP 文件路径映射
├── test/                   # 测试
├── main.py                 # 入口
└── requirements.txt
```

## 标注按钮说明

| 按钮 | 作用 |
|------|------|
| 标注 | 选中多个面 → 归为同一实例（一个特征组） |
| 标注底面 | 选中 1 个面 → 匹配到已有标注行，标记为底面 |
| 高亮 | 选中列表行 → 在 3D 视图中高亮对应面 |
| 批量标注 | 选中多个面 → 每个面各自一个实例 |
| 批量标注底面 | 选中多个面 → 批量匹配底面 |
| 移除 | 选中列表行 → 删除，清除相关数据 |
| [+列] | 点击弹出菜单 → 向已有行追加面ID或底面 |

## 导出数据格式

```json
{
  "source_file": "model.step",
  "feature_mapping": {"圆角": 1, "盲孔": 2},
  "seg": {"0": 1, "1": 1, "2": 2},
  "inst": [[1,1,0],[1,1,0],[0,0,1]],
  "bottom": {"0": 0, "1": 0, "2": 1}
}
```

| 字段 | 说明 |
|------|------|
| `seg` | 面 ID → 类别 ID（语义分割） |
| `inst` | N×N 矩阵，同一实例的面互为 1（实例分割） |
| `bottom` | 底面标记，1 = 底面 |

## 配置

编辑 `config/system_config.json`：

- `dllPath` — NCTI SDK 目录路径
- `addKernelPath` — 附加内核路径（如 OCC）
- `loadDLL` — 启动时加载的 DLL 列表
- `apiServerUrl` — 远程 API 服务器地址（供工作台使用）

## 许可证

内部工具，仅供内部使用。
