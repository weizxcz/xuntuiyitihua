#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Core utilities for the optimized server-side blind-hole pipeline.

This module is not the recommended command-line entry point.  The official
server batch entry point is:

    optimized_pipeline/fast_blindhole_pipeline.py

The code kept here is the shared low-level layer:

1. Backend API wrapper.
2. NCTI initialization and assembly splitting.
3. v15_23 blind-hole recognition bridge.
4. STEP ADVANCED_FACE id to NCTI cell_id mapping.
5. Training JSON construction.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import mimetypes
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from xml.sax.saxutils import escape


ROOT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from blind_hole.detect_blind_holes_and_export_stp_v15_23 import (  # noqa: E402
    BlindHoleRecognizer,
    StepParser,
    apply_corrected_v13_postprocess,
    select_exact_faces_from_holes,
)
from function.on_find_blind_hole_stp import _build_step_face_object_cell_map  # noqa: E402


DEFAULT_API_BASE_URL = os.environ.get("GDM_API_BASE_URL", "http://localhost:5060/api")
DEFAULT_USER = "\u7530\u4e00\u51b0"
DEFAULT_FEATURE_TYPE = "blind_hole"
DEFAULT_FEATURE_NAME = "\u76f2\u5b54"
DEFAULT_CATEGORY_ID = 12
DEFAULT_SOURCE_TYPE = "private"
DEFAULT_INDUSTRY = "unknown"
DEFAULT_PRODUCT_TYPE = "unknown"
SERVER_STEP_DIR = "/mnt/data/geometry_data/steps/step_files"
SERVER_JSON_DIR = "/mnt/data/geometry_data/steps/json_files"


@dataclass
class LeafSolid:
    ncti_name: Any
    path_names: list[str]


@dataclass
class StpTarget:
    key: str
    path: Path
    source_path: Path
    was_split: bool
    solid_path_names: list[str]


def iter_stp_files(input_dir: Path) -> Iterable[Path]:
    for path in sorted(input_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".stp", ".step"}:
            yield path


def sanitize_filename_part(value: Any) -> str:
    text = str(value).strip()
    text = re.sub(r"[<>:\"/\\|?*\x00-\x1f]+", "_", text)
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"_+", "_", text).strip("._ ")
    return text or "unnamed"


def unique_stem(stem: str, used: set[str]) -> str:
    candidate = stem
    index = 2
    while candidate.lower() in used:
        candidate = f"{stem}_{index:03d}"
        index += 1
    used.add(candidate.lower())
    return candidate


def safe_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


class NctiSolidSplitter:
    def __init__(self, ncti: Any):
        self.NCTI = ncti

    def load_doc(self) -> Any:
        doc = self.NCTI.Document()
        doc.New("OCC", "DCM", "GMSH")
        doc.SetImportAssemelFile(1)
        return doc

    def import_stp(self, doc: Any, stp_path: Path) -> None:
        doc.RunCommand("cmd_ncti_import_file", str(stp_path), 2)

    def display_name(self, object_api: Any, node: Any) -> str:
        try:
            names = object_api.GetDisplayName(node)
            if isinstance(names, (list, tuple)) and names:
                return sanitize_filename_part(names[0])
            if names:
                return sanitize_filename_part(names)
        except Exception:
            pass
        return sanitize_filename_part(node)

    def child_groups(self, group_api: Any, node: Any | None = None) -> list[Any]:
        try:
            if node is None:
                return safe_list(group_api.GetCurSubGroup())
            return safe_list(group_api.GetCurSubGroup(node))
        except Exception:
            return []

    def child_solids(self, group_api: Any, node: Any) -> list[Any]:
        try:
            return safe_list(group_api.GetCurSubObject(node))
        except Exception:
            return []

    def collect_leaf_solids(
        self,
        group_api: Any,
        object_api: Any,
        root_nodes: list[Any],
    ) -> tuple[list[LeafSolid], bool]:
        leaves: list[LeafSolid] = []
        saw_branch = len(root_nodes) > 1
        include_root_name = len(root_nodes) > 1

        def walk(node: Any, path_names: list[str]) -> None:
            nonlocal saw_branch
            sub_groups = self.child_groups(group_api, node)
            solids = self.child_solids(group_api, node)
            if len(sub_groups) + len(solids) > 1:
                saw_branch = True

            for solid in solids:
                solid_name = self.display_name(object_api, solid)
                leaves.append(LeafSolid(solid, path_names + [solid_name]))

            for child_group in sub_groups:
                child_name = self.display_name(object_api, child_group)
                walk(child_group, path_names + [child_name])

        for root in root_nodes:
            root_path = [self.display_name(object_api, root)] if include_root_name else []
            walk(root, root_path)

        return leaves, saw_branch

    def export_solid(self, doc: Any, output_path: Path, solid_name: Any) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            doc.RunCommand("cmd_ncti_export_file", str(output_path), solid_name)
        except Exception:
            doc.RunCommand("cmd_ncti_export_file", str(output_path), [solid_name])
        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise RuntimeError(f"NCTI export did not create a valid STP file: {output_path}")

    def split_one_stp(self, stp_path: Path, output_dir: Path, used_stems: set[str]) -> list[StpTarget]:
        doc = self.load_doc()
        try:
            self.import_stp(doc, stp_path)
            group_api = self.NCTI.RootGroup(doc)
            object_api = self.NCTI.Object(doc)
            root_nodes = self.child_groups(group_api)
            if not root_nodes:
                raise RuntimeError("NCTI import produced no root groups")

            leaves, saw_branch = self.collect_leaf_solids(group_api, object_api, root_nodes)
            if not leaves:
                raise RuntimeError("NCTI import produced no leaf solids")

            source_stem = sanitize_filename_part(stp_path.stem)
            if len(leaves) == 1 and not saw_branch:
                key = unique_stem(source_stem, used_stems)
                return [
                    StpTarget(
                        key=key,
                        path=stp_path,
                        source_path=stp_path,
                        was_split=False,
                        solid_path_names=leaves[0].path_names,
                    )
                ]

            targets: list[StpTarget] = []
            for leaf in leaves:
                raw_stem = f"{source_stem}__{'_'.join(leaf.path_names)}"
                output_stem = unique_stem(sanitize_filename_part(raw_stem), used_stems)
                output_path = output_dir / f"{output_stem}.stp"
                self.export_solid(doc, output_path, leaf.ncti_name)
                targets.append(
                    StpTarget(
                        key=output_stem,
                        path=output_path,
                        source_path=stp_path,
                        was_split=True,
                        solid_path_names=leaf.path_names,
                    )
                )
            return targets
        finally:
            try:
                doc.Delete()
            except Exception:
                pass


def xlsx_col_name(index: int) -> str:
    name = ""
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def xlsx_cell(value: Any, row: int, col: int) -> str:
    cell_ref = f"{xlsx_col_name(col)}{row}"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{cell_ref}"><v>{value}</v></c>'
    text = escape("" if value is None else str(value))
    return f'<c r="{cell_ref}" t="inlineStr"><is><t>{text}</t></is></c>'


def write_failures_xlsx(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    headers = ["index", "key", "stp_path", "source_stp_path", "reason", "was_split", "error"]
    table = [headers]
    for index, item in enumerate(rows, 1):
        table.append(
            [
                index,
                item.get("key", ""),
                item.get("stp_path", ""),
                item.get("source_stp_path", ""),
                item.get("reason", ""),
                item.get("was_split", ""),
                item.get("error", ""),
            ]
        )

    rows_xml = []
    for row_index, row in enumerate(table, 1):
        cells = "".join(xlsx_cell(value, row_index, col_index) for col_index, value in enumerate(row, 1))
        rows_xml.append(f'<row r="{row_index}">{cells}</row>')

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(rows_xml)}</sheetData>"
        "</worksheet>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="failures" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types_xml)
        archive.writestr("_rels/.rels", rels_xml)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)


def compute_sha256(file_path: Path) -> str:
    sha256 = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def load_or_create_label_base(*, part_id: int | str, source_file: str) -> dict[str, Any]:
    return {
        "part_id": part_id,
        "source_file": source_file,
        "feature_mapping": {},
        "seg": {},
        "inst": [],
        "bottom": {},
    }


def normalize_hole_instances(raw_holes: list[dict[str, Any]]) -> list[dict[str, list[int]]]:
    normalized = []
    for hole in raw_holes:
        instance_faces = hole.get("instance_faces") or []
        bottom_faces = hole.get("bottom_faces") or []
        normalized.append(
            {
                "instance_faces": sorted({int(face) for face in instance_faces}),
                "bottom_faces": sorted({int(face) for face in bottom_faces}),
            }
        )
    return normalized


def _normalized_square_matrix(existing: list[list[int]], size: int) -> list[list[int]]:
    matrix = [[0 for _ in range(size)] for _ in range(size)]
    for row_index, row in enumerate(existing[:size]):
        for col_index, value in enumerate(row[:size]):
            matrix[row_index][col_index] = int(value)
    return matrix


def build_training_label_json(
    *,
    base_json: dict[str, Any],
    hole_instances: list[dict[str, Any]],
    category_id: int = DEFAULT_CATEGORY_ID,
    feature_name: str = DEFAULT_FEATURE_NAME,
) -> dict[str, Any]:
    data = dict(base_json)
    data["feature_mapping"] = dict(data.get("feature_mapping") or {})
    data["feature_mapping"][feature_name] = category_id

    normalized = normalize_hole_instances(hole_instances)
    all_faces = sorted({face for hole in normalized for face in hole["instance_faces"]})
    max_face_id = max(all_faces, default=-1)
    size = max(max_face_id + 1, len(data.get("inst") or []))

    seg = {str(index): 0 for index in range(size)}
    seg.update({str(key): value for key, value in (data.get("seg") or {}).items()})

    bottom = {str(index): 0 for index in range(size)}
    bottom.update({str(key): value for key, value in (data.get("bottom") or {}).items()})

    inst = _normalized_square_matrix(data.get("inst") or [], size)

    for hole in normalized:
        faces = hole["instance_faces"]
        for face in faces:
            seg[str(face)] = category_id
        for bottom_face in hole["bottom_faces"]:
            bottom[str(bottom_face)] = 1
            seg[str(bottom_face)] = category_id
        for left in faces:
            for right in faces:
                inst[left][right] = 1

    data["seg"] = seg
    data["inst"] = inst
    data["bottom"] = bottom
    return data


def save_label_json_locally(json_data: Any, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(ensure_training_label_json_list(json_data), handle, ensure_ascii=False, indent=2)
    return output_path


def ensure_training_label_json_list(json_data: Any) -> list[Any]:
    if isinstance(json_data, list):
        return json_data
    return [json_data]


@dataclass
class SourcePart:
    stp_path: Path
    original_part: dict[str, Any] | None = None

    @property
    def industry(self) -> str | None:
        return (self.original_part or {}).get("industry")

    @property
    def product_type(self) -> str | None:
        return (self.original_part or {}).get("product_type")

    @property
    def created_by(self) -> str | None:
        return (self.original_part or {}).get("created_by")


@dataclass
class RegisteredPart:
    id: int | str
    name: str
    hash_id: str
    format: str
    file_path: str | None = None
    data: dict[str, Any] | None = None


class RouterAPI:
    """Client for endpoints defined in api/router.py."""

    def __init__(self, base_url: str = DEFAULT_API_BASE_URL):
        self.base_url = base_url.rstrip("/")

    def _post_json(self, path: str, payload: dict[str, Any], timeout: int = 60) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        return self._open_json(req, timeout=timeout)

    @staticmethod
    def _open_json(req: urllib.request.Request, timeout: int) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            data = {}
            try:
                data = json.loads(raw)
            except Exception:
                pass
            message = data.get("message") if isinstance(data, dict) else raw
            error = RuntimeError(f"HTTP {exc.code}: {message or raw}")
            setattr(error, "status", exc.code)
            setattr(error, "data", data)
            raise error from exc

    def get_part(self, part_id: int | str) -> dict[str, Any]:
        return self._post_json("/parts/get_part", {"part_id": part_id}, timeout=30)["data"]

    def list_parts(self, *, skip: int = 0, limit: int = 1000) -> list[dict[str, Any]]:
        return self._post_json("/parts/list_parts", {"skip": skip, "limit": limit}, timeout=60)["data"]

    def find_part_by_hash(self, hash_id: str, *, page_size: int = 1000) -> dict[str, Any] | None:
        skip = 0
        while True:
            rows = self.list_parts(skip=skip, limit=page_size)
            for row in rows:
                if row.get("hash_id") == hash_id:
                    return row
            if len(rows) < page_size:
                return None
            skip += page_size

    def download_stp_by_part_id(self, part_id: int | str, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        body = json.dumps({"part_id": part_id}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/label/send_solid_file",
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            filename = _filename_from_content_disposition(resp.headers.get("Content-Disposition")) or f"{part_id}.stp"
            path = output_dir / filename
            with path.open("wb") as handle:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
        return path

    def upload_stp_file(self, stp_path: Path) -> dict[str, Any]:
        boundary = "----BlindHoleBatchBoundary"
        content_type = mimetypes.guess_type(stp_path.name)[0] or "application/octet-stream"
        file_bytes = stp_path.read_bytes()
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{stp_path.name}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/label/upload_file",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            return self._open_json(req, timeout=180)["data"]
        except RuntimeError as exc:
            if getattr(exc, "status", None) == 409:
                data = getattr(exc, "data", {}) or {}
                if isinstance(data.get("data"), dict):
                    return data["data"]
            raise

    def add_part(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post_json("/parts/add_part", payload, timeout=60)["data"]

    def add_or_get_part(self, payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        try:
            return self.add_part(payload), True
        except RuntimeError as exc:
            if getattr(exc, "status", None) != 409:
                raise
            existing = self.find_part_by_hash(payload["hash_id"])
            if existing is None:
                raise RuntimeError(
                    "add_part returned 409 but existing part could not be found by hash_id. "
                    "Consider adding a /parts/get_part_by_hash endpoint."
                ) from exc
            return existing, False

    def modify_part(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post_json("/parts/modify_part", payload, timeout=60)["data"]

    def update_feature_label(
        self,
        *,
        part_id: int | str,
        feature_type: str,
        status: str,
        modified_by: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "part_id": part_id,
            "feature_type": feature_type,
            "status": status,
        }
        if modified_by:
            payload["modified_by"] = modified_by
        return self._post_json("/parts/update_feature_label", payload, timeout=60)["data"]

    def save_label_json(
        self,
        *,
        name: str,
        feature_type: str,
        industry: str,
        user: str,
        json_data: Any,
    ) -> dict[str, Any]:
        return self._post_json(
            "/label/save_json",
            {
                "name": name,
                "feature_type": feature_type,
                "industry": industry,
                "user": user,
                "json_data": ensure_training_label_json_list(json_data),
            },
            timeout=60,
        )

def _filename_from_content_disposition(value: str | None) -> str | None:
    if not value:
        return None
    marker = "filename*=UTF-8''"
    if marker in value:
        from urllib.parse import unquote

        return unquote(value.split(marker, 1)[1].strip())
    marker = "filename="
    if marker in value:
        return value.split(marker, 1)[1].strip().strip('"')
    return None


def import_ncti() -> Any:
    config_error: Exception | None = None
    try:
        from config.config_load import global_scope, init_ncti_config, load_config_basic  # type: ignore

        ncti = global_scope.get("NCTI")
        if ncti is not None:
            return ncti
        ncti = init_ncti_config()
        if ncti is not None:
            global_scope["NCTI"] = ncti
            return ncti
        try:
            cfg = load_config_basic()
            config_error = RuntimeError(f"config.config_load returned no NCTI. system_config={cfg}")
        except Exception as exc:
            config_error = exc
    except Exception as exc:
        config_error = exc

    try:
        import ncti_python as NCTI  # type: ignore
        try:
            from config.config_load import load_config_basic  # type: ignore

            cfg = load_config_basic()
            path_cfg = cfg.get("ncti_path_config", {}) if isinstance(cfg, dict) else {}
            dll_path = path_cfg.get("dllpath")
            if dll_path:
                NCTI.Init(dll_path)
        except Exception:
            pass
        return NCTI
    except ImportError as exc:
        raise RuntimeError(
            "NCTI module is not available in this Python environment. "
            "The pipeline first tried config.config_load/system_config.json and then direct import. "
            f"config_load_error={config_error!r}"
        ) from exc


def infer_product_type(stp_path: Path, input_dir: Path | None, fallback: str) -> str:
    if input_dir is None:
        return fallback
    try:
        rel = stp_path.relative_to(input_dir)
    except ValueError:
        return fallback
    if len(rel.parts) > 1:
        return rel.parts[0]
    return fallback


def detect_blind_holes_per_hole(stp_path: Path) -> tuple[StepParser, list[dict[str, Any]]]:
    step = StepParser(str(stp_path))
    step.parse()
    recognizer = BlindHoleRecognizer(step)
    raw_holes = recognizer.recognize()
    holes, _, _ = apply_corrected_v13_postprocess(step, recognizer, raw_holes)
    if not holes:
        return step, []
    _, per_hole = select_exact_faces_from_holes(step, recognizer, holes, include_chamfer=True)
    return step, per_hole


def build_step_to_cell_map(ncti: Any, step_parser: StepParser, stp_path: Path) -> dict[int, tuple[str, int]]:
    splitter = NctiSolidSplitter(ncti)
    doc = splitter.load_doc()
    try:
        splitter.import_stp(doc, stp_path)
        face_map, _, _, _ = _build_step_face_object_cell_map(step_parser, doc)
        return face_map
    finally:
        try:
            doc.Delete()
        except Exception:
            pass


def per_hole_to_cell_instances(
    per_hole: list[dict[str, Any]],
    face_map: dict[int, tuple[str, int]],
) -> list[dict[str, list[int]]]:
    instances: list[dict[str, list[int]]] = []
    for hole in per_hole:
        source_faces = hole.get("source_faces") or hole.get("export_faces") or []
        bottom_faces = hole.get("bottom_faces") or hole.get("compound_bottom_faces") or []
        instance_cell_ids = []
        bottom_cell_ids = []
        missing = []
        for step_face in source_faces:
            mapped = face_map.get(step_face)
            if mapped is None:
                missing.append(step_face)
                continue
            instance_cell_ids.append(int(mapped[1]))
        for step_face in bottom_faces:
            mapped = face_map.get(step_face)
            if mapped is None:
                missing.append(step_face)
                continue
            bottom_cell_ids.append(int(mapped[1]))
        if missing:
            raise RuntimeError(f"Missing STEP->cell_id mapping for faces: {sorted(set(missing))}")
        instances.append(
            {
                "instance_faces": sorted(set(instance_cell_ids)),
                "bottom_faces": sorted(set(bottom_cell_ids)),
            }
        )
    return instances


def detect_hole_instances(ncti: Any, stp_path: Path) -> list[dict[str, list[int]]]:
    step_parser, per_hole = detect_blind_holes_per_hole(stp_path)
    if not per_hole:
        return []
    face_map = build_step_to_cell_map(ncti, step_parser, stp_path)
    return per_hole_to_cell_instances(per_hole, face_map)


def load_sources_from_input_dir(
    input_dir: Path,
    *,
    api: RouterAPI | None = None,
    lookup_source_metadata: bool = True,
) -> list[SourcePart]:
    sources: list[SourcePart] = []
    for path in iter_stp_files(input_dir):
        original_part = None
        if api is not None and lookup_source_metadata:
            try:
                source_hash = compute_sha256(path)
                original_part = api.find_part_by_hash(source_hash)
                if original_part:
                    print(
                        "[metadata] "
                        f"{path.name} -> part_id={original_part.get('id')} "
                        f"industry={original_part.get('industry')} "
                        f"product_type={original_part.get('product_type')}"
                    )
            except Exception as exc:
                print(f"[metadata-warning] failed to lookup source metadata for {path}: {exc}")
        sources.append(SourcePart(path, original_part=original_part))
    return sources


def source_meta_dedupe_key(meta: dict[str, Any], fallback_name: str = "") -> str | None:
    hash_id = meta.get("hash_id")
    if hash_id:
        return f"hash:{hash_id}"
    part_id = meta.get("id")
    if part_id is not None:
        return f"part:{part_id}"
    if fallback_name:
        return f"name:{fallback_name}"
    return None


def expected_label_json_path(
    *,
    json_root: Path,
    user: str,
    industry: str | None,
    feature_type: str,
    stp_name: str,
) -> Path:
    return json_root / user / (industry or DEFAULT_INDUSTRY) / feature_type / f"{Path(stp_name).stem}.json"


def label_json_exists(meta: dict[str, Any], *, json_root: Path, user: str, feature_type: str) -> bool:
    name = str(meta.get("name") or "")
    if not name:
        return False
    return expected_label_json_path(
        json_root=json_root,
        user=user,
        industry=meta.get("industry") or DEFAULT_INDUSTRY,
        feature_type=feature_type,
        stp_name=name,
    ).is_file()


def load_sources_from_part_ids(
    api: RouterAPI,
    part_ids: Iterable[str],
    download_dir: Path,
    *,
    skip_keys: set[str] | None = None,
    server_local_step_dir: Path | None = None,
) -> Iterable[SourcePart]:
    for raw_id in part_ids:
        part_id = raw_id.strip()
        if not part_id:
            continue
        meta = api.get_part(part_id)
        key = source_meta_dedupe_key(meta)
        if key is not None and skip_keys is not None and key in skip_keys:
            print(f"[skip-duplicate-source] {key} part_id={part_id}")
            continue
        if server_local_step_dir is not None:
            stp_path = resolve_server_local_stp_path(meta, server_local_step_dir)
        else:
            stp_path = api.download_stp_by_part_id(part_id, download_dir)
        yield SourcePart(stp_path=stp_path, original_part=meta)


def load_sources_from_all_parts(
    api: RouterAPI,
    download_dir: Path,
    *,
    failures: list[dict[str, Any]],
    max_count: int | None = None,
    page_size: int = 1000,
    skip_keys: set[str] | None = None,
    server_local_step_dir: Path | None = None,
    skip_processed: bool = False,
    only_has_blind_hole: bool = False,
    skip_existing_json: bool = False,
    server_json_dir: Path | None = None,
    user: str = DEFAULT_USER,
    feature_type: str = DEFAULT_FEATURE_TYPE,
    mark_existing_json_completed: bool = False,
) -> Iterable[SourcePart]:
    skip = 0
    seen_parts = 0
    while True:
        rows = api.list_parts(skip=skip, limit=page_size)
        for meta in rows:
            name = str(meta.get("name") or "")
            fmt = str(meta.get("format") or "").lower().lstrip(".")
            if fmt not in {"stp", "step"} and Path(name).suffix.lower() not in {".stp", ".step"}:
                continue
            if only_has_blind_hole and not bool(meta.get("has_blind_hole")):
                continue
            if skip_processed and str(meta.get("label_blind_hole_status") or "").lower() == "completed":
                print(
                    "[skip-processed-source] "
                    f"part_id={meta.get('id')} name={name} "
                    f"has_blind_hole={meta.get('has_blind_hole')} "
                    f"label_blind_hole_status={meta.get('label_blind_hole_status')}"
                )
                continue
            if skip_existing_json and server_json_dir is not None and label_json_exists(
                meta,
                json_root=server_json_dir,
                user=user,
                feature_type=feature_type,
            ):
                print(
                    "[skip-existing-json] "
                    f"part_id={meta.get('id')} name={name} "
                    f"industry={meta.get('industry')} json already exists"
                )
                if mark_existing_json_completed and meta.get("id") is not None:
                    try:
                        api.update_feature_label(
                            part_id=meta["id"],
                            feature_type=feature_type,
                            status="completed",
                            modified_by=user,
                        )
                    except Exception as exc:
                        print(f"[mark-completed-warning] part_id={meta.get('id')} name={name}: {exc}")
                continue
            if max_count is not None and seen_parts >= max_count:
                return
            seen_parts += 1
            part_id = meta.get("id")
            if part_id is None:
                continue
            key = source_meta_dedupe_key(meta, name)
            if key is not None and skip_keys is not None and key in skip_keys:
                print(f"[skip-duplicate-source] {key} part_id={part_id} name={name}")
                continue
            print(
                "[db-source] "
                f"part_id={part_id} name={name} "
                f"industry={meta.get('industry')} product_type={meta.get('product_type')}"
            )
            try:
                if server_local_step_dir is not None:
                    stp_path = resolve_server_local_stp_path(meta, server_local_step_dir)
                else:
                    stp_path = api.download_stp_by_part_id(part_id, download_dir)
            except Exception as exc:
                print(f"[source-file-failed] part_id={part_id} name={name}: {exc}")
                failures.append(
                    {
                        "key": str(part_id),
                        "stp_path": name,
                        "source_stp_path": name,
                        "reason": "source_file_failed",
                        "error": str(exc),
                    }
                )
                continue
            yield SourcePart(stp_path=stp_path, original_part=meta)
        if len(rows) < page_size:
            break
        skip += page_size


def source_dedupe_key(source: SourcePart) -> str:
    key = source_meta_dedupe_key(source.original_part or {})
    if key is not None:
        return key
    return f"path:{source.stp_path.resolve()}"


def resolve_server_local_stp_path(meta: dict[str, Any], step_dir: Path) -> Path:
    name = str(meta.get("name") or "")
    if not name:
        raise RuntimeError(f"part_id={meta.get('id')} has empty name")
    candidates = [step_dir / name]
    hash_id = str(meta.get("hash_id") or "")
    if hash_id:
        candidates.append(step_dir / f"{hash_id[:8]}_{name}")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    tried = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(f"STEP file not found for part_id={meta.get('id')} name={name}. Tried: {tried}")


def collect_existing_stems(directory: Path) -> set[str]:
    if not directory.exists():
        return set()
    return {
        path.stem.lower()
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in {".stp", ".step", ".igs"}
    }


def ensure_registered_stp_file(target_path: Path, registered_name: str) -> Path:
    expected_path = target_path.parent / registered_name
    if expected_path.resolve() == target_path.resolve():
        return target_path
    if expected_path.is_file():
        return expected_path
    expected_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target_path, expected_path)
    return expected_path


def register_final_stp(
    *,
    api: RouterAPI,
    target: StpTarget,
    source: SourcePart,
    industry: str,
    product_type: str,
    user: str,
    source_type: str,
    dry_run: bool,
    upload_final_stp: bool = True,
) -> RegisteredPart:
    local_hash = compute_sha256(target.path)
    if dry_run:
        return RegisteredPart(
            id=target.key,
            name=target.path.name,
            hash_id=local_hash,
            format=target.path.suffix.lower().lstrip("."),
            file_path=str(target.path),
        )

    uploaded = api.upload_stp_file(target.path) if upload_final_stp else None
    hash_id = (uploaded or {}).get("hash_id") or local_hash
    name = (uploaded or {}).get("name") or target.path.name
    fmt = (uploaded or {}).get("format") or target.path.suffix.lower().lstrip(".")
    payload = {
        "hash_id": hash_id,
        "name": name,
        "format": fmt,
        "industry": industry,
        "product_type": product_type,
        "is_open_source": bool((source.original_part or {}).get("is_open_source", False)),
        "source_type": (source.original_part or {}).get("source_type") or source_type,
        "created_by": user,
        "has_blind_hole": False,
    }
    part, created = api.add_or_get_part(payload)
    part_id = part.get("id")
    if created and part_id is not None:
        api.modify_part(
            {
                "part_id": part_id,
                "name": name,
                "industry": industry,
                "product_type": product_type,
                "source_type": payload["source_type"],
                "is_open_source": payload["is_open_source"],
                "modified_by": user,
            }
        )
    name = part.get("name") or name
    fmt = part.get("format") or fmt
    file_path = (uploaded or {}).get("file_path") or str(target.path)
    if not upload_final_stp:
        file_path = str(ensure_registered_stp_file(target.path, name))
    return RegisteredPart(
        id=part_id or target.key,
        name=name,
        hash_id=hash_id,
        format=fmt,
        file_path=file_path,
        data=part,
    )


def process_target(
    *,
    api: RouterAPI,
    ncti: Any,
    target: StpTarget,
    source: SourcePart,
    input_dir: Path | None,
    json_cache_dir: Path,
    industry_arg: str | None,
    product_type_arg: str | None,
    user: str,
    source_type: str,
    server_step_dir: str,
    save_local_json: bool,
    dry_run: bool,
    upload_final_stp: bool,
) -> dict[str, Any]:
    industry = source.industry or industry_arg or DEFAULT_INDUSTRY
    product_type = (
        source.product_type
        or product_type_arg
        or infer_product_type(source.stp_path, input_dir, DEFAULT_PRODUCT_TYPE)
    )

    registered = register_final_stp(
        api=api,
        target=target,
        source=source,
        industry=industry,
        product_type=product_type,
        user=user,
        source_type=source_type,
        dry_run=dry_run,
        upload_final_stp=upload_final_stp,
    )
    industry = (registered.data or {}).get("industry") or industry
    product_type = (registered.data or {}).get("product_type") or product_type

    hole_instances = detect_hole_instances(ncti, target.path)
    if not hole_instances:
        if not dry_run:
            api.update_feature_label(
                part_id=registered.id,
                feature_type=DEFAULT_FEATURE_TYPE,
                status="skipped",
                modified_by=user,
            )
        return {
            "status": "skipped",
            "reason": "no_holes",
            "part_id": registered.id,
            "stp_name": registered.name,
            "source_stp": str(target.source_path),
            "final_stp": str(target.path),
            "was_split": target.was_split,
            "stp": str(target.path),
        }

    source_file = f"{server_step_dir.rstrip('/')}/{registered.name}"
    base_json = load_or_create_label_base(part_id=registered.id, source_file=source_file)
    label_json = build_training_label_json(
        base_json=base_json,
        hole_instances=hole_instances,
        category_id=DEFAULT_CATEGORY_ID,
        feature_name=DEFAULT_FEATURE_NAME,
    )

    local_json_path = None
    if save_local_json or dry_run:
        local_json_path = save_label_json_locally(label_json, json_cache_dir / f"{Path(registered.name).stem}.json")

    api_json_path = None
    if not dry_run:
        api_result = api.save_label_json(
            name=Path(registered.name).stem,
            feature_type=DEFAULT_FEATURE_TYPE,
            industry=industry,
            user=user,
            json_data=ensure_training_label_json_list(label_json),
        )
        api_json_path = api_result.get("path")
        api.modify_part(
            {
                "part_id": registered.id,
                "has_blind_hole": True,
                "modified_by": user,
            }
        )
        api.update_feature_label(
            part_id=registered.id,
            feature_type=DEFAULT_FEATURE_TYPE,
            status="completed",
            modified_by=user,
        )

    return {
        "status": "completed",
        "part_id": registered.id,
        "hash_id": registered.hash_id,
        "stp_name": registered.name,
        "source_stp": str(target.source_path),
        "final_stp": str(target.path),
        "was_split": target.was_split,
        "blind_hole_count": len(hole_instances),
        "api_json_path": api_json_path,
        "local_json_path": str(local_json_path) if local_json_path else None,
    }


def write_summary_csv(rows: list[dict[str, Any]], path: Path) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_run_statistics(
    *,
    source_count: int,
    results: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    split_exported_stp_count: int | None = None,
) -> dict[str, int]:
    completed = [row for row in results if row.get("status") == "completed"]
    skipped = [row for row in results if row.get("status") == "skipped"]
    if split_exported_stp_count is None:
        split_exported_stp_count = len([row for row in results if row.get("was_split")])
    return {
        "source_stp_count": source_count,
        "processed_target_count": len(results),
        "completed_target_count": len(completed),
        "skipped_target_count": len(skipped),
        "failure_count": len(failures),
        "split_exported_stp_count": split_exported_stp_count,
        "json_generated_count": len([row for row in completed if row.get("local_json_path") or row.get("api_json_path")]),
    }


def write_run_statistics(stats: dict[str, int], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(stats, handle, ensure_ascii=False, indent=2)


def normalize_server_defaults(args: argparse.Namespace) -> None:
    path_arg = getattr(args, "server_local_step_dir_arg", None)
    if path_arg and args.server_local_step_dir:
        raise SystemExit("Use either positional STEP directory or --server-local-step-dir, not both.")
    if path_arg:
        args.server_local_step_dir = path_arg

    if args.server_local_step_dir:
        args.server_local_step_dir = args.server_local_step_dir.resolve()
    if args.server_local_step_dir and not (args.input_dir or args.part_ids):
        args.all_parts = True
    if args.server_local_step_dir:
        args.no_upload_final_stp = True
        args.no_local_reports = True
        if args.server_step_dir == SERVER_STEP_DIR:
            args.server_step_dir = str(args.server_local_step_dir)


def run_pipeline(args: argparse.Namespace) -> int:
    normalize_server_defaults(args)
    if args.no_upload_final_stp and not args.server_local_step_dir:
        raise SystemExit("--no-upload-final-stp requires --server-local-step-dir")

    api = RouterAPI(args.api_base_url)
    ncti = import_ncti()
    server_local_step_dir = args.server_local_step_dir.resolve() if args.server_local_step_dir else None
    split_output_dir = (
        server_local_step_dir
        if server_local_step_dir is not None and args.no_upload_final_stp
        else args.split_output_dir.resolve()
    )
    json_cache_dir = args.json_cache_dir.resolve()
    download_dir = args.download_dir.resolve()
    used_stems: set[str] = collect_existing_stems(split_output_dir) if args.no_upload_final_stp else set()
    splitter = NctiSolidSplitter(ncti)

    sources: list[SourcePart] = []
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    seen_source_keys: set[str] = set()
    source_count = 0
    input_dir = args.input_dir.resolve() if args.input_dir else None
    if input_dir:
        sources.extend(
            load_sources_from_input_dir(
                input_dir,
                api=api,
                lookup_source_metadata=not args.no_source_metadata_lookup,
            )
        )

    split_exported_stp_count = 0
    found_source = False

    def process_source(source: SourcePart, index: int | None = None, total: int | None = None) -> None:
        nonlocal split_exported_stp_count
        meta = source.original_part or {}
        prefix = f"[progress] source {index}/{total}" if index is not None and total is not None else "[source]"
        print(
            f"{prefix} part_id={meta.get('id', '')} "
            f"name={meta.get('name') or source.stp_path.name} path={source.stp_path}"
        )
        try:
            targets = splitter.split_one_stp(source.stp_path, split_output_dir, used_stems)
            split_exported_stp_count += sum(1 for target in targets if target.was_split)
            print(f"[split] source {index or source_count}: targets={len(targets)} exported={sum(1 for target in targets if target.was_split)}")
        except Exception as exc:
            failures.append(
                {
                    "key": source.stp_path.stem,
                    "stp_path": str(source.stp_path),
                    "source_stp_path": str(source.stp_path),
                    "reason": "split_failed",
                    "error": str(exc),
                }
            )
            print(f"[progress] source {index or source_count} split_failed: {exc}")
            return

        for target_index, target in enumerate(targets, 1):
            print(f"[target] source={index or source_count} target={target_index}/{len(targets)} path={target.path} split={target.was_split}")
            try:
                row = process_target(
                    api=api,
                    ncti=ncti,
                    target=target,
                    source=source,
                    input_dir=input_dir,
                    json_cache_dir=json_cache_dir,
                    industry_arg=args.industry,
                    product_type_arg=args.product_type,
                    user=args.user,
                    source_type=args.source_type,
                    server_step_dir=args.server_step_dir,
                    save_local_json=args.save_local_json,
                    dry_run=args.dry_run,
                    upload_final_stp=not args.no_upload_final_stp,
                )
                results.append(row)
                print(json.dumps(row, ensure_ascii=False))
                print(
                    f"[progress] source {index or source_count} target {target_index}/{len(targets)} "
                    f"status={row.get('status')} completed={len([item for item in results if item.get('status') == 'completed'])} "
                    f"skipped={len([item for item in results if item.get('status') == 'skipped'])} failures={len(failures)}"
                )
            except Exception as exc:
                failures.append(
                    {
                        "key": target.key,
                        "stp_path": str(target.path),
                        "source_stp_path": str(target.source_path),
                        "reason": "process_failed",
                        "was_split": target.was_split,
                        "error": str(exc),
                    }
                )
                print(f"[failed] {target.path}: {exc}")

    def process_sources(source_iter: Iterable[SourcePart], total_hint: int | None = None) -> None:
        nonlocal found_source, source_count
        total = total_hint
        for source in source_iter:
            key = source_dedupe_key(source)
            if key in seen_source_keys:
                print(f"[skip-duplicate-source] {key} {source.stp_path}")
                continue
            if args.max_sources is not None and source_count >= args.max_sources:
                return
            seen_source_keys.add(key)
            found_source = True
            source_count += 1
            process_source(source, source_count, total)

    if sources:
        print(f"[plan] local input sources={len(sources)}")
    process_sources(sources, total_hint=len(sources) if sources else None)
    if args.part_ids and (args.max_sources is None or source_count < args.max_sources):
        part_sources = list(
            load_sources_from_part_ids(
                api,
                args.part_ids.split(","),
                download_dir,
                skip_keys=seen_source_keys,
                server_local_step_dir=server_local_step_dir,
            )
        )
        print(f"[plan] part-id sources={len(part_sources)}")
        process_sources(part_sources, total_hint=source_count + len(part_sources))
    if args.all_parts and (args.max_sources is None or source_count < args.max_sources):
        all_sources = list(
            load_sources_from_all_parts(
                api,
                download_dir,
                failures=failures,
                page_size=args.list_page_size,
                skip_keys=seen_source_keys,
                server_local_step_dir=server_local_step_dir,
                skip_processed=not args.process_completed,
                only_has_blind_hole=args.only_has_blind_hole,
                skip_existing_json=args.skip_existing_json,
                server_json_dir=args.server_json_dir.resolve() if args.server_json_dir else None,
                user=args.user,
                feature_type=DEFAULT_FEATURE_TYPE,
                mark_existing_json_completed=args.mark_existing_json_completed,
            )
        )
        print(
            f"[plan] database sources to process={len(all_sources)} "
            f"precheck_failures={len(failures)} step_dir={server_local_step_dir or download_dir}"
        )
        process_sources(all_sources, total_hint=source_count + len(all_sources))

    if not found_source:
        if not args.no_local_reports:
            write_failures_xlsx(failures, args.failure_xlsx)
        raise SystemExit("No source STP files found. Use --input-dir, --part-ids, or --all-parts.")

    stats = build_run_statistics(
        source_count=source_count,
        results=results,
        failures=failures,
        split_exported_stp_count=split_exported_stp_count,
    )
    if not args.no_local_reports:
        write_summary_csv(results, args.summary_csv)
        write_run_statistics(stats, args.stats_json)
        write_failures_xlsx(failures, args.failure_xlsx)
    print(
        "[done] "
        f"sources={stats['source_stp_count']} "
        f"targets={stats['processed_target_count']} "
        f"completed={stats['completed_target_count']} "
        f"skipped={stats['skipped_target_count']} "
        f"failures={stats['failure_count']} "
        f"split_exported_stp={stats['split_exported_stp_count']} "
        f"json_generated={stats['json_generated_count']}"
    )
    if args.no_local_reports:
        print("[reports] local summary/stat/failure reports disabled")
    else:
        print(f"[summary] {args.summary_csv}")
        print(f"[stats] {args.stats_json}")
        if failures:
            print(f"[failures] {args.failure_xlsx}")
    if failures and args.strict_exit_code:
        return 2
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Split STP files, detect blind holes, generate training JSON, and update backend through api/router.py."
    )
    parser.add_argument(
        "server_local_step_dir_arg",
        nargs="?",
        type=Path,
        help=(
            "Server STEP storage directory. If provided, the pipeline automatically uses all backend parts, "
            "reads/writes STP files in this directory, saves JSON through the API, and writes no local reports."
        ),
    )
    parser.add_argument("--input-dir", type=Path, help="Local STP/STEP input directory.")
    parser.add_argument("--part-ids", help="Comma-separated backend part ids to download and process.")
    parser.add_argument(
        "--all-parts",
        action="store_true",
        help="Read STP/STEP source parts from the backend database through /parts/list_parts.",
    )
    parser.add_argument("--list-page-size", type=int, default=1000)
    parser.add_argument("--max-sources", type=int, help="Only process the first N source STP files. Useful for smoke tests.")
    parser.add_argument(
        "--no-source-metadata-lookup",
        action="store_true",
        help="Do not look up original local STP metadata by hash before processing --input-dir files.",
    )
    parser.add_argument("--download-dir", type=Path, default=ROOT_DIR / "_api_downloaded_stp")
    parser.add_argument("--split-output-dir", type=Path, default=ROOT_DIR / "api_minimal_solid_stp")
    parser.add_argument(
        "--server-local-step-dir",
        type=Path,
        help=(
            "Server-side STEP storage directory. When set with --all-parts, source files are read directly "
            "from this directory instead of downloaded through /label/send_solid_file."
        ),
    )
    parser.add_argument(
        "--no-upload-final-stp",
        action="store_true",
        help=(
            "Do not upload final STP files through /label/upload_file. Split files are written to "
            "--server-local-step-dir and part_info rows are registered by hash/name through /parts/add_part."
        ),
    )
    parser.add_argument(
        "--process-completed",
        action="store_true",
        help="Also process parts whose label_blind_hole_status is completed.",
    )
    parser.add_argument(
        "--only-has-blind-hole",
        action="store_true",
        help="Only process database rows whose existing has_blind_hole flag is true. Useful for recovery from older runs.",
    )
    parser.add_argument(
        "--skip-existing-json",
        action="store_true",
        help="Skip rows whose target blind-hole JSON already exists under --server-json-dir/user/industry/blind_hole.",
    )
    parser.add_argument(
        "--mark-existing-json-completed",
        action="store_true",
        help="When --skip-existing-json skips a row, also mark label_blind_hole_status=completed through the API.",
    )
    parser.add_argument("--json-cache-dir", type=Path, default=ROOT_DIR / "api_json_cache")
    parser.add_argument("--summary-csv", type=Path, default=ROOT_DIR / "api_pipeline_summary.csv")
    parser.add_argument("--stats-json", type=Path, default=ROOT_DIR / "api_pipeline_stats.json")
    parser.add_argument("--failure-xlsx", type=Path, default=ROOT_DIR / "api_pipeline_failures.xlsx")
    parser.add_argument("--api-base-url", default=DEFAULT_API_BASE_URL)
    parser.add_argument("--server-step-dir", default=SERVER_STEP_DIR)
    parser.add_argument("--server-json-dir", type=Path, default=SERVER_JSON_DIR)
    parser.add_argument("--industry", help="Fallback industry for local files. Backend metadata takes priority.")
    parser.add_argument("--product-type", help="Fallback product_type for local files. Backend metadata takes priority.")
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--source-type", default=DEFAULT_SOURCE_TYPE, choices=["private", "public"])
    parser.add_argument("--save-local-json", action="store_true")
    parser.add_argument(
        "--no-local-reports",
        action="store_true",
        help="Do not write local summary CSV, stats JSON, or failure XLSX reports.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not call write/update API endpoints.")
    parser.add_argument(
        "--strict-exit-code",
        action="store_true",
        help="Return a non-zero exit code when skipped/failed files are written to the failure report.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run_pipeline(parse_args()))
