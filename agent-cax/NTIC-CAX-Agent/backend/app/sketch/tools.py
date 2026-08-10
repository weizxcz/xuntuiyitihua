"""LangChain tool wrappers for the NCTI sketch transpiler + verifier.

These expose the deterministic "结构化转译 + 验证闭环" pipeline as callable
tools so the sketch skill can drive it instead of hand-writing NCTI Python.

The agent emits a SketchSpec (JSON); the tools transpile / verify / run the
closed loop deterministically and return structured JSON. See
``docs/sketch-transpile-verify-design.md`` §4.
"""

from __future__ import annotations

import json

from langchain.tools import tool
from pydantic import ValidationError

from app.sketch.kernel import get_kernel_runtime, make_ncti_run_solver
from app.sketch.pipeline import SketchPipeline
from app.sketch.spec import SketchSpec
from app.sketch.transpiler import transpile
from app.sketch.verify import VerificationReport, verify_spec


def _parse_spec(spec_json: str) -> tuple[SketchSpec | None, str | None]:
    """Parse + schema-validate a SketchSpec JSON string.

    Returns ``(spec, None)`` on success or ``(None, error_message)`` on failure.
    """
    try:
        data = json.loads(spec_json)
    except json.JSONDecodeError as exc:
        return None, f"JSON 解析失败: {exc}"
    try:
        return SketchSpec.model_validate(data), None
    except ValidationError as exc:
        return None, "SketchSpec 校验失败:\n" + json.dumps(exc.errors(), ensure_ascii=False, indent=2)


def _report_to_dict(report: VerificationReport) -> dict:
    return {
        "ok": report.ok,
        "issues": [
            {
                "level": i.level,
                "code": i.code,
                "message": i.message,
                "spec_path": i.spec_path,
            }
            for i in report.issues
        ],
    }


@tool("transpile_sketch", parse_docstring=False)
def transpile_sketch_tool(spec_json: str) -> str:
    """把结构化草图规格 SketchSpec(JSON) 确定性转译为 NCTI Python 脚本。

    你（LLM）负责理解用户意图并产出 SketchSpec JSON；本工具**不调用大模型**，
    永远生成 API 正确、变量名取自 id 的脚本，从根上消除语法/API/命名错误。

    Args:
        spec_json: SketchSpec 的 JSON 字符串，结构：
          {
            "plane": "XY" | "XZ" | "YZ",        # 默认 "XY"
            "auto_solve": true,                  # 默认 true
            "primitives": [
              {"id":"l1","type":"line","start":[0,0,0],"end":[50,0,0]},
              {"id":"c1","type":"circle","center":[25,25,0],"radius":10.0}
            ],
            "constraints": [
              {"type":"length","target":"l1","value":50.0},
              {"type":"tangent","target":"c1","target2":"l1"}
            ]
          }
          几何 type ∈ {point,line,centerline,spline,rect,circle,arc,ellipse,
            ellipse_arc,fillet,chamfer,trim,offset}；约束 type ∈ {length,radius,
            angle,xpos,ypos,parallel,perpendicular,tangent,equal,horizontal,
            vertical,coincide}。id 为稳定对象引用（即变量名），须避开保留字
            doc / skt / yh_doc / YH / NCTI。

    Returns:
        JSON 字符串：{"ok": true, "script": "<NCTI Python>"} 或
        {"ok": false, "error": "<校验错误>"}。
    """
    spec, err = _parse_spec(spec_json)
    if err:
        return json.dumps({"ok": False, "error": err}, ensure_ascii=False)
    script = transpile(spec)
    return json.dumps({"ok": True, "script": script}, ensure_ascii=False)


@tool("verify_sketch", parse_docstring=False)
def verify_sketch_tool(spec_json: str) -> str:
    """对 SketchSpec(JSON) 做浅层静态验证，返回结构化问题清单。

    在转译/求解前拦截主要错误类：重复/保留 id、退化几何（零长线、非正半径/
    轴）、悬空引用（约束指向不存在的图元）、类型不匹配（如对直线加半径约束）、
    缺尺寸值。深验（读 RunSolve 反馈 / DOF / 冲突）经内核就绪后由
    run_sketch_pipeline 的 kernel 字段返回。

    Args:
        spec_json: 同 transpile_sketch 的 SketchSpec JSON 字符串。

    Returns:
        JSON 字符串：{"ok": bool, "issues":[{"level","code","message","spec_path"}]}。
    """
    spec, err = _parse_spec(spec_json)
    if err:
        return json.dumps({"ok": False, "error": err}, ensure_ascii=False)
    report = verify_spec(spec)
    return json.dumps({"ok": report.ok, "issues": _report_to_dict(report)["issues"]}, ensure_ascii=False)


@tool("run_sketch_pipeline", parse_docstring=False)
def run_sketch_pipeline_tool(spec_json: str, max_iter: int = 3) -> str:
    """闭环编排：验证 → 转译 → 有界自动修复重试，一次性给出可执行脚本。

    推荐优先调用本工具（而非单独调 transpile/verify）：它先 verify_spec，通过则
    转译并返回脚本；不通过则尝试**安全确定性修复**（当前仅剔除悬空引用约束），
    几何/数值错误回报由你（LLM）或用户修补，绝不瞎猜。最多重试 max_iter 轮。

    Args:
        spec_json: 同 transpile_sketch 的 SketchSpec JSON 字符串。
        max_iter: 最大重试轮数（默认 3）。

    Returns:
        JSON 字符串：
          {"ok": true, "iterations": N, "script": "<NCTI Python>",
           "report": {"ok": true, "issues": []},
           "kernel": {"skipped": true, "reason": "..."}
                     | {"skipped": false, "dof": int, "conflicts": [...], "degenerate": [...]}}
          或 {"ok": false, "unfixable": bool, "iterations": N,
              "report": {"ok": false, "issues": [...]},
              "kernel": {...},
              "message": "请修补 Spec 后重试"}。
          kernel 字段在内核运行时经 set_kernel_runtime 注册后返回真实深验结果，
          否则为 skipped（本环境当前即此状态）。
    """
    spec, err = _parse_spec(spec_json)
    if err:
        return json.dumps({"ok": False, "error": err}, ensure_ascii=False)
    runtime = get_kernel_runtime()
    run_solver = make_ncti_run_solver(runtime) if runtime else None
    res = SketchPipeline(max_iter=max_iter).run(spec, run_solver=run_solver)
    kernel = res.kernel
    kernel_payload = (
        {
            "skipped": kernel.skipped,
            "reason": kernel.reason,
            "dof": kernel.dof,
            "conflicts": kernel.conflicts,
            "degenerate": kernel.degenerate,
        }
        if kernel
        else {"skipped": True, "reason": "kernel status unavailable"}
    )
    payload: dict = {
        "ok": res.ok,
        "unfixable": res.unfixable,
        "iterations": res.iterations,
        "report": _report_to_dict(res.report) if res.report else None,
        "kernel": kernel_payload,
    }
    if res.ok and res.script is not None:
        payload["script"] = res.script
    else:
        payload["message"] = "Spec 未通过验证，请按 report.issues 修补后重试（≤3 轮）"
    return json.dumps(payload, ensure_ascii=False, indent=2)
