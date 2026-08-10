from __future__ import annotations

import argparse
import atexit
import json
import os
import pathlib
import re
import signal
import subprocess
import textwrap
import time
import urllib.request
from typing import Dict, List, Literal, Optional

from openai import OpenAI
from transformers.utils.versions import require_version

require_version("openai>=1.5.0", "To fix: pip install openai>=1.5.0")

Stage = Literal["graph", "mcp", "bpy"]
ROOT_DIR = pathlib.Path(__file__).resolve().parent


class LlamaFactoryServer:
    def __init__(
        self,
        base_model_path: str,
        adapter_path: str,
        port: int,
        gpu: str = "0",
        template: str = "llama3",
        finetuning_type: str = "lora",
        quiet: bool = True,
    ):
        self.base = base_model_path
        self.adapter = adapter_path
        self.port = int(port)
        self.gpu = str(gpu)
        self.template = template
        self.ftype = finetuning_type
        self.quiet = quiet
        self.proc: Optional[subprocess.Popen] = None

    def _wait_http_ready(
        self,
        timeout: float = 600.0,
        interval: float = 0.5,
        probe_timeout: float = 5.0,
    ):
        """Poll /v1/models until a 200/401/403 response indicates readiness."""
        url = f"http://127.0.0.1:{self.port}/v1/models"
        deadline = time.time() + timeout
        last_err: Optional[Exception] = None

        while time.time() < deadline:
            if self.proc and self.proc.poll() is not None:
                raise RuntimeError(
                    f"LLaMA-Factory server on port {self.port} exited early "
                    f"(code {self.proc.returncode})."
                )
            try:
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=probe_timeout) as resp:
                    code = resp.getcode()
                    if code in (200, 401, 403):
                        return
            except Exception as exc:
                last_err = exc
            time.sleep(interval)

        raise TimeoutError(
            f"Server on port {self.port} not ready after {timeout}s. "
            f"Last error: {last_err}"
        )

    def start(
        self,
        ready_timeout: float = 600.0,
        probe_interval: float = 0.5,
        probe_timeout: float = 5.0,
    ):
        env = os.environ.copy()
        env["CUDA_VISIBLE_DEVICES"] = self.gpu
        env["API_PORT"] = str(self.port)

        cmd = [
            "llamafactory-cli",
            "api",
            "--model_name_or_path",
            self.base,
            "--adapter_name_or_path",
            self.adapter,
            "--template",
            self.template,
            "--finetuning_type",
            self.ftype,
        ]

        stdout = subprocess.DEVNULL if self.quiet else None
        stderr = subprocess.STDOUT if self.quiet else None
        self.proc = subprocess.Popen(cmd, env=env, stdout=stdout, stderr=stderr)

        self._wait_http_ready(
            timeout=ready_timeout,
            interval=probe_interval,
            probe_timeout=probe_timeout,
        )

    def stop(self, timeout: int = 10):
        if not self.proc:
            return
        if self.proc.poll() is None:
            try:
                self.proc.send_signal(signal.SIGINT)
                try:
                    self.proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    self.proc.terminate()
                    try:
                        self.proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.proc.kill()
            finally:
                self.proc = None


class APIPool:
    """
    Launch one API service for each stage and expose OpenAI-compatible clients.

    This class can also be used as a context manager so cleanup is guaranteed
    when the caller exits.
    """

    def __init__(
        self,
        base: str,
        adapters: Dict[Stage, str],
        ports: Dict[Stage, int],
        gpus: Dict[Stage, str],
        template: str = "llama3",
        finetuning_type: str = "lora",
        quiet: bool = True,
        *,
        ready_timeout: float = 600.0,
        probe_interval: float = 0.5,
        probe_timeout: float = 5.0,
        # Remote mode: when `remote_base_url` is provided, no local
        # LLaMA-Factory subprocess is spawned. Instead every stage talks to the
        # same remote OpenAI-compatible endpoint (e.g. a server-hosted model).
        remote_base_url: Optional[str] = None,
        api_key: str = "empty",
        model: Optional[str] = None,
    ):
        self.servers: Dict[Stage, LlamaFactoryServer] = {}
        self.clients: Dict[Stage, OpenAI] = {}
        self.remote = bool(remote_base_url)

        self.ready_timeout = float(ready_timeout)
        self.probe_interval = float(probe_interval)
        self.probe_timeout = float(probe_timeout)
        self.remote_base_url = remote_base_url
        self.api_key = api_key
        self.model = model

        if self.remote:
            # All stages share one remote endpoint. No local servers to start.
            return

        for stg in ("graph", "mcp", "bpy"):
            self.servers[stg] = LlamaFactoryServer(
                base_model_path=base,
                adapter_path=adapters[stg],
                port=ports[stg],
                gpu=gpus[stg],
                template=template,
                finetuning_type=finetuning_type,
                quiet=quiet,
            )

        atexit.register(self._cleanup)

    def start_all(self):
        if self.remote:
            # Build one shared client for all stages.
            client = OpenAI(api_key=self.api_key, base_url=self.remote_base_url)
            for stg in ("graph", "mcp", "bpy"):
                self.clients[stg] = client
            return

        # Start services sequentially to reduce transient VRAM spikes.
        for stg in ("graph", "mcp", "bpy"):
            self.servers[stg].start(
                ready_timeout=self.ready_timeout,
                probe_interval=self.probe_interval,
                probe_timeout=self.probe_timeout,
            )
            # Use 127.0.0.1 to avoid IPv6 or hosts-related connection issues.
            self.clients[stg] = OpenAI(
                api_key="0",
                base_url=f"http://127.0.0.1:{self.servers[stg].port}/v1",
            )

    def stop_all(self):
        for stg in ("graph", "mcp", "bpy"):
            self.servers[stg].stop()

    def _cleanup(self):
        self.stop_all()

    def __enter__(self):
        self.start_all()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stop_all()


class LocalBlenderPipeline:
    def __init__(
        self,
        base: str,
        adapters: Dict[Stage, str],
        prompt_dir: str = "prompts",
        temperature: float = 0.2,
        debug: bool = False,
        print_res: bool = False,
        api_ports: Dict[Stage, int] = None,
        gpus: Optional[Dict[Stage, str]] = None,
        api_quiet: bool = True,
        template: str = "llama3",
        finetuning_type: str = "lora",
        max_tokens: Optional[Dict[Stage, Optional[int]]] = None,
        # Remote mode: point all stages at a server-hosted OpenAI-compatible API.
        remote_base_url: Optional[str] = None,
        api_key: str = "empty",
        model: Optional[str] = None,
        request_retries: int = 6,
        request_backoff_base: float = 0.6,
        request_backoff_cap: float = 8.0,
        server_ready_timeout: float = 600.0,
        probe_interval: float = 0.5,
        probe_timeout: float = 5.0,
        request_timeout: float = 600.0,
    ):
        self.debug = debug
        self.print_res = print_res
        self.temperature = temperature

        if api_ports is None:
            api_ports = {"graph": 8000, "mcp": 8001, "bpy": 8002}

        if gpus is None:
            gpus = {"graph": "0", "mcp": "0", "bpy": "0"}

        self.pool = APIPool(
            base=base,
            adapters=adapters,
            ports=api_ports,
            gpus=gpus,
            template=template,
            finetuning_type=finetuning_type,
            quiet=api_quiet,
            ready_timeout=server_ready_timeout,
            probe_interval=probe_interval,
            probe_timeout=probe_timeout,
            remote_base_url=remote_base_url,
            api_key=api_key,
            model=model,
        )
        self.model = model
        self.pool.start_all()

        self.max_tokens: Dict[Stage, Optional[int]] = {
            "graph": None,
            "mcp": None,
            "bpy": None,
        }
        if max_tokens:
            self.max_tokens.update(max_tokens)

        self.request_retries = int(request_retries)
        self.request_backoff_base = float(request_backoff_base)
        self.request_backoff_cap = float(request_backoff_cap)
        self.request_timeout = float(request_timeout)

        # API mode cannot provide exact tokenizer counts here, so this is only
        # a placeholder for a lightweight usage report.
        self.token_usage = {"prompt": 0, "completion": 0, "total": 0}

        prompt_path = pathlib.Path(prompt_dir)
        self.graph_sys = (prompt_path / "graph_prompt.txt").read_text(encoding="utf-8")
        self.mcp_sys = (prompt_path / "mcp_prompt.txt").read_text(encoding="utf-8")
        self.bpy_sys = (prompt_path / "bpy_prompt.txt").read_text(encoding="utf-8")

    def __del__(self):
        try:
            self.pool.stop_all()
        except Exception:
            pass

    def _chat_with_retry(self, stage: Stage, messages: List[Dict[str, str]]) -> str:
        """Call the stage-specific API with retries and per-stage max_tokens."""
        client = self.pool.clients[stage]
        # In remote mode the server requires its own model id; in local mode the
        # LLaMA-Factory API server accepts the placeholder "llamafactory".
        model_name = self.model if self.model else "llamafactory"
        payload = dict(
            model=model_name,
            messages=messages,
            temperature=self.temperature,
            timeout=self.request_timeout,
        )
        # Qwen3 models enable chain-of-thought by default, which exhausts the
        # token budget inside `reasoning_content` and leaves `content` empty
        # (finish_reason == "length"). Graph-CAD parses `content` only, so we
        # disable thinking for both remote and local OpenAI-compatible endpoints.
        payload["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
        max_token_value = self.max_tokens.get(stage)
        if max_token_value is not None:
            payload["max_tokens"] = int(max_token_value)

        last_err: Optional[Exception] = None
        for attempt in range(1, self.request_retries + 1):
            try:
                resp = client.chat.completions.create(**payload)
                return resp.choices[0].message.content if resp.choices else ""
            except Exception as exc:
                last_err = exc
                retryable = True
                status_code = getattr(exc, "status_code", None)
                if status_code is not None and status_code < 500 and status_code not in (
                    408,
                    409,
                    429,
                ):
                    retryable = False
                if not retryable or attempt == self.request_retries:
                    break
                sleep_seconds = min(
                    self.request_backoff_base * (2 ** (attempt - 1)),
                    self.request_backoff_cap,
                )
                time.sleep(sleep_seconds)

        raise RuntimeError(
            f"Chat request failed after {self.request_retries} retries on stage "
            f"'{stage}'. Last error: {last_err}"
        )

    def forward(
        self,
        user_description: str,
        job_name: str,
        out_root: str = "outputs",
    ) -> Dict[str, str]:
        out_dir = pathlib.Path(out_root) / self._sanitize(job_name)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "instruction.txt").write_text(user_description, encoding="utf-8")

        graph_txt = self._run_stage(
            stage="graph",
            system_prompt=self.graph_sys,
            user_content=user_description,
            out_dir=out_dir,
        )

        mcp_txt = self._run_stage(
            stage="mcp",
            system_prompt=self.mcp_sys,
            user_content=graph_txt + "\nPlease return mcp",
            out_dir=out_dir,
        )

        bpy_txt = self._run_stage(
            stage="bpy",
            system_prompt=self.bpy_sys,
            user_content=mcp_txt,
            out_dir=out_dir,
        )

        return {
            "instruction": user_description,
            "structure": graph_txt,
            "action": mcp_txt,
            "bpy": bpy_txt,
        }

    def infer_record(
        self,
        record: Dict,
        out_root: str = "outputs",
        skip_if_done: bool = True,
    ) -> Dict[str, str]:
        sample_id = record.get("id", "unknown-id")
        sample_name = record.get("name", "unknown-name")
        job_name = f"{sample_name} ({sample_id})"
        out_dir = pathlib.Path(out_root) / self._sanitize(job_name)
        out_dir.mkdir(parents=True, exist_ok=True)

        if skip_if_done and (out_dir / "bpy.txt").exists():
            return {"skipped": True, "job_name": job_name}

        user_description = record.get("instruction", "")
        if not isinstance(user_description, str) or not user_description.strip():
            raise ValueError(f"Record {sample_id} is missing a valid instruction.")

        (out_dir / "meta.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        res = self.forward(
            user_description=user_description,
            job_name=job_name,
            out_root=out_root,
        )

        (out_dir / "result.json").write_text(
            json.dumps(res, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return res

    def run_jsonl(
        self,
        jsonl_path: str,
        out_root: str = "outputs",
        limit: Optional[int] = None,
        skip_if_done: bool = True,
        start: int = 0,
    ) -> Dict[str, int]:
        src = pathlib.Path(jsonl_path)
        assert src.exists(), f"JSONL file does not exist: {src}"

        out = pathlib.Path(out_root)
        out.mkdir(parents=True, exist_ok=True)

        total, ok, fail, skipped = 0, 0, 0, 0
        summary_lines: List[str] = []

        try:
            with src.open("r", encoding="utf-8") as file_obj:
                for idx, line in enumerate(file_obj):
                    if idx < start:
                        continue
                    if limit is not None and total >= limit:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    total += 1
                    try:
                        rec = json.loads(line)
                    except Exception as exc:
                        fail += 1
                        err = {"index": idx, "error": f"JSON parsing failed: {exc}"}
                        summary_lines.append(json.dumps(err, ensure_ascii=False))
                        continue

                    job = f"{rec.get('name', 'unknown-name')} ({rec.get('id', 'unknown-id')})"
                    job_dir = out / self._sanitize(job)
                    try:
                        if skip_if_done and (job_dir / "bpy.txt").exists():
                            skipped += 1
                            summary_lines.append(
                                json.dumps(
                                    {
                                        "id": rec.get("id"),
                                        "name": rec.get("name"),
                                        "status": "skipped",
                                        "dir": str(job_dir),
                                    },
                                    ensure_ascii=False,
                                )
                            )
                            continue

                        _ = self.infer_record(rec, out_root=out_root, skip_if_done=False)
                        ok += 1
                        summary_lines.append(
                            json.dumps(
                                {
                                    "id": rec.get("id"),
                                    "name": rec.get("name"),
                                    "status": "ok",
                                    "dir": str(job_dir),
                                },
                                ensure_ascii=False,
                            )
                        )
                    except Exception as exc:
                        fail += 1
                        job_dir.mkdir(parents=True, exist_ok=True)
                        (job_dir / "error.txt").write_text(str(exc), encoding="utf-8")
                        summary_lines.append(
                            json.dumps(
                                {
                                    "id": rec.get("id"),
                                    "name": rec.get("name"),
                                    "status": "failed",
                                    "dir": str(job_dir),
                                    "error": str(exc),
                                },
                                ensure_ascii=False,
                            )
                        )
        finally:
            self.pool.stop_all()

        (out / "summary.jsonl").write_text(
            "\n".join(summary_lines) + "\n",
            encoding="utf-8",
        )
        report = {
            "total": total,
            "ok": ok,
            "failed": fail,
            "skipped": skipped,
            "out_root": str(out.resolve()),
        }
        (out / "run_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nBatch complete - {report}")
        return report

    def _run_stage(
        self,
        stage: Stage,
        system_prompt: str,
        user_content: str,
        out_dir: pathlib.Path,
    ) -> str:
        """Call the corresponding stage API and save the raw output directly."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        resp_txt = self._chat_with_retry(stage, messages)

        if self.print_res:
            print(f"\n== Stage {stage} output ==\n{resp_txt[:1000]}\n")

        if stage == "graph":
            (out_dir / "structure.txt").write_text(resp_txt, encoding="utf-8")
            return resp_txt
        if stage == "mcp":
            (out_dir / "action.txt").write_text(resp_txt, encoding="utf-8")
            return resp_txt

        (out_dir / "bpy.txt").write_text(resp_txt, encoding="utf-8")
        return resp_txt

    def print_report(self):
        token_usage = self.token_usage
        print(
            f"Tokens (approx) - prompt: {token_usage['prompt']:,} | "
            f"completion: {token_usage['completion']:,} | "
            f"total: {token_usage['total']:,}"
        )

    @staticmethod
    def _extract_blocks(full: str) -> Dict[str, str]:
        lib_pat = re.compile(
            r"--\s*MATERIAL LIBRARY\s*--(?P<body>.*?)#END_MATERIALS",
            re.I | re.S,
        )
        graph_pat = re.compile(r"BEGIN_GRAPH(?P<body>.*?)END_GRAPH", re.I | re.S)
        match_lib, match_graph = lib_pat.search(full), graph_pat.search(full)
        if not (match_lib and match_graph):
            raise ValueError("Missing MATERIAL LIBRARY or GRAPH block.")
        library = "-- MATERIAL LIBRARY --" + match_lib.group("body") + "#END_MATERIALS"
        graph = (
            "# ----------  BEGIN_GRAPH  ----------"
            + match_graph.group("body")
            + "# ----------  END_GRAPH  ----------"
        )
        return {
            "library": textwrap.dedent(library).strip(),
            "graph": textwrap.dedent(graph).strip(),
        }

    @staticmethod
    def _extract_mcp_script(full: str) -> str:
        pattern = re.compile(r"(BLOCK\s*0[\s\S]*?All stages complete\.)", re.I)
        match = pattern.search(full)
        if not match:
            raise ValueError("Could not locate complete MCP script.")
        return match.group(1).rstrip()

    @staticmethod
    def _extract_main(text: str, tag: str) -> str:
        clean = re.sub(r"```python\s*", "", text)
        clean = re.sub(r"```", "", clean)
        match = re.search(rf"(^.*{re.escape(tag)}.*$)", clean, re.M | re.S)
        if not match:
            raise ValueError(f"Tag '{tag}' not found.")
        return match.group(1).strip()

    @staticmethod
    def _check_graph(graph_text: str):
        if "BEGIN_GRAPH" not in graph_text or "END_GRAPH" not in graph_text:
            raise ValueError("Graph missing markers.")

    @staticmethod
    def _check_mcp(mcp_text: str):
        if not mcp_text.lstrip().startswith("BLOCK 0"):
            raise ValueError("MCP must start with BLOCK 0")
        if "All stages complete." not in mcp_text:
            raise ValueError("MCP missing completion line")

    @staticmethod
    def _check_bpy(code: str):
        if not code.splitlines()[0].lstrip().startswith("import bpy"):
            raise ValueError("bpy script must begin with 'import bpy'")

    @staticmethod
    def _sanitize(name: str) -> str:
        name = re.sub(r"[\\/:*?\"<>|\n\r\t]", "_", name)
        name = re.sub(r"\s+", " ", name).strip()
        return name[:255]


def parse_args():
    ap = argparse.ArgumentParser(
        description="Local Blender Pipeline (LLaMA-Factory API) - single sample or JSONL batch"
    )

    # Base model and LoRA adapters.
    ap.add_argument("--base", type=str, required=False, default=str(ROOT_DIR / "qwen3"))
    ap.add_argument(
        "--adapter-graph",
        type=str,
        required=False,
        default=str(ROOT_DIR / "checkpoints" / "stage1" / "checkpoint-4800"),
    )
    ap.add_argument(
        "--adapter-mcp",
        type=str,
        required=False,
        default=str(ROOT_DIR / "checkpoints" / "stage2" / "checkpoint-5400"),
    )
    ap.add_argument(
        "--adapter-bpy",
        type=str,
        required=False,
        default=str(ROOT_DIR / "checkpoints" / "stage3" / "checkpoint-5700"),
    )

    # API launch settings.
    ap.add_argument(
        "--gpu-graph",
        type=str,
        default="0",
        help="CUDA_VISIBLE_DEVICES value for the graph stage",
    )
    ap.add_argument(
        "--gpu-mcp",
        type=str,
        default="0",
        help="CUDA_VISIBLE_DEVICES value for the MCP stage",
    )
    ap.add_argument(
        "--gpu-bpy",
        type=str,
        default="0",
        help="CUDA_VISIBLE_DEVICES value for the bpy stage",
    )
    ap.add_argument("--port-graph", type=int, default=7300)
    ap.add_argument("--port-mcp", type=int, default=7301)
    ap.add_argument("--port-bpy", type=int, default=7302)
    ap.add_argument(
        "--api-quiet",
        action="store_true",
        help="Start API services quietly without printing server logs",
    )

    # Remote endpoint mode (server-hosted model, no local GPU needed).
    ap.add_argument(
        "--api-base",
        type=str,
        default=None,
        help="OpenAI-compatible base URL (e.g. http://host:port/v1). "
        "When set, no local LLaMA-Factory subprocess is spawned; all "
        "stages call this remote endpoint.",
    )
    ap.add_argument(
        "--api-key",
        type=str,
        default="empty",
        help="API key for the remote endpoint",
    )
    ap.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model id reported to the remote endpoint",
    )

    # Template and finetuning settings.
    ap.add_argument("--template", type=str, default="qwen3_nothink")
    ap.add_argument("--finetuning-type", type=str, default="lora")

    # Inference behavior and logging.
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--print-res", action="store_true")

    # Per-stage max_tokens.
    ap.add_argument(
        "--max-graph",
        type=int,
        default=6500,
        help="max_tokens for the graph stage (-1 uses the server default)",
    )
    ap.add_argument(
        "--max-mcp",
        type=int,
        default=6500,
        help="max_tokens for the MCP stage (-1 uses the server default)",
    )
    ap.add_argument(
        "--max-bpy",
        type=int,
        default=8000,
        help="max_tokens for the bpy stage (-1 uses the server default)",
    )

    # Request retry settings.
    ap.add_argument(
        "--retries",
        type=int,
        default=6,
        help="Maximum number of retries for inference requests",
    )
    ap.add_argument(
        "--backoff-base",
        type=float,
        default=0.6,
        help="Initial backoff interval in seconds",
    )
    ap.add_argument(
        "--backoff-cap",
        type=float,
        default=8.0,
        help="Maximum backoff interval in seconds",
    )

    # Service readiness and request timeouts.
    ap.add_argument(
        "--server-ready-timeout",
        type=float,
        default=800.0,
        help="Maximum wait time in seconds for service startup",
    )
    ap.add_argument(
        "--probe-interval",
        type=float,
        default=0.5,
        help="Polling interval in seconds for readiness checks",
    )
    ap.add_argument(
        "--probe-timeout",
        type=float,
        default=30.0,
        help="Timeout in seconds for a single readiness probe request",
    )
    ap.add_argument(
        "--request-timeout",
        type=float,
        default=800.0,
        help="Timeout in seconds for a single inference request",
    )

    # I/O.
    ap.add_argument(
        "--prompt-dir",
        type=str,
        required=False,
        default=str(ROOT_DIR / "prompt_sft"),
    )
    ap.add_argument(
        "--out-root",
        type=str,
        default=str(ROOT_DIR / "output" / "result_name"),
    )
    ap.add_argument(
        "--jsonl",
        type=str,
        default=str(ROOT_DIR / "CADBench.jsonl"),
        help="Path to the evaluation JSONL file; omit it to run the demo sample",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of samples to process",
    )
    ap.add_argument(
        "--start",
        type=int,
        default=0,
        help="Zero-based line index to start from",
    )
    ap.add_argument(
        "--no-skip",
        action="store_true",
        help="Do not skip samples that already have outputs",
    )

    # Single-sample demo used when --jsonl is not provided.
    ap.add_argument(
        "--demo-instr",
        type=str,
        default="Create a router with a rectangular body and two antennas protruding from the back.",
    )
    ap.add_argument(
        "--demo-name",
        type=str,
        default="Router (74d180f4-4633-4b8a-9960-d3dd46730657)",
    )

    return ap.parse_args()


if __name__ == "__main__":
    args = parse_args()

    max_tokens = {
        "graph": None if args.max_graph is None or args.max_graph < 0 else args.max_graph,
        "mcp": None if args.max_mcp is None or args.max_mcp < 0 else args.max_mcp,
        "bpy": None if args.max_bpy is None or args.max_bpy < 0 else args.max_bpy,
    }

    pipe = LocalBlenderPipeline(
        base=args.base,
        adapters={
            "graph": args.adapter_graph,
            "mcp": args.adapter_mcp,
            "bpy": args.adapter_bpy,
        },
        debug=args.debug,
        print_res=args.print_res,
        prompt_dir=args.prompt_dir,
        temperature=args.temperature,
        api_ports={
            "graph": args.port_graph,
            "mcp": args.port_mcp,
            "bpy": args.port_bpy,
        },
        gpus={
            "graph": args.gpu_graph,
            "mcp": args.gpu_mcp,
            "bpy": args.gpu_bpy,
        },
        api_quiet=args.api_quiet,
        template=args.template,
        finetuning_type=args.finetuning_type,
        remote_base_url=args.api_base,
        api_key=args.api_key,
        model=args.model,
        max_tokens=max_tokens,
        request_retries=args.retries,
        request_backoff_base=args.backoff_base,
        request_backoff_cap=args.backoff_cap,
        server_ready_timeout=args.server_ready_timeout,
        probe_interval=args.probe_interval,
        probe_timeout=args.probe_timeout,
        request_timeout=args.request_timeout,
    )

    try:
        if args.jsonl:
            pipe.run_jsonl(
                jsonl_path=args.jsonl,
                out_root=args.out_root,
                limit=args.limit,
                start=args.start,
                skip_if_done=not args.no_skip,
            )
        else:
            _ = pipe.forward(
                user_description=args.demo_instr,
                job_name=args.demo_name,
                out_root=args.out_root,
            )
            print("\nGeneration complete!")
    finally:
        pipe.pool.stop_all()
