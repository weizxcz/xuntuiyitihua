# 数据库设计说明文档

## 1. 数据库概述

本数据库用于存储 STP/STEP/IGS 等 CAD 模型文件的基本信息，支持对零件特征（圆角、倒角、孔等）的标注和管理。

### 数据库信息
- **数据库名称**: `solid_info.db`
- **数据表名称**: `part_info`
- **数据库类型**: SQLite

---

## 2. 数据表结构设计

### 2.1 表字段定义

| 字段名 | 数据类型 | 约束 | 说明 |
| :--- | :--- | :--- | :--- |
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | 主键，自增 |
| `hash_id` | VARCHAR(64) | NOT NULL UNIQUE | 文件唯一哈希标识 |
| `name` | VARCHAR(255) | NOT NULL | STP/IGS 文件名 |
| `created_time` | DATETIME | NOT NULL DEFAULT CURRENT_TIMESTAMP | 记录创建时间 |
| `modified_time` | DATETIME | NOT NULL DEFAULT CURRENT_TIMESTAMP | 记录修改时间 |
| `created_by` | VARCHAR(100) | | 创建人 |
| `modified_by` | VARCHAR(100) | | 修改人 |
| `format` | VARCHAR(10) | NOT NULL | 文件格式（stp/igs） |
| `is_open_source` | BOOLEAN | DEFAULT FALSE | 是否开源 |
| `source_type` | VARCHAR(20) | DEFAULT 'private' | 数据来源（public/private） |
| `industry` | VARCHAR(50) | | 行业分类（如：家电、汽车、航空航天、机械、电子等） |
| `product_type` | VARCHAR(100) | | 具体物品（如：冰箱、洗衣机、发动机、电路板等） |
| `has_round` | BOOLEAN | DEFAULT FALSE | 是否包含圆角特征 |
| `has_chamfer` | BOOLEAN | DEFAULT FALSE | 是否包含倒角特征 |
| `has_countersink_hole` | BOOLEAN | DEFAULT FALSE | 是否包含沉头孔特征 |
| `has_counterbore_hole` | BOOLEAN | DEFAULT FALSE | 是否包含沉孔特征 |
| `has_through_hole` | BOOLEAN | DEFAULT FALSE | 是否包含通孔特征 |
| `has_blind_hole` | BOOLEAN | DEFAULT FALSE | 是否包含盲孔特征 |
| `label_round_status` | VARCHAR(20) | DEFAULT 'pending' | 圆角标注状态 |
| `label_chamfer_status` | VARCHAR(20) | DEFAULT 'pending' | 倒角标注状态 |
| `label_countersink_hole_status` | VARCHAR(20) | DEFAULT 'pending' | 沉头孔标注状态 |
| `label_counterbore_hole_status` | VARCHAR(20) | DEFAULT 'pending' | 沉孔标注状态 |
| `label_through_hole_status` | VARCHAR(20) | DEFAULT 'pending' | 通孔标注状态 |
| `label_blind_hole_status` | VARCHAR(20) | DEFAULT 'pending' | 盲孔标注状态 |

### 2.2 字段详细说明

#### 2.2.1 基础信息字段

- **id**: 自增主键，唯一标识每条记录
- **hash_id**: 文件内容的哈希值（如 SHA256），用于唯一标识文件，避免重复上传
- **name**: 原始文件名，不含路径
- **created_time**: 记录创建时间，自动生成
- **modified_time**: 记录最后修改时间，每次更新自动刷新
- **created_by**: 创建该记录的用户标识
- **modified_by**: 最后修改该记录的用户标识
- **format**: 文件格式，取值范围：`stp`、`step`、`igs`
- **is_open_source**: 是否开源，`TRUE` 表示开源，`FALSE` 表示私有
- **source_type**: 数据来源类型，取值：
  - `public`: 公开数据集
  - `private`: 自有数据

#### 2.2.2 行业分类字段

- **industry**: 零件所属行业，可选值包括但不限于：
  - 家电
  - 汽车
  - 航空航天
  - 机械制造
  - 电子设备
  - 医疗器械
  - 船舶制造

- **product_type**: 零件所属的具体产品，可选值包括但不限于：
  - 冰箱、洗衣机、空调（家电）
  - 发动机、变速箱、车身部件（汽车）
  - 机翼、发动机叶片（航空航天）
  - 齿轮、轴承、泵体（机械制造）
  - 电路板、连接器（电子设备）

#### 2.2.3 特征检测字段

| 字段名 | 含义 | 数据类型 |
| :--- | :--- | :--- |
| `has_round` | 模型是否包含圆角特征 | BOOLEAN |
| `has_chamfer` | 模型是否包含倒角特征 | BOOLEAN |
| `has_countersink_hole` | 模型是否包含沉头孔特征 | BOOLEAN |
| `has_counterbore_hole` | 模型是否包含沉孔特征 | BOOLEAN |
| `has_through_hole` | 模型是否包含通孔特征 | BOOLEAN |
| `has_blind_hole` | 模型是否包含盲孔特征 | BOOLEAN |

#### 2.2.4 标注状态字段

标注状态字段用于跟踪特征标注任务的进度，可选值：

| 状态值 | 含义 |
| :--- | :--- |
| `pending` | 待标注 |
| `in_progress` | 标注中 |
| `completed` | 已完成 |
| `skipped` | 跳过 |
| `error` | 标注异常 |

---

## 3. SQL 建表语句

```sql
CREATE TABLE IF NOT EXISTS part_info (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hash_id VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    modified_by VARCHAR(100),
    format VARCHAR(10) NOT NULL,
    is_open_source BOOLEAN DEFAULT FALSE,
    source_type VARCHAR(20) DEFAULT 'private',
    industry VARCHAR(50),
    product_type VARCHAR(100),
    has_round BOOLEAN DEFAULT FALSE,
    has_chamfer BOOLEAN DEFAULT FALSE,
    has_countersink_hole BOOLEAN DEFAULT FALSE,
    has_counterbore_hole BOOLEAN DEFAULT FALSE,
    has_through_hole BOOLEAN DEFAULT FALSE,
    has_blind_hole BOOLEAN DEFAULT FALSE,
    label_round_status VARCHAR(20) DEFAULT 'pending',
    label_chamfer_status VARCHAR(20) DEFAULT 'pending',
    label_countersink_hole_status VARCHAR(20) DEFAULT 'pending',
    label_counterbore_hole_status VARCHAR(20) DEFAULT 'pending',
    label_through_hole_status VARCHAR(20) DEFAULT 'pending',
    label_blind_hole_status VARCHAR(20) DEFAULT 'pending'
);

CREATE INDEX IF NOT EXISTS idx_part_info_hash_id ON part_info(hash_id);
CREATE INDEX IF NOT EXISTS idx_part_info_format ON part_info(format);
CREATE INDEX IF NOT EXISTS idx_part_info_industry ON part_info(industry);
CREATE INDEX IF NOT EXISTS idx_part_info_product_type ON part_info(product_type);
```

---

## 4. 索引设计

为优化查询性能，创建以下索引：

| 索引名称 | 字段 | 说明 |
| :--- | :--- | :--- |
| `idx_part_info_hash_id` | hash_id | 加速文件去重查询 |
| `idx_part_info_format` | format | 加速按格式筛选 |
| `idx_part_info_industry` | industry | 加速按行业筛选 |
| `idx_part_info_product_type` | product_type | 加速按产品类型筛选 |

---

## 5. 数据操作示例

### 5.1 使用 ORM 操作示例

#### 5.1.1 插入记录

```python
from app.database import SessionLocal, init_db
from app.database.crud import create_part

init_db()
db = SessionLocal()

part_data = {
    "hash_id": "abc123def456...",
    "name": "engine_part.stp",
    "format": "stp",
    "industry": "汽车",
    "product_type": "发动机",
    "has_round": True,
    "has_chamfer": False,
    "has_through_hole": True,
    "is_open_source": False,
    "source_type": "private",
    "created_by": "user001"
}

new_part = create_part(db, part_data)
print(f"插入成功: {new_part.name}, ID: {new_part.id}")

db.close()
```

#### 5.1.2 查询某行业的所有零件

```python
from app.database import SessionLocal
from app.database.crud import get_parts

db = SessionLocal()

parts = get_parts(db, industry="家电", limit=10)
for part in parts:
    print(f"{part.id}: {part.name} ({part.product_type})")

db.close()
```

#### 5.1.3 更新标注状态

```python
from app.database import SessionLocal
from app.database.crud import update_label_status

db = SessionLocal()

updated_part = update_label_status(
    db,
    part_id=1,
    feature_type="round",
    status="completed",
    modified_by="user002"
)
print(f"圆角标注状态已更新为: {updated_part.label_round_status}")

db.close()
```

#### 5.1.4 查询待标注的零件

```python
from app.database import SessionLocal
from app.database.crud import get_parts_by_label_status

db = SessionLocal()

pending_parts = get_parts_by_label_status(db, label_status="pending")
print(f"待标注零件数量: {len(pending_parts)}")

db.close()
```

#### 5.1.5 查询包含特定特征的零件

```python
from app.database import SessionLocal
from app.database.crud import get_parts_by_feature

db = SessionLocal()

parts = get_parts_by_feature(
    db,
    has_round=True,
    has_through_hole=True
)
for part in parts:
    print(f"{part.name}")

db.close()
```

### 5.2 内部 CRUD 函数调用示例

#### 5.2.1 创建零件

```python
from app.database import SessionLocal
from app.database.crud import create_part

db = SessionLocal()

part_data = {
    "hash_id": "abc123def456...",
    "name": "engine_part.stp",
    "format": "stp",
    "industry": "汽车",
    "product_type": "发动机",
    "has_round": True,
    "has_chamfer": False,
    "has_through_hole": True,
    "is_open_source": False,
    "source_type": "private",
    "created_by": "user001"
}

new_part = create_part(db, part_data)
print(f"创建成功: ID={new_part.id}, 名称={new_part.name}")

db.close()
```

#### 5.2.2 查询零件列表

```python
from app.database import SessionLocal
from app.database.crud import get_parts

db = SessionLocal()

parts = get_parts(
    db,
    industry="家电",
    limit=10,
    skip=0
)

for part in parts:
    print(f"ID: {part.id}, 名称: {part.name}, 产品: {part.product_type}")

db.close()
```

#### 5.2.3 获取单个零件

```python
from app.database import SessionLocal
from app.database.crud import get_part_by_id, get_part_by_hash_id

db = SessionLocal()

# 按 ID 查询
part = get_part_by_id(db, part_id=1)

# 按 hash_id 查询
part = get_part_by_hash_id(db, hash_id="abc123def456...")

if part:
    print(f"ID: {part.id}, 名称: {part.name}, 格式: {part.format}")

db.close()
```

#### 5.2.4 更新零件信息

```python
from app.database import SessionLocal
from app.database.crud import update_part

db = SessionLocal()

update_data = {
    "industry": "家电",
    "product_type": "冰箱",
    "modified_by": "user002"
}

updated_part = update_part(db, part_id=1, update_data=update_data)
if updated_part:
    print(f"更新成功: {updated_part.name}")

db.close()
```

#### 5.2.5 更新标注状态

```python
from app.database import SessionLocal
from app.database.crud import update_label_status

db = SessionLocal()

updated_part = update_label_status(
    db,
    part_id=1,
    feature_type="round",
    status="completed",
    modified_by="user002"
)

if updated_part:
    print(f"圆角标注状态: {updated_part.label_round_status}")

db.close()
```

#### 5.2.6 删除零件

```python
from app.database import SessionLocal
from app.database.crud import delete_part

db = SessionLocal()

deleted = delete_part(db, part_id=1)
print(f"删除结果: {'成功' if deleted else '失败'}")

db.close()
```

#### 5.2.7 按特征筛选

```python
from app.database import SessionLocal
from app.database.crud import get_parts_by_feature

db = SessionLocal()

parts = get_parts_by_feature(
    db,
    has_round=True,
    has_through_hole=True
)

for part in parts:
    print(f"{part.id}: {part.name}")

db.close()
```

#### 5.2.8 按标注状态筛选

```python
from app.database import SessionLocal
from app.database.crud import get_parts_by_label_status

db = SessionLocal()

pending_parts = get_parts_by_label_status(db, label_status="pending")
completed_parts = get_parts_by_label_status(db, label_status="completed")

print(f"待标注: {len(pending_parts)} 个")
print(f"已完成: {len(completed_parts)} 个")

db.close()
```

#### 5.2.9 统计记录数

```python
from app.database import SessionLocal
from app.database.crud import count_parts

db = SessionLocal()

total = count_parts(db)
auto_count = count_parts(db, industry="汽车")

print(f"总记录数: {total}")
print(f"汽车行业: {auto_count}")

db.close()
```

---

## 6. 数据字典

| 分类 | 字段前缀 | 说明 |
| :--- | :--- | :--- |
| 基础信息 | `id`, `hash_id`, `name`, `format` | 文件唯一标识和基本属性 |
| 开源与来源 | `is_open_source`, `source_type` | 开源状态和数据来源 |
| 时间与人员 | `created_time`, `modified_time`, `created_by`, `modified_by` | 记录维护信息 |
| 分类信息 | `industry`, `product_type` | 行业和产品类型分类 |
| 特征检测 | `has_*` | 是否包含各类几何特征 |
| 标注状态 | `label_*_status` | 各类特征的标注进度 |