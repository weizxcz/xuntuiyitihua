# py-viewer 状态输出设计方案

## 概述

本文档描述在执行完 AI 脚本后，如何获取并输出当前文档的状态信息。

## 设计原则

1. **状态与执行结果分离** - 脚本执行结果（output/error）与文档状态分开返回
2. **仅使用 doc API** - 不依赖 yh_doc，yh_doc 需 AI 脚本自行获取
3. **不包含网格数据** - 避免输出过大
4. **不包含相机信息** - 视图状态暂不捕获
5. **JSON 格式输出** - 便于前端解析

## 架构设计

### 执行流程

```
AI 脚本执行 → main_window.run_sketch_script() → 返回 (output, error)
                                               ↓
文档状态查询 → main_window.capture_document_status() → 返回 状态 JSON
```

### HTTP 接口（可选）

HTTP 接口用于远程调用，非必需：
```
POST /api/execute → 执行脚本
GET  /api/status  → 获取状态
```

### 全局执行上下文

脚本执行时可用的全局变量：

```python
global_scope = {
    "NCTI": self.NCTI,
    "doc": self.doc,
    "YH": self.YH,
    # 内置函数：print, len, str, int, float, list, dict, tuple
}
```

**注意**：`yh_doc` 不在全局上下文中，AI 脚本需要自行获取：
```python
yh_doc = YH.YHDocument(doc.ID)
```

## doc API 可获取的信息

| 类别 | 命令 | 返回内容 |
|------|------|----------|
| **文档级** | `doc.AllNames()` | 所有对象名称列表 |
| **文档级** | `doc.IsModified()` | 是否被修改 (bool) |
| **文档级** | `doc.GetCmdInfo()` | 命令执行信息 |
| **文档级** | `doc.InterfaceResult` | 中间层接口结果 |
| **文档级** | `doc.ID` | 文档 ID |
| **建模** | `doc.GetTopoNb(objName)` | 拓扑信息（顶点/边/面数量） |
| **建模** | `doc.GetBoundingBox(names)` | 外包盒坐标 |
| **建模** | `doc.GetObbBoungdingBox(names)` | OBB 包围盒 |
| **建模** | `doc.Scene(objName)` | 场景对象信息 |
| **建模** | `doc.GetMesh(objName)` | 网格数据（**不包含**） |
| **草图** | `yh_doc.GetActivitySketch()` | 激活草图（需自行获取 yh_doc） |
| **选择** | `NCTI.SelectionManager(doc)` | 选择管理器 |
| **选择** | `sel.ObjectNames` | 选中对象名称 |
| **选择** | `sel.CellIDs` | 选中拓扑 ID |

## 状态 JSON 结构

```json
{
  "timestamp": "2026-08-07T15:30:00Z",
  "document": {
    "id": 12345,
    "is_modified": false,
    "total_objects": 3,
    "object_names": ["box1", "cylinder1", "sphere1"]
  },
  "scene": {
    "root": {
      "type": "Root",
      "children": ["box1", "cylinder1", "sphere1"]
    },
    "objects": {
      "box1": {
        "type": "Part",
        "parent": null,
        "transform": [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]
      }
    }
  },
  "modeling": {
    "objects": [
      {
        "name": "box1",
        "topology": {
          "vertices": 8,
          "edges": 12,
          "faces": 6
        },
        "bounding_box": {
          "min": [0, 0, 0],
          "max": [10, 20, 30]
        }
      }
    ]
  },
  "sketch": {
    "is_open": false,
    "active_sketch": null,
    "geometry": {
      "points": 0,
      "lines": 0,
      "circles": 0,
      "splines": 0,
      "rectangles": 0,
      "arcs": 0,
      "ellipses": 0
    },
    "constraints": {
      "dimensional": 0,
      "geometric": 0,
      "total": 0
    },
    "is_solved": false,
    "is_fully_constrained": false
  },
  "selection": {
    "selected_objects": [],
    "selected_cell_ids": [],
    "selected_count": 0
  }
}
```

## 字段说明

### document（文档级状态）
- `id`: 文档 ID
- `is_modified`: 文档是否被手动修改
- `total_objects`: 对象总数
- `object_names`: 所有对象名称列表

### modeling（建模状态）
- `objects`: 对象列表
  - `name`: 对象名称
  - `topology`: 拓扑信息
    - `vertices`: 顶点数
    - `edges`: 边数
    - `faces`: 面数
  - `bounding_box`: 外包盒
    - `min`: 最小角点 [x, y, z]
    - `max`: 最大角点 [x, y, z]

### scene（场景层级）
- `root`: 场景根节点
  - `type`: 节点类型
  - `children`: 子节点名称列表
- `objects`: 各对象的场景信息
  - `type`: 对象类型（Part/Feature/Sketch 等）
  - `parent`: 父节点名称（null 表示根节点）
  - `transform`: 变换矩阵（12 个元素的数组）

**注意**：场景信息通过 `doc.Scene(objName)` 获取，反映对象在文档中的层级关系。

### sketch（草图状态）
- `is_open`: 是否有激活草图
- `active_sketch`: 激活草图名称
- `geometry`: 几何元素统计
  - `points`: 点数
  - `lines`: 直线数
  - `circles`: 圆数
  - `splines`: 样条曲线数
  - `rectangles`: 矩形数
  - `arcs`: 圆弧数
  - `ellipses`: 椭圆数
- `constraints`: 约束统计
  - `dimensional`: 尺寸约束数
  - `geometric`: 几何约束数
  - `total`: 总约束数
- `is_solved`: 草图是否已求解
- `is_fully_constrained`: 草图是否完全约束

**注意**：草图状态需要通过 `yh_doc` 获取，AI 脚本中需自行获取：
```python
yh_doc = YH.YHDocument(doc.ID)
skt = yh_doc.GetActivitySketch()
```

### selection（选择集状态）
- `selected_objects`: 选中对象名称列表
- `selected_cell_ids`: 选中拓扑 ID 列表
- `selected_count`: 选中对象数量

## 调用方式

### 方式一：直接调用（推荐）

在 `main_window.py` 中直接调用：

```python
# 执行脚本
output, error = self.run_sketch_script(script)

# 获取状态
if not error:
    status = self.capture_document_status()
```

### 方式二：HTTP 接口（可选）

HTTP 接口用于远程调用，非必需：

```
POST /api/execute
Body: {"script": "...", "description": "..."}
Response: {"success": true, "output": "...", "error": null, "description": "..."}

GET /api/status
Response: 状态 JSON
```

## 实现位置

### 1. 状态捕获方法（main_window.py）

```python
def capture_document_status(self) -> dict:
    """捕获当前文档状态（仅用 doc API，不含网格和相机）"""
    from datetime import datetime
    
    # ... 实现 ...
```

### 2. 使用方式（main_window.py）

```python
# 执行脚本
output, error = self.run_sketch_script(script)

# 获取状态
if not error:
    status = self.capture_document_status()
```

### 3. HTTP 端点（可选，http_server.py）

```python
@app.get("/api/status")
async def get_status():
    """获取当前文档状态"""
    status = main_window.capture_document_status()
    return status
```

## 待实现内容

- [ ] `capture_document_status()` 方法实现
- [ ] `/api/status` 端点实现
- [ ] 草图状态获取逻辑（需要测试 `yh_doc` API）
- [ ] 选择集状态获取逻辑（需要测试 `SelectionManager` API）

## 相关文档

- [main_window.py](ui/main_window.py) - 脚本执行入口
- [http_server.py](services/http_server.py) - HTTP 服务器
