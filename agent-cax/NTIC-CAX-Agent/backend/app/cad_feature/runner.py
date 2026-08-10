"""cad_feature 运行器：进程外调用 cad_feature/cli/recognition_cli.py（架构 A）。

后端（uv 管理的 Python，可能 Linux/Docker）与装了 NCTI SDK 的 wygcleaner 环境
不是同一个 Python，因此必须经 subprocess 调 recognition_cli.py。所有调用都是同步
阻塞 IO；上层工具用 asyncio.to_thread 包裹以遵守 DeerFlow 的 blocking_io 门禁。

契约与 cli/recognition_cli.py 严格对齐：
  - recognize 子命令：打印识别结果 JSON 到 stdout，可选 --out 写文件。
  - clean 子命令：打印 {"ok","cleaned_step","removed_count",...} JSON 到 stdout。

NCTI SDK 路径（sdk_path）由 runner 注入子进程环境变量 NCTI_SDK_PATH，
CLI 自身不再读取任何外部工程的 config。
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile

from app.cad_feature.kernel import get_cad_feature_config


class CadFeatureRunnerError(RuntimeError):
    """CLI 进程非零退出或输出非 JSON。"""


def _run_cli(subcommand: str, *cli_args: str) -> dict:
    cfg = get_cad_feature_config()
    cmd = [cfg.python_path, cfg.cli_path, subcommand, *cli_args]
    # 把 NCTI SDK 路径透传给子进程（独立于外部工程，避免读取任何 config 文件）
    env = dict(os.environ)
    if cfg.sdk_path:
        env["NCTI_SDK_PATH"] = cfg.sdk_path
    try:
        proc = subprocess.run(
            cmd,
            cwd=os.path.dirname(os.path.abspath(cfg.cli_path)),
            env=env,
            capture_output=True,
            text=True,
            timeout=cfg.timeout,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as e:
        raise CadFeatureRunnerError(
            f"无法启动 CLI（python={cfg.python_path!r} 或 cli={cfg.cli_path!r} 不存在）：{e}"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise CadFeatureRunnerError(
            f"CLI 超时（>{cfg.timeout}s）：{' '.join(cmd)}"
        ) from e

    out = (proc.stdout or "").strip()
    # CLI 末尾 os._exit 规避拆卸崩溃；只有真正非零且无可解析输出才算失败
    if proc.returncode != 0 and not out:
        raise CadFeatureRunnerError(
            f"CLI 退出码 {proc.returncode}。stderr:\n{proc.stderr[-2000:]}"
        )
    try:
        return json.loads(out)
    except json.JSONDecodeError as e:
        raise CadFeatureRunnerError(
            f"CLI 输出不是合法 JSON（退出码 {proc.returncode}）：\n{out[:2000]}"
        ) from e


def recognize(
    stp_path: str,
    feature_type: str,
    method: str = "geometry",
    params: dict | None = None,
) -> dict:
    """识别几何特征，返回识别结果 dict（对齐 docs 契约 5.1）。"""
    params_json = json.dumps(params or {}, ensure_ascii=False)
    return _run_cli(
        "recognize",
        "--stp", stp_path,
        "--type", feature_type,
        "--method", method,
        "--params", params_json,
    )


def clean(
    stp_path: str,
    recognition: dict,
    output_step_path: str,
) -> dict:
    """按识别 JSON 清理特征并导出 STEP，返回 {"ok","cleaned_step","removed_count"}。"""
    with tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8"
    ) as tf:
        json.dump(recognition, tf, ensure_ascii=False)
        rec_path = tf.name
    try:
        return _run_cli(
            "clean",
            "--stp", stp_path,
            "--recognition", rec_path,
            "--out", output_step_path,
        )
    finally:
        try:
            os.unlink(rec_path)
        except OSError:
            pass
