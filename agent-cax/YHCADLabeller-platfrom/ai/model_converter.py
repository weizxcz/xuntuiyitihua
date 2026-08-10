"""Main-process helpers for exporting a trained AAGNet PTH weight to ONNX."""

import json
import subprocess
from pathlib import Path


def onnx_path_for_weight(weight_path):
    return str(Path(weight_path).with_suffix(".onnx"))


def export_weight_to_onnx(weight_path, python_exe):
    weight = Path(weight_path)
    if weight.suffix.lower() != ".pth":
        raise ValueError("模型转换只支持 .pth 权重文件")
    if not weight.is_file():
        raise FileNotFoundError(f"未找到 PTH 权重: {weight}")

    output = Path(onnx_path_for_weight(weight))
    report = output.with_suffix(".onnx.verify.json")
    command = [str(python_exe), "-m", "ai.onnx_export_worker", "--weight", str(weight), "--output", str(output), "--report", str(report)]
    result = subprocess.run(command, cwd=str(Path(__file__).resolve().parents[1]), capture_output=True, text=True)
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or f"退出码 {result.returncode}"
        raise RuntimeError(f"ONNX 转换失败: {detail}")
    if not output.is_file() or not report.is_file():
        raise RuntimeError("ONNX 转换未生成预期的模型或验证报告")
    verification = json.loads(report.read_text(encoding="utf-8"))
    if not verification.get("finite_outputs"):
        raise RuntimeError("导出的 ONNX 模型未通过有限输出验证")
    return output, report, verification
