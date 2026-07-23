# YHCADLabeller

YHCADLabeller 是用于 CAD 几何特征标注、ONNX 识别、预标注和 AAGNet 训练的 Windows 桌面工具。

项目内置的识别模型全部使用 ONNX Runtime；训练和 PTH 转 ONNX 需要在安装了完整训练依赖的 Python 环境中执行。本文以 `Geometry_new` 为示例环境名，实际可使用任意名称的 Conda/venv 环境，并在配置文件中填写其 Python 解释器路径。

## 环境

- Windows 10/11、NCTI SDK。
- 推理环境：`onnx`，仅需要 GUI、NumPy、ONNX 和 ONNX Runtime 等依赖。
- 训练环境：示例名为 `Geometry_new`，需要 PyTorch、DGL、torch_ema、torchmetrics 等完整训练依赖；环境名称并非固定要求。

安装总依赖：

```powershell
pip install -r requirements.txt
```

先复制 `config/system_config.json.example` 为 `config/system_config.json`，再配置本机 SDK 和训练解释器。该本机配置文件不会提交到仓库：

```json
{
  "dllPath": "C:/path/to/YHPreCAE",
  "trainEnvPython": "C:/Users/你的用户名/anaconda3/envs/Geometry_new/python.exe"
}
```

启动：

```powershell
python main.py
```

## 快速上手：界面功能

首次使用可按以下顺序操作：创建零件或导入 STEP → 调整选择模式 → 标注或 AI 识别 → 导出标注 JSON。

### 文件

- **创建零件**：新建一个空的零件文档，并清空当前标注状态。
- **导入**：导入 `.stp`、`.step` 或 `.igs` 模型；导入新模型会重置旧模型的标注状态。
- **保存 / 关闭文档**：保存或关闭当前 NCTI 文档。
- **导出**：将当前模型导出为 STEP。

### 选择/显示

- **显示模式**：分别控制实体、面、边、点的显示，便于观察几何结构。
- **选择模式**：分别控制是否可选实体、面、边、点。进行特征标注或识别前，建议启用“面”选择。
- **可视化**：提供多视图、属性、拓扑、网格和点云可视化，用于检查模型和图数据。

### 标注

1. 在标注页添加或选择特征名称。
2. 在三维视图选择属于同一几何特征的面。
3. 点击“标注”创建一个实例；需要时使用“标注底面”“批量标注”“高亮”或“移除”。
4. 导出 JSON，或使用自动保存文件继续标注。

标注导出的 JSON 可直接作为训练数据；其格式和目录要求见“训练页面”。

### 识别

- **AI 圆角识别、AI 倒角识别、AI 盲孔识别、AI 沉头孔识别**：对当前模型或选中的局部区域执行内置 ONNX 模型识别。
- **移除特征**：移除当前选中的特征面。
- **导出特征**：将当前选中的同一对象特征导出为 STEP。

识别结果会高亮显示，并在特征列表中展示。若要为数据集批量生成初始标注，请使用标注页的“选择预标注模型”和“预标注”。

## 内置识别与预标注

识别页的圆角、倒角、盲孔、沉头孔按钮固定使用 `ai/AAGNet_infer/weights/` 下对应的 ONNX 与统计 JSON。

预标注的操作顺序：

1. 创建零件并导入 STEP/STP。
2. 在标注页选择“预标注模型”。
3. 先选择 `.onnx` 权重，再选择与该模型配套的统计 `.json`。
4. 点击“预标注”。

ONNX 与 JSON 必须成对使用；JSON 中保存了输入特征标准化的均值和标准差。

## 训练页面

训练页依次提供“选择数据集”“选择训练特征”“生成 graph”“训练神经网络”“模型转换”。

### 数据集目录规则

选择的是**一个目录**，程序只扫描该目录的第一层，不递归扫描子目录。每个参与训练的零件必须是同名 STEP 与 JSON 配对：

```text
dataset/
├── part_001.stp
├── part_001.json
├── part_002.step
├── part_002.json
└── ...
```

没有同名 `.stp`/`.step` 的 JSON，以及没有同名 JSON 的 STEP，不会参与训练。

### JSON 格式

训练支持以下两种对象格式：

1. JSON 中包含 `feature_mapping`，程序直接读取特征名称与类别编号。
2. JSON 中不包含 `feature_mapping`，在“选择训练特征”时由用户通过弹窗填写本次训练的特征名称和类别编号。

两种格式中的 `seg`、`bottom` 键均为面 ID 字符串；`inst` 是按面 ID 顺序排列的 N×N 实例矩阵。

#### 格式一：包含 `feature_mapping`

```json
{
  "source_file": "part_001.stp",
  "feature_mapping": {
    "盲孔": 12
  },
  "seg": {
    "0": 0,
    "1": 12,
    "2": 12,
    "3": 0
  },
  "inst": [
    [0, 0, 0, 0],
    [0, 1, 1, 0],
    [0, 1, 1, 0],
    [0, 0, 0, 0]
  ],
  "bottom": {
    "0": 0,
    "1": 0,
    "2": 1,
    "3": 0
  }
}
```

#### 格式二：不包含 `feature_mapping`

```json
{
  "source_file": "part_001.stp",
  "seg": {
    "0": 0,
    "1": 12,
    "2": 12,
    "3": 0
  },
  "inst": [
    [0, 0, 0, 0],
    [0, 1, 1, 0],
    [0, 1, 1, 0],
    [0, 0, 0, 0]
  ],
  "bottom": {
    "0": 0,
    "1": 0,
    "2": 1,
    "3": 0
  }
}
```

对于上述无映射格式，如果要训练盲孔，点击“选择训练特征”后在弹窗中填写：

- 训练几何特征：`盲孔`
- 类别：`12`

这里的类别必须是整数，并且必须与 `seg` 中代表目标特征的类别编号一致。弹窗填写的映射只用于当前选择的数据集和本次训练流程，不会写回或修改原始 JSON 文件。

字段含义：

| 字段 | 说明 |
| --- | --- |
| `source_file` | 对应 STEP 文件名。 |
| `feature_mapping` | 可选。特征名到训练类别编号的映射；缺失时通过“选择训练特征”弹窗补充。 |
| `seg` | 面 ID 到类别编号；`0` 表示非当前训练特征。 |
| `inst` | 同一特征实例的两个面为 `1`，不同实例为 `0`。 |
| `bottom` | 底面为 `1`，非底面为 `0`。 |

旧格式 `[模型名, { ...上述字段... }]` 也能读取，但建议统一转换为上述对象格式。

### 选择训练特征与映射要求

点击“选择训练特征”后，程序根据数据集内容执行以下逻辑：

- **JSON 包含 `feature_mapping`**：程序从所有有效 JSON 中收集可训练特征。只有一个特征时自动选中；存在多个特征时弹出选择列表。
- **JSON 不包含 `feature_mapping`**：程序弹出“填写训练特征映射”窗口，要求输入“训练几何特征”和“类别”。训练几何特征不能为空，类别必须填写为整数。

对于包含映射的数据集，选择一个特征后，该特征在所有包含它的 JSON 中必须拥有相同编号。

例如训练盲孔时，每个相关 JSON 都应使用：

```json
"feature_mapping": {"盲孔": 12}
```

如果有的文件写为 `"盲孔": 1`、有的写为 `"盲孔": 12`，生成 graph 会拒绝执行，避免把不同标签混为同一类别。对于不含映射的数据集，弹窗中填写的类别也必须与各 JSON 的 `seg` 目标类别保持一致。

### 执行流程与输出

1. 选择数据集目录。
2. 点击“选择训练特征”：有映射时自动读取或选择特征；无映射时在弹窗中填写训练几何特征和整数类别。
3. 点击“生成 graph”。
4. 点击“训练神经网络”。训练进度与日志显示在训练页。
5. 训练完成后，输出位于数据集目录：

```text
dataset/_train_work/
├── 0000-00-00_processed_data/   # graph、标签、划分和统计量
├── logs/                        # 训练日志
├── metrics.jsonl                # 指标记录
└── model_weights/<时间戳>/
    ├── <训练几何特征>_best_model.pth
    └── <训练几何特征>_best_model.json  # 与权重配套的标准化统计文件
```

例如训练几何特征为“盲孔”时，输出文件为 `盲孔_best_model.pth` 和 `盲孔_best_model.json`。

### 模型转换

点击“模型转换”，选择训练生成的 `<训练几何特征>_best_model.pth`。程序会在同一文件夹写出同前缀的 ONNX 文件，例如：

```text
盲孔_best_model.onnx
盲孔_best_model.onnx.verify.json
```

转换时会在 `trainEnvPython` 所指向的完整训练环境中导出，并立即使用 ONNX Runtime 做一次数值有效性验证。`Geometry_new` 仅为默认示例。使用该模型预标注时，选择转换后的 ONNX，再选择同目录、同前缀的统计 JSON，例如 `盲孔_best_model.json`。

## 项目结构

```text
YHCADLabeller/
├── ai/
│   ├── AAGNet_infer/weights/    # 4 组内置 ONNX 权重及统计 JSON
│   ├── AAGNet_train/            # 训练模型、数据处理和训练管线
│   ├── onnx_export_worker.py    # PTH 转 ONNX 子进程
│   └── train_worker.py          # graph 生成与训练子进程
├── function/                    # 页面操作逻辑
├── ui/                          # 桌面界面
├── scripts/extract_pointcloud.py # 拓扑可视化使用的点云提取脚本
├── config/system_config.json    # 本机 SDK 与训练环境配置
└── requirements.txt             # 项目总依赖
```

## 清理原则

项目仅保留当前 ONNX 识别链路的 4 组内置模型及其统计 JSON。PTH 仅作为训练产物和模型转换输入，不再作为运行时识别后端。
