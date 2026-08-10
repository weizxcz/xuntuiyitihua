#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""加载标签 + 生成边训练数据（featurefox-NCTI 版）。

与 featurefox(STEP版).instance_data 的差异：
  - 训练数据路径换 D:\\wyg\\data\\data\\steps + labels（62495 件，通槽 17799 的超集）；
  - 数据加载用 NctiPart（NCTI 导入），不再用 StepParser；
  - cell_id 即 ai.FaceID 位置索引（零映射），删除 shell_face_order；
  - build_training_sample 的 edges fa/fb 已是 cell_id，直接对 inst 矩阵；
  - collect_dataset 加 NCTI 导入 + 面数断言（验证 shell==ai.FaceID 假设）。

边标签设计（同 STEP 版）:
    y=1: 该共享边连接的两个面属于同一个通槽实例
         （两面的 cell_id 都在 seg=9 集合中，且 inst[i][j]=1）
    y=0: 其他所有边（非通槽边、通槽边界边、不同通槽间的边）

预测时: 边分类器预测 P(该边在通槽内部) → 保留高概率边 → 连通分量 = 通槽实例。
"""

import json
import os
import sys

UTILS_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if UTILS_DIR not in sys.path:
    sys.path.insert(0, UTILS_DIR)

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from ncti_backend import load_part, count_advanced_faces  # noqa: E402

STEPS_DIR = os.environ.get("FEATUREFOX_STEPS_DIR", r"D:\wyg\data\data\steps")
LABELS_DIR = r"D:\wyg\data\data\labels"


def load_label(name):
    """加载标签，返回 (seg9_set, inst_matrix, n_faces)。"""
    json_path = os.path.join(LABELS_DIR, name + ".json")
    if not os.path.exists(json_path):
        return None, None, 0
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        seg = data.get("seg", {})
        inst = data.get("inst", None)
    elif isinstance(data, list) and len(data) >= 1:
        inner = data[0][1] if isinstance(data[0], list) else data[0]
        seg = inner.get("seg", {})
        inst = inner.get("inst", None)
    else:
        return None, None, 0

    seg9 = {int(k) for k, v in seg.items() if v == 9}
    return seg9, inst, len(inst) if inst else 0


def list_step_files(limit=0, offset=0):
    """列出 STEP 文件（按名排序）。limit=0 表示全部，offset 跳过前 offset 个。"""
    files = sorted(f for f in os.listdir(STEPS_DIR) if f.endswith(".step"))
    if offset > 0:
        files = files[offset:]
    return files[:limit] if limit > 0 else files


def build_training_sample(edges, seg9, inst_matrix):
    """为一个零件的所有边生成 (X, y)。

    edges 的 fa/fb 已是 cell_id（ai.FaceID 位置索引），直接对 inst 矩阵。

    返回:
        X: list[list[float]]，每行是一条边的特征向量
        y: list[int]，0/1 标签
        meta: list[dict]，每条边的元信息 {fa, fb, key}（fa/fb 为 cell_id）
    """
    if inst_matrix is None or seg9 is None:
        return [], [], []

    X, y, meta = [], [], []
    for e in edges:
        ca, cb = e["fa"], e["fb"]  # 已是 cell_id
        # y=1: 两面都在 seg=9 且属于同一实例（inst[ca][cb]=1）
        in_seg9 = (ca in seg9) and (cb in seg9)
        same_inst = False
        if ca < len(inst_matrix) and cb < len(inst_matrix[0]):
            same_inst = (inst_matrix[ca][cb] == 1) or (inst_matrix[cb][ca] == 1)
        label = 1 if (in_seg9 and same_inst) else 0

        X.append(e["features"])
        y.append(label)
        meta.append({"fa": ca, "fb": cb, "key": e["key"]})

    return X, y, meta


def collect_dataset(step_files, ncti, build_face_graph_fn, verbose=True):
    """收集多个文件的边训练数据（子进程隔离版）。

    NCTI 批量 50-100 件 C++ 累积 segfault（约定A/B 都崩）。解法：每 40 件 subprocess
    独立 python 进程（_chunk_worker），进程退出彻底释放 NCTI。主进程合并 pickle 结果。

    参数 ncti 仅用于主进程提前验证 NCTI 可用（子进程各自 init）。
    build_face_graph_fn 保留兼容签名（子进程内各自 import build_face_graph）。
    """
    import subprocess
    import pickle
    CHUNK = 40
    chunks = [(i, min(i + CHUNK, len(step_files))) for i in range(0, len(step_files), CHUNK)]
    ts_dir = os.path.dirname(_THIS_DIR)
    nextcid_path = os.path.join(_THIS_DIR, "_train_nextcid.txt")

    # 断点续传：加载已完成 chunk（_done_*.pkl）+ 起始 chunk（_train_nextcid.txt）
    all_X, all_y, all_meta = [], [], []
    start_cid = 0
    if os.path.exists(nextcid_path):
        try:
            with open(nextcid_path, "r") as f:
                start_cid = int(f.read().strip())
            for cid in range(start_cid):
                done = os.path.join(_THIS_DIR, "_done_{}.pkl".format(cid))
                if os.path.exists(done):
                    with open(done, "rb") as f:
                        X, y, meta = pickle.load(f)
                    all_X.extend(X)
                    all_y.extend(y)
                    all_meta.extend(meta)
            if verbose:
                print("  断点续传: 从 chunk {} 恢复 (已累计 {} 边样本)".format(
                    start_cid + 1, len(all_X)), flush=True)
        except Exception:
            all_X, all_y, all_meta = [], [], []
            start_cid = 0

    for cid in range(start_cid, len(chunks)):
        start, end = chunks[cid]
        pkl = os.path.join(_THIS_DIR, "_chunk_{}.pkl".format(cid))
        env = {**os.environ, "PYTHONPATH": ts_dir, "PYTHONIOENCODING": "utf-8"}
        # 不 check：worker exit 127（NCTI 析构正常）/ 139（崩件 segfault）都非0；
        # 主进程只看 pkl 是否存在（worker 增量 pickle 保证崩件前数据保留）
        subprocess.run(
            [sys.executable, "-m", "featurefox_ncti._chunk_worker",
             str(start), str(end), pkl],
            env=env)
        if os.path.exists(pkl):
            with open(pkl, "rb") as f:
                X, y, meta = pickle.load(f)
            all_X.extend(X)
            all_y.extend(y)
            all_meta.extend(meta)
            # 改名保留（断点续传用），全部完成后统一清理
            try:
                os.replace(pkl, os.path.join(_THIS_DIR, "_done_{}.pkl".format(cid)))
            except Exception:
                pass
        if verbose:
            print("  chunk {}/{} [{}:{}] (累计 {} 边样本)".format(
                cid + 1, len(chunks), start, end, len(all_X)), flush=True)
        # 原子写 nextcid（崩了下次从这恢复）
        try:
            tmp = nextcid_path + ".tmp"
            with open(tmp, "w") as f:
                f.write(str(cid + 1))
            os.replace(tmp, nextcid_path)
        except Exception:
            pass

    # 全部完成，清理续传文件
    for fn in os.listdir(_THIS_DIR):
        if fn.startswith("_done_") and fn.endswith(".pkl"):
            try:
                os.remove(os.path.join(_THIS_DIR, fn))
            except Exception:
                pass
    if os.path.exists(nextcid_path):
        try:
            os.remove(nextcid_path)
        except Exception:
            pass

    if verbose:
        print("  完成: {} 边样本".format(len(all_X)))
    return all_X, all_y, all_meta
