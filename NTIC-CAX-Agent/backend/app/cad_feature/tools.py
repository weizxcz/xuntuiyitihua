"""LangChain 工具封装：把识别/清理暴露成 Agent 可调用的确定性工具。

与 app/sketch/tools.py 同构：工具只做「参数解析 + 调 runner + 返回结构化 JSON」，
不调用大模型。两阶段纪律（先识别给用户确认、再清理）由子 Agent 的
system_prompt 约束（见 config.yaml 的 cad-feature-cleaner）。

阻塞 IO 经 asyncio.to_thread 包裹，遵守 DeerFlow 的 blocking_io 门禁。
"""
from __future__ import annotations

import asyncio
import json

from langchain.tools import tool

from app.cad_feature.runner import CadFeatureRunnerError, clean, recognize


def _err(msg: str) -> str:
    return json.dumps({"ok": False, "error": msg}, ensure_ascii=False)


@tool("recognize_cad_features", parse_docstring=False)
async def recognize_cad_features_tool(
    stp_path: str,
    feature_type: str,
    method: str = "geometry",
    params_json: str = "{}",
) -> str:
    """识别 CAD 模型的几何特征，返回结构化 JSON 字符串。

    你（LLM）负责把用户自然语言映射到 feature_type / method / params：
      - feature_type: fillet(圆角) | chamfer(倒角) | blind_hole(盲孔) |
                      through_step(通孔) | plane | cylinder | cone | logo
      - method: geometry(几何法，确定性) | ai | hybrid（当前仅 fillet 的 geometry 已落地）
      - params_json: 半径区间等，如 '{"min_radius":1.0,"max_radius":10.0}'

    返回 JSON：{"ok":true,"features":[{"id","object_name","cell_id","face_type",
    "radius","confidence"}],"summary":{"count","by_type"}}。

    纪律：本工具只识别、**不清理**。识别结果应交给用户确认后，再调 clean_cad_features。

    Args:
        stp_path: 待识别的 STP 路径（如 /mnt/user-data/uploads/part.stp）。
        feature_type: 特征类型（见上方枚举）。
        method: 识别方法，默认 geometry。
        params_json: 附加参数 JSON 字符串，默认 "{}"。

    Returns:
        JSON 字符串：识别结果或 {"ok":false,"error":...}。
    """
    try:
        params = json.loads(params_json) if params_json else {}
    except json.JSONDecodeError as e:
        return _err(f"params_json 不是合法 JSON: {e}")
    try:
        res = await asyncio.to_thread(
            recognize, stp_path, feature_type, method, params
        )
    except CadFeatureRunnerError as e:
        return _err(f"识别运行器错误: {e}")
    return json.dumps(res, ensure_ascii=False)


@tool("clean_cad_features", parse_docstring=False)
async def clean_cad_features_tool(
    stp_path: str,
    recognition_json: str,
    output_step_path: str,
) -> str:
    """按识别结果清理 CAD 几何特征，导出清理后的 STEP 文件。

    破坏性操作：仅当用户明确说「清理/移除/删除这些特征」时才调用。入参
    recognition_json 必须是 recognize_cad_features 产出的完整 JSON 字符串。

    返回 JSON：{"ok":true,"cleaned_step":"<path>","removed_count":N} 或
    {"ok":false,"error":...}。

    Args:
        stp_path: 原始 STP 路径（清理基于此文件，不会改动源文件，产物写到 output_step_path）。
        recognition_json: recognize_cad_features 返回的完整 JSON 字符串。
        output_step_path: 清理后 STEP 输出路径（如 /mnt/user-data/outputs/part_cleaned.step）。

    Returns:
        JSON 字符串：清理结果（含产物路径与移除数量）。
    """
    try:
        recognition = json.loads(recognition_json)
    except json.JSONDecodeError as e:
        return _err(f"recognition_json 不是合法 JSON: {e}")
    try:
        res = await asyncio.to_thread(
            clean, stp_path, recognition, output_step_path
        )
    except CadFeatureRunnerError as e:
        return _err(f"清理运行器错误: {e}")
    return json.dumps(res, ensure_ascii=False)
