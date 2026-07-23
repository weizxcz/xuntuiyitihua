#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 0 可行性 spike（v4）—— NCTI 内核纯无头能力验证（自包含于 NTIC-CAX-Agent）。

已确认结论（基于 v3 实测）：
  - RunCommand(cmd_ncti_import_file) 无头可用（打印 "Imoprt file:288ms"）。
  - 识别 FindAllFaces + FindFillets 无头可用。
  - RunCommand 清理/导出无头可用，但：① 每次命令前须 doc.ResetCaseResult()；
    ② 清理入参必须是真实存在的 cell id；③ NCTI 进程拆卸会触发 0xC0000005 段错误，
    用 os._exit(0) 跳过拆卸规避。

与 YHCADSmartCleaner 下的旧版不同：本脚本不再硬编码 SDK / STP 绝对路径，
改为由环境变量提供，便于独立仓库部署：
  - NCTI_SDK_PATH：NCTI SDK 目录（必填）。
  - SPIKE_STP：测试用 STP 路径（默认回退到常见本地样本，部署时请覆盖）。

运行：conda activate wygcleaner && python spike_headless.py
"""
import os
import sys
import json
import ctypes
import traceback
import subprocess
import tempfile

SDK = os.environ.get("NCTI_SDK_PATH", "").strip()
STP = os.environ.get("SPIKE_STP") or r"D:\wyg\data\含倒角、圆角、通孔、盲孔(单solid).stp"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spike_headless_report.json")
INNER = os.environ.get("SPOKE_INNER") == "1"
WATCHDOG_TIMEOUT = 90

report = {"python": sys.version, "python_supported": False, "dll_level": None, "steps": []}


def step(name, fn):
    rec = {"name": name, "ok": False, "detail": None, "error": None}
    try:
        rec["detail"] = fn()
        rec["ok"] = True
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
    report["steps"].append(rec)
    tag = "OK  " if rec["ok"] else "FAIL"
    print(f"[{tag}] {name}")
    if not rec["ok"]:
        print("       " + (rec["error"] or "").strip().splitlines()[-1])
    return rec


def load_ncti(level):
    if not SDK:
        raise RuntimeError("未设置环境变量 NCTI_SDK_PATH（NCTI SDK 目录）")
    sdk = SDK
    if sdk not in sys.path:
        sys.path.insert(0, sdk)
    try:
        os.add_dll_directory(sdk)
        os.add_dll_directory(os.path.join(sdk, "OCC"))
    except Exception:
        pass
    dlls = {
        "geom": ["ncti_command.dll", "ncti_occ_plugin.dll", "ncti_doc_occ.dll"],
        "full": ["ncti_command.dll", "ncti_occ_plugin.dll", "ncti_doc_occ.dll",
                 "ncti_render_vulkan.dll", "ncti_window.dll"],
    }[level]
    for d in dlls:
        p = os.path.join(sdk, d)
        if os.path.exists(p):
            ctypes.CDLL(p)
    import ncti_python
    ncti_python.Init(sdk)
    return ncti_python


def run_inner():
    vi = sys.version_info
    report["python_supported"] = (3, 8) <= (vi.major, vi.minor) <= (3, 12)
    if not report["python_supported"]:
        print(f"[WARN] Python {vi.major}.{vi.minor} 不在支持范围 3.8~3.12")
    if not os.path.exists(STP):
        print(f"[FATAL] 测试 stp 不存在: {STP}（请用 SPIKE_STP 环境变量指定）")
        return

    ncti = None

    def do_init():
        nonlocal ncti
        last_err = None
        for lvl in ("geom", "full"):
            try:
                ncti = load_ncti(lvl)
                report["dll_level"] = lvl
                return f"level={lvl}"
            except Exception as e:
                last_err = e
                print(f"  (load_ncti {lvl} 失败: {type(e).__name__}: {e})")
        raise last_err

    step("1. NCTI.Init + import ncti_python（无头 DLL 加载）", do_init)
    if not report["steps"][-1]["ok"]:
        print("\n>>> 地基失败：必须走架构 B（宿主 NCTI 进程）。")
        return

    doc = ncti.Document()
    step("2. NCTI.Document() 创建", lambda: "ok")

    def rc(*args):
        doc.ResetCaseResult()
        return bool(doc.RunCommand(*args))

    ctx = {"detected": []}

    def do_import_runcmd():
        doc.New("OCC", "DCM", 0)
        ok = rc("cmd_ncti_import_file", str(STP), "testbox")
        names = doc.AllNames() or []
        return {"return_bool": ok, "objects": names,
                "verdict": "EXECUTED（RunCommand 无头可用）" if (ok and names) else "NO-OP"}

    step("3. RunCommand(cmd_ncti_import_file) 导入（决定性）", do_import_runcmd)

    def do_recognize():
        all_names = doc.AllNames() or []
        obj = all_names[0]
        faces = doc.FindAllFaces(obj) or []
        sel = ncti.SelectionManager(doc)
        sel.ObjectNames = all_names
        fillets = doc.FindFillets(sel.ObjectNames, 0.0, 1e9, 0)
        cells = []
        if fillets:
            for k, v in fillets.items():
                for cid in v:
                    cells.append((k, cid))
        ctx["detected"] = cells
        return {"object": obj, "total_faces": len(faces),
                "fillet_count": len(cells), "fillet_sample": cells[:10]}

    step("4. 识别：FindAllFaces + FindFillets（纯内核 API）", do_recognize)

    def do_runcmd_remove():
        all_names = doc.AllNames() or []
        obj = all_names[0]
        if not ctx["detected"]:
            raise RuntimeError("未识别到圆角，无法测试清理")
        cid = ctx["detected"][0][1]
        before = len(doc.FindAllFaces(obj) or [])
        ok = rc("cmd_ncti_remove_features", obj, [cid])
        after = len(doc.FindAllFaces(obj) or [])
        return {"removed_cell": cid, "return_bool": ok,
                "faces_before": before, "faces_after": after,
                "removed_ok": after < before}

    step("5. RunCommand(cmd_ncti_remove_features) 真实清理一个圆角（testbox，非源文件）", do_runcmd_remove)

    def do_runcmd_export():
        obj = (doc.AllNames() or [])[0]
        tmp = os.path.join(tempfile.gettempdir(), "spike_export_probe.step")
        ok = rc("cmd_ncti_export_file", tmp, obj)
        return {"target": tmp, "return_bool": ok, "file_exists": os.path.exists(tmp)}

    step("6. RunCommand(cmd_ncti_export_file) 导出", do_runcmd_export)

    print("\n================ Phase 0 结论 ================")
    verdict = (report["steps"][2]["detail"] or {}).get("verdict", "")
    rec_ok = (report["steps"][4]["detail"] or {}).get("removed_ok", False)
    if "EXECUTED" in verdict and rec_ok:
        print("[结论] 全链路无头可用（导入→识别→清理→导出）→ 架构 A（无头直跑）可行，进入 Phase 1。")
    elif "EXECUTED" in verdict:
        print("[导入/识别] 无头可用，但清理验证未通过，需检查 remove 入参/状态。")
    else:
        print("[结论] RunCommand 无头 NO-OP → 必须走架构 B。")
    print(f"[DLL] 成功加载级别 = {report['dll_level']}")
    print("=============================================")


def dump():
    try:
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n报告已写入: {OUT}")
    except Exception as e:
        print(f"写报告失败: {e}")


def main():
    if INNER:
        run_inner()
        dump()
        os._exit(0)
    env = dict(os.environ)
    env["SPOKE_INNER"] = "1"
    try:
        p = subprocess.Popen([sys.executable, os.path.abspath(__file__)], env=env)
    except Exception as e:
        print(f"[FATAL] 无法启动子进程: {e}")
        return
    try:
        p.wait(timeout=WATCHDOG_TIMEOUT)
    except subprocess.TimeoutExpired:
        p.kill()
        try:
            p.wait(timeout=10)
        except Exception:
            pass
        print(f"\n[HANG] 内部流程 {WATCHDOG_TIMEOUT}s 超时，已强制结束 → 必须走架构 B。")
        dump()
        return
    if p.returncode != 0:
        print(f"\n[EXIT] 子进程退出 code={p.returncode}（可能 C 层问题，但结果应已落盘）。")


if __name__ == "__main__":
    main()
