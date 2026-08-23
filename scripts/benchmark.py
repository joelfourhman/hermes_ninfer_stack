#!/usr/bin/env python3
"""Collect reproducible direct-NInfer RTX 5090 benchmark evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
COMPOSE_FILE = ROOT / "docker-compose.yml"
EXPECTED_COMMIT = "feaf4dd0983fdaeb2ba4c06eec6da350e644fb3a"
EXPECTED_SHA = "bb3360522a06e136e0367f5703414d26272b7285c8a6ab6194135c17dbd81b32"
EXPECTED_BASE = "docker.io/nvidia/cuda:13.1.2-runtime-ubuntu24.04"
PROMPT_TEMPLATE = (
    "Explain how prefill and decode differ in an autoregressive transformer. Use eight numbered "
    "points, include one concrete latency example, and finish with a two-sentence summary."
)
NONCES = "Amber Birch Cobalt Delta Ember Fjord Granite Harbor Indigo Juniper Kestrel Linden Maple Nimbus Onyx Poppy Quartz Rowan Sable Topaz".split()


def die(message: str) -> None:
    raise SystemExit(f"benchmark: {message}")


def run(command: list[str], *, timeout: int = 120, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        die(str(exc))
    if check and result.returncode != 0:
        die(result.stderr.strip() or result.stdout.strip() or f"command failed: {' '.join(command)}")
    return result


def compose(*args: str, timeout: int = 120, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(
        ["docker", "compose", "--project-directory", str(ROOT), "--env-file", str(ENV_FILE), "-f", str(COMPOSE_FILE), *args],
        timeout=timeout,
        check=check,
    )


def read_env() -> dict[str, str]:
    if not ENV_FILE.is_file():
        die("missing .env; run python stack.py setup")
    values: dict[str, str] = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if re.match(r"^[A-Z][A-Z0-9_]*=", line):
            key, value = line.split("=", 1)
            values[key] = value.rstrip("\r")
    return values


def post(url: str, token: str, payload: dict, *, timeout: int = 1800):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.URLError as exc:
        die(f"request failed: {exc}")


def file_sha256(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def gpu_sampler(container_id: str, stop: threading.Event, samples: list[tuple[float, float]]) -> None:
    while not stop.is_set():
        result = run(
            [
                "docker",
                "exec",
                container_id,
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used",
                "--format=csv,noheader,nounits",
            ],
            timeout=15,
            check=False,
        )
        if result.returncode == 0:
            try:
                utilization, memory = [float(item.strip()) for item in result.stdout.splitlines()[0].split(",")[:2]]
                samples.append((utilization, memory))
            except (IndexError, ValueError):
                pass
        stop.wait(0.25)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=int(os.environ.get("BENCHMARK_RUNS", "3")))
    parser.add_argument("--max-tokens", type=int, default=int(os.environ.get("BENCHMARK_MAX_TOKENS", "512")))
    args = parser.parse_args()
    values = read_env()
    required = ["NINFER_API_KEY", "NINFER_HOST_PORT", "NINFER_MODEL_ID", "NINFER_MODEL_FILE", "NINFER_CONTEXT_LENGTH", "NINFER_MAX_CONCURRENCY", "HERMES_IMAGE"]
    missing = [key for key in required if not values.get(key)]
    if missing:
        die("missing .env values: " + ", ".join(missing))
    runs = args.runs
    max_tokens = args.max_tokens
    if not 1 <= runs <= len(NONCES):
        die(f"BENCHMARK_RUNS must be from 1 through {len(NONCES)}")
    if not 32 <= max_tokens <= 4096:
        die("BENCHMARK_MAX_TOKENS must be from 32 through 4096")

    ninfer_id = compose("ps", "-q", "ninfer").stdout.strip()
    if not ninfer_id:
        die("NInfer is not running; use python stack.py up")
    health = run(["docker", "inspect", "--format", "{{.State.Health.Status}}", ninfer_id]).stdout.strip()
    if health != "healthy":
        die(f"NInfer health is {health!r}; inspect docker compose logs ninfer")

    api_key = values["NINFER_API_KEY"]
    model_id = values["NINFER_MODEL_ID"]
    endpoint = f"http://127.0.0.1:{values['NINFER_HOST_PORT']}/v1/chat/completions"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    result_dir = ROOT / "benchmarks" / timestamp
    result_dir.mkdir(parents=True)
    (result_dir / "prompt-template.txt").write_text(f"<unique first word>. {PROMPT_TEMPLATE}\n", encoding="utf-8")
    print(f"Benchmark evidence: {result_dir}")

    source_commit = run(["git", "-C", str(ROOT / "ninfer"), "rev-parse", "HEAD"]).stdout.strip()
    if source_commit != EXPECTED_COMMIT:
        die(f"NInfer source is {source_commit}; expected {EXPECTED_COMMIT}")
    if run(["git", "-C", str(ROOT / "ninfer"), "status", "--porcelain", "--untracked-files=all"]).stdout.strip():
        die("NInfer source has local or untracked changes")
    image_id = run(["docker", "inspect", "--format", "{{.Image}}", ninfer_id]).stdout.strip()
    revision = run(["docker", "image", "inspect", "--format", '{{ index .Config.Labels "org.opencontainers.image.revision" }}', image_id]).stdout.strip()
    cuda_base = run(["docker", "image", "inspect", "--format", '{{ index .Config.Labels "org.opencontainers.image.base.name" }}', image_id]).stdout.strip()
    if revision != source_commit or cuda_base != EXPECTED_BASE:
        die("running NInfer image provenance does not match the pinned source and CUDA base")
    gpu_line = run(
        ["docker", "exec", ninfer_id, "nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader,nounits"]
    ).stdout.splitlines()[0]
    gpu_name, driver, vram_total = [item.strip() for item in gpu_line.split(",")[:3]]
    model_path = ROOT / "models" / values["NINFER_MODEL_FILE"]
    if not model_path.is_file() or file_sha256(model_path) != EXPECTED_SHA:
        die("model file is absent or does not match the registered benchmark checksum")

    environment = {
        "collected_at_utc": timestamp,
        "gpu": gpu_name,
        "driver_version": driver,
        "vram_total_mib": int(float(vram_total)),
        "docker_engine": run(["docker", "version", "--format", "{{.Server.Version}}"]).stdout.strip(),
        "docker_compose": run(["docker", "compose", "version", "--short"]).stdout.strip(),
        "cuda_image": cuda_base,
        "ninfer_commit": revision,
        "ninfer_image_id": image_id,
        "model_id": model_id,
        "model_file": values["NINFER_MODEL_FILE"],
        "model_sha256": EXPECTED_SHA,
        "quantization": "NVFP4",
        "context_length": int(values["NINFER_CONTEXT_LENGTH"]),
        "max_concurrency": int(values["NINFER_MAX_CONCURRENCY"]),
        "benchmark_runs": runs,
        "max_completion_tokens": max_tokens,
        "timing": "client-observed SSE wall clock",
        "server_state": "warm persistent server",
    }
    (result_dir / "environment.json").write_text(json.dumps(environment, indent=2) + "\n", encoding="utf-8")

    print("Warming the persistent NInfer server...")
    with post(
        endpoint,
        api_key,
        {"model": model_id, "messages": [{"role": "user", "content": "Reply with exactly WARMUP_OK."}], "max_tokens": 32, "temperature": 0, "enable_thinking": False},
    ) as response:
        warmup = json.loads(response.read())
    (result_dir / "warmup.json").write_text(json.dumps(warmup, indent=2) + "\n", encoding="utf-8")

    rows: list[dict[str, object]] = []
    for index in range(runs):
        run_number = index + 1
        run_id = f"{run_number:02d}"
        prompt = f"{NONCES[index]}. {PROMPT_TEMPLATE}"
        (result_dir / f"run-{run_id}.prompt.txt").write_text(prompt + "\n", encoding="utf-8")
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
            "max_completion_tokens": max_tokens,
            "temperature": 0,
            "seed": run_number,
            "enable_thinking": False,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        print(f"Running measurement {run_number}/{runs}...")
        samples: list[tuple[float, float]] = []
        stop = threading.Event()
        sampler = threading.Thread(target=gpu_sampler, args=(ninfer_id, stop, samples), daemon=True)
        sampler.start()
        start_ns = time.perf_counter_ns()
        first_ns: int | None = None
        prompt_tokens = completion_tokens = None
        finish_reason = ""
        output: list[str] = []
        events: list[dict[str, object]] = []
        try:
            with post(endpoint, api_key, payload) as response:
                for raw in response:
                    event_ns = time.perf_counter_ns()
                    line = raw.decode("utf-8").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        continue
                    event = json.loads(data)
                    events.append({"elapsed_ms": (event_ns - start_ns) / 1_000_000, "data": event})
                    choice = event.get("choices", [{}])[0]
                    delta = choice.get("delta", {})
                    content = delta.get("content") or delta.get("reasoning_content") or ""
                    if content and first_ns is None:
                        first_ns = event_ns
                    output.append(content)
                    usage = event.get("usage") or {}
                    prompt_tokens = usage.get("prompt_tokens", prompt_tokens)
                    completion_tokens = usage.get("completion_tokens", completion_tokens)
                    finish_reason = choice.get("finish_reason") or finish_reason
        finally:
            end_ns = time.perf_counter_ns()
            stop.set()
            sampler.join(timeout=20)
        if first_ns is None or prompt_tokens is None or completion_tokens is None or not samples:
            die(f"measurement {run_number} did not produce complete timing, usage, and GPU evidence")
        (result_dir / f"run-{run_id}.response.txt").write_text("".join(output), encoding="utf-8")
        with (result_dir / f"run-{run_id}.sse.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            for event in events:
                handle.write(json.dumps(event, separators=(",", ":")) + "\n")
        with (result_dir / f"run-{run_id}.gpu.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["utilization_gpu_pct", "memory_used_mib"])
            writer.writerows(samples)
        decode_seconds = (end_ns - first_ns) / 1_000_000_000
        rows.append(
            {
                "run": run_number,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "finish_reason": finish_reason,
                "ttft_ms": round((first_ns - start_ns) / 1_000_000, 2),
                "total_seconds": round((end_ns - start_ns) / 1_000_000_000, 3),
                "generation_tokens_per_second": round((completion_tokens - 1) / decode_seconds, 2) if decode_seconds > 0 and completion_tokens > 1 else 0,
                "gpu_samples": len(samples),
                "gpu_utilization_mean_pct": round(statistics.mean(item[0] for item in samples), 2),
                "gpu_utilization_max_pct": max(item[0] for item in samples),
                "vram_max_mib": max(item[1] for item in samples),
            }
        )

    with (result_dir / "runs.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    logs = compose("logs", "--no-color", "--since", started_at, "ninfer", timeout=120, check=False)
    (result_dir / "ninfer.log").write_text(logs.stdout + logs.stderr, encoding="utf-8")
    mean_ttft = statistics.mean(float(row["ttft_ms"]) for row in rows)
    mean_tps = statistics.mean(float(row["generation_tokens_per_second"]) for row in rows)
    peak_vram = max(float(row["vram_max_mib"]) for row in rows)
    summary = (
        "# Local NInfer benchmark\n\n"
        f"Collected: {timestamp}\n\n"
        f"- GPU: {gpu_name} ({vram_total} MiB), driver {driver}\n"
        f"- NInfer: `{revision}`\n"
        f"- Model: {model_id} / {values['NINFER_MODEL_FILE']} (NVFP4)\n"
        "- Timing: client-observed SSE wall clock on a warm persistent server\n\n"
        "| Runs | Mean TTFT | Mean generation | Peak VRAM |\n"
        "|---:|---:|---:|---:|\n"
        f"| {runs} | {mean_ttft:.2f} ms | {mean_tps:.2f} tok/s | {peak_vram:.0f} MiB |\n"
    )
    (result_dir / "summary.md").write_text(summary, encoding="utf-8")
    print(f"Benchmark complete: {result_dir}")
    print(f"Mean TTFT: {mean_ttft:.2f} ms; mean generation: {mean_tps:.2f} tok/s; peak VRAM: {peak_vram:.0f} MiB")
    print("Review generated responses before publishing any result.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
