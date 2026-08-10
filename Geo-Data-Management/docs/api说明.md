# API 接口说明文档

## 1. 概述

本文档描述了零件数据管理系统的 RESTful API 接口，用于前端/客户端与后端进行数据交互。

**基础路径**: `/api`

**通用响应格式**:
```json
{
  "code": 0,
  "data": { ... },
  "message": "success"
}
```

| 错误码 | 含义 |
| :--- | :--- |
| 0 | 成功 |
| 400 | 请求参数错误 |
| 404 | 资源未找到 |
| 409 | 资源冲突（如重复数据） |
| 500 | 服务器内部错误 |

---

## 2. 接口列表

### 2.1 获取零件列表

**路径**: `POST /api/parts/list_parts`

**功能**: 获取零件列表，支持分页和多条件筛选

**请求体**:

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| skip | int | 否 | 0 | 跳过的记录数 |
| limit | int | 否 | 100 | 返回的最大记录数 |
| industry | string | 否 | - | 行业分类筛选 |
| product_type | string | 否 | - | 产品类型筛选 |
| format | string | 否 | - | 文件格式（stp/step/igs） |
| is_open_source | bool | 否 | - | 是否开源（true/false） |
| source_type | string | 否 | - | 数据来源（public/private） |

**请求示例**:
```json
{
  "skip": 0,
  "limit": 10,
  "industry": "汽车",
  "format": "stp"
}
```

**成功响应** (HTTP 200):
```json
{
  "code": 0,
  "data": [
    {
      "id": 1,
      "hash_id": "abc123def456...",
      "name": "engine_part.stp",
      "created_time": "2024-01-01T12:00:00",
      "modified_time": "2024-01-01T12:00:00",
      "created_by": "user001",
      "modified_by": null,
      "format": "stp",
      "is_open_source": false,
      "source_type": "private",
      "industry": "汽车",
      "product_type": "发动机",
      "has_round": true,
      "has_chamfer": false,
      "has_countersink_hole": false,
      "has_counterbore_hole": false,
      "has_through_hole": true,
      "has_blind_hole": false,
      "label_round_status": "pending",
      "label_chamfer_status": "pending",
      "label_countersink_hole_status": "pending",
      "label_counterbore_hole_status": "pending",
      "label_through_hole_status": "pending",
      "label_blind_hole_status": "pending"
    }
  ]
}
```

---

### 2.2 获取单个零件详情

**路径**: `POST /api/parts/get_part`

**功能**: 根据ID获取单个零件的详细信息

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| part_id | int | 是 | 零件ID |

**请求示例**:
```json
{
  "part_id": 1
}
```

**成功响应** (HTTP 200):
```json
{
  "code": 0,
  "data": {
    "id": 1,
    "hash_id": "abc123def456...",
    "name": "engine_part.stp",
    "created_time": "2024-01-01T12:00:00",
    "modified_time": "2024-01-01T12:00:00",
    "created_by": "user001",
    "modified_by": null,
    "format": "stp",
    "is_open_source": false,
    "source_type": "private",
    "industry": "汽车",
    "product_type": "发动机",
    "has_round": true,
    "has_chamfer": false,
    "has_countersink_hole": false,
    "has_counterbore_hole": false,
    "has_through_hole": true,
    "has_blind_hole": false,
    "label_round_status": "pending",
    "label_chamfer_status": "pending",
    "label_countersink_hole_status": "pending",
    "label_counterbore_hole_status": "pending",
    "label_through_hole_status": "pending",
    "label_blind_hole_status": "pending"
  }
}
```

**失败响应** (HTTP 400):
```json
{
  "code": 400,
  "message": "Missing part_id"
}
```

**失败响应** (HTTP 404):
```json
{
  "code": 404,
  "message": "Part not found"
}
```

---

### 2.3 创建零件记录

**路径**: `POST /api/parts/add_part`

**功能**: 创建新的零件记录

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| hash_id | string | 是 | 文件哈希值（唯一标识） |
| name | string | 是 | 文件名 |
| format | string | 是 | 文件格式（stp/step/igs） |
| industry | string | 否 | 行业分类 |
| product_type | string | 否 | 产品类型 |
| is_open_source | bool | 否 | 是否开源（默认false） |
| source_type | string | 否 | 数据来源（public/private，默认private） |
| created_by | string | 否 | 创建人 |
| has_round | bool | 否 | 是否包含圆角（默认false） |
| has_chamfer | bool | 否 | 是否包含倒角（默认false） |
| has_countersink_hole | bool | 否 | 是否包含沉头孔（默认false） |
| has_counterbore_hole | bool | 否 | 是否包含沉孔（默认false） |
| has_through_hole | bool | 否 | 是否包含通孔（默认false） |
| has_blind_hole | bool | 否 | 是否包含盲孔（默认false） |

**请求示例**:
```json
{
  "hash_id": "abc123def456...",
  "name": "engine_part.stp",
  "format": "stp",
  "industry": "汽车",
  "product_type": "发动机",
  "is_open_source": false,
  "source_type": "private",
  "created_by": "user001",
  "has_round": true,
  "has_through_hole": true
}
```

**成功响应** (HTTP 201):
```json
{
  "code": 0,
  "data": {
    "id": 2,
    "hash_id": "abc123def456...",
    "name": "engine_part.stp",
    "created_time": "2024-01-01T12:00:00",
    "modified_time": "2024-01-01T12:00:00",
    "created_by": "user001",
    "modified_by": null,
    "format": "stp",
    "is_open_source": false,
    "source_type": "private",
    "industry": "汽车",
    "product_type": "发动机",
    "has_round": true,
    "has_chamfer": false,
    "has_countersink_hole": false,
    "has_counterbore_hole": false,
    "has_through_hole": true,
    "has_blind_hole": false,
    "label_round_status": "pending",
    "label_chamfer_status": "pending",
    "label_countersink_hole_status": "pending",
    "label_counterbore_hole_status": "pending",
    "label_through_hole_status": "pending",
    "label_blind_hole_status": "pending"
  }
}
```

**失败响应**:

- 缺少必填字段 (HTTP 400):
```json
{
  "code": 400,
  "message": "Missing required field: hash_id"
}
```

- hash_id重复 (HTTP 409):
```json
{
  "code": 409,
  "message": "Part with this hash_id already exists"
}
```

---

### 2.4 更新零件信息

**路径**: `POST /api/parts/modify_part`

**功能**: 更新指定零件的信息

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| part_id | int | 是 | 零件ID |
| name | string | 否 | 文件名 |
| industry | string | 否 | 行业分类 |
| product_type | string | 否 | 产品类型 |
| is_open_source | bool | 否 | 是否开源 |
| source_type | string | 否 | 数据来源 |
| modified_by | string | 否 | 修改人 |
| has_round | bool | 否 | 是否包含圆角 |
| has_chamfer | bool | 否 | 是否包含倒角 |
| has_countersink_hole | bool | 否 | 是否包含沉头孔 |
| has_counterbore_hole | bool | 否 | 是否包含沉孔 |
| has_through_hole | bool | 否 | 是否包含通孔 |
| has_blind_hole | bool | 否 | 是否包含盲孔 |

**请求示例**:
```json
{
  "part_id": 1,
  "industry": "家电",
  "product_type": "冰箱",
  "modified_by": "user002"
}
```

**成功响应** (HTTP 200):
```json
{
  "code": 0,
  "data": {
    "id": 1,
    "name": "engine_part.stp",
    "industry": "家电",
    "product_type": "冰箱",
    "modified_by": "user002",
    ...
  }
}
```

**失败响应**:

- 缺少参数 (HTTP 400):
```json
{
  "code": 400,
  "message": "Missing part_id"
}
```

- 零件不存在 (HTTP 404):
```json
{
  "code": 404,
  "message": "Part not found"
}
```

---

### 2.5 删除零件记录

**路径**: `POST /api/parts/remove_part`

**功能**: 删除指定的零件记录

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| part_id | int | 是 | 零件ID |

**请求示例**:
```json
{
  "part_id": 1
}
```

**成功响应** (HTTP 200):
```json
{
  "code": 0,
  "message": "Part deleted successfully"
}
```

**失败响应** (HTTP 404):
```json
{
  "code": 404,
  "message": "Part not found"
}
```

---

### 2.6 更新特征标注状态

**路径**: `POST /api/parts/update_feature_label`

**功能**: 更新指定零件的特征标注状态

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| part_id | int | 是 | 零件ID |
| feature_type | string | 是 | 特征类型 |
| status | string | 是 | 标注状态 |
| modified_by | string | 否 | 修改人 |

**feature_type 可选值**:
| 值 | 说明 |
| :--- | :--- |
| round | 圆角 |
| chamfer | 倒角 |
| countersink_hole | 沉头孔 |
| counterbore_hole | 沉孔 |
| through_hole | 通孔 |
| blind_hole | 盲孔 |

**status 可选值**:
| 值 | 说明 |
| :--- | :--- |
| pending | 待标注 |
| in_progress | 标注中 |
| completed | 已完成 |
| skipped | 跳过 |
| error | 标注异常 |

**请求示例**:
```json
{
  "part_id": 1,
  "feature_type": "round",
  "status": "completed",
  "modified_by": "user002"
}
```

**成功响应** (HTTP 200):
```json
{
  "code": 0,
  "data": {
    "id": 1,
    "label_round_status": "completed",
    ...
  }
}
```

**失败响应**:

- 缺少必要参数 (HTTP 400):
```json
{
  "code": 400,
  "message": "Missing part_id or feature_type"
}
```

- 缺少状态参数 (HTTP 400):
```json
{
  "code": 400,
  "message": "Missing status"
}
```

- 零件或特征不存在 (HTTP 404):
```json
{
  "code": 404,
  "message": "Part or feature not found"
}
```

---

### 2.7 按特征筛选零件

**路径**: `POST /api/parts/filter_by_feature`

**功能**: 根据特征检测结果筛选零件

**请求体**:

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| has_round | bool | 否 | - | 是否包含圆角 |
| has_chamfer | bool | 否 | - | 是否包含倒角 |
| has_countersink_hole | bool | 否 | - | 是否包含沉头孔 |
| has_counterbore_hole | bool | 否 | - | 是否包含沉孔 |
| has_through_hole | bool | 否 | - | 是否包含通孔 |
| has_blind_hole | bool | 否 | - | 是否包含盲孔 |
| limit | int | 否 | 100 | 返回的最大记录数 |

**请求示例**:
```json
{
  "has_round": true,
  "has_through_hole": true,
  "limit": 50
}
```

**成功响应** (HTTP 200):
```json
{
  "code": 0,
  "data": [
    {
      "id": 1,
      "name": "engine_part.stp",
      "has_round": true,
      "has_through_hole": true,
      ...
    }
  ]
}
```

---

### 2.8 按标注状态筛选零件

**路径**: `POST /api/parts/filter_by_label_status`

**功能**: 根据标注状态筛选零件

**请求体**:

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| label_round_status | string | 否 | - | 圆角标注状态 |
| label_chamfer_status | string | 否 | - | 倒角标注状态 |
| label_countersink_hole_status | string | 否 | - | 沉头孔标注状态 |
| label_counterbore_hole_status | string | 否 | - | 沉孔标注状态 |
| label_through_hole_status | string | 否 | - | 通孔标注状态 |
| label_blind_hole_status | string | 否 | - | 盲孔标注状态 |
| limit | int | 否 | 100 | 返回的最大记录数 |

**请求示例**:
```json
{
  "label_round_status": "pending",
  "label_chamfer_status": "completed",
  "limit": 50
}
```

**成功响应** (HTTP 200):
```json
{
  "code": 0,
  "data": [
    {
      "id": 1,
      "name": "engine_part.stp",
      "label_round_status": "pending",
      ...
    }
  ]
}
```

---

### 2.9 统计零件数量

**路径**: `POST /api/stats`

**功能**: 统计零件数量（支持按行业筛选）

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| industry | string | 否 | 行业分类筛选 |

**请求示例**:
```json
{
  "industry": "汽车"
}
```

**成功响应** (HTTP 200):
```json
{
  "code": 0,
  "data": {
    "total": 87845,
    "industry": "汽车"
  }
}
```

---

### 2.10 保存零件标注JSON文件

**路径**: `POST /api/label/save_json`

**功能**: 保存零件标注JSON文件到指定目录

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| name | string | 是 | 零件名称（文件名） |
| feature_type | string | 是 | 特征类型 |
| industry | string | 是 | 行业分类 |
| user | string | 是 | 用户名称 |
| json_data | object | 是 | 标注数据（字典格式） |

**请求示例**:
```json
{
  "name": "零件123",
  "feature_type": "round",
  "industry": "汽车",
  "user": "张三",
  "json_data": {
    "annotations": [...],
    "part_id": 1
  }
}
```

**成功响应** (HTTP 200):
```json
{
  "code": 0,
  "message": "JSON saved successfully",
  "path": "/labels/张三/汽车/round/零件123.json"
}
```

**失败响应**:

- 缺少必填字段 (HTTP 400):
```json
{
  "code": 400,
  "message": "Missing required field: name"
}
```

- 保存失败 (HTTP 500):
```json
{
  "code": 500,
  "message": "Failed to save JSON: ..."
}
```

---

### 2.11 发送零件模型文件

**路径**: `POST /api/label/send_solid_file`

**功能**: 根据零件ID返回对应的STP/STEP模型文件

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| part_id | int | 是 | 零件ID |

**请求示例**:
```json
{
  "part_id": 1
}
```

**成功响应** (HTTP 200):
- 返回文件流（附件下载）

**失败响应**:

- 缺少参数 (HTTP 400):
```json
{
  "code": 400,
  "message": "Missing part_id"
}
```

- 零件不存在 (HTTP 404):
```json
{
  "code": 404,
  "message": "Part not found"
}
```

- 文件不存在 (HTTP 404):
```json
{
  "code": 404,
  "message": "File not found"
}
```

---

### 2.12 导入零件标注JSON文件

**路径**: `POST /api/label/import_json`

**功能**: 导入零件标注JSON文件，并返回对应的STEP模型文件

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| name | string | 是 | 零件名称 |
| feature_type | string | 是 | 特征类型 |
| industry | string | 是 | 行业分类 |
| user | string | 是 | 用户名称 |

**请求示例**:
```json
{
  "name": "零件123",
  "feature_type": "round",
  "industry": "汽车",
  "user": "张三"
}
```

**成功响应** (HTTP 200):
- 返回 multipart/form-data 格式，包含：
  - `metadata`: JSON数据（标注信息）
  - `file`: STEP模型文件

**失败响应**:

- 缺少必填字段 (HTTP 400):
```json
{
  "code": 400,
  "message": "Missing required field: name"
}
```

- JSON文件不存在 (HTTP 404):
```json
{
  "code": 404,
  "message": "JSON file not found"
}
```

- 零件不存在 (HTTP 404):
```json
{
  "code": 404,
  "message": "Part not found"
}
```

- STEP文件不存在 (HTTP 404):
```json
{
  "code": 404,
  "message": "STEP file not found"
}
```

- JSON中缺少part_id (HTTP 400):
```json
{
  "code": 400,
  "message": "part_id not found in JSON data"
}
```

---

### 2.13 上传 CAD 模型文件

**路径**: `POST /api/label/upload_file`

**功能**: 上传 STP/STEP/IGS 模型文件到服务器，自动计算 SHA256 哈希值用于去重

**请求格式**: `multipart/form-data`

**请求参数**:

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| file | file | 是 | STP/STEP/IGS 文件（二进制） |

**调用示例**:
```python
import requests

resp = requests.post(
    "http://172.16.45.61:5060/api/label/upload_file",
    files={"file": open("零件.stp", "rb")}
)
print(resp.json())
```

**成功响应** (HTTP 200):
```json
{
  "code": 0,
  "data": {
    "hash_id": "8be22d5d5957f390...",
    "name": "零件.stp",
    "format": "stp",
    "file_path": "/data/Geo-Data-Management/steps/零件.stp"
  }
}
```

**失败响应**:

- 缺少文件 (HTTP 400):
```json
{
  "code": 400,
  "message": "Missing file"
}
```

- 格式不支持 (HTTP 400):
```json
{
  "code": 400,
  "message": "Unsupported format: .txt"
}
```

- 文件已存在 (HTTP 409):
```json
{
  "code": 409,
  "message": "File already exists",
  "data": {
    "hash_id": "8be22d5d5957f390...",
    "name": "零件.stp"
  }
}
```

**说明**:

- 接口仅负责文件上传和哈希计算，不操作数据库
- 上传成功后，需调用 `POST /api/parts/add_part` 将返回的 `hash_id`、`name`、`format` 写入数据库
- 同名文件会比对哈希值，内容相同返回 409，内容不同则自动加哈希前缀保存

---

### 2.14 筛选 JSON 标注文件

**路径**: `POST /api/label/filter_json`

**功能**: 根据用户、行业、特征类型筛选 JSON 标注文件

**请求体**:

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| user | string | 否 | all | 用户名称筛选 |
| industry | string | 否 | all | 行业类型筛选 |
| feature_type | string | 否 | all | 特征类型筛选 |

**请求示例**:
```json
{
  "user": "张三",
  "industry": "汽车",
  "feature_type": "round"
}
```

**成功响应** (HTTP 200):
```json
{
  "code": 0,
  "data": [
    {
      "path": "张三/汽车/round",
      "filename": "零件123.json"
    }
  ],
  "message": "filter successful"
}
```

**失败响应**:

- 缺少请求数据 (HTTP 400):
```json
{
  "code": 400,
  "message": "No data provided"
}
```

- 服务器错误 (HTTP 500):
```json
{
  "code": 500,
  "message": "..."
}
```

**说明**:

- 目录结构为 `user/industry/feature_type/`
- 各筛选条件支持 `all` 作为通配符，表示不筛选
- 返回结果包含文件相对路径和文件名

---

## 3. 数据模型

### 3.1 PartInfo（零件信息）

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| id | int | 主键，自增 |
| hash_id | string | 文件哈希值（唯一） |
| name | string | 文件名 |
| created_time | string | 创建时间（ISO格式） |
| modified_time | string | 修改时间（ISO格式） |
| created_by | string | 创建人 |
| modified_by | string | 修改人 |
| format | string | 文件格式 |
| is_open_source | bool | 是否开源 |
| source_type | string | 数据来源 |
| industry | string | 行业分类 |
| product_type | string | 产品类型 |
| has_round | bool | 是否包含圆角 |
| has_chamfer | bool | 是否包含倒角 |
| has_countersink_hole | bool | 是否包含沉头孔 |
| has_counterbore_hole | bool | 是否包含沉孔 |
| has_through_hole | bool | 是否包含通孔 |
| has_blind_hole | bool | 是否包含盲孔 |
| label_round_status | string | 圆角标注状态 |
| label_chamfer_status | string | 倒角标注状态 |
| label_countersink_hole_status | string | 沉头孔标注状态 |
| label_counterbore_hole_status | string | 沉孔标注状态 |
| label_through_hole_status | string | 通孔标注状态 |
| label_blind_hole_status | string | 盲孔标注状态 |

---

## 4. 标注状态说明

| 状态值 | 含义 |
| :--- | :--- |
| pending | 待标注 |
| in_progress | 标注中 |
| completed | 已完成 |
| skipped | 跳过 |
| error | 标注异常 |

---

## 5. 数据来源类型

| 值 | 含义 |
| :--- | :--- |
| public | 公开数据集 |
| private | 自有数据 |

---

## 6. 文件格式

| 值 | 说明 |
| :--- | :--- |
| stp | STEP 格式 |
| step | STEP 格式 |
| igs | IGES 格式 |

---

## 7. 接口路径汇总

```
/api/parts/list_parts          POST    获取零件列表
/api/parts/get_part            POST    获取单个零件
/api/parts/add_part            POST    创建零件记录
/api/parts/modify_part         POST    更新零件信息
/api/parts/remove_part         POST    删除零件记录
/api/parts/update_feature_label POST   更新特征标注状态
/api/parts/filter_by_feature   POST    按特征筛选零件
/api/parts/filter_by_label_status POST 按标注状态筛选零件
/api/stats                     POST    统计零件数量
/api/label/save_json           POST    保存零件标注JSON文件
/api/label/send_solid_file     POST    发送零件模型文件
/api/label/import_json         POST    导入零件标注JSON文件
/api/label/upload_file         POST    上传CAD模型文件
/api/label/filter_json         POST    筛选JSON标注文件
```