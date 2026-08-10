# AI模型类型参考文档

共 5 个命令

---

## 定义AI模型对象

**类型：** 建模命令

**说明：** 定义AI模型对象

**示例：**

```python
doc.Clear()
doc.ResetCaseResult()
doc.RunCommand("cmd_ncti_create_box", "bx", 10, 20, 30)
ai = NCTI.AiModel(doc, "bx")
```

---

## 导入AI推理结果

**类型：** 建模命令

**说明：** 导入AI推理结果

**示例：**

```python
doc.Clear()
doc.ResetCaseResult()
doc.RunCommand("cmd_ncti_create_box", "bx", 10, 20, 30)
sys.path.insert(0, "D:/MyProject/GitCode/NCTICAXSDK/Windows/RelWithDebInfo/AI/AAGNet_package_AI4CAD")
from base_utils import AGGNetInference
ai = NCTI.AiModel(doc, "bx")
FaceID = ai.FaceID
FaceFID = ai.FaceFID
FaceEID = ai.FaceEID
graph_face_attr = ai.FaceAttr
FacePoints = ai.FacePoints
FaceNormals = ai.FaceNormals
FaceMask = ai.FaceMask
graph_edge_attr = ai.EdgeAttr

AAGNet = AGGNetInference()
face_logits, inst_out, bottom_out = AAGNet.AI_model_inference(FaceID,FaceFID,FaceEID,FacePoints,FaceNormals,FaceMask,graph_edge_attr,graph_face_attr)
result_dict = AAGNet.postprocess(face_logits, inst_out, bottom_out,graph_face_attr)
ai.ImportAiResult(result_dict)
```

---

## 获取AI属性变量

**类型：** 建模命令

**说明：** 获取AI属性变量

**示例：**

```python
doc.Clear()
doc.ResetCaseResult()
doc.RunCommand("cmd_ncti_create_box", "bx", 10, 20, 30)
ai = NCTI.AiModel(doc, 'bx')
aiObj = NCTI.AiObjectData("bx", 1,2)
aiAtt = NCTI.AiAttribute("圆角",[aiObj])
doc.RunCommand("cmd_ncti_ai_model_add_label", [aiAtt])
att = ai.AiAttributes[0]
print(att.Label)
```

---

## 获取两个面是否相邻

**类型：** 建模命令

**说明：** 获取两个面是否相邻

**示例：**

```python
doc.Clear()
doc.ResetCaseResult()
doc.RunCommand("cmd_ncti_create_box", "bx", 10, 20, 30)
ai = NCTI.AiModel(doc, 'bx')
doc.RunCommand("cmd_ncti_ai_attr_topo_display", 'bx',ai)
print(ai.GetTwoFacesAdjacent(0,3))
```

---

## 获得AI模型对象属性集

**类型：** 基础命令

**说明：** 获取AI模型对象属性集

**示例：**

```python
import time

doc.RunCommand("cmd_ncti_create_box", "b1", NCTI.Point(20,0,0),2,3,4)

t0 = time.time()
ai = NCTI.AiModel(doc, "b1")
print(f"创建推理模型耗时：{round(time.time()-t0, 3)}")
print("ID:", ai.ID)
print("\n")
print("StpName:", ai.StpName)
print("\n")
print("objName:", ai.objName)
print("\n")
print("leftNormal:", ai.leftNormal)
print("\n")
print("rightNormal:", ai.rightNormal)
print("\n")
print("FaceEID:", ai.FaceEID)
print("\n")
print("FaceFID:", ai.FaceFID)
print("\n")
print("FaceID:", ai.FaceID)
print("\n")
print("FaceAttr:", ai.FaceAttr)
print("\n")
print("FaceLabel:", ai.FaceLabel)
print("\n")
print("FaceMask:", ai.FaceMask)
print("\n")
print("FaceNormals:", ai.FaceNormals)
print("\n")
print("FacePoints:", ai.FacePoints)
print("\n")
print("EdgeAttr: ", ai.EdgeAttr)
print("\n")
print("EdgePoints: ", ai.EdgePoints)
print("\n")
print("EdgeTangents: ", ai.EdgeTangents)

```

---

