#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""FeatureFox 通槽批量标注脚本（无数据库 / 无 NCTI）。

模仿 Split_Assembly_and_Detect_blind_hole/blind_hole/pipeline_core.py 的标注逻辑，
识别器换成 FeatureFox（数据驱动），并去掉所有 API 上传 / 数据库回写操作。

流程：
  1. 获取 STEP 文件（两种模式，见 INPUT_MODE）：
     - "local"  : 读本地目录 INPUT_STEP_DIR 的所有 STEP
     - "http"   : 从后端 API 按 part_id 列表下载 STEP 到 DOWNLOAD_DIR
  2. FeatureFox 两级识别（边分类器 0.35 + 实例分类器 0.80）→ 通槽实例（STEP face_id）
  3. 把同一份 STEP 导入 NCTI（与 Geo-Rec 训练建图完全一致），cell_id = 面在 ai.FaceID
     中的位置索引；STEP face_id ↔ NCTI 面用几何最近邻（重心↔中点）匹配。
     —— 装配体拆分后 NCTI 合并/拆分面致面数变化时，标签 cell_id 仍与训练图节点严格对齐。
  4. 构造训练标签 JSON：[[name, {"seg":{cell:9}, "inst":NxN, "bottom":{}}]]
     bottom 用底面启发式标注：3 面槽中"非平行那个面"= 底面
  5. STEP 文件 + JSON 一起写到输出目录

⚠ 需要 NCTI：cell_id 必须落在 NCTI FaceID 空间（否则与 Geo-Rec 训练图错位）。
   在 config/ncti_config.json 配置 SDK 路径（复制 ncti_config.server.json 改），
   或设环境变量 NCTI_DLLPATH。

JSON 格式与 Geo-Rec 标签一致（real_data_generate_labels.py / step2graph_mfr_ncti.py
读的就是 data[0][1]["seg"]/["inst"]/["bottom"]，cell_id 直接当 feature_labels 下标）。
seg=9 = 通槽面；inst 矩阵把同一通槽的面互连；bottom 标底面。
"""

# ============================================================
#  配置区 —— 只改这一段就行
# ============================================================

# FeatureFox 代码 + 模型所在目录（YHCADSmartCleaner 仓库里的 utils/through_step）
# 服务器部署时，把这个目录（含 featurefox/ 子目录、edge_clf.json、calibrator.pkl、
# inst_clf.json、inst_calibrator.pkl、detect_through_step.py、geom_helpers.py、
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

# ── NCTI（必需）──
# cell_id 走 NCTI FaceID 空间以对齐 Geo-Rec 训练图。配置方式二选一：
#   (a) 在 config/ncti_config.json 写 SDK 路径（复制 ncti_config.server.json 改）
#   (b) 设环境变量 NCTI_DLLPATH 指向含 ncti_python 与 NCTI 动态库的目录
NCTI_OBJ_NAME = "testbox"   # 导入对象名（与 real_data_generate_labels.py 一致）

# ============================================================

import os
import sys
import json
import shutil
import io
import multiprocessing

# 把 FeatureFox 及其依赖目录加入 sys.path（插在最前，优先于脚本自身目录）
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
    from detect_blind_holes_and_export_stp_v15_22 import StepParser
    from featurefox.predict import predict_through_slots, load_models, load_instance_models
    from featurefox.edge_features import build_face_graph
except Exception as _e:
    sys.stderr.write(
        "FeatureFox 导入失败，请检查 FEATUREFOX_ROOT 是否指向正确的目录。\n"
        "  FEATUREFOX_ROOT = {}\n  错误: {}\n".format(FEATUREFOX_ROOT, _e))
    raise

# canonical NCTI 对齐映射（位置索引语义，DEBUG 验证；FEATUREFOX_ROOT 已在 sys.path）
from ncti_faceid_map import build_step_face_to_ncti_pos_map  # noqa: E402


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def find_bottom_cell(parser, fa_attrs, face_ids):
    """从实例的面集合里找底面 cell：U 型槽里"非平行的那个面"= 底面。

    3 面 U 槽：两壁平行（法向接近平行/反平行），底面法向与两壁都近垂直。
    启发式：取实例内平面法向，找两两 |cos| 最大的那对（壁），剩下的就是底面。
    多面/无法判定时返回 None。
    """
    normals = {}
    for fid in face_ids:
        if parser.face_surface_type(fid) != "PLANE":
            continue
        n = fa_attrs.normal(fid)
        if n is not None:
            normals[fid] = n
    if len(normals) < 3:
        return None
    fids = list(normals.keys())
    # 找最平行的一对（|cos| 最大）
    best = None
    best_abs = -1.0
    for i in range(len(fids)):
        for j in range(i + 1, len(fids)):
            ni, nj = normals[fids[i]], normals[fids[j]]
            d = abs(_dot(ni, nj))
            if d > best_abs:
                best_abs = d
                best = (fids[i], fids[j])
    if best is None:
        return None
    # 剩下的面里，与这对最不平行（|cos| 最小）的当底面
    others = [f for f in fids if f not in best]
    if not others:
        return None
    bottom_fid = min(others, key=lambda f: (abs(_dot(normals[f], normals[best[0]]))
                                            + abs(_dot(normals[f], normals[best[1]]))) / 2.0)
    return bottom_fid


# ---------------- NCTI FaceID 空间映射（与 Geo-Rec 训练建图同源）----------------

def init_ncti_safe():
    """用本项目的 config.config_load 初始化 NCTI。失败返回 None。"""
    try:
        from config.config_load import init_ncti_config  # type: ignore
        return init_ncti_config()
    except Exception as e:
        sys.stderr.write("config.config_load 不可用: {}\n".format(e))
        return None


def import_step_to_ncti(ncti, stp_path, obj_name):
    """把 STEP 导入 NCTI（与训练建图完全一致：real_data_generate_labels / step2graph_mfr_ncti）。
    返回 (doc, ai)；调用方负责 doc.Clear()。"""
    doc = ncti.Document()
    doc.New("OCC", "DCM", 0)
    ok = doc.RunCommand("cmd_ncti_import_file", str(stp_path), obj_name)
    if not ok:
        raise RuntimeError("NCTI 导入失败: {}".format(stp_path))
    ai = ncti.AiModel(doc, obj_name)
    return doc, ai


def build_step_to_ncti_pos_map(parser, fa_attrs, doc, ncti, obj_name, tol=None):
    """STEP face_id → ai.FaceID 位置索引（= Geo-Rec 标签 cell_id 空间）。

    委托 canonical ncti_faceid_map.build_step_face_to_ncti_pos_map（位置索引语义，
    DEBUG 验证）。旧实现把 entity ID 传给 GetFaceMidPoint，当 entity ID≠位置序号
    （NCTI 合并面后常见）时会取错面中点 → 标签错位；现统一走 canonical 修正。
    """
    step_centroids = {}
    for fid in parser.advanced_faces:
        c = fa_attrs.centroid(fid)
        if c is not None:
            step_centroids[fid] = (float(c[0]), float(c[1]), float(c[2]))
    return build_step_face_to_ncti_pos_map(step_centroids, doc, ncti, obj_name, tol=tol)


def annotate_one(stp_path, booster, calib, inst_booster, inst_calib, ncti, obj_name):
    """识别一个 STEP，返回 (label_json, slot_cell_groups)。
    cell_id = NCTI ai.FaceID 位置索引（与 Geo-Rec 训练建图同空间）。"""
    parser = StepParser(stp_path)
    parser.parse()
    instances = predict_through_slots(
        stp_path, booster, calib, parser=parser,
        inst_booster=inst_booster, inst_calibrator=inst_calib)
    _, fa_attrs = build_face_graph(parser)   # 拿面属性（法向/重心），供底面判定与几何匹配

    # 导入 NCTI（与训练建图一致）→ cell_id 取 ai.FaceID 位置索引
    doc, _ai = import_step_to_ncti(ncti, stp_path, obj_name)
    try:
        pos_map, n_faces = build_step_to_ncti_pos_map(parser, fa_attrs, doc, ncti, obj_name)
    finally:
        try:
            doc.Clear()
        except Exception:
            pass

    seg = {str(i): 0 for i in range(n_faces)}
    bottom = {str(i): 0 for i in range(n_faces)}
    inst = [[0] * n_faces for _ in range(n_faces)]

    slot_cell_groups = []
    for one in instances:
        face_ids = list(one["faces"])
        cells = sorted({pos_map[f] for f in face_ids if f in pos_map})
        if not cells:
            continue
        slot_cell_groups.append(cells)
        for c in cells:
            seg[str(c)] = CATEGORY_ID
        for a in cells:
            for b in cells:
                inst[a][b] = 1
        # 底面标注（仍在 STEP face 空间判定，再映射到 NCTI 位置）
        if ANNOTATE_BOTTOM:
            bfid = find_bottom_cell(parser, fa_attrs, face_ids)
            if bfid is not None and bfid in pos_map:
                bottom[str(pos_map[bfid])] = 1

    name = os.path.splitext(os.path.basename(stp_path))[0]
    label_json = [[name, {"seg": seg, "inst": inst, "bottom": bottom}]]
    return label_json, slot_cell_groups


def iter_step_files(d):
    for f in sorted(os.listdir(d)):
        if f.lower().endswith((".step", ".stp")):
            yield os.path.join(d, f)


# ---------------- HTTP 下载模式（只下载，不上传/不回写数据库）----------------

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
        # 从 Content-Disposition 取文件名，否则用 part_id
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
            _WORKER["inst_booster"], _WORKER["inst_calib"], _WORKER["ncti"], NCTI_OBJ_NAME)
        return ("ok", label_json, groups, None)
    except Exception as e:
        return ("fail", None, None, str(e))


def main():
    print("FeatureFox 通槽批量标注（NCTI FaceID 空间）")
    print("  FEATUREFOX_ROOT = {}".format(FEATUREFOX_ROOT))
    print("  输入模式        = {}".format(INPUT_MODE))
    print("  输出目录        = {}".format(OUTPUT_DIR))
    print("  seg(通槽)       = {}   底面标注={}".format(CATEGORY_ID, ANNOTATE_BOTTOM), flush=True)

    use_pool = bool(TIMEOUT_SECONDS and TIMEOUT_SECONDS > 0)
    if use_pool:
        print("  超时保护        = 每文件 {}s 超时杀进程跳过".format(TIMEOUT_SECONDS), flush=True)
    else:
        print("  超时保护        = 关闭（主进程串行）", flush=True)
    print("  无通槽文件      = {}".format("输出空JSON" if WRITE_EMPTY else "跳过不输出"), flush=True)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 取 STEP 文件列表
    if INPUT_MODE == "http":
        print("  API             = {}".format(API_BASE_URL))
        files = download_step_files(API_BASE_URL, PART_IDS, LIST_PAGE_SIZE, DOWNLOAD_DIR)
    elif INPUT_MODE == "local":
        if not os.path.isdir(INPUT_STEP_DIR):
            sys.exit("输入目录不存在: {}".format(INPUT_STEP_DIR))
        print("  输入目录        = {}".format(INPUT_STEP_DIR))
        files = list(iter_step_files(INPUT_STEP_DIR))
    else:
        sys.exit("未知 INPUT_MODE: {}（应为 local / http）".format(INPUT_MODE))

    if MAX_FILES:
        files = files[:MAX_FILES]
    print("  待处理          = {} 个 STEP\n".format(len(files)), flush=True)

    # 加载模型 + NCTI：超时模式在工作进程加载（_worker_init），否则主进程加载
    pool = None
    booster = calib = inst_booster = inst_calib = ncti = None
    if use_pool:
        pool = multiprocessing.Pool(1, initializer=_worker_init)
        print("  工作进程        = 已启动（模型+NCTI 已在子进程加载）", flush=True)
    else:
        booster, calib = load_models()
        inst_booster, inst_calib = load_instance_models()
        print("  实例分类器      = {}".format("已加载" if inst_booster is not None else "未找到（仅第一级）"),
              flush=True)
        ncti = init_ncti_safe()
        if ncti is None:
            sys.exit("NCTI 初始化失败：标注必须走 NCTI FaceID 空间以对齐训练图。"
                     "请在 config/ncti_config.json 配置 SDK 路径（见 ncti_config.server.json），"
                     "或设环境变量 NCTI_DLLPATH。")
        print("  NCTI            = 已初始化（对象名 {}）".format(NCTI_OBJ_NAME), flush=True)

    n_ok = n_empty = n_fail = n_timeout = 0
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

    print("\n完成: 有通槽={}  无通槽={}  超时={}  失败={}".format(
        n_ok, n_empty, n_timeout, n_fail), flush=True)
    print("输出目录: {}".format(OUTPUT_DIR), flush=True)
    # NCTI DLL 析构可能 segfault，直接退出（与 through_step NCTI 测试脚本同惯例）
    os._exit(0)


if __name__ == "__main__":
    main()
