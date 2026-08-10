"""Export a single AAGNet state dict to a dynamic-shape Scatter ONNX model."""

import argparse
import json
import sys
import types
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch

sys.modules.setdefault("dgl.graphbolt", types.ModuleType("dgl.graphbolt"))

from ai.AAGNet_infer.onnx_tools.tensor_segmentor import AAGNetTensorSegmentor


def _state_dict(weight_path):
    value = torch.load(weight_path, map_location="cpu")
    if isinstance(value, dict) and "state_dict" in value:
        value = value["state_dict"]
    if not isinstance(value, dict):
        raise ValueError("PTH 文件不包含 state_dict")
    return {key.removeprefix("module."): tensor for key, tensor in value.items()}


def build_tensor_model(state_dict):
    node_attr_dim = state_dict["node_attr_encoder.0.weight"].shape[1]
    edge_attr_dim = state_dict["edge_attr_encoder.0.weight"].shape[1]
    model = AAGNetTensorSegmentor(
        num_classes=2, edge_attr_dim=edge_attr_dim, node_attr_dim=node_attr_dim,
        edge_attr_emb=64, node_attr_emb=64, node_grid_dim=7, node_grid_emb=64,
        num_layers=4, delta=2, mlp_ratio=4, drop=0.0, drop_path=0.0, head_hidden_dim=256,
    )
    model.load_state_dict(state_dict)
    model.eval()
    return model, int(node_attr_dim), int(edge_attr_dim)


def export_and_verify(weight_path, output_path, report_path, opset=17):
    model, node_attr_dim, edge_attr_dim = build_tensor_model(_state_dict(weight_path))
    num_nodes, num_edges = 12, 24
    dummy = (
        torch.randn(num_nodes, node_attr_dim), torch.randn(num_nodes, 7, 5, 5),
        torch.randn(num_edges, edge_attr_dim), torch.randint(0, num_nodes, (num_edges,), dtype=torch.int64),
        torch.randint(0, num_nodes, (num_edges,), dtype=torch.int64),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        model, dummy, output_path, export_params=True, opset_version=opset, do_constant_folding=True,
        input_names=["node_attr", "node_grid", "edge_attr", "src", "dst"],
        output_names=["seg_out", "inst_out", "bottom_out"],
        dynamic_axes={
            "node_attr": {0: "num_nodes"}, "node_grid": {0: "num_nodes"}, "edge_attr": {0: "num_edges"},
            "src": {0: "num_edges"}, "dst": {0: "num_edges"}, "seg_out": {0: "num_nodes"},
            "inst_out": {1: "num_nodes", 2: "num_nodes"}, "bottom_out": {0: "num_nodes"},
        },
    )
    session = ort.InferenceSession(str(output_path), providers=["CPUExecutionProvider"])
    feeds = {"node_attr": dummy[0].numpy(), "node_grid": dummy[1].numpy(), "edge_attr": dummy[2].numpy(), "src": dummy[3].numpy(), "dst": dummy[4].numpy()}
    outputs = session.run(None, feeds)
    report = {
        "source_weight": str(weight_path), "onnx_path": str(output_path), "finite_outputs": all(np.isfinite(value).all() for value in outputs),
        "output_shapes": [list(value.shape) for value in outputs], "node_attr_dim": node_attr_dim, "edge_attr_dim": edge_attr_dim,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if not report["finite_outputs"]:
        raise AssertionError("ONNX Runtime produced non-finite outputs")
    return report


def main():
    parser = argparse.ArgumentParser(description="Export one AAGNet PTH weight to ONNX and validate it.")
    parser.add_argument("--weight", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export_and_verify(args.weight, args.output, args.report), ensure_ascii=False))


if __name__ == "__main__":
    main()
