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

from .ncti_backend import load_part, count_advanced_faces
from ._env import get_steps_dir, get_labels_dir

STEPS_DIR = get_steps_dir()
LABELS_DIR = get_labels_dir()

# 批量训练中间产物（chunk pickle + 断点续传指针）集中存放，避免与 .py 混放
# CHUNK_DIR 指向 featurefox/_chunks/（从 lib/ 向上到 featurefox/）
_CHUNK_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_chunks")
CHUNK_DIR = _CHUNK_DIR


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
        if isinstance(data[0], list):
            # [[name, content], ...]
            inner = data[0][1]
        elif len(data) >= 2 and isinstance(data[1], dict):
            # [name_string, content_dict]
            inner = data[1]
        else:
            inner = data[0]
        seg = inner.get("seg", {})
        inst = inner.get("inst", None)
    else:
        return None, None, 0

    seg9 = {int(k) for k, v in seg.items() if v == 12}  # 盲孔 seg=12
    return seg9, inst, len(inst) if inst else 0


def _has_seg12_in_label(name):
    """快速检查 label JSON 是否包含 seg=12 的盲孔面。"""
    json_path = os.path.join(LABELS_DIR, name + ".json")
    if not os.path.exists(json_path):
        return False
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return False
    if isinstance(data, dict):
        seg = data.get("seg", {})
    elif isinstance(data, list) and len(data) >= 1:
        inner = data[0][1] if isinstance(data[0], list) else data[0]
        seg = inner.get("seg", {}) if isinstance(inner, dict) else {}
    else:
        return False
    return any(v == 12 for v in seg.values())


def _filter_seg12_only(files):
    """只保留有盲孔 seg=12 面标注的 STEP 文件。"""
    return [f for f in files if _has_seg12_in_label(os.path.splitext(f)[0])]


def list_step_files(limit=0, offset=0, name_filter=None, seg12_only=False):
    """列出 STEP 文件（按名排序）。limit=0 表示全部，offset 跳过前 offset 个。
    name_filter: 可选 set[str], 只保留文件名(不含.step)在此集合中的文件。
    seg12_only:  只保留含有盲孔 seg=12 面标注的文件。
                 若环境变量 NCTI_SEG12_ONLY=1，自动启用（穿透到子进程）。
    """
    if os.environ.get("NCTI_SEG12_ONLY") == "1":
        seg12_only = True
    files = sorted(f for f in os.listdir(STEPS_DIR) if f.endswith(".step"))
    if seg12_only:
        files = _filter_seg12_only(files)
    if name_filter is not None:
        files = [f for f in files if os.path.splitext(f)[0] in name_filter]
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
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # featurefox 根目录（lib/ 的父目录）
    _featfox_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    CHUNK = 40
    chunks = [(i, min(i + CHUNK, len(step_files))) for i in range(0, len(step_files), CHUNK)]
    os.makedirs(CHUNK_DIR, exist_ok=True)
    # 并发数：每 worker 单核（NCTI import + 建图），受 CPU 核数限制；内存约 300MB/worker
    max_workers = int(os.environ.get("NCTI_CHUNK_WORKERS", "32"))

    # 断点续传（集合制，适配并行乱序完成）：扫描已完成 _done_*.pkl
    all_X, all_y, all_meta = [], [], []
    done_cids = set()
    for fn in os.listdir(CHUNK_DIR):
        if fn.startswith("_done_") and fn.endswith(".pkl"):
            try:
                done_cids.add(int(fn[len("_done_"):-len(".pkl")]))
            except ValueError:
                pass
    for cid in sorted(done_cids):
        done = os.path.join(CHUNK_DIR, "_done_{}.pkl".format(cid))
        if os.path.exists(done):
            with open(done, "rb") as f:
                X, y, meta = pickle.load(f)
            all_X.extend(X)
            all_y.extend(y)
            all_meta.extend(meta)
    if verbose:
        print("  断点续传: 已完成 {}/{} chunks (累计 {} 边样本)".format(
            len(done_cids & set(range(len(chunks)))), len(chunks), len(all_X)), flush=True)

    # 待跑 chunks（已完成的跳过）
    todo = [cid for cid in range(len(chunks)) if cid not in done_cids]
    if verbose:
        print("  并行收集: {} 待跑 chunks, {} 并发".format(len(todo), max_workers), flush=True)

    def run_chunk(cid):
        start, end = chunks[cid]
        pkl = os.path.join(CHUNK_DIR, "_chunk_{}.pkl".format(cid))
        env = {**os.environ, "PYTHONPATH": _featfox_root, "PYTHONIOENCODING": "utf-8"}
        # 不 check：worker exit 127（NCTI 析构正常）/ 139（崩件 segfault）都非0；
        # 主进程只看 pkl 是否存在（worker 增量 pickle 保证崩件前数据保留）
        subprocess.run(
            [sys.executable, "-m", "featurefox.workers._chunk_worker",
             str(start), str(end), pkl],
            env=env)
        done = os.path.join(CHUNK_DIR, "_done_{}.pkl".format(cid))
        if os.path.exists(pkl):
            try:
                os.replace(pkl, done)
            except Exception:
                pass
        return cid if os.path.exists(done) else None

    # ThreadPool 调 subprocess：线程只等子进程，CPU 全在 worker 子进程
    finished = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(run_chunk, cid): cid for cid in todo}
        for fut in as_completed(futures):
            ok = fut.result()
            finished += 1
            if verbose and (finished % 20 == 0 or finished == len(todo)):
                print("  进度 {}/{} (本批 {} | 总完成 chunk {}/{})".format(
                    finished, len(todo), "OK" if ok else "SKIP",
                    len(done_cids) + finished, len(chunks)), flush=True)

    # 合并本批新完成的 _done_*.pkl
    for cid in todo:
        done = os.path.join(CHUNK_DIR, "_done_{}.pkl".format(cid))
        if os.path.exists(done):
            with open(done, "rb") as f:
                X, y, meta = pickle.load(f)
            all_X.extend(X)
            all_y.extend(y)
            all_meta.extend(meta)

    # 全部完成，清理续传文件
    for fn in list(os.listdir(CHUNK_DIR)):
        if fn.startswith("_done_") and fn.endswith(".pkl"):
            try:
                os.remove(os.path.join(CHUNK_DIR, fn))
            except Exception:
                pass
    nextcid_path = os.path.join(CHUNK_DIR, "_train_nextcid.txt")
    if os.path.exists(nextcid_path):
        try:
            os.remove(nextcid_path)
        except Exception:
            pass

    if verbose:
        print("  完成: {} 边样本".format(len(all_X)), flush=True)
    return all_X, all_y, all_meta
