#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""FeatureFox 通槽批量标注脚本 —— **零映射 NCTI 版**。

与 `annotate_through_step.py`（STEP 版，几何最近邻映射到 cell_id）的差异：
  - 识别器：featurefox_ncti（直接在 NCTI AiModel 数据上跑）
  - 输出 cell_id：**零映射**——predict 返回的 faces 列表直接是 ai.FaceID 位置索引
    （与 Geo-Rec 训练图节点下标严格对齐，不再走 build_step_face_to_ncti_pos_map）
  - 凸凹性：取自 EdgeAttr[0/1/2]（NCTI 原生离散 ±1/0），比 STEP 质心偏移法更准
  - 面积：取自 FaceAttr[5]（OCC 引擎精确积分）

流程：
  1. 获取 STEP 文件（local / http，与原版一致）
  2. load_part → NctiPart（NCTI 约定B，批量稳定）
  3. 一次性 n_faces == count_advanced_faces 一致性断言（不等则跳过+告警）
  4. predict_through_slots → 通槽实例（cell_id 列表）
  5. 构造 JSON：[[name, {"seg": {cell: 9}, "inst": NxN, "bottom": {cell: 1}}]]
     bottom 用 NCTI 真法向判定 U 槽底面

⚠ 需要 NCTI：cell_id 必须落在 NCTI FaceID 空间（与 Geo-Rec 训练建图同空间）。

约定 B（doc.New OCC,DCM,GMSH + SetCreateGeGeom(1) + SetImportAssemelFile(1)）由
featurefox_ncti.ncti_backend.load_part 内部处理。批量场景通过复用 doc 避免
NCTI C++ 对象累积 segfault（每 60-100 件新建 doc 是已知崩点）。

⚠ cell_id 对齐前提：约定 B 下 NCTI 可能合并/拆分共面，cell_id 位置索引可能不
严格等于 shell ADVANCED_FACE 顺序。一致性断言捕获多数破裂情形，但极端情况
仍可能错位（与 STEP 版几何最近邻映射同阶误差量级）。
"""

# ============================================================
#  配置区 —— 只改这一段就行
# ============================================================

# FeatureFox-NCTI 代码 + 模型所在目录（YHCADSmartCleaner 仓库里的 utils/through_step）
# 服务器部署时，把这个目录（含 featurefox_ncti/ 子目录、edge_clf.json、calibrator.pkl、
# inst_clf.json、inst_calibrator.pkl、featurefox/、geom_helpers.py、
# 以及 ../detect_blind_holes_and_export_stp_v15_22.py）一起拷过去，再指向它。
FEATUREFOX_ROOT = r"D:/wyg/xuntuiyitihua/YHCADSmartCleaner/utils/through_step"

# ── 输入模式 ──
INPUT_MODE = "local"   # "local"=读本地目录；"http"=从后端 API 下载

# [local 模式] STEP 输入目录（服务器上 STEP 的存放位置）
INPUT_STEP_DIR = r"D:/wyg/data/data/通槽/steps"

# [http 模式] 后端 API
API_BASE_URL = "http://172.16.36.154:5060/api"
# [http 模式] 要下载的 part_id 列表（逗号分隔）；为空则调 list_parts 拉全部
PART_IDS = ""           # 例: "123,456,789" ；留空 = 全部零件
LIST_PAGE_SIZE = 200    # PART_IDS 为空时分页拉取的每页数量

# [http 模式] STEP 下载到的本地临时目录
DOWNLOAD_DIR = r"D:/wyg/xuntuiyitihua/Geo-Data-Management/Split_Assembly_and_Detect_blind_hole/through_step/_download"

# 输出目录（STEP + JSON 都写到这）
OUTPUT_DIR = r"D:/wyg/xuntuiyitihua/Geo-Data-Management/Split_Assembly_and_Detect_blind_hole/through_step/_out"

# 通槽 seg 值（与训练标签一致；盲孔用 12，通槽用 9）
CATEGORY_ID = 9

# 底面标注（True=用启发式标 bottom；False=bottom 全留 0）
ANNOTATE_BOTTOM = True

# 处理上限（0=全部；调试先用小数，如 5）
MAX_FILES = 0

# 无通槽的文件是否也输出 JSON（全 0 seg）+ 拷贝 STEP
WRITE_EMPTY = False   # False=未检测到通槽则不输出（默认）

# 单文件解析超时（秒）。>0 时启用：每文件在独立工作进程里跑，超时则杀进程跳过
# （防过大 STEP 卡死 NCTI import_file）。=0 关闭，走主进程串行（无超时保护）。
TIMEOUT_SECONDS = 30

# ── 识别阈值（与 featurefox_ncti.predict 默认一致）──
EDGE_THRESHOLD = 0.35     # 第一级边剪枝阈值
INST_THRESHOLD = 0.80     # 第二级实例分类器拒绝阈值（< 该值判非通槽）
USE_INSTANCE_FILTER = True   # 启用第二级；模型缺失自动降级

# ── NCTI（必需）──
# 复用本项目 config.config_load 初始化 NCTI（约定B范式由 load_part 内部处理）。
# 配置方式二选一：
#   (a) 在 config/ncti_config.json 写 SDK 路径（复制 ncti_config.server.json 改）
#   (b) 设环境变量 NCTI_DLLPATH 指向含 ncti_python 与 NCTI 动态库的目录
NCTI_OBJ_NAME = "testbox"   # 导入对象名（与 real_data_generate_labels.py / featurefox_ncti 一致）

# ============================================================

import os
import sys
import json
import shutil
import io
import multiprocessing

# 把 FeatureFox-NCTI 及其依赖目录加入 sys.path
UTILS_DIR = os.path.dirname(FEATUREFOX_ROOT)  # .../utils（StepParser、detect_through_step 在此）
for _p in (FEATUREFOX_ROOT, UTILS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# 本项目根（Split_Assembly_and_Detect_blind_hole），用于 import config.config_load 初始化 NCTI
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Windows 控制台中文输出
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

try:
    from featurefox_ncti.predict import (
        predict_through_slots, load_models, load_instance_models, DEFAULT_THRESHOLD, INST_THRESHOLD)
    from featurefox_ncti.ncti_backend import NctiPart, load_part, count_advanced_faces
except Exception as _e:
    sys.stderr.write(
        "FeatureFox-NCTI 导入失败，请检查 FEATUREFOX_ROOT 是否指向正确的目录。\n"
        "  FEATUREFOX_ROOT = {}\n  错误: {}\n".format(FEATUREFOX_ROOT, _e))
    raise


# ============================================================
#  底面标注 —— U 型槽里"非平行的那个面"= 底面
#  用 NCTI 真法向（FaceNormals[i][2][2]，来自 GetNormalByUV(0.5, 0.5)）
# ============================================================

def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def find_bottom_cell(part, fa_attrs, cell_ids):
    """从实例的 cell 集合里找底面 cell：U 型槽里"非平行的那个面"= 底面。

    3 面 U 槽：两壁平行（法向接近平行/反平行），底面法向与两壁都近垂直。
    启发式：取实例内 PLANE 面，找两两 |cos| 最大的那对（壁），剩下的就是底面。
    多面/无法判定时返回 None。

    注：NCTI 真法向通过 fa_attrs.normal(cell) 取得（内部调 GetNormalByUV(0.5, 0.5)），
       对 PLANE 恒定、对 CYL 径向，PLANE 上准确。
    """
    normals = {}
    for c in cell_ids:
        if fa_attrs.ftype(c) != "PLANE":
            continue
        n = fa_attrs.normal(c)
        if n is not None:
            normals[c] = n
    if len(normals) < 3:
        return None
    cells = list(normals.keys())
    # 找最平行的一对（|cos| 最大）= 两壁
    best = None
    best_abs = -1.0
    for i in range(len(cells)):
        for j in range(i + 1, len(cells)):
            ni, nj = normals[cells[i]], normals[cells[j]]
            d = abs(_dot(ni, nj))
            if d > best_abs:
                best_abs = d
                best = (cells[i], cells[j])
    if best is None:
        return None
    # 剩下的面里，与这对最不平行（|cos| 最小）的当底面
    others = [c for c in cells if c not in best]
    if not others:
        return None
    bottom_cell = min(others, key=lambda c: (abs(_dot(normals[c], normals[best[0]]))
                                              + abs(_dot(normals[c], normals[best[1]]))) / 2.0)
    return bottom_cell


# ============================================================
#  NCTI 初始化（用本项目 config_load）
# ============================================================

def init_ncti_safe():
    """用本项目的 config.config_load 初始化 NCTI。失败返回 None。"""
    try:
        from config.config_load import init_ncti_config  # type: ignore
        return init_ncti_config()
    except Exception as e:
        sys.stderr.write("config.config_load 不可用: {}\n".format(e))
        return None


def annotate_one(stp_path, booster, calib, inst_booster, inst_calib, ncti, obj_name, shared_doc=None):
    """识别一个 STEP，返回 (label_json, slot_cell_groups)。

    零映射：cell_id = ai.FaceID 位置索引（与 Geo-Rec 训练建图同空间）。
    shared_doc 提供时复用（批量场景），None 时新建。
    """
    # 1. NCTI 导入（约定B：load_part 内部处理 SetCreateGeGeom 等）
    part, doc = load_part(stp_path, ncti, obj_name=obj_name, doc=shared_doc)

    # 2. 一致性断言：NCTI n_faces == STEP ADVANCED_FACE 数
    #    不等则 cell_id 零映射假设破裂，跳过+告警
    n_step_adv = count_advanced_faces(stp_path)
    if part.n_faces != n_step_adv:
        sys.stderr.write(
            "  WARN: {} NCTI n_faces={} != STEP ADVANCED_FACE={}, "
            "cell_id 对齐假设可能破裂，跳过\n".format(
                os.path.basename(stp_path), part.n_faces, n_step_adv))
        if shared_doc is None:
            try:
                doc.Clear()
            except Exception:
                pass
        return None, None

    # 3. predict（零映射：返回的 faces 即 cell_id）
    instances = predict_through_slots(
        stp_path, booster, calib, ncti=ncti, part=part,
        threshold=EDGE_THRESHOLD,
        inst_booster=inst_booster, inst_calibrator=inst_calib,
        inst_threshold=INST_THRESHOLD)

    if not instances:
        if shared_doc is None:
            try:
                doc.Clear()
            except Exception:
                pass
        # 无通槽仍输出空标签（callers 决定要不要写入）
        return None, []

    # 4. 构造 JSON（cell_id 空间，与 Geo-Rec 训练标签一致）
    n_faces = part.n_faces
    seg = {str(i): 0 for i in range(n_faces)}
    bottom = {str(i): 0 for i in range(n_faces)}
    inst = [[0] * n_faces for _ in range(n_faces)]

    # fa_attrs 缓存包装（normal/ftype 复用）
    from featurefox_ncti.ncti_backend import NctiFaceAttrs
    fa_attrs = NctiFaceAttrs(part)

    slot_cell_groups = []
    for one in instances:
        cells = sorted(set(one["faces"]))   # zero-mapping: predict 直接给 cell_id
        if not cells:
            continue
        slot_cell_groups.append(cells)
        for c in cells:
            seg[str(c)] = CATEGORY_ID
        for a in cells:
            for b in cells:
                inst[a][b] = 1
        # 底面标注（直接用 cell_id，无需映射）
        if ANNOTATE_BOTTOM:
            bcell = find_bottom_cell(part, fa_attrs, cells)
            if bcell is not None:
                bottom[str(bcell)] = 1

    name = os.path.splitext(os.path.basename(stp_path))[0]
    label_json = [[name, {"seg": seg, "inst": inst, "bottom": bottom}]]

    if shared_doc is None:
        try:
            doc.Clear()
        except Exception:
            pass

    return label_json, slot_cell_groups


def iter_step_files(d):
    for f in sorted(os.listdir(d)):
        if f.lower().endswith((".step", ".stp")):
            yield os.path.join(d, f)


# ---------------- HTTP 下载模式（与 STEP 版完全一致）----------------

def _post_json(base_url, path, payload, timeout=60):
    """极简 POST JSON，仅依赖标准库 urllib。"""
    import urllib.request
    import urllib.error
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        "{}{}".format(base_url.rstrip("/"), path),
        data=body, headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def download_step_files(base_url, part_ids_csv, page_size, download_dir):
    """按 part_id 列表下载 STEP；part_ids_csv 为空则 list_parts 拉全部。返回下载后的本地路径列表。"""
    os.makedirs(download_dir, exist_ok=True)
    out = []

    def _one(part_id, meta=None):
        try:
            path = _download_one(base_url, part_id, download_dir)
            out.append(path)
            print("  下载 part_id={} -> {}".format(part_id, os.path.basename(path)), flush=True)
        except Exception as e:
            print("  下载失败 part_id={}: {}".format(part_id, e), flush=True)

    if part_ids_csv.strip():
        for pid in [x.strip() for x in part_ids_csv.split(",") if x.strip()]:
            _one(pid)
    else:
        skip, fetched = 0, 0
        while True:
            rows = _post_json(base_url, "/parts/list_parts",
                              {"skip": skip, "limit": page_size})["data"]
            if not rows:
                break
            for meta in rows:
                pid = meta.get("id")
                if pid is None:
                    continue
                _one(pid, meta)
                fetched += 1
                if MAX_FILES and fetched >= MAX_FILES:
                    return out
            if len(rows) < page_size:
                break
            skip += page_size
    return out


def _download_one(base_url, part_id, download_dir):
    import urllib.request
    body = json.dumps({"part_id": part_id}).encode("utf-8")
    req = urllib.request.Request(
        "{}{}".format(base_url.rstrip("/"), "/label/send_solid_file"),
        data=body, headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    with urllib.request.urlopen(req, timeout=180) as resp:
        cd = resp.headers.get("Content-Disposition") or ""
        fname = None
        if "filename*=UTF-8''" in cd:
            from urllib.parse import unquote
            fname = unquote(cd.split("filename*=UTF-8''", 1)[1].strip())
        elif "filename=" in cd:
            fname = cd.split("filename=", 1)[1].strip().strip('"')
        if not fname:
            fname = "{}.stp".format(part_id)
        path = os.path.join(download_dir, fname)
        with open(path, "wb") as fh:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
    return path


# ---------------- 超时机制：独立工作进程标注单文件 ----------------
# 为什么用进程而非线程/信号：NCTI 的 cmd_ncti_import_file 是单次 C 调用，
# 过大 STEP 会让它阻塞数分钟；signal.alarm 无法打断阻塞中的 C 调用，
# 线程也无法强杀。只有独立进程能被 OS 强杀，从而真正执行 30s 硬超时。
# Pool(1) 单工作进程=仍串行；超时则 terminate 重建（仅超时文件付重初始化开销）。

_WORKER = {}   # 工作进程内共享：模型 + NCTI


def _worker_init():
    """工作进程初始化（每进程一次）：加载模型 + 初始化 NCTI。"""
    _WORKER["booster"], _WORKER["calib"] = load_models()
    _WORKER["inst_booster"], _WORKER["inst_calib"] = load_instance_models()
    ncti = init_ncti_safe()
    if ncti is None:
        raise RuntimeError("NCTI 初始化失败（检查 config/ncti_config.json 或 NCTI_DLLPATH）")
    _WORKER["ncti"] = ncti


def _worker_annotate(stp_path):
    """工作进程：标注单文件。返回 (status, label_json, groups, err)。"""
    try:
        label_json, groups = annotate_one(
            stp_path, _WORKER["booster"], _WORKER["calib"],
            _WORKER["inst_booster"], _WORKER["inst_calib"],
            _WORKER["ncti"], NCTI_OBJ_NAME)
        return ("ok", label_json, groups, None)
    except Exception as e:
        return ("fail", None, None, str(e))


def main():
    print("FeatureFox 通槽批量标注（**NCTI 零映射版**）")
    print("  FEATUREFOX_ROOT    = {}".format(FEATUREFOX_ROOT))
    print("  输入模式           = {}".format(INPUT_MODE))
    print("  输出目录           = {}".format(OUTPUT_DIR))
    print("  seg(通槽)          = {}   底面标注={}".format(CATEGORY_ID, ANNOTATE_BOTTOM), flush=True)
    print("  第一级阈值         = {}   第二级阈值={}   启用={}".format(
        EDGE_THRESHOLD, INST_THRESHOLD, USE_INSTANCE_FILTER), flush=True)

    use_pool = bool(TIMEOUT_SECONDS and TIMEOUT_SECONDS > 0)
    if use_pool:
        print("  超时保护           = 每文件 {}s 超时杀进程跳过".format(TIMEOUT_SECONDS), flush=True)
    else:
        print("  超时保护           = 关闭（主进程串行）", flush=True)
    print("  无通槽文件         = {}".format("输出空JSON" if WRITE_EMPTY else "跳过不输出"), flush=True)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 取 STEP 文件列表
    if INPUT_MODE == "http":
        print("  API                = {}".format(API_BASE_URL))
        files = download_step_files(API_BASE_URL, PART_IDS, LIST_PAGE_SIZE, DOWNLOAD_DIR)
    elif INPUT_MODE == "local":
        if not os.path.isdir(INPUT_STEP_DIR):
            sys.exit("输入目录不存在: {}".format(INPUT_STEP_DIR))
        print("  输入目录           = {}".format(INPUT_STEP_DIR))
        files = list(iter_step_files(INPUT_STEP_DIR))
    else:
        sys.exit("未知 INPUT_MODE: {}（应为 local / http）".format(INPUT_MODE))

    if MAX_FILES:
        files = files[:MAX_FILES]
    print("  待处理             = {} 个 STEP\n".format(len(files)), flush=True)

    # 加载模型 + NCTI：超时模式在工作进程加载（_worker_init），否则主进程加载
    pool = None
    booster = calib = inst_booster = inst_calib = ncti = None
    if use_pool:
        pool = multiprocessing.Pool(1, initializer=_worker_init)
        print("  工作进程           = 已启动（模型+NCTI 已在子进程加载）", flush=True)
    else:
        booster, calib = load_models()
        if USE_INSTANCE_FILTER:
            inst_booster, inst_calib = load_instance_models()
            print("  实例分类器         = {}".format("已加载" if inst_booster is not None else "未找到（仅第一级）"),
                  flush=True)
        ncti = init_ncti_safe()
        if ncti is None:
            sys.exit("NCTI 初始化失败：标注必须走 NCTI FaceID 空间以对齐训练图。"
                     "请在 config/ncti_config.json 配置 SDK 路径（见 ncti_config.server.json），"
                     "或设环境变量 NCTI_DLLPATH。")
        print("  NCTI               = 已初始化（对象名 {}）".format(NCTI_OBJ_NAME), flush=True)

    n_ok = n_empty = n_fail = n_timeout = n_misalign = 0
    for idx, stp in enumerate(files, 1):
        name = os.path.basename(stp)

        if use_pool:
            res = pool.apply_async(_worker_annotate, (stp,))
            try:
                status, label_json, groups, err = res.get(timeout=TIMEOUT_SECONDS)
            except multiprocessing.TimeoutError:
                n_timeout += 1
                print("[{}/{}] TIMEOUT {} (>{:.0f}s，杀进程跳过)".format(
                    idx, len(files), name, TIMEOUT_SECONDS), flush=True)
                pool.terminate(); pool.join()
                pool = multiprocessing.Pool(1, initializer=_worker_init)   # 重建工作进程
                continue
            except Exception as e:
                sys.exit("工作进程异常退出（多为 NCTI/模型初始化失败）: {}".format(e))
            if status != "ok":
                n_fail += 1
                print("[{}/{}] FAIL    {} : {}".format(idx, len(files), name, err), flush=True)
                continue
        else:
            try:
                label_json, groups = annotate_one(
                    stp, booster, calib, inst_booster, inst_calib, ncti, NCTI_OBJ_NAME)
            except Exception as e:
                n_fail += 1
                print("[{}/{}] FAIL    {} : {}".format(idx, len(files), name, e), flush=True)
                continue

        out_json = os.path.join(OUTPUT_DIR, os.path.splitext(name)[0] + ".json")
        out_stp = os.path.join(OUTPUT_DIR, name)

        if label_json is None:
            # 一致性断言失败（cell_id 对齐破裂）
            n_misalign += 1
            print("[{}/{}] MISALIGN {} (cell_id 对齐破裂，未输出)".format(
                idx, len(files), name), flush=True)
            continue

        if groups or WRITE_EMPTY:
            with open(out_json, "w", encoding="utf-8") as fh:
                json.dump(label_json, fh, ensure_ascii=False, indent=2)
            if os.path.abspath(stp) != os.path.abspath(out_stp):
                shutil.copy2(stp, out_stp)

        if groups:
            n_ok += 1
            print("[{}/{}] OK    {} ({} 个通槽: {})".format(
                idx, len(files), name, len(groups), groups), flush=True)
        else:
            n_empty += 1
            tag = "已输出空 JSON" if WRITE_EMPTY else "跳过"
            print("[{}/{}] EMPTY {} (无通槽, {})".format(idx, len(files), name, tag), flush=True)

    if pool is not None:
        pool.close(); pool.join()

    print("\n完成: 有通槽={}  无通槽={}  超时={}  失败={}  对齐破裂={}".format(
        n_ok, n_empty, n_timeout, n_fail, n_misalign), flush=True)
    print("输出目录: {}".format(OUTPUT_DIR), flush=True)
    # NCTI DLL 析构可能 segfault，直接退出（与 through_step NCTI 测试脚本同惯例）
    os._exit(0)


if __name__ == "__main__":
    main()