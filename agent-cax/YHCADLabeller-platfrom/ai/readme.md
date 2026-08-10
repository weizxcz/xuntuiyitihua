# AI 模块说明

运行时识别和预标注只使用 ONNX：

- `AAGNet_infer/base_utils_onnx.py`：ONNX Runtime 推理与后处理。
- `AAGNet_infer/weights/`：圆角、倒角、盲孔、沉头孔各一组 `.onnx` 与统计 `.json`。
- `infer_worker.py`：预标注的 ONNX 子进程入口。

训练相关内容位于 `AAGNet_train/`，由 `train_worker.py` 在 `Geometry_new` 环境执行。训练输出的 `best_model.pth` 可通过 `onnx_export_worker.py` 转换为同目录的 `best_model.onnx`；使用时必须搭配训练同时生成的 `best_model.json`。

详细数据集格式、训练步骤与环境配置见项目根目录 `README.md`。
