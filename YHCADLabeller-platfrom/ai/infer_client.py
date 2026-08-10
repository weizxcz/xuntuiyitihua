"""主进程侧的推理子进程调用工具。

本模块只用标准库，不 import torch/dgl，因此可以在缺少 dgl 的主进程环境中安全导入。
真正的模型前向计算在 `ai/infer_worker.py` 里，由 `YHCAD_ENV_PYTHON` 指定的解释器
（装了 dgl/torch 的 conda 环境）以子进程方式执行。
"""

import json
import os
import subprocess
import sys
import tempfile

YHCAD_ENV_PYTHON = os.environ.get("YHCAD_AI_PYTHON", sys.executable)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_inference_subprocess(weight_path, stat_path, face_id, face_f_id, face_e_id,
                              face_points, face_normals, face_mask,
                              graph_edge_attr, graph_face_attr, adj_true,
                              min_faces_num=0, max_faces_num=9, feature_name="ai_feature",
                              python_exe=None, timeout=120):
    """把几何数据交给子进程做模型推理，返回 (instance, groups)。

    instance: 检测到的面 id 列表
    groups: 按连通性分好组的面 id 列表的列表
    """
    python_exe = python_exe or YHCAD_ENV_PYTHON
    if not os.path.exists(python_exe):
        raise RuntimeError(f"未找到推理环境 python: {python_exe}")

    payload = {
        "weight_path": weight_path,
        "stat_path": stat_path,
        "face_id": face_id,
        "face_f_id": face_f_id,
        "face_e_id": face_e_id,
        "face_points": face_points,
        "face_normals": face_normals,
        "face_mask": face_mask,
        "graph_edge_attr": graph_edge_attr,
        "graph_face_attr": graph_face_attr,
        "adj_true": adj_true,
        "min_faces_num": min_faces_num,
        "max_faces_num": max_faces_num,
        "feature_name": feature_name,
    }

    in_fd, in_path = tempfile.mkstemp(suffix=".json", prefix="ai_infer_in_")
    out_fd, out_path = tempfile.mkstemp(suffix=".json", prefix="ai_infer_out_")
    os.close(in_fd)
    os.close(out_fd)
    try:
        with open(in_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        proc = subprocess.run(
            [python_exe, "-m", "ai.infer_worker", in_path, out_path],
            cwd=_PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            stderr_tail = (proc.stderr or "").strip()[-2000:]
            raise RuntimeError(f"推理子进程失败(returncode={proc.returncode}): {stderr_tail}")

        with open(out_path, "r", encoding="utf-8") as f:
            result = json.load(f)
        if "error" in result:
            raise RuntimeError(f"推理失败: {result['error']}")
        return result.get("instance", []), result.get("groups", [])
    finally:
        for p in (in_path, out_path):
            try:
                os.remove(p)
            except OSError:
                pass
