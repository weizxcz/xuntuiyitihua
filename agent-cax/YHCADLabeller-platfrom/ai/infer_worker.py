import sys
import json
import traceback

import numpy as np


def main(input_path, output_path):
    with open(input_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    result = {}
    try:
        if not payload["weight_path"].lower().endswith(".onnx"):
            raise ValueError("预标注仅支持 ONNX 模型（.onnx）")
        from .AAGNet_infer.base_utils_onnx import AGGNetInferenceONNX
        aag_net = AGGNetInferenceONNX(
            weight_path=payload["weight_path"], stat_path=payload["stat_path"]
        )

        graph_face_attr = [row[:aag_net.node_attr_dim] for row in payload["graph_face_attr"]]
        graph_edge_attr = [row[:aag_net.edge_attr_dim] for row in payload["graph_edge_attr"]]
        adj_true = np.array(payload["adj_true"], dtype=np.int32)

        seg_out, inst_out, bottom_out = aag_net.ai_model_inference(
            payload["face_id"], payload["face_f_id"], payload["face_e_id"],
            payload["face_points"], payload["face_normals"], payload["face_mask"],
            graph_edge_attr, graph_face_attr,
        )
        postprocess_kwargs = {
            "min_faces_num": payload["min_faces_num"],
            "max_faces_num": payload["max_faces_num"],
            "feature_name": payload["feature_name"],
        }
        postprocess_kwargs["face_ids"] = payload["face_id"]
        result_dict = aag_net.postprocess_feature(
            seg_out, inst_out, bottom_out, adj_true,
            **postprocess_kwargs,
        )
        instance = result_dict.get(0, {}).get("instance", [])
        # postprocess_feature 内部算过 groups 但没有放进 result_dict，这里用同一个
        # public 方法对 instance 重新分组，不改动 postprocess_feature 本身。
        groups = result_dict.get(0, {}).get("groups")
        if groups is None:
            groups = aag_net.group_connected_faces(instance, adj_true)

        result["instance"] = instance
        result["groups"] = groups
    except Exception as e:
        result["error"] = f"{e}\n{traceback.format_exc()}"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
