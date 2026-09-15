#!/usr/bin/env python3
"""Cross-platform, layer-by-layer verification for the NInfer runtime."""

from __future__ import annotations

import hashlib
import json
import os
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
sys.path.insert(0, str(ROOT))
from stack.config import MANIFEST, MODEL_PROFILES as MODELS, RUNTIME_PROFILES as RUNTIMES, runtime_env_values
EXPECTED_COMMIT = MANIFEST["ninfer"]["commit"]
EXPECTED_BASE = MANIFEST["ninfer"]["cuda_base"]
MODEL_PROFILES = {key: {"file": p.filename, "sha256": p.sha256, "bytes": p.expected_bytes,
                        "label": p.label, "quantization": p.quantization} for key, p in MODELS.items()}
RUNTIME_PROFILES = {key: runtime_env_values(p) for key, p in RUNTIMES.items()}

TOTAL = 11
step = 0
temp_dir = Path(tempfile.mkdtemp(prefix="ninfer-verify-"))


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


def run(
    command: list[str],
    *,
    timeout: int = 120,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
            env=dict(env or os.environ, NINFER_SOURCE_REVISION=EXPECTED_COMMIT),
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
        raise Failure("Missing .env", "python ninfer.py setup")
    values: dict[str, str] = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if re.match(r"^[A-Z][A-Z0-9_]*=", line):
            key, value = line.split("=", 1)
            values[key] = value.rstrip("\r")
    return values


def private_env_value(path: Path, key: str) -> str | None:
    """Read the final value of one dotenv key without exposing other secrets."""
    if not path.is_file():
        return None
    found: str | None = None
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        candidate = line.strip()
        if candidate.startswith("export "):
            candidate = candidate[7:].lstrip()
        assigned, separator, raw = candidate.partition("=")
        if not separator or assigned.upper() != key.upper():
            continue
        raw = raw.strip()
        if len(raw) >= 2 and raw[0] == raw[-1] == '"':
            try:
                found = json.loads(raw)
            except json.JSONDecodeError:
                found = raw[1:-1]
        elif len(raw) >= 2 and raw[0] == raw[-1] == "'":
            found = raw[1:-1]
        else:
            found = raw
    return found


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
        raise Failure(f"{service} is not running", "python ninfer.py up")
    health = run(
        ["docker", "inspect", "--format", "{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}", container_id]
    ).stdout.strip()
    return container_id, health


def native_hermes_command() -> tuple[list[str], dict[str, str]] | None:
    configured_home = os.environ.get("HERMES_HOME")
    if configured_home:
        home = Path(configured_home).expanduser()
    elif os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        home = Path(os.environ["LOCALAPPDATA"]) / "hermes"
    else:
        home = Path.home() / ".hermes"

    if os.name == "nt":
        python_candidates = [home / "hermes-agent" / "venv" / "Scripts" / "python.exe"]
        launcher_candidates = [
            home / "bin" / "hermes.exe",
            home / "hermes-agent" / "venv" / "Scripts" / "hermes.exe",
        ]
    else:
        python_candidates = [home / "hermes-agent" / "venv" / "bin" / "python"]
        launcher_candidates = [
            home / "bin" / "hermes",
            home / "hermes-agent" / "venv" / "bin" / "hermes",
        ]

    command: list[str] | None = None
    for candidate in python_candidates:
        if candidate.is_file():
            command = [str(candidate), "-m", "hermes_cli.main"]
            break
    if command is None:
        for candidate in launcher_candidates:
            if candidate.is_file():
                command = [str(candidate)]
                break
    if command is None:
        discovered = shutil.which("hermes.exe" if os.name == "nt" else "hermes")
        if discovered:
            command = [discovered]
    if command is None:
        return None

    process_env = os.environ.copy()
    process_env["HERMES_HOME"] = str(home)
    return command, process_env


def verify_optional_hermes(
    *,
    endpoint: str,
    model_id: str,
    context: str,
    compression: str,
    compression_threshold: str,
    max_turns: str,
) -> None:
    begin("Optional native Hermes config")
    resolved = native_hermes_command()
    if resolved is None:
        passed("Stock Hermes Desktop is not installed or discoverable; skipped")
        return
    command, process_env = resolved

    if Path(command[0]).stem.lower().startswith("python"):
        run([command[0], str(ROOT / "scripts/check_hermes_context.py")], env=process_env)

    config_check = run([*command, "config", "check"], check=False, env=process_env)
    if config_check.returncode != 0:
        raise Failure(
            "Stock Hermes is installed, but its native configuration is invalid",
            "python ninfer.py install-hermes",
        )

    expected = {
        "model.provider": "custom:ninfer",
        "model.default": model_id,
        "model.context_length": context,
        "model.supports_vision": "false",
        "providers.ninfer.api": endpoint,
        "compression.enabled": compression,
        "compression.threshold": "0.5",
        "compression.threshold_tokens": compression_threshold,
        "auxiliary.compression.provider": "main",
        "auxiliary.compression.timeout": "600",
        "auxiliary.compression.extra_body.enable_thinking": "false",
        "agent.max_turns": max_turns,
        "terminal.backend": "local",
        "approvals.mode": "manual",
    }
    actual: dict[str, str] = {}
    for key in expected:
        result = run([*command, "config", "get", key], check=False, env=process_env)
        if result.returncode != 0:
            raise Failure(
                f"Hermes is missing the native NInfer setting {key}",
                "python ninfer.py install-hermes",
            )
        actual[key] = result.stdout.strip().strip('"')
    mismatches = [
        f"{key}={actual[key]!r} (expected {value!r})"
        for key, value in expected.items()
        if actual[key].lower() != value.lower()
    ]
    if mismatches:
        raise Failure(
            "Native Hermes NInfer configuration mismatch: " + "; ".join(mismatches),
            "python ninfer.py install-hermes",
        )
    profile_home = Path(process_env["HERMES_HOME"]).expanduser().resolve()
    if private_env_value(profile_home / ".env", "HERMES_WRITE_SAFE_ROOT") is not None:
        raise Failure(
            "Hermes still has the legacy project workspace write restriction",
            "python ninfer.py install-hermes",
        )

    marker = "HERMES_NINFER_OK"
    probe = run(
        [
            *command,
            "--ignore-rules",
            "-z",
            f"Reply with exactly {marker} and nothing else. Do not use tools.",
        ],
        timeout=900,
        env=process_env,
    ).stdout.strip()
    if probe != marker:
        raise Failure(
            f"Native Hermes did not return the expected route marker; received {probe!r}",
            "python ninfer.py install-hermes",
        )
    passed(f"Hermes generated through {expected['providers.ninfer.api']} with model {model_id}")


def main() -> int:
    values = env_values()
    from stack.config import validate_spec
    from stack.provenance import verify_cli_help
    try:
        validate_spec(values)
    except ValueError as exc:
        raise Failure(str(exc)) from exc
    api_key = values.get("NINFER_API_KEY", "")
    access_mode = values.get("NINFER_ACCESS_MODE", "")
    bind_address = values.get("NINFER_BIND_ADDRESS", "")
    host_port = values.get("NINFER_HOST_PORT", "")
    gpu = values.get("NINFER_GPU_DEVICE", "")
    profile_key = values.get("NINFER_MODEL_PROFILE", "")
    runtime_key = values.get("NINFER_RUNTIME_PROFILE", "")
    model = values.get("NINFER_MODEL_FILE", "")
    model_id = values.get("NINFER_MODEL_ID", "")
    context = values.get("NINFER_CONTEXT_LENGTH", "")
    kv_capacity = values.get("NINFER_KV_CAPACITY", "")
    concurrency = values.get("NINFER_MAX_CONCURRENCY", "")
    compression = values.get("HERMES_COMPRESSION_ENABLED", "")
    compression_threshold = values.get("HERMES_COMPRESSION_THRESHOLD_TOKENS", "")
    max_turns = values.get("HERMES_MAX_TURNS", "")

    begin("Prerequisites and configuration")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", api_key):
        raise Failure("NINFER_API_KEY must be a 64-character hexadecimal secret", "python ninfer.py setup")
    if not (
        (access_mode == "local" and bind_address == "127.0.0.1")
        or (access_mode == "lan" and bind_address == "0.0.0.0")
    ):
        raise Failure(
            "NInfer network mode and bind address are inconsistent",
            "python ninfer.py network",
        )
    if not host_port.isdigit() or not 1 <= int(host_port) <= 65535:
        raise Failure("NINFER_HOST_PORT must be from 1 through 65535", "edit .env")
    if profile_key not in MODEL_PROFILES:
        raise Failure("NINFER_MODEL_PROFILE must be stock or uncensored", "python ninfer.py setup")
    if runtime_key not in RUNTIME_PROFILES:
        raise Failure("NINFER_RUNTIME_PROFILE is invalid", "python ninfer.py select-runtime")
    runtime_mismatches = [
        key
        for key, expected in RUNTIME_PROFILES[runtime_key].items()
        if values.get(key) != expected
    ]
    if runtime_mismatches:
        raise Failure(
            f"The {runtime_key} runtime has inconsistent values: " + ", ".join(runtime_mismatches),
            "python ninfer.py select-runtime",
        )
    if not gpu.isdigit() or not re.fullmatch(r"[A-Za-z0-9._-]+\.ninfer", model):
        raise Failure("GPU device or model filename is invalid", "compare .env with .env.example")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", model_id) or not context.isdigit():
        raise Failure("Model ID or context length is invalid", "compare .env with .env.example")
    if not concurrency.isdigit() or not 1 <= int(concurrency) <= 8:
        raise Failure("NInfer concurrency must be from 1 through 8", "compare .env with .env.example")
    if not kv_capacity.isdigit() or not int(context) <= int(kv_capacity) <= int(context) * int(concurrency):
        raise Failure("KV capacity must be between context and context times concurrency", "compare .env with .env.example")
    if (
        compression not in {"true", "false"}
        or not compression_threshold.isdigit()
        or not max_turns.isdigit()
    ):
        raise Failure("Hermes compression or maximum turns is invalid", "compare .env with .env.example")
    endpoint = f"http://127.0.0.1:{host_port}/v1"
    passed(
        f"model={model_id} runtime={runtime_key} access={access_mode} "
        f"context={context} KV={kv_capacity} concurrency={concurrency} GPU={gpu}"
    )

    begin("Compose and source pin")
    rendered_compose = compose("config").stdout
    if f"host_ip: {bind_address}" not in rendered_compose:
        raise Failure("NInfer is not published on its configured host address")
    commit = run(["git", "-C", str(ROOT / "ninfer"), "rev-parse", "HEAD"]).stdout.strip()
    if commit != EXPECTED_COMMIT:
        raise Failure(f"NInfer is at {commit}, expected {EXPECTED_COMMIT}")
    if run(["git", "-C", str(ROOT / "ninfer"), "status", "--porcelain", "--untracked-files=all"]).stdout.strip():
        raise Failure("The NInfer worktree has local or untracked changes")
    passed(f"NInfer {commit[:12]}; authenticated {access_mode} Compose config resolves")

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
        raise Failure("NInfer image provenance labels do not match the pinned source and CUDA base", "python ninfer.py build")
    help_text = compose("run", "--rm", "--no-deps", "-T", "ninfer", "ninfer-serve", "--help").stdout
    try:
        verify_cli_help(help_text)
    except ValueError as exc:
        raise Failure(str(exc)) from exc
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
    profile = MODEL_PROFILES[profile_key]
    if model != profile["file"]:
        raise Failure(f"Model {model} does not match profile {profile_key}")
    model_path = ROOT / "models" / model
    if not model_path.is_file():
        raise Failure(f"Missing models/{model}", f"python ninfer.py prepare-model --model {profile_key}")
    if model_path.stat().st_size != profile["bytes"]:
        raise Failure(f"Model size mismatch: expected {profile['bytes']:,} bytes")
    checksum = hashlib.sha256()
    with model_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            checksum.update(chunk)
    actual_sha = checksum.hexdigest()
    if actual_sha != profile["sha256"]:
        raise Failure(f"{profile_key.capitalize()} model checksum does not match the pin")
    detail = "pinned published artifact"
    passed(f"{profile['label']} checksum matches ({detail})")

    begin("NInfer container health")
    ninfer_id, health = container_health("ninfer")
    running_image = run(["docker", "inspect", "--format", "{{.Image}}", ninfer_id]).stdout.strip()
    if health != "healthy" or running_image != image_id:
        raise Failure(f"NInfer health is '{health}' or its running image is stale", "docker compose logs --tail=200 ninfer")
    confinement = run(
        [
            "docker",
            "inspect",
            "--format",
            "{{.HostConfig.ReadonlyRootfs}}|{{json .HostConfig.Tmpfs}}",
            ninfer_id,
        ]
    ).stdout.strip()
    if not confinement.startswith("true|") or '"/tmp"' not in confinement:
        raise Failure("NInfer does not have the reviewed read-only root and temporary filesystem")
    passed("NInfer /health reports ready; container root is read-only")

    begin("NInfer authentication boundary")
    models_url = f"{endpoint}/models"
    try:
        urllib.request.urlopen(models_url, timeout=30).close()
    except urllib.error.HTTPError as exc:
        if exc.code not in {401, 403}:
            raise Failure(f"Unauthenticated NInfer request returned HTTP {exc.code}, expected 401 or 403") from exc
    except urllib.error.URLError as exc:
        raise Failure(f"Could not reach NInfer at {endpoint}: {exc}") from exc
    else:
        raise Failure("NInfer accepted an unauthenticated request")
    passed("Host API rejects requests without the bearer key")

    begin("NInfer authenticated API")
    models = request_json(models_url, token=api_key, timeout=30)
    if model_id not in [item.get("id") for item in models.get("data", [])]:
        raise Failure(f"NInfer does not advertise model ID {model_id}")
    passed(f"GET /v1/models advertises {model_id}")

    begin("Direct NInfer generation")
    direct = request_json(
        f"{endpoint}/chat/completions",
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

    verify_optional_hermes(
        endpoint=endpoint,
        model_id=model_id,
        context=context,
        compression=compression,
        compression_threshold=compression_threshold,
        max_turns=max_turns,
    )

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
