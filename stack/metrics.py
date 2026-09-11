"""Small, structured observations; unknown counters remain null."""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import threading
import time
from pathlib import Path

from stack.config import MANIFEST, NINFER_COMMIT
from stack.provenance import verify_image, verify_model


def command_json(command: list[str]) -> object:
    return json.loads(
        subprocess.check_output(command, text=True, stderr=subprocess.PIPE, timeout=60)
    )


def runtime_metadata(helper, *, baseline: bool = False, hash_model: bool = True) -> dict:
    values = helper.read_env()
    container = helper.compose("ps", "-q", "ninfer", capture=True).stdout.strip()
    if not container:
        raise ValueError("NInfer is not running")
    info = command_json([helper.docker_executable() or "docker", "inspect", container])[0]
    labels = (
        command_json([helper.docker_executable() or "docker", "image", "inspect", info["Image"]])[
            0
        ]["Config"].get("Labels")
        or {}
    )
    revision = labels.get("org.opencontainers.image.revision")
    if baseline:
        if revision != MANIFEST["ninfer"]["baseline_commit"]:
            raise ValueError("--baseline requires the original known-good image revision")
    else:
        verify_image(labels)
    args = info["Config"].get("Cmd") or []
    flags = {
        args[i]: args[i + 1]
        for i in range(len(args) - 1)
        if args[i].startswith("--") and not args[i + 1].startswith("--")
    }
    mapping = {
        "--max-context": "NINFER_CONTEXT_LENGTH",
        "--kv-capacity": "NINFER_KV_CAPACITY",
        "--max-concurrency": "NINFER_MAX_CONCURRENCY",
        "--kv-dtype": "NINFER_KV_DTYPE",
        "--device-state-slots": "NINFER_DEVICE_STATE_SLOTS",
        "--host-state-slots": "NINFER_HOST_STATE_SLOTS",
        "--host-kv-mib": "NINFER_HOST_KV_MIB",
        "--spec": "NINFER_SPEC_BACKEND",
        "--draft-tokens": "NINFER_DRAFT_TOKENS",
        "--model-id": "NINFER_MODEL_ID",
    }
    defaults = {"NINFER_SPEC_BACKEND": "mtp", "NINFER_DRAFT_TOKENS": "3"}
    for flag, key in mapping.items():
        if flags.get(flag) != values.get(key, defaults.get(key)):
            raise ValueError(
                f"Running {flag} differs from configured {key}; recreate before benchmarking"
            )
    if "/models/" + values["NINFER_MODEL_FILE"] not in args:
        raise ValueError("Running model filename differs from configured artifact")
    digest = (
        verify_model(
            helper.ROOT / "models" / values["NINFER_MODEL_FILE"],
            values["NINFER_MODEL_PROFILE"],
        )
        if hash_model
        else None
    )
    return {
        "container_id": container,
        "image_id": info["Image"],
        "ninfer_revision": revision,
        "source_expected": NINFER_COMMIT,
        "baseline": baseline,
        "model_sha256_verified": digest,
        "config": {
            key: value
            for key, value in values.items()
            if key.startswith("NINFER_") and key != "NINFER_API_KEY"
        },
        "runtime_flags": {key: flags.get(key) for key in mapping},
        "hermes_session_id": None,
    }


def parse_native_logs(text: str) -> list[dict]:
    records = []
    for line in text.splitlines():
        start = line.find("{")
        if start < 0:
            continue
        try:
            record = json.loads(line[start:])
        except json.JSONDecodeError:
            continue
        if record.get("event") in {
            "server_start",
            "request_done",
            "throughput",
            "request_error",
            "request_rejected",
            "request_start",
        }:
            records.append(record)
    return records


def memory_used_mib() -> float | None:
    if os.name == "nt":

        class MemoryStatus(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                (key, ctypes.c_ulonglong)
                for key in (
                    "total_phys",
                    "avail_phys",
                    "total_page",
                    "avail_page",
                    "total_virtual",
                    "avail_virtual",
                    "extended",
                )
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return (status.total_phys - status.avail_phys) / 1048576
    elif Path("/proc/meminfo").exists():
        fields = {
            line.split(":")[0]: int(line.split()[1])
            for line in Path("/proc/meminfo").read_text().splitlines()
        }
        return (fields["MemTotal"] - fields["MemAvailable"]) / 1024
    return None


class Sampler:
    def __init__(self, gpu_command: str | None, gpu: str = "0"):
        self.command, self.gpu = gpu_command, gpu
        self.samples: list[dict] = []
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self.stop.is_set():
            row = {
                "time_unix": time.time(),
                "system_ram_used_mib": memory_used_mib(),
                "gpu_utilization_percent": None,
                "vram_used_mib": None,
            }
            if self.command:
                try:
                    result = subprocess.run(
                        [
                            self.command,
                            "-i",
                            self.gpu,
                            "--query-gpu=utilization.gpu,memory.used",
                            "--format=csv,noheader,nounits",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        check=False,
                    )
                    values = [float(v.strip()) for v in result.stdout.strip().split(",")]
                    row.update(gpu_utilization_percent=values[0], vram_used_mib=values[1])
                except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
                    pass
            self.samples.append(row)
            self.stop.wait(1)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join(timeout=7)


def observe(args) -> None:
    from stack.commands import _helper

    helper = _helper()
    metadata = runtime_metadata(helper, hash_model=False, baseline=args.baseline)
    raw = helper.compose(
        "logs", "--no-color", "--tail", str(args.lines), "ninfer", capture=True
    ).stdout
    records = parse_native_logs(raw)
    latest = {}
    for record in records:
        latest[record["event"]] = record
    with Sampler(helper.nvidia_smi_executable(), helper.read_env()["NINFER_GPU_DEVICE"]) as sampler:
        sampler.stop.wait(1.1)
    result = {
        "metadata": metadata,
        "hardware": sampler.samples[-1] if sampler.samples else None,
        "latest_native_events": latest,
        "job": None,
        "scope": "Native cache/scheduler gauges are interval-level; absent data is unknown.",
    }
    if args.state:
        from stack.jobs import load_state

        result["job"] = load_state(Path(args.state))
        events = Path(result["job"]["job_dir"]) / "events/events.jsonl"
        if events.exists():
            # Seek only the log tail; observations must remain cheap on long jobs.
            with events.open("rb") as stream:
                stream.seek(max(0, events.stat().st_size - 65536))
                lines = stream.read().decode("utf-8", errors="replace").splitlines()
            for line in reversed(lines):
                try:
                    result["latest_job_event"] = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue
    output = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
