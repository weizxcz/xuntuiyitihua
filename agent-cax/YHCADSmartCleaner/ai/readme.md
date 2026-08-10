# AI识别模块使用说明

## 1. 模块介绍

AI识别模块是一个基于深度学习的几何特征识别系统，主要用于识别CAD模型中的几何特征，如倒圆角、倒角等。该模块包含以下核心组件：

- **AAGNet_infer**: 基于图神经网络的几何特征识别模型，支持PyTorch格式
- **utils**: 提供数据预处理和后处理工具函数

现在可以根据不同输入face_attr特征维度自适应调整模型入参，保证在不同权重下都能推理。
如需新加推理类型，需要在`main_window.py`中添加对应的按钮、响应函数

## 2. 安装方法

### 2.1 依赖项

该模块依赖以下库：

- PyTorch (>=1.8.0)
- DGL (Deep Graph Library) (>=0.7.0)
- NumPy (>=1.19.0)

### 2.2 安装步骤

1. 克隆或下载项目代码
2. 安装依赖项：
   ```bash
   pip install torch dgl numpy
   ```
3. 确保模型文件（.pth）和统计数据文件（.json）位于正确的路径

## 3. 使用示例

### 3.1 使用PyTorch模型

```python
from ai.AAGNet_infer.base_utils import AAGNetInference

# 初始化模型
aag_net = AAGNetInference(
    weight_path="ai/AAGNet_infer/weights/weight_round.pth",
    stat_path="ai/AAGNet_infer/weights/attr_stat_ncti_62k.json"
)

# 准备输入数据
# face_id: 面ID列表
# face_fid: 面的源边ID列表
# face_eid: 面的目标边ID列表
# face_points: 面点坐标列表
# face_normals: 面法线列表
# face_mask: 面掩码列表
# graph_edge_attr: 边属性列表
# graph_face_attr: 面属性列表

# 执行推理
seg_out, inst_out, bottom_out = aag_net.ai_model_inference(
    face_id, face_fid, face_eid, face_points, face_normals,
    face_mask, graph_edge_attr, graph_face_attr
)

# 后处理结果
result_dict = aag_net.postprocess_round(seg_out, inst_out, bottom_out)
face_list = result_dict.get(0, {}).get("instance", [])
```


### 3.2 完整示例

以下是一个完整的使用示例，基于`main_window.py`和`on_find_fillet_by_ai.py`：

```python
from ai.AAGNet_infer.base_utils import AAGNetInference
from ai.ai_recognizer import infer

# 初始化模型
aag_net = AAGNetInference(
    weight_path="ai/AAGNet_infer/weights/weight_round.pth",
    stat_path="ai/AAGNet_infer/weights/attr_stat_ncti_62k.json"
)

# 使用AI模型进行推理
cell_ids, obj_names, face_type_dict, filtered_face_points, filtered_face_normals = infer(
    doc, NCTI, aag_net
)

# 处理识别结果
if cell_ids:
    print(f"共识别到{len(cell_ids)}个倒圆角面")
    print(f"识别结果: {cell_ids}")
else:
    print("未识别到倒圆角面")
```

## 4. API文档

### 4.1 AAGNetInference类

#### 初始化

```python
def __init__(self, weight_path: str = "weight.pth", stat_path: str = "attr_stat.json")
```

- **weight_path**: 模型权重文件路径
- **stat_path**: 统计数据文件路径

#### 方法

##### ai_model_inference

```python
def ai_model_inference(self, face_id, face_fid, face_eid, face_points, face_normals, face_mask, graph_edge_attr, graph_face_attr)
```

- **参数**:
  - face_id: 面ID列表
  - face_fid: 面的源边ID列表
  - face_eid: 面的目标边ID列表
  - face_points: 面点坐标列表
  - face_normals: 面法线列表
  - face_mask: 面掩码列表
  - graph_edge_attr: 边属性列表
  - graph_face_attr: 面属性列表

- **返回值**:
  - seg_out: 分割输出
  - inst_out: 实例输出
  - bottom_out: 底部输出

##### postprocess

```python
def postprocess(self, seg_out, inst_out, bottom_out)
```

- **参数**:
  - seg_out: 分割输出
  - inst_out: 实例输出
  - bottom_out: 底部输出

- **返回值**:
  - 包含识别结果的字典

##### postprocess_round

```python
def postprocess_round(self, seg_out, inst_out, bottom_out)
```

- **参数**:
  - seg_out: 分割输出
  - inst_out: 实例输出
  - bottom_out: 底部输出

- **返回值**:
  - 包含倒圆角识别结果的字典

### 4.2 utils工具函数

#### index_mapper.py

提供索引映射和压缩功能，用于处理面ID的映射关系。

#### normalize_points.py

提供点云归一化和缩放功能，用于预处理输入数据。

## 5. 模型文件说明

### 5.1 权重文件

- **weight_round.pth**: PyTorch格式的倒圆角识别模型权重

### 5.2 统计数据文件

- **attr_stat.json**: 通用统计数据文件
- **attr_stat_ncti_62k.json**: 针对NCTI数据集的统计数据文件


## 6. 注意事项

1. 确保输入数据的格式正确，特别是面属性和边属性的维度
2. 对于不同类型的几何特征，应使用对应的模型权重文件
3. 对于大型CAD模型，可能需要调整批处理大小以避免内存不足
4. 模型的识别精度取决于训练数据的质量和多样性

## 7. 故障排除

### 7.1 常见错误

- **模型加载失败**: 检查权重文件路径是否正确，确保文件存在
- **推理错误**: 检查输入数据的格式和维度是否正确

### 7.2 性能优化

- 对于大型模型，可以考虑使用GPU加速
- 可以通过调整模型的超参数来平衡精度和速度