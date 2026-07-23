"""Tests for the cad_feature tool layer (recognize / clean).

Mock the subprocess runner so these stay pure unit tests — no NCTI SDK, no
Windows, no real STP. They lock down the JSON contract that
``recognition_cli.py`` emits and that ``tools.py`` forwards to the agent,
plus the kernel config resolution and runner command assembly.
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from app.cad_feature import (
    CadFeatureConfig,
    CadFeatureRunnerError,
    clean,
    clean_cad_features_tool,
    clear_cad_feature_config,
    get_cad_feature_config,
    recognize,
    recognize_cad_features_tool,
    set_cad_feature_config,
)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

_RECOGNIZE_RESULT = {
    "ok": True,
    "source_file": "part.stp",
    "feature_type": "fillet",
    "method": "kernel_FindFillets",
    "features": [
        {
            "id": 1,
            "object_name": "target",
            "cell_id": 6,
            "face_type": "圆柱面(圆角)",
            "radius": 3.0,
            "confidence": 1.0,
        }
    ],
    "summary": {"count": 1, "by_type": {"圆柱面(圆角)": 1}},
}

_CLEAN_RESULT = {
    "ok": True,
    "cleaned_step": "/mnt/user-data/outputs/part_cleaned.step",
    "removed_count": 1,
    "file_exists": True,
}


@pytest.fixture(autouse=True)
def _reset_config():
    """Each test starts from a clean config singleton (no injection leak)."""
    clear_cad_feature_config()
    yield
    clear_cad_feature_config()


def _set_cfg(cli: str = "/fake/cli.py", python: str = "/fake/python"):
    set_cad_feature_config(cli_path=cli, python_path=python, timeout=30)


class _FakeProc:
    def __init__(self, stdout: str, returncode: int = 0, stderr: str = ""):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


# ---------------------------------------------------------------------------
# kernel config
# ---------------------------------------------------------------------------

def test_config_explicit_injection_wins():
    set_cad_feature_config(cli_path="/injected/cli.py", python_path="/p/py", timeout=42)
    cfg = get_cad_feature_config()
    assert cfg.cli_path == "/injected/cli.py"
    assert cfg.python_path == "/p/py"
    assert cfg.timeout == 42


def test_config_env_vars_when_not_injected(monkeypatch):
    monkeypatch.setenv("CAD_FEATURE_CLI", "/env/cli.py")
    monkeypatch.setenv("CAD_FEATURE_PYTHON", "/env/python")
    monkeypatch.setenv("CAD_FEATURE_TIMEOUT", "120")
    cfg = get_cad_feature_config()
    assert cfg.cli_path == "/env/cli.py"
    assert cfg.python_path == "/env/python"
    assert cfg.timeout == 120


def test_config_bad_timeout_falls_back(monkeypatch):
    monkeypatch.setenv("CAD_FEATURE_CLI", "/x/cli.py")
    monkeypatch.setenv("CAD_FEATURE_PYTHON", "/x/python")
    monkeypatch.setenv("CAD_FEATURE_TIMEOUT", "not-an-int")
    cfg = get_cad_feature_config()
    assert cfg.timeout == 300  # default on ValueError


# ---------------------------------------------------------------------------
# runner command assembly
# ---------------------------------------------------------------------------

def test_recognize_assembles_subcommand_and_args():
    _set_cfg()
    with patch("app.cad_feature.runner.subprocess.run") as run:
        run.return_value = _FakeProc(json.dumps(_RECOGNIZE_RESULT))
        res = recognize("/mnt/u/part.stp", "fillet", "ai", {"min_radius": 1.0})
    cmd = run.call_args.args[0]
    assert cmd == [
        "/fake/python", "/fake/cli.py", "recognize",
        "--stp", "/mnt/u/part.stp",
        "--type", "fillet",
        "--method", "ai",
        "--params", json.dumps({"min_radius": 1.0}, ensure_ascii=False),
    ]
    assert res == _RECOGNIZE_RESULT


def test_clean_writes_recognition_to_tempfile_and_passes_path():
    _set_cfg()
    with patch("app.cad_feature.runner.subprocess.run") as run, \
         patch("app.cad_feature.runner.tempfile.NamedTemporaryFile") as tf:
        tf.return_value.__enter__.return_value.name = "/tmp/rec.json"
        run.return_value = _FakeProc(json.dumps(_CLEAN_RESULT))
        res = clean("/mnt/u/part.stp", _RECOGNIZE_RESULT, "/mnt/o/out.step")
    cmd = run.call_args.args[0]
    assert cmd[:5] == [
        "/fake/python", "/fake/cli.py", "clean",
        "--stp", "/mnt/u/part.stp",
    ]
    # recognition json is passed by path, not inline
    assert "--recognition" in cmd
    rec_idx = cmd.index("--recognition")
    assert cmd[rec_idx + 1] == "/tmp/rec.json"
    assert "--out" in cmd
    out_idx = cmd.index("--out")
    assert cmd[out_idx + 1] == "/mnt/o/out.step"
    assert res == _CLEAN_RESULT


def test_runner_raises_on_non_json_output():
    _set_cfg()
    with patch("app.cad_feature.runner.subprocess.run") as run:
        run.return_value = _FakeProc("not json at all")
        with pytest.raises(CadFeatureRunnerError, match="不是合法 JSON"):
            recognize("/p.stp", "fillet")


def test_runner_raises_on_missing_python():
    _set_cfg(python="/does/not/exist/python")
    with patch("app.cad_feature.runner.subprocess.run", side_effect=FileNotFoundError("no such file")):
        with pytest.raises(CadFeatureRunnerError, match="无法启动 CLI"):
            recognize("/p.stp", "fillet")


def test_runner_raises_on_timeout():
    _set_cfg()
    with patch("app.cad_feature.runner.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=[], timeout=30)):
        with pytest.raises(CadFeatureRunnerError, match="超时"):
            recognize("/p.stp", "fillet")


def test_runner_tolerates_nonzero_exit_with_json_output():
    """CLI ends with os._exit(rc); a nonzero code WITH valid JSON output is OK
    (matches recognition_cli.py's os._exit(1) on result.ok=False path)."""
    _set_cfg()
    err_payload = {"ok": False, "error": "feature not supported"}
    with patch("app.cad_feature.runner.subprocess.run") as run:
        run.return_value = _FakeProc(json.dumps(err_payload), returncode=1)
        res = recognize("/p.stp", "chamfer")
    assert res == err_payload


def test_runner_fails_on_nonzero_exit_and_empty_output():
    _set_cfg()
    with patch("app.cad_feature.runner.subprocess.run") as run:
        run.return_value = _FakeProc("", returncode=139, stderr="segfault")
        with pytest.raises(CadFeatureRunnerError, match="退出码 139"):
            recognize("/p.stp", "fillet")


# ---------------------------------------------------------------------------
# tools (JSON contract surfaced to the agent)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recognize_tool_returns_json_contract():
    with patch("app.cad_feature.tools.recognize", return_value=_RECOGNIZE_RESULT):
        out = await recognize_cad_features_tool.ainvoke(
            {"stp_path": "/p.stp", "feature_type": "fillet", "method": "ai", "params_json": "{}"}
        )
    data = json.loads(out)
    assert data["ok"] is True
    assert data["feature_type"] == "fillet"
    assert data["features"][0]["cell_id"] == 6
    assert data["summary"]["count"] == 1


@pytest.mark.asyncio
async def test_clean_tool_returns_json_contract():
    with patch("app.cad_feature.tools.clean", return_value=_CLEAN_RESULT):
        out = await clean_cad_features_tool.ainvoke(
            {
                "stp_path": "/p.stp",
                "recognition_json": json.dumps(_RECOGNIZE_RESULT),
                "output_step_path": "/o/out.step",
            }
        )
    data = json.loads(out)
    assert data["ok"] is True
    assert data["cleaned_step"] == "/mnt/user-data/outputs/part_cleaned.step"
    assert data["removed_count"] == 1


@pytest.mark.asyncio
async def test_recognize_tool_bad_params_json_returns_structured_error():
    with patch("app.cad_feature.tools.recognize") as rec:
        out = await recognize_cad_features_tool.ainvoke(
            {"stp_path": "/p.stp", "feature_type": "fillet", "method": "ai", "params_json": "not-json{"}
        )
    rec.assert_not_called()  # fails fast before hitting the runner
    data = json.loads(out)
    assert data["ok"] is False
    assert "params_json" in data["error"]


@pytest.mark.asyncio
async def test_clean_tool_bad_recognition_json_returns_structured_error():
    with patch("app.cad_feature.tools.clean") as cln:
        out = await clean_cad_features_tool.ainvoke(
            {
                "stp_path": "/p.stp",
                "recognition_json": "{broken",
                "output_step_path": "/o/out.step",
            }
        )
    cln.assert_not_called()
    data = json.loads(out)
    assert data["ok"] is False
    assert "recognition_json" in data["error"]


@pytest.mark.asyncio
async def test_recognize_tool_runner_error_returns_structured_error():
    with patch("app.cad_feature.tools.recognize", side_effect=CadFeatureRunnerError("boom")):
        out = await recognize_cad_features_tool.ainvoke(
            {"stp_path": "/p.stp", "feature_type": "fillet", "method": "ai", "params_json": "{}"}
        )
    data = json.loads(out)
    assert data["ok"] is False
    assert "boom" in data["error"]


@pytest.mark.asyncio
async def test_clean_tool_runner_error_returns_structured_error():
    with patch("app.cad_feature.tools.clean", side_effect=CadFeatureRunnerError("boom")):
        out = await clean_cad_features_tool.ainvoke(
            {
                "stp_path": "/p.stp",
                "recognition_json": json.dumps(_RECOGNIZE_RESULT),
                "output_step_path": "/o/out.step",
            }
        )
    data = json.loads(out)
    assert data["ok"] is False
    assert "boom" in data["error"]
