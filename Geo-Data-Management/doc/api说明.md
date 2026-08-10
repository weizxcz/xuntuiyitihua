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

---

## 2. 接口列表

### 2.1 获取零件列表

**路径**: `POST /api/parts`

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

**路径**: `POST /api/parts/{part_id}`

**功能**: 根据ID获取单个零件的详细信息

**路径参数**:

| 参数 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| part_id | int | 是 | 零件ID |

**请求示例**:
```
POST /api/parts/1
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

**失败响应** (HTTP 404):
```json
{
  "code": 404,
  "message": "Part not found"
}
```

---

### 2.3 创建零件记录

**路径**: `POST /api/parts`

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

**路径**: `PUT /api/parts/{part_id}`

**功能**: 更新指定零件的信息

**路径参数**:

| 参数 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| part_id | int | 是 | 零件ID |

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
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

**失败响应** (HTTP 404):
```json
{
  "code": 404,
  "message": "Part not found"
}
```

---

### 2.5 删除零件记录

**路径**: `DELETE /api/parts/{part_id}`

**功能**: 删除指定的零件记录

**路径参数**:

| 参数 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| part_id | int | 是 | 零件ID |

**请求示例**:
```
DELETE /api/parts/1
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

**路径**: `PATCH /api/parts/{part_id}/label/{feature_type}`

**功能**: 更新指定零件的特征标注状态

**路径参数**:

| 参数 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| part_id | int | 是 | 零件ID |
| feature_type | string | 是 | 特征类型 |

**feature_type 可选值**:
| 值 | 说明 |
| :--- | :--- |
| round | 圆角 |
| chamfer | 倒角 |
| countersink_hole | 沉头孔 |
| counterbore_hole | 沉孔 |
| through_hole | 通孔 |
| blind_hole | 盲孔 |

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| status | string | 是 | 标注状态 |
| modified_by | string | 否 | 修改人 |

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

**路径**: `POST /api/parts/filter/feature`

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

**路径**: `POST /api/parts/filter/label-status`

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

### 2.10 上传 CAD 模型文件

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
