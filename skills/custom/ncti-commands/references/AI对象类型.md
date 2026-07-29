# AI对象类型参考文档

共 2 个命令

---

## 定义AI对象变量

**类型：** 建模命令

**说明：** 定义AI对象变量

**示例：**

```python
doc.RunCommand("cmd_ncti_create_box", "bx", 10, 20, 30)
aiObj = NCTI.AiObjectData("bx", 1, 2)
```

---

## 获取AI对象属性

**类型：** 建模命令

**说明：** 获取AI对象属性

**示例：**

```python
#aiObj = att.AiObjects[0]
aiObj = NCTI.AiObjectData("bx", 1, 2)
print(aiObj.Id)
print(aiObj.Type)
print(aiObj.Name)
```

---

