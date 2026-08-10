#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""FeatureFox 盲孔批量标注脚本（NCTI 原生数据源版 / 零映射）。

与 through_step/featurefox_ncti_annotate/annotate_through_step_ncti.py（通槽版）平行实现，
区别仅在识别目标：盲孔 seg=12 vs 通槽 seg=9。

流程：
  1. 获取 STEP 文件（local 模式：读本地目录 INPUT_STEP_DIR 的所有 STEP）
  2. NCTI 导入（约定A，与 featurefox_blindhole 训练 load_part 一致）→ NctiPart
  3. FeatureFox-NCTI 两级识别（边分类器 0.05 + 实例分类器 0.80）→ 盲孔实例
     （faces 直接就是 cell_id = ai.FaceID 位置索引，零映射对齐 Geo-Rec 训练图）
  4. 构造训练标签 JSON：[[name, {"seg":{cell:12}, "inst":NxN, "bottom":{}}]]
     （盲孔没有底面启发式，bottom 全标 0）
  5. STEP 文件 + JSON 一起写到输出目录（仅含盲孔的文件）

与通槽版差异：
  - CATEGORY_ID = 12（盲孔 seg）
  - 特征模块 featurefox_blindhole（30 维边特征 + 26 维实例特征）
  - 边阈值 0.05（评估最优）、MIN_INSTANCE_FACES=2、MIN_PLANE_RATIO=0
  - 无底面标注（盲孔底面判定与通槽不同，暂不做启发式）
  - 只输出含盲孔的文件（WRITE_EMPTY=False）

⚠ 需要 NCTI：识别与建图都在 NCTI 上做。设环境变量 NCTI_DLLPATH 或
   LD_LIBRARY_PATH 指向 NCTI SDK。

JSON 格式与 Geo-Rec 标签一致：data[0][1]["seg"]/["inst"]/["bottom"]，
cell_id 直接当 feature_labels 下标。
"""

# ============================================================
import os
# ============================================================
#  配置区
# ============================================================

# FeatureFox-NCTI 模块所在目录（自动计算，环境变量 NCTI_PROJECT_ROOT 可覆盖）
FEATUREFOX_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── 输入模式 ──
INPUT_MODE = "local"   # "local"=读本地目录

# [local 模式] STEP 输入目录
INPUT_STEP_DIR = r"/mnt/data/geometry_data/steps/step_files"

# 输出目录（STEP + JSON 都写到这下面的两个子目录）
OUTPUT_DIR = r"/mnt/data/geometry_data/steps/json_files/wyg/ncti-盲孔"
OUTPUT_JSON_SUBDIR = "labels"
OUTPUT_STEP_SUBDIR = "step"

# 盲孔 seg 值（与训练标签一致；盲孔用 12，通槽用 9）
CATEGORY_ID = 12

# 第一级边分类器剪枝阈值（评估最优 F1=95.4% @ 0.05）
EDGE_THRESHOLD = 0.05
# 第二级实例分类器阈值（< 此值判为非盲孔）
INST_THRESHOLD = 0.80

# 盲孔不适用底面启发式（与通槽 U 型槽不同），bottom 全标 0
ANNOTATE_BOTTOM = False

# 面数断言：part.n_faces 与 STEP 文本 ADVANCED_FACE 数不等时跳过
SKIP_FACE_MISMATCH = True

# 处理上限（0=全部）
MAX_FILES = 0

# 无盲孔的文件不输出（默认只保留有盲孔的）
WRITE_EMPTY = False

# 单文件解析超时（秒）。>0 时启用独立工作进程超时保护
TIMEOUT_SECONDS = 30

# ── NCTI（必需）──
NCTI_OBJ_NAME = "OCC"

# ── 并行 ──
N_WORKERS = 8
MAX_FILE_MB = 60
RESUME = True

# ============================================================

import os
import sys
import json
import shutil
import io
import multiprocessing

# 路径设置：featurefox 包根目录（scripts/ 的父目录）
_FEATFOX_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _FEATFOX_ROOT not in sys.path:
    sys.path.insert(0, _FEATFOX_ROOT)
from featurefox.lib._env import get_project_root
_PROJECT_ROOT = get_project_root()
if _PROJECT_ROOT and _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

try:
    from featurefox.scripts.predict import (
        predict_through_slots, load_models, load_instance_models)
    from featurefox.lib.ncti_backend import load_part, NctiFaceAttrs, count_advanced_faces
    from featurefox.lib.ncti_faceid_map import init_ncti_safe
except Exception as _e:
    sys.stderr.write(
        "FeatureFox-BlindHole 导入失败，请检查路径是否正确。\n"
        "  FEATUREFOX_ROOT = {}\n  错误: {}\n".format(_FEATFOX_ROOT, _e))
    raise


def init_ncti_or_die():
    """初始化 NCTI。失败则退出。"""
    ncti = init_ncti_safe(_PROJECT_ROOT)
    if ncti is None:
        sys.exit(
            "NCTI 初始化失败：标注必须走 NCTI。\n"
            "请在 config/ncti_config.json 配置 SDK 路径，"
            "或设环境变量 NCTI_DLLPATH / LD_LIBRARY_PATH。")
    return ncti


def annotate_one(stp_path, booster, calib, inst_booster, inst_calib, ncti, obj_name, doc):
    """识别一个 STEP 中的盲孔，返回 (label_json, blind_hole_cell_groups)。

    cell_id 直接来自 featurefox_blindhole 的输出（ai.FaceID 位置索引），零映射，
    与 Geo-Rec 训练图严格同空间。doc 由调用方提供并复用。
    """
    # NCTI 导入（约定A，与 featurefox_blindhole 训练 load_part 一致）
    part, doc = load_part(stp_path, ncti, obj_name=obj_name, doc=doc)
    try:
        n_faces = part.n_faces

        # 面数断言
        n_adv = count_advanced_faces(stp_path)
        if n_adv is not None and n_adv != n_faces:
            msg = "面数不匹配: ADVANCED_FACE={} ai.FaceID={}".format(n_adv, n_faces)
            if SKIP_FACE_MISMATCH:
                raise RuntimeError(
                    "{}，跳过（cell_id 可能错位；关 SKIP_FACE_MISMATCH 可强制输出）".format(msg))
            sys.stderr.write("  警告: {} {}\n".format(msg, os.path.basename(stp_path)))

        # FeatureFox 盲孔两级识别 → instances[i].faces 即 cell_id（零映射）
        instances = predict_through_slots(
            stp_path, booster, calib, part=part, ncti=ncti,
            threshold=EDGE_THRESHOLD,
            inst_booster=inst_booster, inst_calibrator=inst_calib,
            inst_threshold=INST_THRESHOLD)

        seg = {str(i): 0 for i in range(n_faces)}
        bottom = {str(i): 0 for i in range(n_faces)}
        inst = [[0] * n_faces for _ in range(n_faces)]

        blind_hole_groups = []
        for one in instances:
            cells = sorted(set(one["faces"]))   # 已是 cell_id
            if not cells:
                continue
            blind_hole_groups.append(cells)
            for c in cells:
                seg[str(c)] = CATEGORY_ID
            for a in cells:
                for b in cells:
                    inst[a][b] = 1

        name = os.path.splitext(os.path.basename(stp_path))[0]
        label_json = [[name, {"seg": seg, "inst": inst, "bottom": bottom}]]
        return label_json, blind_hole_groups
    finally:
        try:
            doc.Clear()
        except Exception:
            pass


def iter_step_files(d):
    for f in sorted(os.listdir(d)):
        if f.lower().endswith((".step", ".stp")):
            yield os.path.join(d, f)


# ---------------- 超时/并行机制 ----------------

_WORKER = {}


def _worker_init():
    """工作进程初始化：加载模型 + 初始化 NCTI + 建持久 doc。"""
    _WORKER["booster"], _WORKER["calib"] = load_models()
    _WORKER["inst_booster"], _WORKER["inst_calib"] = load_instance_models()
    ncti = init_ncti_or_die()
    _WORKER["ncti"] = ncti
    _WORKER["doc"] = ncti.Document()


def _worker_annotate(stp_path):
    """工作进程：标注单文件。"""
    try:
        label_json, groups = annotate_one(
            stp_path, _WORKER["booster"], _WORKER["calib"],
            _WORKER["inst_booster"], _WORKER["inst_calib"],
            _WORKER["ncti"], NCTI_OBJ_NAME, _WORKER["doc"])
        return ("ok", stp_path, label_json, groups, None)
    except Exception as e:
        return ("fail", stp_path, None, None, str(e))


def main():
    global N_WORKERS, MAX_FILES, MAX_FILE_MB, RESUME, INPUT_STEP_DIR
    if os.environ.get("ATS_N_WORKERS"):
        N_WORKERS = int(os.environ["ATS_N_WORKERS"])
    if os.environ.get("ATS_INPUT_DIR"):
        INPUT_STEP_DIR = os.environ["ATS_INPUT_DIR"]
    if os.environ.get("ATS_MAX_FILES"):
        MAX_FILES = int(os.environ["ATS_MAX_FILES"])
    if os.environ.get("ATS_MAX_FILE_MB"):
        MAX_FILE_MB = int(os.environ["ATS_MAX_FILE_MB"])
    if os.environ.get("ATS_RESUME"):
        RESUME = os.environ["ATS_RESUME"].lower() in ("1", "true", "yes")

    print("FeatureFox-NCTI 盲孔批量标注（零映射）")
    print("  FEATUREFOX_ROOT = {}".format(_FEATFOX_ROOT))
    print("  输入模式        = {}".format(INPUT_MODE))
    print("  输入目录        = {}".format(INPUT_STEP_DIR))
    print("  输出目录        = {}".format(OUTPUT_DIR))
    print("  seg(盲孔)       = {}   底面标注={}".format(CATEGORY_ID, ANNOTATE_BOTTOM))
    print("  边阈值/实例阈值 = {} / {}".format(EDGE_THRESHOLD, INST_THRESHOLD))
    print("  面数断言        = {}".format("跳过不匹配" if SKIP_FACE_MISMATCH else "仅告警"))

    use_pool = bool(TIMEOUT_SECONDS and TIMEOUT_SECONDS > 0)
    parallel = bool(N_WORKERS and N_WORKERS > 1)
    serial_timeout = (not parallel) and use_pool
    if parallel:
        print("  并发            = {} 个工作进程".format(N_WORKERS))
    elif serial_timeout:
        print("  超时保护        = 每文件 {}s 超时杀进程跳过".format(TIMEOUT_SECONDS))
    else:
        print("  超时保护        = 关闭（主进程串行）")
    print("  大文件跳过      = > {} MB".format(MAX_FILE_MB))
    print("  续跑            = {}".format("开" if RESUME else "关"))
    print("  无盲孔文件      = {}".format("输出空JSON" if WRITE_EMPTY else "跳过不输出"), flush=True)

    out_json_dir = os.path.join(OUTPUT_DIR, OUTPUT_JSON_SUBDIR)
    out_stp_dir = os.path.join(OUTPUT_DIR, OUTPUT_STEP_SUBDIR)
    os.makedirs(out_json_dir, exist_ok=True)
    os.makedirs(out_stp_dir, exist_ok=True)

    # 取 STEP 文件列表
    skipped_big = 0
    if INPUT_MODE == "local":
        if not os.path.isdir(INPUT_STEP_DIR):
            sys.exit("输入目录不存在: {}".format(INPUT_STEP_DIR))
        max_bytes = MAX_FILE_MB * 1024 * 1024
        files = []
        for fp in iter_step_files(INPUT_STEP_DIR):
            try:
                sz = os.path.getsize(fp)
            except OSError:
                sz = 0
            if max_bytes and sz > max_bytes:
                skipped_big += 1
                continue
            files.append(fp)
    else:
        sys.exit("未知 INPUT_MODE: {}（当前只支持 local）".format(INPUT_MODE))

    if MAX_FILES:
        files = files[:MAX_FILES]
    print("  待处理          = {} 个 STEP（跳过大文件 {} 个）\n".format(
        len(files), skipped_big), flush=True)

    pool = None
    booster = calib = inst_booster = inst_calib = ncti = doc = None
    if parallel:
        pool = multiprocessing.Pool(N_WORKERS, initializer=_worker_init)
        print("  工作进程        = {} 个已启动（模型+NCTI 已在各子进程加载）".format(N_WORKERS), flush=True)
    elif serial_timeout:
        pool = multiprocessing.Pool(1, initializer=_worker_init)
        print("  工作进程        = 已启动", flush=True)
    else:
        booster, calib = load_models()
        inst_booster, inst_calib = load_instance_models()
        print("  实例分类器      = {}".format("已加载" if inst_booster is not None else "未找到"), flush=True)
        ncti = init_ncti_or_die()
        doc = ncti.Document()
        print("  NCTI            = 已初始化", flush=True)

    n_ok = [0]
    n_empty = [0]
    n_fail = n_timeout = n_skip_done = 0
    total = len(files)

    def _json_path(name):
        return os.path.join(out_json_dir, os.path.splitext(name)[0] + ".json")

    def _emit(idx, name, stp, label_json, groups, count_total):
        out_json = _json_path(name)
        out_stp = os.path.join(out_stp_dir, name)
        if groups or WRITE_EMPTY:
            with open(out_json, "w", encoding="utf-8") as fh:
                json.dump(label_json, fh, ensure_ascii=False, indent=2)
            if os.path.abspath(stp) != os.path.abspath(out_stp):
                shutil.copy2(stp, out_stp)
        if groups:
            n_ok[0] += 1
            print("[{}/{}] OK    {} ({} 个盲孔: {})".format(
                idx, count_total, name, len(groups), groups), flush=True)
        else:
            n_empty[0] += 1
            tag = "已输出空 JSON" if WRITE_EMPTY else "跳过"
            print("[{}/{}] EMPTY {} (无盲孔, {})".format(
                idx, count_total, name, tag), flush=True)

    if parallel:
        work = []
        for stp in files:
            name = os.path.basename(stp)
            if RESUME and os.path.exists(_json_path(name)):
                n_skip_done += 1
                continue
            work.append(stp)
        if n_skip_done:
            print("  续跑跳过        = {} 个已输出\n".format(n_skip_done), flush=True)
        work_total = len(work)
        for idx, res in enumerate(pool.imap_unordered(_worker_annotate, work), 1):
            status, stp, label_json, groups, err = res
            name = os.path.basename(stp)
            if status != "ok":
                n_fail += 1
                print("[{}/{}] FAIL    {} : {}".format(idx, work_total, name, err), flush=True)
                continue
            _emit(idx, name, stp, label_json, groups, work_total)
    else:
        for idx, stp in enumerate(files, 1):
            name = os.path.basename(stp)
            if RESUME and os.path.exists(_json_path(name)):
                n_skip_done += 1
                print("[{}/{}] SKIP   {} (已输出)".format(idx, total, name), flush=True)
                continue

            if serial_timeout:
                res = pool.apply_async(_worker_annotate, (stp,))
                try:
                    status, _, label_json, groups, err = res.get(timeout=TIMEOUT_SECONDS)
                except multiprocessing.TimeoutError:
                    n_timeout += 1
                    print("[{}/{}] TIMEOUT {} (>{:.0f}s，杀进程跳过)".format(
                        idx, total, name, TIMEOUT_SECONDS), flush=True)
                    pool.terminate(); pool.join()
                    pool = multiprocessing.Pool(1, initializer=_worker_init)
                    continue
                except Exception as e:
                    n_fail += 1
                    print("[{}/{}] CRASH   {} (工作进程崩溃: {})".format(
                        idx, total, name, e), flush=True)
                    try:
                        pool.terminate(); pool.join()
                    except Exception:
                        pass
                    pool = multiprocessing.Pool(1, initializer=_worker_init)
                    continue
                if status != "ok":
                    n_fail += 1
                    print("[{}/{}] FAIL    {} : {}".format(idx, total, name, err), flush=True)
                    continue
            else:
                try:
                    label_json, groups = annotate_one(
                        stp, booster, calib, inst_booster, inst_calib,
                        ncti, NCTI_OBJ_NAME, doc)
                except Exception as e:
                    n_fail += 1
                    print("[{}/{}] FAIL    {} : {}".format(idx, total, name, e), flush=True)
                    continue

            _emit(idx, name, stp, label_json, groups, total)

    if pool is not None:
        pool.close(); pool.join()

    print("\n完成: 有盲孔={}  无盲孔={}  续跑跳过={}  超时={}  失败={}".format(
        n_ok[0], n_empty[0], n_skip_done, n_timeout, n_fail), flush=True)
    print("输出目录: {}（JSON: {}/  STEP: {}/）".format(
        OUTPUT_DIR, OUTPUT_JSON_SUBDIR, OUTPUT_STEP_SUBDIR), flush=True)
    os._exit(0)


if __name__ == "__main__":
    main()
