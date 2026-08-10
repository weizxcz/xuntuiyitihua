#!/usr/bin/env python

import argparse
import base64
import glob
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from openai import OpenAI
from PIL import Image
from tqdm import tqdm


EXPLANATIONS_KEY = "_explanations"
DIMENSION_MAP = {
    "Object Attributes": "Attr",
    "Spatial Understanding and Structure": "Spat",
    "User Instruction Understanding and Execution": "Inst",
}


try:
    RESAMPLE = Image.Resampling.LANCZOS
except AttributeError:
    RESAMPLE = Image.LANCZOS


logger = logging.getLogger("merged_evaluator")
ROOT_DIR = Path(__file__).resolve().parent


@dataclass
class RuntimeConfig:
    api_base: str
    api_key: str
    model: str
    max_tokens: int
    temperature: float
    retries: int
    request_timeout: int
    delay_per_param: float
    delay_per_dimension: float
    delay_per_project: float
    max_image_size: int


def setup_logging(log_path: str) -> None:
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)


def load_projects(config_path: str) -> Dict[str, Dict[str, Any]]:
    projects: Dict[str, Dict[str, Any]] = {}
    with open(config_path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                row = json.loads(line)
                project_id = row["id"]
                projects[project_id] = {
                    "id": project_id,
                    "name": row["name"],
                    "instruction": row["instruction"],
                    "criteria": row["criteria"],
                    "type": row.get("type", "Unknown"),
                }
            except Exception as exc:
                logger.error("Skip invalid config line %s: %s", line_number, exc)
    return projects


def resize_image(image_path: str, max_dimension: int) -> Tuple[Optional[str], Optional[str]]:
    try:
        with Image.open(image_path) as image:
            if image.mode == "RGBA":
                background = Image.new("RGB", image.size, (255, 255, 255))
                background.paste(image, mask=image.split()[3])
                image = background
            elif image.mode != "RGB":
                image = image.convert("RGB")

            width, height = image.size
            if max(width, height) > max_dimension:
                scale = max_dimension / max(width, height)
                image = image.resize((int(width * scale), int(height * scale)), RESAMPLE)

            image_format = (image.format or "PNG").upper()
            if image_format not in {"PNG", "JPEG", "JPG"}:
                image_format = "PNG"

            buffer = BytesIO()
            save_format = "JPEG" if image_format in {"JPEG", "JPG"} else "PNG"
            if save_format == "JPEG":
                image.save(buffer, format=save_format, quality=95)
                mime_type = "image/jpeg"
            else:
                image.save(buffer, format=save_format)
                mime_type = "image/png"

            return base64.b64encode(buffer.getvalue()).decode("utf-8"), mime_type
    except Exception as exc:
        logger.error("Failed to process image %s: %s", image_path, exc)
        return None, None


def build_image_content(image_paths: Sequence[str], max_dimension: int) -> List[Dict[str, Any]]:
    content: List[Dict[str, Any]] = []
    for image_path in image_paths:
        base64_data, mime_type = resize_image(image_path, max_dimension=max_dimension)
        if base64_data:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{base64_data}",
                        "detail": "high",
                    },
                }
            )
    return content


def find_model_images(folder_path: str) -> List[str]:
    view_files: List[str] = []
    for index in range(1, 9):
        patterns = [
            f"*_view{index}.png",
            f"*view{index}*.png",
            f"*_view{index}.jpg",
            f"*view{index}*.jpg",
            f"*_view{index}.jpeg",
            f"*view{index}*.jpeg",
        ]
        for pattern in patterns:
            matches = glob.glob(os.path.join(folder_path, pattern))
            if matches:
                view_files.append(matches[0])
                break
    try:
        view_files.sort(
            key=lambda path: int(re.search(r"view(\d+)", os.path.basename(path), re.IGNORECASE).group(1))
        )
    except Exception:
        pass
    return view_files[:8]


def create_prompt_content(
    dimension: str,
    param: str,
    requirements: Sequence[str],
    project: Dict[str, Any],
    image_content: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    skeleton = {
        param: [0] * len(requirements),
        "reasons": [""] * len(requirements),
    }
    rules = (
        "You are a rigorous 3D model evaluation expert.\n"
        "Based ONLY on the images and the listed criteria for the single parameter below, "
        "return exactly one JSON object with two keys:\n"
        f'1. "{param}": a list of integers (0 or 1)\n'
        '2. "reasons": a list of short factual strings in the same order\n\n'
        "Rules:\n"
        "1. Output JSON only.\n"
        "2. Keep the same list length and order as the criteria.\n"
        "3. Ignore realism, texture, material, color, lighting, shadows, and minor clipping.\n"
        "4. Primitive simplifications and low detail should not be penalized.\n"
        "5. For absolute units, judge relative proportion only.\n"
        "6. If uncertain because of viewpoint ambiguity, default to 1.\n"
    )
    instruction = (
        f"Project Name: {project['name']}\n"
        f"Type: {project['type']}\n"
        f"Instruction: {project['instruction']}\n"
        f"Dimension: {dimension}\n"
        f"Parameter: {param}\n\n"
        f"Return this JSON skeleton filled in:\n{json.dumps(skeleton, ensure_ascii=False, indent=2)}\n\n"
        f"Criteria:\n{json.dumps(list(requirements), ensure_ascii=False, indent=2)}"
    )
    return list(image_content) + [{"type": "text", "text": rules}, {"type": "text", "text": instruction}]


def repair_json(raw_text: str) -> str:
    match = re.search(r"\{[\s\S]*\}", raw_text)
    fixed = match.group(0) if match else raw_text
    fixed = re.sub(r"/\*.*?\*/", "", fixed, flags=re.DOTALL)
    fixed = re.sub(r"(?m)^\s*//.*$", "", fixed)
    fixed = re.sub(r"(?m)^\s*#.*$", "", fixed)
    fixed = re.sub(r"\s+", " ", fixed).strip()
    return fixed


def normalize_scores(param: str, requirements: Sequence[str], values: Any) -> List[int]:
    if not isinstance(values, list):
        raise ValueError(f"{param} is not a list")
    if len(values) != len(requirements):
        raise ValueError(f"{param} length mismatch: expect {len(requirements)}, got {len(values)}")

    normalized: List[int] = []
    for index, value in enumerate(values, 1):
        if isinstance(value, bool):
            score = int(value)
        elif isinstance(value, (int, float)):
            score = int(value)
        elif isinstance(value, str) and value.strip() in {"0", "1"}:
            score = int(value.strip())
        else:
            raise ValueError(f"{param} item {index} is invalid: {value!r}")
        if score not in {0, 1}:
            raise ValueError(f"{param} item {index} is not 0/1: {score}")
        normalized.append(score)
    return normalized


def normalize_reasons(requirements: Sequence[str], values: Any) -> List[str]:
    if not isinstance(values, list):
        raise ValueError("reasons is not a list")
    if len(values) != len(requirements):
        raise ValueError(f"reasons length mismatch: expect {len(requirements)}, got {len(values)}")

    normalized: List[str] = []
    for value in values:
        if value is None:
            value = ""
        if not isinstance(value, str):
            raise ValueError(f"reason is not a string: {type(value)}")
        normalized.append(" ".join(value.strip().split())[:200])
    return normalized


def call_model_for_param(
    client: OpenAI,
    runtime: RuntimeConfig,
    dimension: str,
    param: str,
    requirements: Sequence[str],
    project: Dict[str, Any],
    image_content: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    content = create_prompt_content(dimension, param, requirements, project, image_content)
    last_error: Optional[str] = None

    for attempt in range(1, runtime.retries + 1):
        try:
            response = client.chat.completions.create(
                model=runtime.model,
                messages=[{"role": "user", "content": content}],
                max_tokens=runtime.max_tokens,
                temperature=runtime.temperature,
                response_format={"type": "json_object"},
                timeout=runtime.request_timeout,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
            raw_text = response.choices[0].message.content.strip()
            try:
                parsed = json.loads(raw_text)
            except json.JSONDecodeError:
                parsed = json.loads(repair_json(raw_text))

            if isinstance(parsed, list):
                parsed = {param: parsed, "reasons": [""] * len(requirements)}

            if isinstance(parsed, dict) and param not in parsed:
                candidate_keys = [key for key in parsed if key != "reasons"]
                if len(candidate_keys) == 1:
                    parsed[param] = parsed.pop(candidate_keys[0])

            scores = normalize_scores(param, requirements, parsed[param])
            reasons = normalize_reasons(requirements, parsed["reasons"])
            if runtime.delay_per_param > 0:
                time.sleep(runtime.delay_per_param)
            return {"scores": scores, "reasons": reasons}
        except Exception as exc:
            last_error = str(exc)
            logger.warning("%s / %s failed on attempt %s: %s", dimension, param, attempt, exc)
            if attempt < runtime.retries:
                time.sleep(min(2 * attempt, 5))

    return {"error": last_error or "unknown error"}


def validate_dimension_scores(
    dimension: str, project: Dict[str, Any], result: Dict[str, Any]
) -> Optional[str]:
    criteria = project["criteria"].get(dimension, {})
    errors: List[str] = []
    score_dict = {key: value for key, value in result.items() if key != EXPLANATIONS_KEY}

    expected = set(criteria)
    actual = set(score_dict)
    if expected - actual:
        errors.append(f"missing params: {sorted(expected - actual)}")
    if actual - expected:
        errors.append(f"extra params: {sorted(actual - expected)}")

    for param, requirements in criteria.items():
        if param not in score_dict:
            continue
        try:
            normalize_scores(param, requirements, score_dict[param])
        except Exception as exc:
            errors.append(str(exc))
    return "; ".join(errors) if errors else None


def evaluate_dimension(
    client: OpenAI,
    runtime: RuntimeConfig,
    dimension: str,
    project: Dict[str, Any],
    image_content: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    criteria = project["criteria"].get(dimension, {})
    if not criteria:
        return {}

    scores: Dict[str, List[int]] = {}
    reasons: Dict[str, List[str]] = {}
    errors: List[Dict[str, Any]] = []

    for param, requirements in criteria.items():
        result = call_model_for_param(client, runtime, dimension, param, requirements, project, image_content)
        if "error" in result:
            errors.append({"param": param, "error": result["error"]})
            continue
        scores[param] = result["scores"]
        reasons[param] = result["reasons"]

    merged = {**scores, EXPLANATIONS_KEY: reasons}
    validation_error = validate_dimension_scores(dimension, project, merged)
    if validation_error or errors:
        return {
            "error": "partial_failure",
            "validation_error": validation_error,
            "failed_params": errors,
            "result_partial": merged,
        }
    return merged


def calculate_overall_scores(results: Dict[str, Any]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    total_score = 0
    total_count = 0

    for dimension, dimension_result in results.items():
        if dimension == "Overall_Scores" or not isinstance(dimension_result, dict):
            continue
        score_dict = {key: value for key, value in dimension_result.items() if key != EXPLANATIONS_KEY}
        dim_sum = 0
        dim_count = 0
        for values in score_dict.values():
            if isinstance(values, list):
                dim_sum += sum(int(item) for item in values)
                dim_count += len(values)
        if dim_count:
            average = dim_sum / dim_count
            summary[dimension] = {"score": average, "max_possible": 1.0}
            total_score += dim_sum
            total_count += dim_count

    if total_count:
        summary["Overall"] = {"score": total_score / total_count, "max_possible": 1.0}
    return summary


def evaluate_project(
    client: OpenAI,
    runtime: RuntimeConfig,
    project: Dict[str, Any],
    project_folder: str,
) -> Dict[str, Any]:
    image_paths = find_model_images(project_folder)
    if not image_paths:
        return {"status": "error", "message": "no images found", "folder_path": project_folder}

    image_content = build_image_content(image_paths, max_dimension=runtime.max_image_size)
    if not image_content:
        return {"status": "error", "message": "failed to load images", "folder_path": project_folder}

    results: Dict[str, Any] = {}
    failed_dimensions: List[Dict[str, Any]] = []
    for dimension in project["criteria"]:
        dimension_result = evaluate_dimension(client, runtime, dimension, project, image_content)
        if isinstance(dimension_result, dict) and "error" in dimension_result:
            failed_dimensions.append({"dimension": dimension, **dimension_result})
            if isinstance(dimension_result.get("result_partial"), dict):
                results[dimension] = dimension_result["result_partial"]
        else:
            results[dimension] = dimension_result
        if runtime.delay_per_dimension > 0:
            time.sleep(runtime.delay_per_dimension)

    if results:
        results["Overall_Scores"] = calculate_overall_scores(results)

    if failed_dimensions:
        return {
            "status": "partial_success",
            "message": "some dimensions failed",
            "results": results,
            "failed_dimensions": failed_dimensions,
        }
    return {"status": "success", "results": results}


def locate_project_folder(base_dir: str, project_id: str) -> Optional[str]:
    matches = glob.glob(os.path.join(base_dir, f"*{project_id}*"))
    return matches[0] if matches else None


def build_project_record(
    client: OpenAI,
    runtime: RuntimeConfig,
    base_dir: str,
    project: Dict[str, Any],
) -> Dict[str, Any]:
    folder_path = locate_project_folder(base_dir, project["id"])
    if not folder_path:
        evaluation = {"status": "error", "message": "project folder not found"}
    else:
        evaluation = evaluate_project(client, runtime, project, folder_path)

    record = {
        "project_id": project["id"],
        "project_name": project["name"],
        "project_type": project["type"],
        "folder_path": folder_path,
        "instruction": project["instruction"],
        "evaluation": evaluation,
        "evaluation_time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if runtime.delay_per_project > 0:
        time.sleep(runtime.delay_per_project)
    return record


def run_evaluation(
    projects: Dict[str, Dict[str, Any]],
    base_dir: str,
    runtime: RuntimeConfig,
    max_workers: int,
    debug_ids: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    filtered_projects = projects
    debug_set = {item.strip() for item in (debug_ids or []) if item and item.strip()}
    if debug_set:
        filtered_projects = {key: value for key, value in projects.items() if key in debug_set}
        logger.info("Debug mode enabled for %s project(s)", len(filtered_projects))

    project_items = list(filtered_projects.values())
    if not project_items:
        return []

    client = OpenAI(base_url=runtime.api_base, api_key=runtime.api_key)
    results: List[Optional[Dict[str, Any]]] = [None] * len(project_items)

    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as executor:
        future_map = {
            executor.submit(build_project_record, client, runtime, base_dir, project): index
            for index, project in enumerate(project_items)
        }
        progress = tqdm(total=len(future_map), desc="Evaluating")
        for future in as_completed(future_map):
            index = future_map[future]
            project = project_items[index]
            try:
                results[index] = future.result()
            except Exception as exc:
                logger.exception("Project %s failed: %s", project["id"], exc)
                results[index] = {
                    "project_id": project["id"],
                    "project_name": project["name"],
                    "project_type": project["type"],
                    "folder_path": None,
                    "instruction": project["instruction"],
                    "evaluation": {"status": "error", "message": str(exc)},
                    "evaluation_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
            progress.update(1)
        progress.close()

    return [item for item in results if item is not None]


def save_jsonl(records: Sequence[Dict[str, Any]], output_path: str) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def scan_obj_presence(base_dir: str) -> Tuple[Dict[str, bool], Dict[str, str], Dict[str, Any]]:
    obj_map: Dict[str, bool] = {}
    folder_id_map: Dict[str, str] = {}
    total_folders = 0
    found_objs = 0

    for folder_name in os.listdir(base_dir):
        folder_path = os.path.join(base_dir, folder_name)
        if not os.path.isdir(folder_path):
            continue
        total_folders += 1

        has_obj = False
        for root, _, files in os.walk(folder_path):
            if any(file.lower().endswith(".obj") for file in files):
                has_obj = True
                found_objs += 1
                break
        obj_map[folder_name] = has_obj

        match = re.search(
            r"([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})",
            folder_name,
            re.IGNORECASE,
        )
        if match:
            folder_id_map[match.group(1)] = folder_name

    missing = total_folders - found_objs
    summary = {
        "scanned_folders": total_folders,
        "folders_with_obj": found_objs,
        "folders_missing_obj": missing,
        "scan_missing_rate": round((missing / total_folders) * 100, 4) if total_folders else 0.0,
    }
    return obj_map, folder_id_map, summary


def compute_project_scores(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    evaluation = record.get("evaluation")
    if not isinstance(evaluation, dict):
        return None
    if evaluation.get("status") not in {"success", "partial_success"}:
        return None

    results = evaluation.get("results")
    if not isinstance(results, dict):
        return None

    metrics = {
        "DimScore_Attr": 0.0,
        "DimScore_Spat": 0.0,
        "DimScore_Inst": 0.0,
        "Avg": 0.0,
    }
    for full_name, short_name in DIMENSION_MAP.items():
        dimension_result = results.get(full_name, {})
        parameter_means: List[float] = []
        if isinstance(dimension_result, dict):
            for key, values in dimension_result.items():
                if key in {EXPLANATIONS_KEY, "Overall_Scores"}:
                    continue
                if isinstance(values, list):
                    valid = [int(item) for item in values if item in {0, 1}]
                    if valid:
                        parameter_means.append(sum(valid) / len(valid))
        metrics[f"DimScore_{short_name}"] = (
            sum(parameter_means) / len(parameter_means) if parameter_means else 0.0
        )

    metrics["Avg"] = (
        metrics["DimScore_Attr"] + metrics["DimScore_Spat"] + metrics["DimScore_Inst"]
    ) / 3.0
    return metrics


def summarize_metrics(records: Sequence[Dict[str, Any]], obj_base_dir: str) -> Dict[str, Any]:
    obj_map, folder_id_map, scan_summary = scan_obj_presence(obj_base_dir)
    grouped: Dict[str, Dict[str, Any]] = {
        "overall": {"projects": [], "all_samples": [], "invalid": 0},
        "Wild": {"projects": [], "all_samples": [], "invalid": 0},
        "Simulative": {"projects": [], "all_samples": [], "invalid": 0},
        "Unknown": {"projects": [], "all_samples": [], "invalid": 0},
    }

    for record in records:
        project_type = record.get("project_type", "Unknown")
        if project_type not in grouped:
            project_type = "Unknown"

        project_id = record.get("project_id", "")
        project_name = record.get("project_name", "")

        matched_folder = None
        if project_id in folder_id_map:
            matched_folder = folder_id_map[project_id]
        elif project_id in obj_map:
            matched_folder = project_id
        elif project_name in obj_map:
            matched_folder = project_name

        sample_info = {
            "project_id": project_id,
            "project_name": project_name,
            "matched_folder": matched_folder,
            "matched": matched_folder is not None,
            "has_obj": obj_map.get(matched_folder, False) if matched_folder else False,
        }

        grouped["overall"]["all_samples"].append(sample_info)
        grouped[project_type]["all_samples"].append(sample_info)

        metrics = compute_project_scores(record)
        if metrics is None:
            grouped["overall"]["invalid"] += 1
            grouped[project_type]["invalid"] += 1
            continue

        merged_metrics = {**sample_info, **metrics}
        grouped["overall"]["projects"].append(merged_metrics)
        grouped[project_type]["projects"].append(merged_metrics)

    report: Dict[str, Any] = {}
    for name, payload in grouped.items():
        total = len(payload["all_samples"])
        valid = len(payload["projects"])
        if total == 0 and payload["invalid"] == 0:
            continue

        attr_total = sum(item["DimScore_Attr"] for item in payload["projects"])
        spat_total = sum(item["DimScore_Spat"] for item in payload["projects"])
        inst_total = sum(item["DimScore_Inst"] for item in payload["projects"])
        avg_total = sum(item["Avg"] for item in payload["projects"])
        missing_obj = sum(1 for item in payload["all_samples"] if not item["has_obj"])
        unmatched = sum(1 for item in payload["all_samples"] if not item["matched"])

        divisor = total if total else 1
        report[name] = {
            "Attr.↑": attr_total / divisor,
            "Spat.↑": spat_total / divisor,
            "Inst.↑": inst_total / divisor,
            "Avg.↑": avg_total / divisor,
            "Esyntax↓": (missing_obj / total) * 100 if total else 0.0,
            "valid_projects": valid,
            "invalid_projects": payload["invalid"],
            "total_projects": total,
            "missing_obj_projects": missing_obj,
            "unmatched_projects": unmatched,
        }

    report["_ScanSummary"] = scan_summary
    return report


def save_metrics(metrics: Dict[str, Any], output_path: str) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(metrics, handle, indent=2, ensure_ascii=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CADBench evaluation and metrics in one script.")
    parser.add_argument("--configs", default=str(ROOT_DIR / "CADBench.jsonl"))
    parser.add_argument("--input-dir", default=str(ROOT_DIR / "output" / "result_name"))
    parser.add_argument("--obj-dir", default=str(ROOT_DIR / "output" / "result_name"))
    parser.add_argument("--output-jsonl", default=str(ROOT_DIR / "output" / "result_name.jsonl"))
    parser.add_argument("--metrics-output", default=str(ROOT_DIR / "output" / "result_name.metrics.json"))
    parser.add_argument("--log-file", default=str(ROOT_DIR / "evaluation_system_merged.log"))
    parser.add_argument("--api-base", default="http://172.16.55.7:9026/v1")
    parser.add_argument("--api-key", default="empty")
    parser.add_argument("--model", default="Qwen3.6-35B-A3B")
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--request-timeout", type=int, default=120)
    parser.add_argument("--max-tokens", type=int, default=2000)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--max-image-size", type=int, default=1024)
    parser.add_argument("--delay-per-param", type=float, default=0.0)
    parser.add_argument("--delay-per-dimension", type=float, default=1.2)
    parser.add_argument("--delay-per-project", type=float, default=0.0)
    parser.add_argument("--debug-ids", default="", help="Comma-separated project ids.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging(args.log_file)

    runtime = RuntimeConfig(
        api_base=args.api_base,
        api_key=args.api_key,
        model=args.model,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        retries=args.retries,
        request_timeout=args.request_timeout,
        delay_per_param=args.delay_per_param,
        delay_per_dimension=args.delay_per_dimension,
        delay_per_project=args.delay_per_project,
        max_image_size=args.max_image_size,
    )

    projects = load_projects(args.configs)
    if not projects:
        raise SystemExit("No valid projects loaded from config.")

    debug_ids = [item.strip() for item in args.debug_ids.split(",") if item.strip()]
    records = run_evaluation(
        projects=projects,
        base_dir=args.input_dir,
        runtime=runtime,
        max_workers=args.max_workers,
        debug_ids=debug_ids,
    )
    save_jsonl(records, args.output_jsonl)

    metrics = summarize_metrics(records, obj_base_dir=args.obj_dir)
    metrics["run_summary"] = {
        "total_projects": len(records),
        "success": sum(1 for item in records if item["evaluation"].get("status") == "success"),
        "partial_success": sum(1 for item in records if item["evaluation"].get("status") == "partial_success"),
        "error": sum(1 for item in records if item["evaluation"].get("status") == "error"),
        "output_jsonl": args.output_jsonl,
    }
    save_metrics(metrics, args.metrics_output)

    print(f"Saved merged results to {args.output_jsonl}")
    print(f"Saved metrics to {args.metrics_output}")


if __name__ == "__main__":
    main()
