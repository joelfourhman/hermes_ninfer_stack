#!/usr/bin/env python3
"""Cross-platform, layer-by-layer verification for the running stack."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
COMPOSE_FILE = ROOT / "docker-compose.yml"
EXPECTED_COMMIT = "feaf4dd0983fdaeb2ba4c06eec6da350e644fb3a"
EXPECTED_MODEL = "qwen3_8_27b_nvfp4.ninfer"
EXPECTED_SHA = "bb3360522a06e136e0367f5703414d26272b7285c8a6ab6194135c17dbd81b32"
EXPECTED_BASE = "docker.io/nvidia/cuda:13.1.2-runtime-ubuntu24.04"
TOTAL = 11
step = 0
temp_dir = Path(tempfile.mkdtemp(prefix="hermes-ninfer-verify-"))


class Failure(RuntimeError):
    def __init__(self, reason: str, diagnostic: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.diagnostic = diagnostic


def begin(label: str) -> None:
    global step
    step += 1
    print(f"[{step:02d}/{TOTAL:02d}] {label:<34}", end="", flush=True)


def passed(detail: str = "") -> None:
    print(" PASS")
    if detail:
        print(f"         {detail}")


def run(command: list[str], *, timeout: int = 120, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise Failure(f"Missing required command: {command[0]}", "install the documented prerequisites") from exc
    except subprocess.TimeoutExpired as exc:
        raise Failure(f"Command timed out after {timeout}s: {' '.join(command)}") from exc
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise Failure(detail or f"Command exited {completed.returncode}: {' '.join(command)}")
    return completed


def compose(*args: str, timeout: int = 120, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "docker",
            "compose",
            "--project-directory",
            str(ROOT),
            "--env-file",
            str(ENV_FILE),
            "-f",
            str(COMPOSE_FILE),
            *args,
        ],
        timeout=timeout,
        check=check,
    )


def env_values() -> dict[str, str]:
    if not ENV_FILE.is_file():
        raise Failure("Missing .env", "python stack.py setup")
    values: dict[str, str] = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if re.match(r"^[A-Z][A-Z0-9_]*=", line):
            key, value = line.split("=", 1)
            values[key] = value.rstrip("\r")
    return values


def request_json(url: str, *, token: str, payload: dict | None = None, timeout: int = 600) -> dict:
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
    headers = {"Authorization": f"Bearer {token}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers), timeout=timeout) as response:
            return json.loads(response.read())
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise Failure(f"Request failed for {url}: {exc}") from exc


def container_health(service: str) -> tuple[str, str]:
    container_id = compose("ps", "-q", service).stdout.strip()
    if not container_id:
        raise Failure(f"{service} is not running", f"python stack.py up")
    health = run(
        ["docker", "inspect", "--format", "{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}", container_id]
    ).stdout.strip()
    return container_id, health


def main() -> int:
    values = env_values()
    api_key = values.get("NINFER_API_KEY", "")
    hermes_key = values.get("HERMES_API_SERVER_KEY", "")
    host_port = values.get("NINFER_HOST_PORT", "")
    gpu = values.get("NINFER_GPU_DEVICE", "")
    model = values.get("NINFER_MODEL_FILE", "")
    model_id = values.get("NINFER_MODEL_ID", "")
    context = values.get("NINFER_CONTEXT_LENGTH", "")

    begin("Prerequisites and configuration")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", api_key):
        raise Failure("NINFER_API_KEY must be a 64-character hexadecimal secret", "python stack.py setup")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", hermes_key):
        raise Failure("HERMES_API_SERVER_KEY must be a 64-character hexadecimal secret", "python stack.py setup")
    if not host_port.isdigit() or not 1 <= int(host_port) <= 65535:
        raise Failure("NINFER_HOST_PORT must be from 1 through 65535", "edit .env")
    if not gpu.isdigit() or not re.fullmatch(r"[A-Za-z0-9._-]+\.ninfer", model):
        raise Failure("GPU device or model filename is invalid", "compare .env with .env.example")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", model_id) or not context.isdigit():
        raise Failure("Model ID or context length is invalid", "compare .env with .env.example")
    passed(f"model={model_id} context={context} GPU device={gpu}")

    begin("Compose and source pin")
    compose("config", "--quiet")
    commit = run(["git", "-C", str(ROOT / "ninfer"), "rev-parse", "HEAD"]).stdout.strip()
    if commit != EXPECTED_COMMIT:
        raise Failure(f"NInfer is at {commit}, expected {EXPECTED_COMMIT}")
    if run(["git", "-C", str(ROOT / "ninfer"), "status", "--porcelain", "--untracked-files=all"]).stdout.strip():
        raise Failure("The NInfer worktree has local or untracked changes")
    passed(f"NInfer {commit[:12]}; Compose resolves")

    begin("Docker daemon")
    run(["docker", "info"])
    version = run(["docker", "version", "--format", "{{.Server.Version}}"]).stdout.strip()
    passed(f"Docker Engine {version}")

    begin("NVIDIA container runtime")
    runtimes = run(["docker", "info", "--format", "{{json .Runtimes}}"]).stdout
    if "nvidia" not in runtimes.lower():
        raise Failure("Docker does not advertise the NVIDIA runtime", "configure NVIDIA Container Toolkit and restart Docker")
    passed("NVIDIA runtime is registered with Docker")

    begin("RTX 5090 GPU passthrough")
    image_ref = compose("config", "--images", "ninfer").stdout.strip()
    if not image_ref:
        raise Failure("Compose did not resolve the NInfer image name")
    image_id = run(["docker", "image", "inspect", "--format", "{{.Id}}", image_ref]).stdout.strip()
    revision = run(
        ["docker", "image", "inspect", "--format", '{{ index .Config.Labels "org.opencontainers.image.revision" }}', image_id]
    ).stdout.strip()
    base = run(
        ["docker", "image", "inspect", "--format", '{{ index .Config.Labels "org.opencontainers.image.base.name" }}', image_id]
    ).stdout.strip()
    if revision != EXPECTED_COMMIT or base != EXPECTED_BASE:
        raise Failure("NInfer image provenance labels do not match the pinned source and CUDA base", "python stack.py build")
    gpu_output = compose(
        "run",
        "--rm",
        "--no-deps",
        "-T",
        "--entrypoint",
        "nvidia-smi",
        "ninfer",
        "--query-gpu=name,driver_version,memory.total",
        "--format=csv,noheader",
        timeout=180,
    ).stdout.strip()
    if "RTX 5090" not in gpu_output.upper().replace("GEFORCE ", ""):
        raise Failure(f"The selected container GPU is not an RTX 5090: {gpu_output}")
    passed(f"image {revision[:12]}; {gpu_output}")

    begin("Pinned model artifact")
    if model != EXPECTED_MODEL:
        raise Failure(f"No checksum is registered for {model}")
    model_path = ROOT / "models" / model
    if not model_path.is_file() or model_path.stat().st_size == 0:
        raise Failure(f"Missing models/{model}", "python stack.py download-model")
    checksum = hashlib.sha256()
    with model_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            checksum.update(chunk)
    if checksum.hexdigest() != EXPECTED_SHA:
        raise Failure("Model checksum mismatch", "python stack.py download-model")
    passed("Qwen3.8-27B NVFP4 checksum matches")

    begin("NInfer container health")
    ninfer_id, health = container_health("ninfer")
    running_image = run(["docker", "inspect", "--format", "{{.Image}}", ninfer_id]).stdout.strip()
    if health != "healthy" or running_image != image_id:
        raise Failure(f"NInfer health is '{health}' or its running image is stale", "docker compose logs --tail=200 ninfer")
    passed("NInfer /health reports ready")

    begin("NInfer authenticated API")
    models = request_json(f"http://127.0.0.1:{host_port}/v1/models", token=api_key, timeout=30)
    if model_id not in [item.get("id") for item in models.get("data", [])]:
        raise Failure(f"NInfer does not advertise model ID {model_id}")
    passed(f"GET /v1/models advertises {model_id}")

    begin("Direct NInfer generation")
    direct = request_json(
        f"http://127.0.0.1:{host_port}/v1/chat/completions",
        token=api_key,
        payload={
            "model": model_id,
            "messages": [{"role": "user", "content": "Reply with exactly NINFER_DIRECT_OK and nothing else."}],
            "max_tokens": 64,
            "temperature": 0,
            "enable_thinking": False,
        },
    )
    (temp_dir / "ninfer-chat.json").write_text(json.dumps(direct, indent=2), encoding="utf-8")
    if direct.get("choices", [{}])[0].get("message", {}).get("content", "").strip() != "NINFER_DIRECT_OK":
        raise Failure("NInfer did not return the deterministic verification marker")
    passed("OpenAI-compatible chat completion succeeded")

    begin("Hermes health and routing")
    _, health = container_health("hermes")
    if health != "healthy":
        raise Failure(f"Hermes health is '{health}'", "docker compose logs --tail=200 hermes")
    checks = {
        "model.provider": "custom:ninfer",
        "model.default": model_id,
        "model.context_length": context,
        "providers.ninfer.api": "http://ninfer:8080/v1",
    }
    compose("exec", "-T", "hermes", "hermes", "config", "check")
    for key, expected in checks.items():
        actual = compose("exec", "-T", "hermes", "hermes", "config", "get", key).stdout.strip()
        if actual != expected:
            raise Failure(f"Hermes {key} is {actual!r}, expected {expected!r}", "python stack.py configure-hermes")
    compose("exec", "-T", "hermes", "getent", "hosts", "ninfer")
    passed(f"Hermes uses custom:ninfer / {model_id} / context {context}")

    def hermes_request(payload: dict, filename: str) -> dict:
        result = compose(
            "exec",
            "-T",
            "hermes",
            "curl",
            "--fail",
            "--silent",
            "--show-error",
            "--max-time",
            "900",
            "-H",
            f"Authorization: Bearer {hermes_key}",
            "-H",
            "Content-Type: application/json",
            "--data",
            json.dumps(payload, separators=(",", ":")),
            "http://127.0.0.1:8642/v1/chat/completions",
            timeout=930,
        )
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise Failure("Hermes returned invalid JSON") from exc
        (temp_dir / filename).write_text(json.dumps(parsed, indent=2), encoding="utf-8")
        return parsed

    begin("Hermes to NInfer generation")
    response = hermes_request(
        {
            "model": "hermes-agent",
            "messages": [{"role": "user", "content": "Reply with exactly HERMES_NINFER_OK and nothing else. Do not use tools."}],
            "stream": False,
        },
        "hermes-chat.json",
    )
    if response.get("choices", [{}])[0].get("message", {}).get("content", "").strip() != "HERMES_NINFER_OK":
        raise Failure("Hermes did not return the deterministic verification marker")
    passed("Hermes completed a request through NInfer")

    begin("Agent tool execution in sandbox")
    with tempfile.NamedTemporaryFile(prefix=".hermes-sandbox-verify.", dir=ROOT / "workspace", delete=False) as sentinel:
        sentinel_path = Path(sentinel.name)
    sentinel_path.write_bytes(b"")
    try:
        response = hermes_request(
            {
                "model": "hermes-agent",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "You must use the terminal tool. Run this exact command on its own line and do not alter it:\n"
                            f"uname -r > /workspace/{sentinel_path.name}\n"
                            "After it succeeds, reply exactly TOOL_EXECUTION_OK."
                        ),
                    }
                ],
                "stream": False,
            },
            "hermes-tool.json",
        )
        if not sentinel_path.is_file() or sentinel_path.stat().st_size == 0:
            raise Failure("The model did not produce a terminal side effect in workspace/")
        if response.get("choices", [{}])[0].get("message", {}).get("content", "").strip() != "TOOL_EXECUTION_OK":
            raise Failure("The sandbox command ran, but Hermes did not return the expected marker")
        passed(f"Hermes executed uname in the SSH sandbox ({sentinel_path.read_text().strip()})")
    finally:
        sentinel_path.unlink(missing_ok=True)

    print(f"\nAll {TOTAL} verification layers passed.")
    shutil.rmtree(temp_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Failure as exc:
        print(" FAIL", file=sys.stderr)
        print(f"         {exc.reason}", file=sys.stderr)
        if exc.diagnostic:
            print(f"         Next: {exc.diagnostic}", file=sys.stderr)
        print(f"         Verification responses: {temp_dir}", file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        print("\nVerification interrupted.", file=sys.stderr)
        raise SystemExit(130)
