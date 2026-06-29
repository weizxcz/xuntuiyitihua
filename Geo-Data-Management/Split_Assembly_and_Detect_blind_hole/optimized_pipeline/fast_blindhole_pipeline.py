#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Optimized server-side blind-hole pipeline.

The old pipeline registered every split target before blind-hole detection. That
made no-hole split parts expensive and caused duplicate-hash recovery to scan the
whole backend repeatedly. This script detects first, then registers only targets
that actually contain blind holes.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from blind_hole.pipeline_core import (  # noqa: E402
    DEFAULT_API_BASE_URL,
    DEFAULT_CATEGORY_ID,
    DEFAULT_FEATURE_NAME,
    DEFAULT_FEATURE_TYPE,
    DEFAULT_INDUSTRY,
    DEFAULT_PRODUCT_TYPE,
    DEFAULT_SOURCE_TYPE,
    DEFAULT_USER,
    SERVER_JSON_DIR,
    NctiSolidSplitter,
    RegisteredPart,
    RouterAPI,
    SourcePart,
    StpTarget,
    build_training_label_json,
    compute_sha256,
    detect_hole_instances,
    ensure_training_label_json_list,
    expected_label_json_path,
    import_ncti,
    infer_product_type,
    load_or_create_label_base,
    resolve_server_local_stp_path,
    source_meta_dedupe_key,
)


@dataclass
class DbSnapshot:
    rows: list[dict[str, Any]]
    by_hash: dict[str, dict[str, Any]]


@dataclass
class Counters:
    scanned_sources: int = 0
    selected_sources: int = 0
    split_targets: int = 0
    exported_split_stp: int = 0
    completed: int = 0
    skipped_no_holes: int = 0
    skipped_completed: int = 0
    skipped_existing_json: int = 0
    failures: int = 0


class RunLogger:
    def __init__(self, log_dir: Path):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.split_success_csv = self.log_dir / "split_success_stp.csv"
        self.split_failed_csv = self.log_dir / "split_failed.csv"
        self.detect_failed_csv = self.log_dir / "blind_hole_detect_failed.csv"
        self.results_jsonl = self.log_dir / "target_results.jsonl"
        self.summary_json = self.log_dir / "summary.json"

        self._csv_headers = {
            self.split_success_csv: [
                "source_index",
                "part_id",
                "source_name",
                "source_stp",
                "target_index",
                "target_stp",
                "was_split",
            ],
            self.split_failed_csv: ["source_index", "part_id", "source_name", "source_stp", "error"],
            self.detect_failed_csv: [
                "source_index",
                "part_id",
                "source_name",
                "source_stp",
                "target_index",
                "target_stp",
                "was_split",
                "error",
            ],
        }
        for path, headers in self._csv_headers.items():
            if not path.exists():
                with path.open("w", newline="", encoding="utf-8-sig") as handle:
                    csv.DictWriter(handle, fieldnames=headers).writeheader()

    def append_csv(self, path: Path, row: dict[str, Any]) -> None:
        headers = self._csv_headers[path]
        with path.open("a", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
            writer.writerow(row)

    def log_split_success(
        self,
        *,
        source_index: int,
        source: SourcePart,
        target_index: int,
        target: StpTarget,
    ) -> None:
        meta = source.original_part or {}
        self.append_csv(
            self.split_success_csv,
            {
                "source_index": source_index,
                "part_id": meta.get("id"),
                "source_name": meta.get("name") or source.stp_path.name,
                "source_stp": str(source.stp_path),
                "target_index": target_index,
                "target_stp": str(target.path),
                "was_split": target.was_split,
            },
        )

    def log_split_failed(self, *, source_index: int, source: SourcePart, error: Exception) -> None:
        meta = source.original_part or {}
        self.append_csv(
            self.split_failed_csv,
            {
                "source_index": source_index,
                "part_id": meta.get("id"),
                "source_name": meta.get("name") or source.stp_path.name,
                "source_stp": str(source.stp_path),
                "error": str(error),
            },
        )

    def log_detect_failed(
        self,
        *,
        source_index: int,
        source: SourcePart,
        target_index: int,
        target: StpTarget,
        error: Exception,
    ) -> None:
        meta = source.original_part or {}
        self.append_csv(
            self.detect_failed_csv,
            {
                "source_index": source_index,
                "part_id": meta.get("id"),
                "source_name": meta.get("name") or source.stp_path.name,
                "source_stp": str(source.stp_path),
                "target_index": target_index,
                "target_stp": str(target.path),
                "was_split": target.was_split,
                "error": str(error),
            },
        )

    def log_result(self, row: dict[str, Any]) -> None:
        with self.results_jsonl.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def write_summary(self, data: dict[str, Any]) -> None:
        with self.summary_json.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)


def list_all_parts(api: RouterAPI, *, page_size: int) -> DbSnapshot:
    rows: list[dict[str, Any]] = []
    by_hash: dict[str, dict[str, Any]] = {}
    skip = 0
    while True:
        page = api.list_parts(skip=skip, limit=page_size)
        rows.extend(page)
        for row in page:
            hash_id = row.get("hash_id")
            if hash_id:
                by_hash[str(hash_id)] = row
        print(f"[db] loaded={len(rows)} last_page={len(page)}")
        if len(page) < page_size:
            break
        skip += page_size
    return DbSnapshot(rows=rows, by_hash=by_hash)


def is_step_row(meta: dict[str, Any]) -> bool:
    name = str(meta.get("name") or "")
    fmt = str(meta.get("format") or "").lower().lstrip(".")
    return fmt in {"stp", "step"} or Path(name).suffix.lower() in {".stp", ".step"}


def json_exists_for_row(
    meta: dict[str, Any],
    *,
    json_root: Path,
    user: str,
    feature_type: str,
) -> bool:
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


def select_sources(
    *,
    api: RouterAPI,
    snapshot: DbSnapshot,
    step_dir: Path,
    json_root: Path,
    user: str,
    skip_completed: bool,
    only_has_blind_hole: bool,
    skip_existing_json: bool,
    repair_status_from_json: bool,
    max_sources: int | None,
    counters: Counters,
) -> list[SourcePart]:
    sources: list[SourcePart] = []
    seen: set[str] = set()
    for meta in snapshot.rows:
        counters.scanned_sources += 1
        name = str(meta.get("name") or "")
        if not is_step_row(meta):
            continue
        if only_has_blind_hole and not bool(meta.get("has_blind_hole")):
            continue
        if skip_completed and str(meta.get("label_blind_hole_status") or "").lower() == "completed":
            counters.skipped_completed += 1
            continue
        if skip_existing_json and json_exists_for_row(
            meta,
            json_root=json_root,
            user=user,
            feature_type=DEFAULT_FEATURE_TYPE,
        ):
            counters.skipped_existing_json += 1
            print(f"[skip-existing-json] part_id={meta.get('id')} name={name}")
            if repair_status_from_json and meta.get("id") is not None:
                try:
                    api.update_feature_label(
                        part_id=meta["id"],
                        feature_type=DEFAULT_FEATURE_TYPE,
                        status="completed",
                        modified_by=user,
                    )
                except Exception as exc:
                    counters.failures += 1
                    print(f"[repair-status-failed] part_id={meta.get('id')} name={name}: {exc}")
            continue

        key = source_meta_dedupe_key(meta, name)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        if max_sources is not None and len(sources) >= max_sources:
            break
        try:
            path = resolve_server_local_stp_path(meta, step_dir)
        except Exception as exc:
            counters.failures += 1
            print(f"[source-file-failed] part_id={meta.get('id')} name={name}: {exc}")
            continue
        sources.append(SourcePart(stp_path=path, original_part=meta))
    counters.selected_sources = len(sources)
    return sources


def add_or_get_part_fast(
    *,
    api: RouterAPI,
    snapshot: DbSnapshot,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    hash_id = str(payload["hash_id"])
    existing = snapshot.by_hash.get(hash_id)
    if existing is not None:
        return existing, False
    try:
        part = api.add_part(payload)
        snapshot.by_hash[hash_id] = part
        snapshot.rows.append(part)
        return part, True
    except RuntimeError as exc:
        if getattr(exc, "status", None) != 409:
            raise
        existing = api.find_part_by_hash(hash_id)
        if existing is None:
            raise RuntimeError(
                "add_part returned 409, but the duplicate row was not found by hash_id."
            ) from exc
        snapshot.by_hash[hash_id] = existing
        return existing, False


def registered_from_original(source: SourcePart, target: StpTarget) -> RegisteredPart | None:
    if target.was_split:
        return None
    meta = source.original_part or {}
    part_id = meta.get("id")
    if part_id is None:
        return None
    name = meta.get("name") or target.path.name
    hash_id = meta.get("hash_id") or compute_sha256(target.path)
    fmt = meta.get("format") or target.path.suffix.lower().lstrip(".")
    return RegisteredPart(
        id=part_id,
        name=name,
        hash_id=hash_id,
        format=fmt,
        file_path=str(target.path),
        data=meta,
    )


def register_blind_hole_target(
    *,
    api: RouterAPI,
    snapshot: DbSnapshot,
    source: SourcePart,
    target: StpTarget,
    industry: str,
    product_type: str,
    user: str,
    source_type: str,
    dry_run: bool,
) -> RegisteredPart:
    original = registered_from_original(source, target)
    if original is not None:
        return original

    hash_id = compute_sha256(target.path)
    if dry_run:
        return RegisteredPart(
            id=f"dry-{target.key}",
            name=target.path.name,
            hash_id=hash_id,
            format=target.path.suffix.lower().lstrip("."),
            file_path=str(target.path),
        )

    payload = {
        "hash_id": hash_id,
        "name": target.path.name,
        "format": target.path.suffix.lower().lstrip("."),
        "industry": industry,
        "product_type": product_type,
        "is_open_source": bool((source.original_part or {}).get("is_open_source", False)),
        "source_type": (source.original_part or {}).get("source_type") or source_type,
        "created_by": user,
        "has_blind_hole": True,
    }
    part, created = add_or_get_part_fast(api=api, snapshot=snapshot, payload=payload)
    part_id = part.get("id")
    if created and part_id is not None:
        part = api.modify_part(
            {
                "part_id": part_id,
                "name": part.get("name") or payload["name"],
                "industry": industry,
                "product_type": product_type,
                "source_type": payload["source_type"],
                "is_open_source": payload["is_open_source"],
                "modified_by": user,
                "has_blind_hole": True,
            }
        )
    return RegisteredPart(
        id=part_id or target.key,
        name=part.get("name") or target.path.name,
        hash_id=part.get("hash_id") or hash_id,
        format=part.get("format") or target.path.suffix.lower().lstrip("."),
        file_path=str(target.path),
        data=part,
    )


def process_target_detect_first(
    *,
    api: RouterAPI,
    snapshot: DbSnapshot,
    ncti: Any,
    source: SourcePart,
    target: StpTarget,
    input_dir: Path | None,
    server_step_dir: str,
    user: str,
    source_type: str,
    dry_run: bool,
    mark_no_holes: bool,
    skip_existing_json: bool,
    repair_status_from_json: bool,
    json_root: Path,
    counters: Counters,
) -> dict[str, Any]:
    industry = (
        (source.original_part or {}).get("industry")
        or DEFAULT_INDUSTRY
    )
    product_type = (
        (source.original_part or {}).get("product_type")
        or infer_product_type(source.stp_path, input_dir, DEFAULT_PRODUCT_TYPE)
    )
    existing_json_path = expected_label_json_path(
        json_root=json_root,
        user=user,
        industry=industry,
        feature_type=DEFAULT_FEATURE_TYPE,
        stp_name=target.path.name,
    )
    original_id = (source.original_part or {}).get("id")
    if skip_existing_json and existing_json_path.is_file():
        counters.skipped_existing_json += 1
        repaired_part_id = original_id if not target.was_split else None
        if repair_status_from_json and target.was_split:
            try:
                repaired_part_id = (snapshot.by_hash.get(compute_sha256(target.path)) or {}).get("id")
            except Exception as exc:
                print(f"[repair-hash-warning] path={target.path}: {exc}")
        if repair_status_from_json and repaired_part_id is not None and not dry_run:
            try:
                api.update_feature_label(
                    part_id=repaired_part_id,
                    feature_type=DEFAULT_FEATURE_TYPE,
                    status="completed",
                    modified_by=user,
                )
            except Exception as exc:
                counters.failures += 1
                print(f"[repair-status-failed] part_id={repaired_part_id} path={target.path}: {exc}")
        return {
            "status": "skipped",
            "reason": "existing_json",
            "part_id": repaired_part_id,
            "stp_name": target.path.name,
            "source_stp": str(target.source_path),
            "final_stp": str(target.path),
            "was_split": target.was_split,
            "json_path": str(existing_json_path),
        }

    detect_start = time.perf_counter()
    hole_instances = detect_hole_instances(ncti, target.path)
    detect_ms = (time.perf_counter() - detect_start) * 1000

    if not hole_instances:
        counters.skipped_no_holes += 1
        if mark_no_holes and not target.was_split and original_id is not None and not dry_run:
            api.update_feature_label(
                part_id=original_id,
                feature_type=DEFAULT_FEATURE_TYPE,
                status="skipped",
                modified_by=user,
            )
        return {
            "status": "skipped",
            "reason": "no_holes",
            "part_id": original_id,
            "stp_name": target.path.name,
            "source_stp": str(target.source_path),
            "final_stp": str(target.path),
            "was_split": target.was_split,
            "detect_ms": round(detect_ms, 3),
        }

    registered = register_blind_hole_target(
        api=api,
        snapshot=snapshot,
        source=source,
        target=target,
        industry=industry,
        product_type=product_type,
        user=user,
        source_type=source_type,
        dry_run=dry_run,
    )

    industry = (registered.data or {}).get("industry") or industry
    source_file = f"{server_step_dir.rstrip('/')}/{registered.name}"
    label_json = build_training_label_json(
        base_json=load_or_create_label_base(part_id=registered.id, source_file=source_file),
        hole_instances=hole_instances,
        category_id=DEFAULT_CATEGORY_ID,
        feature_name=DEFAULT_FEATURE_NAME,
    )

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

    counters.completed += 1
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
        "detect_ms": round(detect_ms, 3),
    }


def run(args: argparse.Namespace) -> int:
    step_dir = args.step_dir.resolve()
    if not step_dir.is_dir():
        raise SystemExit(f"STEP directory not found: {step_dir}")

    api = RouterAPI(args.api_base_url)
    ncti = import_ncti()
    splitter = NctiSolidSplitter(ncti)
    counters = Counters()
    logger = RunLogger(args.log_dir.resolve())
    started = time.perf_counter()

    snapshot = list_all_parts(api, page_size=args.list_page_size)
    sources = select_sources(
        api=api,
        snapshot=snapshot,
        step_dir=step_dir,
        json_root=args.server_json_dir.resolve(),
        user=args.user,
        skip_completed=not args.process_completed,
        only_has_blind_hole=args.only_has_blind_hole,
        skip_existing_json=args.skip_existing_json,
        repair_status_from_json=args.repair_status_from_json,
        max_sources=args.max_sources,
        counters=counters,
    )
    print(
        "[plan] "
        f"db_rows={len(snapshot.rows)} selected_sources={len(sources)} "
        f"skip_completed={counters.skipped_completed} "
        f"skip_existing_json={counters.skipped_existing_json} "
        f"source_failures={counters.failures}"
    )

    for source_index, source in enumerate(sources, 1):
        meta = source.original_part or {}
        print(
            "[progress] "
            f"source {source_index}/{len(sources)} part_id={meta.get('id')} "
            f"name={meta.get('name') or source.stp_path.name} path={source.stp_path}"
        )
        try:
            split_start = time.perf_counter()
            used_stems: set[str] = set()
            targets = splitter.split_one_stp(source.stp_path, step_dir, used_stems)
            split_ms = (time.perf_counter() - split_start) * 1000
            counters.split_targets += len(targets)
            exported = sum(1 for target in targets if target.was_split)
            counters.exported_split_stp += exported
            print(f"[split] source={source_index} targets={len(targets)} exported={exported} split_ms={split_ms:.3f}")
        except Exception as exc:
            counters.failures += 1
            logger.log_split_failed(source_index=source_index, source=source, error=exc)
            print(f"[split-failed] source={source_index} path={source.stp_path}: {exc}")
            continue

        for target_index, target in enumerate(targets, 1):
            logger.log_split_success(
                source_index=source_index,
                source=source,
                target_index=target_index,
                target=target,
            )
            try:
                print(
                    "[target] "
                    f"source={source_index} target={target_index}/{len(targets)} "
                    f"path={target.path} split={target.was_split}"
                )
                row = process_target_detect_first(
                    api=api,
                    snapshot=snapshot,
                    ncti=ncti,
                    source=source,
                    target=target,
                    input_dir=step_dir,
                    server_step_dir=str(step_dir),
                    user=args.user,
                    source_type=args.source_type,
                    dry_run=args.dry_run,
                    mark_no_holes=args.mark_no_holes,
                    skip_existing_json=args.skip_existing_json,
                    repair_status_from_json=args.repair_status_from_json,
                    json_root=args.server_json_dir.resolve(),
                    counters=counters,
                )
                logger.log_result(row)
                print(json.dumps(row, ensure_ascii=False))
            except Exception as exc:
                counters.failures += 1
                logger.log_detect_failed(
                    source_index=source_index,
                    source=source,
                    target_index=target_index,
                    target=target,
                    error=exc,
                )
                print(f"[target-failed] source={source_index} target={target_index} path={target.path}: {exc}")

            elapsed = time.perf_counter() - started
            done_targets = counters.completed + counters.skipped_no_holes + counters.failures
            print(
                "[progress] "
                f"sources={source_index}/{len(sources)} targets_done={done_targets}/{counters.split_targets} "
                f"completed={counters.completed} no_holes={counters.skipped_no_holes} "
                f"failures={counters.failures} elapsed_s={elapsed:.1f}"
            )

    total_s = time.perf_counter() - started
    summary = {
        "scanned_sources": counters.scanned_sources,
        "selected_sources": counters.selected_sources,
        "split_targets": counters.split_targets,
        "exported_split_stp": counters.exported_split_stp,
        "completed": counters.completed,
        "no_holes": counters.skipped_no_holes,
        "skip_completed": counters.skipped_completed,
        "skip_existing_json": counters.skipped_existing_json,
        "failures": counters.failures,
        "elapsed_s": round(total_s, 3),
        "log_dir": str(logger.log_dir),
    }
    logger.write_summary(summary)
    print("[done] " + " ".join(f"{key}={value}" for key, value in summary.items()))
    print(f"[logs] {logger.log_dir}")
    return 2 if args.strict_exit_code and counters.failures else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect-first optimized blind-hole API pipeline.")
    parser.add_argument("step_dir", type=Path, help="Server STEP directory, e.g. /mnt/data/geometry_data/steps/step_files.")
    parser.add_argument("--api-base-url", default=DEFAULT_API_BASE_URL)
    parser.add_argument("--server-json-dir", type=Path, default=Path(SERVER_JSON_DIR))
    parser.add_argument("--list-page-size", type=int, default=1000)
    parser.add_argument("--max-sources", type=int)
    parser.add_argument("--log-dir", type=Path, default=PROJECT_ROOT / "optimized_pipeline_logs")
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--source-type", default=DEFAULT_SOURCE_TYPE, choices=["private", "public"])
    parser.add_argument("--process-completed", action="store_true", help="Also process rows whose blind-hole label status is completed.")
    parser.add_argument("--only-has-blind-hole", action="store_true", help="Only select existing DB rows with has_blind_hole=True.")
    parser.add_argument("--skip-existing-json", action="store_true", help="Skip rows whose final JSON already exists in server json_files.")
    parser.add_argument(
        "--repair-status-from-json",
        action="store_true",
        help="When skipping existing JSON, mark label_blind_hole_status=completed.",
    )
    parser.add_argument(
        "--mark-no-holes",
        action="store_true",
        help="Mark original unsplit source rows as skipped when no blind holes are detected.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not call write/update API endpoints.")
    parser.add_argument("--strict-exit-code", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
