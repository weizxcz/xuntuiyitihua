import onnx

# 加载ONNX模型
model_path = r"D:\code\YHCADSmartCleaner\ai\AAGNet_infer\weights\weight_round.onnx"
model = onnx.load(model_path)

# 打印模型信息
print(f"模型名称: {model.graph.name}")
print(f"输入数量: {len(model.graph.input)}")
print(f"输出数量: {len(model.graph.output)}")

# 打印输入信息
print("\n输入信息:")
for i, input in enumerate(model.graph.input):
    print(f"输入 {i+1}:")
    print(f"  名称: {input.name}")
    print(f"  形状: {input.type.tensor_type.shape}")
    print(f"  数据类型: {input.type.tensor_type.elem_type}")

# 打印输出信息
print("\n输出信息:")
for i, output in enumerate(model.graph.output):
    print(f"输出 {i+1}:")
    print(f"  名称: {output.name}")
    print(f"  形状: {output.type.tensor_type.shape}")
    print(f"  数据类型: {output.type.tensor_type.elem_type}")
