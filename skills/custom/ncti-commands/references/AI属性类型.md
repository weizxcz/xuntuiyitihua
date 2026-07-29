# AI属性类型参考文档

共 3 个命令

---

## 定义AI属性对象

**类型：** 建模命令

**说明：** 定义AI属性对象

**示例：**

```python
doc.RunCommand("cmd_ncti_create_box", "bx", 10, 20, 30)
aiObj = NCTI.AiObjectData("bx", 1, 2)
aiAtt = NCTI.AiAttribute("圆角", [aiObj])
doc.RunCommand("cmd_ncti_ai_model_add_label", [aiAtt])
```

---

## 获取AI对象变量

**类型：** 建模命令

**说明：** 获取AI对象变量

**示例：**

```python
doc.RunCommand("cmd_ncti_create_box", "bx", 10, 20, 30)
aiObj = NCTI.AiObjectData("bx", 1, 2)
aiAtt = NCTI.AiAttribute("圆角", [aiObj])
aiObj0 = aiAtt.AiObjects[0]
print(aiObj0.Name)
```

---

## 获取AI属性标签

**类型：** 建模命令

**说明：** 获取AI属性标签

**示例：**

```python
doc.RunCommand("cmd_ncti_create_box", "bx", 10, 20, 30)
aiObj = NCTI.AiObjectData("bx", 1, 2)
aiAtt = NCTI.AiAttribute("圆角", [aiObj])
print(aiAtt.Label)
```

---

