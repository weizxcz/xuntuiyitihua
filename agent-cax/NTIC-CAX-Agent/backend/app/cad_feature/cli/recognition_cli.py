#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
cad_feature 无头识别/清理 CLI（M1，架构 A 落地，自包含于 NTIC-CAX-Agent）。

本脚本是 cad_feature 能力的「内核执行器」，被 backend 的 runner 经 subprocess
在装了 NCTI SDK 的 wygcleaner 子进程内调用。它**不依赖 YHCADSmartCleaner**：
  - 几何识别核心已内化到同目录的 ``recognition_core.py``（仅依赖
    ``numpy`` / ``scikit-learn``，见同目录 ``requirements.txt``）；
  - NCTI SDK 路径由 ``NCTI_SDK_PATH`` 环境变量或 ``--sdk`` 提供，不再读取任何
    外部工程的 ``config/system_config.json``。

设计约束（由 Phase 0 spike v4 实测确定）：
  - 不能用 config.config_load.init_ncti_config()，它会 ctypes.CDLL 加载
    ncti_window.dll / ncti_render_vulkan.dll，纯无头下会挂起。
  - 必须走「geom 级 DLL 降级加载」：只加载 command/occ_plugin/doc_occ，
    再 import ncti_python + NCTI.Init(sdk)。
  - 导入用 doc.New("OCC","DCM",0) + doc.RunCommand("cmd_ncti_import_file", path, name)
    （doc.Open 在无头会挂起，绝不能用）。
  - 每次 RunCommand 前必须 doc.ResetCaseResult()（否则命令系统被锁）。
  - RunCommand 返回值可能是 PyCapsule，统一强转 bool。
  - 进程末尾用 os._exit(0) 跳过 NCTI 拆卸，规避 0xC0000005 段错误。

子命令：
  recognize  识别几何特征 → 写识别 JSON
  clean      按识别 JSON 清理特征 → 导出 STEP

运行示例（wygcleaner 环境，已设 NCTI_SDK_PATH）：
  python recognition_cli.py recognize --stp part.stp --type fillet --method geometry \
      --params '{"min_radius":0,"max_radius":1000}' --out part_fillets.json
  python recognition_cli.py clean --stp part.stp --recognition part_fillets.json \
      --out part_cleaned.step
"""
import os
import sys
import json
import ctypes
import argparse
import traceback

# 让本脚本无论 cwd 都能解析同目录的 recognition_core
_THIS = os.path.dirname(os.path.abspath(__file__))
if _THIS not in sys.path:
    sys.path.insert(0, _THIS)

# 双导入：作为脚本直接运行时回退到 `from recognition_core`；作为包的一部分
# 被导入时走相对导入。两者都指向同目录的识别核心模块。
try:
    from .recognition_core import (
        get_face_sample,
        is_constant_radius_fillet_by_points_and_normals,
    )
except ImportError:
    from recognition_core import (
        get_face_sample,
        is_constant_radius_fillet_by_points_and_normals,
    )


# ---------------------------------------------------------------------------
# NCTI SDK 路径解析（不再依赖任何外部工程的 config）
# ---------------------------------------------------------------------------
def _resolve_sdk() -> str:
    """SDK 路径优先级：环境变量 NCTI_SDK_PATH → 报错。

    独立仓库部署时，NCTI SDK 是机器相关路径（不入库），必须经此环境变量或
    ``--sdk`` 提供。例如 YHCADSmartCleaner 工程内即 ``<repo>/SDK`` 的绝对路径。
    """
    sdk = os.environ.get("NCTI_SDK_PATH", "").strip()
    if sdk:
        return sdk
    raise RuntimeError(
        "未指定 NCTI SDK 路径。请通过环境变量 NCTI_SDK_PATH 或 --sdk 提供"
        "（例如 YHCADSmartCleaner/SDK 的绝对路径）。"
    )


def load_ncti_geom(sdk: str | None = None):
    """复刻 spike v4 的可工作配方：只加载几何相关 DLL，纯无头可跑。

    Args:
        sdk: NCTI SDK 目录（含 ncti_*.dll 与 OCC 子目录）。为空时从
            ``NCTI_SDK_PATH`` 环境变量解析。
    """
    sdk = (sdk or "").strip() or _resolve_sdk()
    if not os.path.isabs(sdk):
        sdk = os.path.abspath(sdk)
    if sdk not in sys.path:
        sys.path.insert(0, sdk)
    try:
        os.add_dll_directory(sdk)
        os.add_dll_directory(os.path.join(sdk, "OCC"))
    except Exception:
        pass
    geom_dlls = ["ncti_command.dll", "ncti_occ_plugin.dll", "ncti_doc_occ.dll"]
    for d in geom_dlls:
        p = os.path.join(sdk, d)
        if os.path.exists(p):
            ctypes.CDLL(p)
    import ncti_python
    ncti_python.Init(sdk)
    return ncti_python


def _rc(doc, *args):
    """RunCommand 包装：先 ResetCaseResult，返回值强转 bool。"""
    doc.ResetCaseResult()
    return bool(doc.RunCommand(*args))


# ---------------------------------------------------------------------------
# 识别
# ---------------------------------------------------------------------------
def _recognize_fillet_by_kernel(ncti, doc, params):
    """内核原生法识别圆角：doc.FindFillets（spike v4 已验证无头可用）。

    比「逐面几何采样判定」更准更快——FindFillets 直接返回圆角 cell。
    半径通过 get_face_sample + is_constant_radius_fillet_by_points_and_normals
    对每个 cell 二次采样补出（FindFillets 只返回 cell_id，不含半径）。
    """
    min_r = float(params.get("min_radius", 0.0))
    max_r = float(params.get("max_radius", 1e9))
    fillet_type = int(params.get("fillet_type", 0))

    sel = ncti.SelectionManager(doc)
    sel.ObjectNames = doc.AllNames() or []
    fillets = doc.FindFillets(sel.ObjectNames, min_r, max_r, fillet_type) or {}

    cells = []
    for obj_name, cell_ids in fillets.items():
        for cid in cell_ids:
            cells.append((obj_name, int(cid)))
    if not cells:
        return []

    obj_names = [c[0] for c in cells]
    cell_ids = [c[1] for c in cells]
    try:
        face_points, face_normals = get_face_sample(doc, obj_names, cell_ids)
    except Exception:
        face_points, face_normals = [None] * len(cells), [None] * len(cells)

    import numpy as np

    features = []
    for i, (obj_name, cid) in enumerate(cells):
        radius = 0.0
        try:
            pts = face_points[i]
            nrm = face_normals[i]
            if pts is not None and nrm is not None:
                _, info = is_constant_radius_fillet_by_points_and_normals(
                    np.asarray(pts), np.asarray(nrm)
                )
                radius = float(info.get("radius_mean") or 0.0)
        except Exception:
            pass
        features.append({
            "id": len(features) + 1,
            "object_name": obj_name,
            "cell_id": cid,
            "face_type": "圆柱面(圆角)",
            "radius": round(radius, 4) if radius > 0 else None,
            "confidence": 1.0,
        })
    return features


def _recognize_fillet_geometry(ncti, doc, params):
    """几何采样法识别圆角（fallback）：FindAllFaces + 逐面采样 + 恒半径判定。"""
    all_names = doc.AllNames() or []
    if not all_names:
        return []
    obj = all_names[0]
    face_ids = doc.FindAllFaces(obj) or []
    if not face_ids:
        return []
    obj_names = [obj] * len(face_ids)
    face_points, face_normals = get_face_sample(doc, obj_names, face_ids)

    min_r = float(params.get("min_radius", 0.0))
    max_r = float(params.get("max_radius", 1e9))

    features = []
    for i, fid in enumerate(face_ids):
        try:
            pts = face_points[i]
            nrm = face_normals[i]
        except Exception:
            continue
        if pts is None or nrm is None:
            continue
        try:
            import numpy as np

            is_round, info = is_constant_radius_fillet_by_points_and_normals(
                np.asarray(pts), np.asarray(nrm)
            )
        except Exception:
            continue
        if not is_round:
            continue
        radius = float(info.get("radius_mean") or 0.0)
        if radius < min_r or radius > max_r:
            continue
        features.append({
            "id": len(features) + 1,
            "object_name": obj,
            "cell_id": int(fid),
            "face_type": "圆柱面(圆角)",
            "radius": round(radius, 4),
            "confidence": 1.0,
        })
    return features


def run_recognize(ncti, doc, stp, feature_type, method, params):
    doc.New("OCC", "DCM", 0)
    ok = _rc(doc, "cmd_ncti_import_file", str(stp), "recognize_target")
    if not ok:
        raise RuntimeError("导入 STP 失败（RunCommand(cmd_ncti_import_file) 未生效）")

    supported = ["fillet"]
    if feature_type not in supported:
        return {
            "ok": False,
            "error": f"feature_type='{feature_type}' 暂未实现；当前支持：{supported}",
            "supported": supported,
        }

    if method == "geometry":
        features = _recognize_fillet_geometry(ncti, doc, params or {})
        method_used = "geometry"
    elif method in ("ai", "hybrid"):
        features = _recognize_fillet_by_kernel(ncti, doc, params or {})
        method_used = "kernel_FindFillets"
    else:
        return {"ok": False, "error": f"未知 method='{method}'（支持 geometry/ai/hybrid）"}

    by_type = {}
    for f in features:
        by_type[f["face_type"]] = by_type.get(f["face_type"], 0) + 1
    return {
        "ok": True,
        "source_file": os.path.basename(str(stp)),
        "feature_type": feature_type,
        "method": method_used,
        "features": features,
        "summary": {"count": len(features), "by_type": by_type},
    }


def cmd_recognize(args):
    params = {}
    if args.params:
        params = json.loads(args.params)
    ncti = load_ncti_geom(args.sdk)
    doc = ncti.Document()
    result = run_recognize(ncti, doc, args.stp, args.type, args.method, params)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


# ---------------------------------------------------------------------------
# 清理
# ---------------------------------------------------------------------------
def run_clean(ncti, doc, stp, recognition, output_step):
    features = recognition.get("features") or []
    if not features:
        return {"ok": False, "error": "recognition_json 中无 features，无法清理"}

    import_name = features[0].get("object_name") or "clean_target"

    doc.New("OCC", "DCM", 0)
    ok = _rc(doc, "cmd_ncti_import_file", str(stp), import_name)
    if not ok:
        raise RuntimeError("导入 STP 失败（RunCommand(cmd_ncti_import_file) 未生效）")

    removed = 0
    object_names = set()
    for feat in features:
        obj = feat.get("object_name")
        cid = feat.get("cell_id")
        if obj is None or cid is None:
            continue
        object_names.add(obj)
        try:
            _rc(doc, "cmd_ncti_remove_features", obj, [int(cid)])
            removed += 1
        except Exception as e:
            sys.stderr.write(f"[warn] 移除 {obj}#{cid} 失败: {e}\n")
    all_names = doc.AllNames() or []
    export_obj = all_names[0] if all_names else (next(iter(object_names), import_name))
    _rc(doc, "cmd_ncti_export_file", str(output_step), export_obj)
    return {
        "ok": True,
        "cleaned_step": str(output_step),
        "removed_count": removed,
        "file_exists": os.path.exists(output_step),
    }


def cmd_clean(args):
    with open(args.recognition, "r", encoding="utf-8") as f:
        recognition = json.load(f)
    ncti = load_ncti_geom(args.sdk)
    doc = ncti.Document()
    result = run_clean(ncti, doc, args.stp, recognition, args.out)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="cad_feature 无头识别/清理 CLI（NTIC-CAX-Agent）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    rp = sub.add_parser("recognize", help="识别几何特征")
    rp.add_argument("--stp", required=True, help="输入 STP 路径")
    rp.add_argument("--type", required=True, help="特征类型：fillet/chamfer/...")
    rp.add_argument("--method", default="ai", help="ai(内核FindFillets,推荐) / geometry(逐面采样) / hybrid")
    rp.add_argument("--params", default="{}", help="半径区间等 JSON 字符串")
    rp.add_argument("--sdk", default=None, help="NCTI SDK 目录（否则用环境变量 NCTI_SDK_PATH）")
    rp.add_argument("--out", default=None, help="识别结果 JSON 输出路径")
    rp.set_defaults(func=cmd_recognize)

    cp = sub.add_parser("clean", help="按识别 JSON 清理并导出 STEP")
    cp.add_argument("--stp", required=True, help="原始 STP 路径")
    cp.add_argument("--recognition", required=True, help="识别结果 JSON 路径")
    cp.add_argument("--out", required=True, help="清理后 STEP 输出路径")
    cp.add_argument("--sdk", default=None, help="NCTI SDK 目录（否则用环境变量 NCTI_SDK_PATH）")
    cp.set_defaults(func=cmd_clean)

    args = ap.parse_args()
    try:
        rc = args.func(args)
    except Exception as e:
        err = {"ok": False, "error": f"{type(e).__name__}: {e}",
               "trace": traceback.format_exc()}
        print(json.dumps(err, ensure_ascii=False))
        os._exit(1)
    os._exit(rc if rc is not None else 0)


if __name__ == "__main__":
    main()
