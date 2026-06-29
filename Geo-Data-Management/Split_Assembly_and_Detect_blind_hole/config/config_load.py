from __future__ import annotations

import ctypes
import importlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


CONFIG_ENV = "NCTI_CONFIG"
DLLPATH_ENV = "NCTI_DLLPATH"
API_PATH_ENV = "NCTI_API_PATH"
PYTHON_PATH_ENV = "NCTI_PYTHON_PATH"
INIT_PATH_ENV = "NCTI_INIT_PATH"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_path(value: str | None, base: Path | None = None) -> str | None:
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (base or _project_root()) / path
    return str(path.resolve())


def load_config_basic(config_path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Load NCTI runtime config from JSON and environment variables."""

    raw_path = config_path or os.environ.get(CONFIG_ENV)
    if raw_path:
        resolved = Path(raw_path).expanduser()
        if not resolved.is_absolute():
            resolved = _project_root() / resolved
    else:
        resolved = Path(__file__).with_name("ncti_config.json")

    data: dict[str, Any] = {}
    if resolved.exists():
        with resolved.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

    path_cfg = dict(data.get("ncti_path_config") or {})
    if os.environ.get(DLLPATH_ENV):
        path_cfg["dllpath"] = os.environ[DLLPATH_ENV]
    if os.environ.get(API_PATH_ENV):
        path_cfg["Ncti_api_path"] = os.environ[API_PATH_ENV]
    if os.environ.get(PYTHON_PATH_ENV):
        path_cfg["python_path"] = os.environ[PYTHON_PATH_ENV]
    if os.environ.get(INIT_PATH_ENV):
        path_cfg["init_path"] = os.environ[INIT_PATH_ENV]

    base = resolved.parent if resolved.exists() else _project_root()
    dllpath = _resolve_path(path_cfg.get("dllpath"), base)
    api_path = _resolve_path(path_cfg.get("Ncti_api_path") or dllpath, base)
    python_path = _resolve_path(path_cfg.get("python_path") or dllpath, base)
    init_path = _resolve_path(path_cfg.get("init_path") or dllpath, base)
    data["ncti_path_config"] = {
        "dllpath": dllpath,
        "Ncti_api_path": api_path,
        "python_path": python_path,
        "init_path": init_path,
    }
    data.setdefault(
        "linux_libraries",
        [
            "libncti_base.so",
            "libncti_object.so",
            "libncti_pubfun.so",
            "libncti_command.so",
            "libncti_occ_plugin.so",
            "libncti.so",
        ],
    )
    data.setdefault(
        "windows_libraries",
        ["ncti_command.dll", "ncti_doc_occ.dll", "ncti_occ_plugin.dll", "ncti_window.dll"],
    )
    return data


def init_ncti(config_path: str | os.PathLike[str] | None = None) -> Any:
    """Initialize NCTI on Windows or Linux.

    Linux servers should point ``dllpath`` at the directory that contains
    ``ncti_python`` and the NCTI shared libraries, or use ``NCTI_DLLPATH``.
    """

    config = load_config_basic(config_path)
    path_cfg = config["ncti_path_config"]
    dllpath = path_cfg.get("dllpath")
    api_path = path_cfg.get("Ncti_api_path") or dllpath
    python_path = path_cfg.get("python_path") or dllpath
    init_path = path_cfg.get("init_path") or dllpath
    if not dllpath:
        raise RuntimeError(
            "NCTI dllpath is not configured. Create config/ncti_config.json "
            "from ncti_config.example.json or set NCTI_DLLPATH."
        )

    for candidate in [python_path, dllpath, api_path]:
        if candidate and candidate not in sys.path:
            sys.path.insert(0, candidate)

    try:
        cdll_mode = getattr(os, "RTLD_GLOBAL", getattr(ctypes, "RTLD_GLOBAL", 0))
        cdll_mode |= getattr(os, "RTLD_LAZY", 0)
        if os.name == "nt":
            if api_path and hasattr(os, "add_dll_directory"):
                os.add_dll_directory(api_path)
            for name in config.get("windows_libraries", []):
                ctypes.CDLL(os.path.join(dllpath, name))
        else:
            for candidate in {python_path, dllpath, api_path}:
                if candidate and candidate not in sys.path:
                    sys.path.insert(0, candidate)
            for name in config.get("linux_libraries", []):
                lib_path = os.path.join(api_path or dllpath, name)
                if not os.path.exists(lib_path):
                    lib_path = os.path.join(dllpath, name)
                ctypes.CDLL(lib_path, mode=cdll_mode)

        ncti = import_ncti_python_module(python_path)
        ncti.Init(init_path)
        return ncti
    except Exception as exc:
        raise RuntimeError(
            "Failed to initialize NCTI with "
            f"dllpath={dllpath!r}, api_path={api_path!r}, "
            f"python_path={python_path!r}, init_path={init_path!r}: {exc}"
        ) from exc


def import_ncti_python_module(python_path: str | None) -> Any:
    try:
        return importlib.import_module("ncti_python")
    except ModuleNotFoundError:
        pass

    if not python_path:
        raise ModuleNotFoundError("No python_path configured for ncti_python fallback loading")

    major = sys.version_info.major
    minor = sys.version_info.minor
    candidates = [
        f"libncti_python{major}{minor}.so",
        f"libncti_python{major}.{minor}.so",
        "libncti_python.so",
        f"ncti_python{major}{minor}.so",
        f"ncti_python{major}.{minor}.so",
        "ncti_python.so",
    ]
    for name in candidates:
        module_path = os.path.join(python_path, name)
        if not os.path.exists(module_path):
            continue
        module_name = detect_python_extension_module_name(module_path) or Path(module_path).stem
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(module_name, None)
            continue
        sys.modules["ncti_python"] = module
        setattr(module, "_ncti_loaded_from", module_path)
        return module

    raise ModuleNotFoundError(
        "No ncti_python module found. Tried import ncti_python and binary candidates under "
        f"{python_path!r}: {', '.join(candidates)}"
    )


def detect_python_extension_module_name(module_path: str) -> str | None:
    """Return the extension module name exported as PyInit_<name>, if visible."""

    try:
        result = subprocess.run(
            ["nm", "-D", module_path],
            text=True,
            capture_output=True,
            check=False,
        )
    except Exception:
        return None
    for line in result.stdout.splitlines():
        if "PyInit_" not in line:
            continue
        symbol = line.rsplit(" ", 1)[-1].strip()
        if symbol.startswith("PyInit_"):
            return symbol[len("PyInit_") :]
    return None


def init_ncti_config() -> Any:
    try:
        return init_ncti()
    except Exception as exc:
        print(exc)
        return None


def get_system_config_json() -> dict[str, Any]:
    return load_config_basic()


global_scope: dict[str, Any] = {}
