# 草图初始化 (Sketch Initialization)

适用场景：创建、打开、关闭草图，获取或删除草图对象。

## API 参考

### 1. 创建草图实例 (Create Sketch Work Plane)

**默认平面：**
```python
skt = NCTI.SketchWorkPlane(doc)
```

**自定义平面（指定原点和方向）：**
```python
skt = NCTI.SketchWorkPlane(doc, NCTI.Point(0, 0, 0), NCTI.Vector(1, 0, 0), NCTI.Vector(0, 1, 0))
```

| 参数 | 类型 | 说明 |
|------|------|------|
| doc | Document | 活动文档对象（预注入） |
| origin | NCTI.Point | 草图平面原点（自定义平面重载使用） |
| dirX | NCTI.Vector | X 轴方向向量（自定义平面重载使用） |
| dirY | NCTI.Vector | Y 轴方向向量（自定义平面重载使用） |

> 两份基准文档仅给出两种固定重载：默认平面（仅 doc）和自定义平面（doc + origin + dirX + dirY）。各参数是否可作为可选关键字参数省略，文档未明示，使用时按上述两种完整重载调用。

### 2. 打开草图 (Open Sketch)

```python
skt.Open()
```

进入草图绘制模式。无参数。所有绘制操作前必须先调用。

### 3. 关闭草图 (Close Sketch)

```python
skt.Close()
```

退出草图绘制模式。无参数。

### 4. 获取草图对象 (Get Object)

```python
obj = skt.GetObject("object_name")
```

| 参数 | 类型 | 说明 |
|------|------|------|
| object_name | str | 对象名称（基本对象、约束对象或基准对象） |

可通过名称获取任何草图对象（几何对象、约束对象、坐标轴、坐标原点等）。在约束编辑流程中常用于获取已创建的约束对象。

### 5. 删除草图对象 (Delete Objects)

```python
skt.Delete(["obj1", "obj2"])
```

| 参数 | 类型 | 说明 |
|------|------|------|
| names | list[str] | 要删除的对象名称列表 |

## 代码示例

**示例：在自定义平面上创建草图**

```python
# 创建草图（自定义平面，原点在 (5, 0, 0)，X 方向为 (0, 1, 0)，Y 方向为 (0, 0, 1)）
skt = NCTI.SketchWorkPlane(doc, NCTI.Point(5, 0, 0), NCTI.Vector(0, 1, 0), NCTI.Vector(0, 0, 1))

# 进入草图模式
skt.Open()

# ... 绘制操作 ...

# 退出
skt.Close()
```

## 注意事项

- 创建草图后必须调用 `skt.Open()` 才能进行绘制操作。
- `skt` 变量是所有草图操作的入口，必须保持一致的变量名。
- `GetObject` 可获取已命名对象的引用，在约束编辑和对象引用时使用。
- `Delete` 接受名称列表，可一次删除多个对象。
