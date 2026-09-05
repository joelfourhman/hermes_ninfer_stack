#!/usr/bin/env python3
"""Cross-platform setup and control for NInfer plus native Hermes Desktop."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
COMPOSE_FILE = ROOT / "docker-compose.yml"
NINFER_COMMIT = "feaf4dd0983fdaeb2ba4c06eec6da350e644fb3a"
NINFER_URL = "https://github.com/Neroued/ninfer.git"
MODEL_FILE = "qwen3_8_27b_uncensored.ninfer"
LEGACY_MODEL_FILE = "qwen3_8_27b_nvfp4.ninfer"
MODEL_SIZE_GIB = "16.96"
MODEL_SOURCE_GIB = "55"
MODEL_BUILD_GIB = "90"
MODEL_EXPECTED_BYTES = 18_210_531_328
MODEL_MANIFEST_FILE = f"{MODEL_FILE}.local-manifest.json"
HERMES_DESKTOP_URL = "https://hermes-agent.nousresearch.com/desktop"
DOCKER_DESKTOP_URL = "https://www.docker.com/products/docker-desktop/"
DOCKER_ENGINE_URL = "https://docs.docker.com/engine/install/"
PYTHON_DOWNLOAD_URL = "https://www.python.org/downloads/"
GIT_DOWNLOAD_URL = "https://git-scm.com/downloads"
NVIDIA_DRIVER_URL = "https://www.nvidia.com/Download/index.aspx"
REQUIRED_FREE_BYTES = 90 * 1024**3
SETUP_COMMAND = "python ninfer.py setup"


class StackError(RuntimeError):
    pass


def stage(number: int, total: int, title: str) -> None:
    print()
    print(f"[{number}/{total}] {title}")


def open_official_page(url: str, description: str) -> bool:
    try:
        opened = webbrowser.open_new_tab(url)
    except (OSError, webbrowser.Error):
        opened = False
    if opened:
        print(f"Opened the official {description} page in your browser.")
    else:
        print(f"Open the official {description} page: {url}")
    return opened


def run(
    command: list[str],
    *,
    check: bool = True,
    capture: bool = False,
    env: dict[str, str] | None = None,
    redact: set[int] | None = None,
) -> subprocess.CompletedProcess[str]:
    display_command = list(command)
    for index in redact or set():
        if -len(display_command) <= index < len(display_command):
            display_command[index] = "<redacted>"
    try:
        return subprocess.run(
            command,
            cwd=ROOT,
            check=check,
            text=True,
            env=env,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
        )
    except FileNotFoundError as exc:
        raise StackError(f"Required command is not installed or not on PATH: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        if capture and exc.stderr and not redact:
            print(exc.stderr.rstrip(), file=sys.stderr)
        raise StackError(
            f"Command failed with exit code {exc.returncode}: {' '.join(display_command)}"
        ) from exc


def docker_executable() -> str | None:
    discovered = shutil.which("docker.exe" if os.name == "nt" else "docker")
    if discovered:
        return discovered
    if os.name == "nt":
        roots = [os.environ.get("ProgramW6432"), os.environ.get("ProgramFiles")]
        for root in filter(None, roots):
            candidate = Path(root) / "Docker" / "Docker" / "resources" / "bin" / "docker.exe"
            if candidate.is_file():
                return str(candidate)
    return None


def compose(*args: str, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess[str]:
    command = [docker_executable() or "docker", "compose", "--project-directory", str(ROOT)]
    if ENV_FILE.is_file():
        command += ["--env-file", str(ENV_FILE)]
    command += ["-f", str(COMPOSE_FILE), *args]
    return run(command, check=check, capture=capture)


def windows_docker_desktop_executable() -> Path | None:
    if os.name != "nt":
        return None
    roots = [os.environ.get("ProgramW6432"), os.environ.get("ProgramFiles")]
    local_app_data = os.environ.get("LOCALAPPDATA")
    candidates = [
        *(Path(root) / "Docker" / "Docker" / "Docker Desktop.exe" for root in filter(None, roots)),
        *([Path(local_app_data) / "Docker" / "Docker Desktop.exe"] if local_app_data else []),
    ]
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def launch_windows_docker_desktop() -> bool:
    executable = windows_docker_desktop_executable()
    if executable is None:
        return False
    try:
        subprocess.Popen(
            [str(executable)],
            cwd=executable.parent,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except OSError:
        return False
    return True


def docker_server_os(docker: str) -> str | None:
    try:
        result = run(
            [docker, "info", "--format", "{{.OSType}}"],
            check=False,
            capture=True,
        )
    except StackError:
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip().strip('"').lower()
    return value or None


def nvidia_smi_executable() -> str | None:
    discovered = shutil.which("nvidia-smi.exe" if os.name == "nt" else "nvidia-smi")
    if discovered:
        return discovered
    if os.name == "nt" and os.environ.get("WINDIR"):
        candidate = Path(os.environ["WINDIR"]) / "System32" / "nvidia-smi.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def check_setup_prerequisites() -> str:
    terminal = "Command Prompt" if os.name == "nt" else "your terminal"
    docker_name = "Docker Desktop" if os.name == "nt" else "Docker Engine"
    docker_url = DOCKER_DESKTOP_URL if os.name == "nt" else DOCKER_ENGINE_URL
    if sys.version_info < (3, 10):
        raise StackError(
            f"Python 3.10 or newer is required; this is Python {sys.version_info.major}."
            f"{sys.version_info.minor}. Install it from {PYTHON_DOWNLOAD_URL}, then rerun "
            f"'{SETUP_COMMAND}'."
        )
    print(f"Python {sys.version_info.major}.{sys.version_info.minor} is ready.")

    model_path = ROOT / "models" / MODEL_FILE
    manifest_path = ROOT / "models" / MODEL_MANIFEST_FILE
    if (
        model_path.is_file()
        and model_path.stat().st_size == MODEL_EXPECTED_BYTES
        and manifest_path.is_file()
    ):
        print("The locally built AI model is already present; its checksum will be verified.")
    else:
        free = shutil.disk_usage(ROOT).free
        free_gib = free / 1024**3
        if free < REQUIRED_FREE_BYTES:
            raise StackError(
                f"The drive containing this project has {free_gib:.1f} GiB free; setup needs at "
                f"least {MODEL_BUILD_GIB} GiB for the source weights and conversion workspace. "
                f"Free some space, then rerun '{SETUP_COMMAND}'."
            )
        print(
            f"Disk space is ready ({free_gib:.1f} GiB free; "
            f"{MODEL_BUILD_GIB} GiB required during the model build)."
        )

    if shutil.which("git.exe" if os.name == "nt" else "git") is None:
        raise StackError(
            f"Git is required to fetch the pinned NInfer source. Install it from "
            f"{GIT_DOWNLOAD_URL}, reopen {terminal}, then rerun '{SETUP_COMMAND}'."
        )
    print("Git is ready.")

    nvidia_smi = nvidia_smi_executable()
    if nvidia_smi is None:
        raise StackError(
            "The NVIDIA driver was not detected. Install the current RTX 5090 driver from "
            f"{NVIDIA_DRIVER_URL}, restart the computer if asked, then rerun "
            f"'{SETUP_COMMAND}'."
        )
    gpu_result = run(
        [nvidia_smi, "--query-gpu=index,name,driver_version", "--format=csv,noheader"],
        check=False,
        capture=True,
    )
    if gpu_result.returncode != 0:
        raise StackError(
            "The NVIDIA driver could not report the GPU. Restart the computer or update the "
            f"RTX 5090 driver from {NVIDIA_DRIVER_URL}, then rerun '{SETUP_COMMAND}'."
        )
    gpu_rows = gpu_result.stdout.strip()
    parsed_gpus: list[tuple[str, str, str]] = []
    for row in gpu_rows.splitlines():
        fields = [field.strip() for field in row.split(",", 2)]
        if len(fields) >= 2:
            parsed_gpus.append((fields[0], fields[1], row.strip()))
    rtx_5090_gpus = [gpu for gpu in parsed_gpus if "RTX 5090" in gpu[1].upper()]
    if not rtx_5090_gpus:
        detected = gpu_rows or "no NVIDIA GPU"
        raise StackError(
            f"This setup requires an RTX 5090, but NVIDIA reported: {detected}."
        )
    configured_gpu = read_env().get("NINFER_GPU_DEVICE") if ENV_FILE.is_file() else None
    if configured_gpu:
        selected = next((gpu for gpu in rtx_5090_gpus if gpu[0] == configured_gpu), None)
        if selected is None:
            available = ", ".join(gpu[0] for gpu in rtx_5090_gpus)
            raise StackError(
                f".env selects NVIDIA GPU {configured_gpu}, but the RTX 5090 is at GPU "
                f"{available}. Set NINFER_GPU_DEVICE={rtx_5090_gpus[0][0]} in .env, then "
                f"rerun '{SETUP_COMMAND}'."
            )
    else:
        selected = rtx_5090_gpus[0]
    print(f"RTX 5090 is ready ({selected[2]}).")

    docker = docker_executable()
    if docker is None:
        if sys.stdin.isatty():
            open_official_page(docker_url, f"{docker_name} installation")
        raise StackError(
            f"{docker_name} is not installed or its command is not available. Install it from "
            f"{docker_url}, reopen {terminal}, then rerun '{SETUP_COMMAND}'."
        )
    compose_result = run([docker, "compose", "version"], check=False, capture=True)
    if compose_result.returncode != 0:
        raise StackError(
            f"Docker Compose is missing. Update {docker_name}, reopen {terminal}, then rerun "
            f"'{SETUP_COMMAND}'."
        )
    compose_version = compose_result.stdout.strip()
    print(f"Docker Compose is ready ({compose_version}).")

    server_os = docker_server_os(docker)
    if server_os is None and os.name == "nt" and launch_windows_docker_desktop():
        print("Docker Desktop is installed but stopped. Opening it now...")
        print("Waiting up to 3 minutes for its engine to become ready.")
        deadline = time.monotonic() + 180
        next_update = time.monotonic() + 20
        while time.monotonic() < deadline:
            server_os = docker_server_os(docker)
            if server_os is not None:
                break
            if time.monotonic() >= next_update:
                print("Docker Desktop is still starting...")
                next_update = time.monotonic() + 20
            time.sleep(2)
    if server_os is None:
        action = (
            "Open Docker Desktop and wait until it says the engine is running"
            if os.name == "nt"
            else "Start Docker Engine and wait until it is running"
        )
        raise StackError(f"{action}, then rerun '{SETUP_COMMAND}'. No completed work will be lost.")
    if server_os != "linux":
        raise StackError(
            "Docker Desktop is using Windows containers. Switch Docker Desktop to Linux "
            f"containers, wait for it to finish, then rerun '{SETUP_COMMAND}'."
        )
    if os.name == "nt":
        print("Docker Desktop is running with Linux containers.")
    else:
        print("Docker Engine is running.")
    return selected[0]


def read_env(path: Path | None = None) -> dict[str, str]:
    if path is None:
        path = ENV_FILE
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip("\r")
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            values[key] = value
    return values


def atomic_write(path: Path, text: str) -> None:
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as output:
            output.write(text)
        try:
            os.chmod(temp_name, 0o600)
        except OSError:
            pass
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def set_private_env_value(path: Path, key: str, value: str) -> None:
    """Atomically set one dotenv value while preserving unrelated settings."""
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
        raise StackError(f"Invalid private environment key: {key!r}")
    if "\n" in value or "\r" in value:
        raise StackError(f"Invalid newline in private environment value for {key}")
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = (
        path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        if path.is_file()
        else []
    )
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    assignment = f'{key}="{escaped}"'
    output: list[str] = []
    replaced = False
    for line in existing:
        candidate = line.strip()
        if candidate.startswith("export "):
            candidate = candidate[7:].lstrip()
        assigned_key, separator, _ = candidate.partition("=")
        matches = bool(separator) and (
            assigned_key.upper() == key if os.name == "nt" else assigned_key == key
        )
        if matches:
            if not replaced:
                output.append(assignment)
                replaced = True
            continue
        output.append(line)
    if not replaced:
        output.append(assignment)
    atomic_write(path, "\n".join(output).rstrip() + "\n")


def merge_env(detected_gpu_device: str | None = None) -> None:
    creating = not ENV_FILE.is_file()
    example_lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    existing = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.is_file() else []
    existing_keys = {
        line.split("=", 1)[0]
        for line in existing
        if re.match(r"^[A-Z][A-Z0-9_]*=", line)
    }
    original_values = {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in existing
        if re.match(r"^[A-Z][A-Z0-9_]*=", line)
    }
    merged = list(existing)
    for line in example_lines:
        match = re.match(r"^([A-Z][A-Z0-9_]*)=", line)
        if match and match.group(1) not in existing_keys:
            merged.append(line)
            existing_keys.add(match.group(1))
    if creating:
        merged = list(example_lines)

    replacements = {"NINFER_API_KEY": secrets.token_hex(32)}
    forced: dict[str, str] = {}
    if detected_gpu_device is not None and not original_values.get("NINFER_GPU_DEVICE"):
        forced["NINFER_GPU_DEVICE"] = detected_gpu_device
    if os.name != "nt" and hasattr(os, "getuid") and hasattr(os, "getgid"):
        if not original_values.get("MODEL_BUILD_UID"):
            forced["MODEL_BUILD_UID"] = str(os.getuid())
        if not original_values.get("MODEL_BUILD_GID"):
            forced["MODEL_BUILD_GID"] = str(os.getgid())
    values = {}
    for line in merged:
        if re.match(r"^[A-Z][A-Z0-9_]*=", line):
            key, value = line.split("=", 1)
            values[key] = value
    for key in list(replacements):
        if values.get(key):
            replacements.pop(key)

    output: list[str] = []
    for line in merged:
        if re.match(r"^[A-Z][A-Z0-9_]*=", line):
            key = line.split("=", 1)[0]
            if key in forced:
                line = f"{key}={forced[key]}"
            elif key in replacements:
                line = f"{key}={replacements[key]}"
        output.append(line)
    atomic_write(ENV_FILE, "\n".join(output).rstrip() + "\n")


def validate_env() -> None:
    values = read_env()
    required = [
        "NINFER_API_KEY",
        "MODEL_BUILD_UID",
        "MODEL_BUILD_GID",
        "NINFER_HOST_PORT",
        "NINFER_GPU_DEVICE",
        "NINFER_MODEL_FILE",
        "NINFER_MODEL_ID",
        "NINFER_CONTEXT_LENGTH",
        "NINFER_KV_CAPACITY",
        "NINFER_MAX_CONCURRENCY",
        "HERMES_COMPRESSION_ENABLED",
        "HERMES_COMPRESSION_THRESHOLD_TOKENS",
        "HERMES_MAX_TURNS",
    ]
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise StackError("Missing required .env values: " + ", ".join(missing))
    if not re.fullmatch(r"[0-9a-fA-F]{64}", values["NINFER_API_KEY"]):
        raise StackError("NINFER_API_KEY must be a 64-character hexadecimal secret")
    host_port = values["NINFER_HOST_PORT"]
    if not host_port.isdigit() or not 1 <= int(host_port) <= 65535:
        raise StackError("NINFER_HOST_PORT must be from 1 through 65535")
    if not values["NINFER_GPU_DEVICE"].isdigit():
        raise StackError("NINFER_GPU_DEVICE must be a non-negative integer")
    for key in ("MODEL_BUILD_UID", "MODEL_BUILD_GID"):
        if not values[key].isdigit() or int(values[key]) < 0:
            raise StackError(f"{key} must be a non-negative integer")
    if not re.fullmatch(r"[A-Za-z0-9._-]+\.ninfer", values["NINFER_MODEL_FILE"]):
        raise StackError("NINFER_MODEL_FILE must be a .ninfer filename, not a path")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", values["NINFER_MODEL_ID"]):
        raise StackError("NINFER_MODEL_ID contains unsupported characters")
    context = values["NINFER_CONTEXT_LENGTH"]
    kv_capacity = values["NINFER_KV_CAPACITY"]
    concurrency = values["NINFER_MAX_CONCURRENCY"]
    max_turns = values["HERMES_MAX_TURNS"]
    if not context.isdigit() or not 1024 <= int(context) <= 262144:
        raise StackError("NINFER_CONTEXT_LENGTH must be from 1024 through 262144")
    if not concurrency.isdigit() or not 1 <= int(concurrency) <= 8:
        raise StackError("NINFER_MAX_CONCURRENCY must be from 1 through 8")
    if not kv_capacity.isdigit() or not int(context) <= int(kv_capacity) <= int(context) * int(concurrency):
        raise StackError("NINFER_KV_CAPACITY must be between context and context times concurrency")
    if values["HERMES_COMPRESSION_ENABLED"] not in {"true", "false"}:
        raise StackError("HERMES_COMPRESSION_ENABLED must be true or false")
    compression_threshold = values["HERMES_COMPRESSION_THRESHOLD_TOKENS"]
    if (
        not compression_threshold.isdigit()
        or not 1024 <= int(compression_threshold) < int(context)
    ):
        raise StackError(
            "HERMES_COMPRESSION_THRESHOLD_TOKENS must be at least 1024 and below context"
        )
    if not max_turns.isdigit() or not 1 <= int(max_turns) <= 1000:
        raise StackError("HERMES_MAX_TURNS must be from 1 through 1000")


def initialize_ninfer_source() -> None:
    """Materialize the pinned gitlink without Git's shell-based submodule wrapper."""
    source = ROOT / "ninfer"
    metadata = source / ".git"
    created_by_setup = False
    if not metadata.exists():
        if source.exists() and any(source.iterdir()):
            raise StackError(
                "The uninitialized ninfer directory is not empty. Move those files elsewhere, "
                f"then rerun '{SETUP_COMMAND}'."
            )
        source.mkdir(parents=True, exist_ok=True)
        print("Initializing the pinned NInfer source...")
        run(["git", "init", str(source)])
        created_by_setup = True

    git_dir_result = run(
        ["git", "-C", str(source), "rev-parse", "--absolute-git-dir"],
        check=False,
        capture=True,
    )
    if git_dir_result.returncode != 0 or not git_dir_result.stdout.strip():
        raise StackError("The NInfer source does not contain valid Git metadata")
    marker = Path(git_dir_result.stdout.strip()) / "ninfer-setup-in-progress"
    if created_by_setup:
        atomic_write(marker, "This checkout is managed by ninfer.py setup.\n")

    setup_in_progress = marker.is_file()

    remote = run(
        ["git", "-C", str(source), "remote", "get-url", "origin"],
        check=False,
        capture=True,
    )
    if remote.returncode != 0:
        run(["git", "-C", str(source), "remote", "add", "origin", NINFER_URL])
    elif remote.stdout.strip() != NINFER_URL:
        raise StackError("The NInfer origin is not the reviewed canonical repository")

    current = run(
        ["git", "-C", str(source), "rev-parse", "--verify", "HEAD"],
        check=False,
        capture=True,
    )
    status = run(
        ["git", "-C", str(source), "status", "--porcelain", "--untracked-files=all"],
        check=False,
        capture=True,
    )
    if status.returncode != 0:
        raise StackError("The NInfer source checkout could not be inspected")
    dirty = bool(status.stdout.strip())
    if dirty and not setup_in_progress:
        raise StackError("The NInfer source has local or untracked changes")

    pinned_object = run(
        ["git", "-C", str(source), "cat-file", "-e", f"{NINFER_COMMIT}^{{commit}}"],
        check=False,
        capture=True,
    )
    if pinned_object.returncode != 0:
        print("Fetching the pinned NInfer revision...")
        run(
            [
                "git",
                "-C",
                str(source),
                "fetch",
                "--depth",
                "1",
                "--no-tags",
                "origin",
                NINFER_COMMIT,
            ]
        )

    needs_checkout = (
        current.returncode != 0
        or current.stdout.strip() != NINFER_COMMIT
        or (setup_in_progress and dirty)
    )
    if needs_checkout and not setup_in_progress:
        # Record ownership before touching a previously clean worktree. If the
        # checkout is interrupted, the next setup run can distinguish its own
        # partial update from user changes and safely converge.
        atomic_write(marker, "This checkout is managed by ninfer.py setup.\n")
        setup_in_progress = True
    if needs_checkout:
        checkout = ["git", "-C", str(source), "checkout"]
        # A previous setup can be interrupted after Git has populated part of
        # the worktree. Only a checkout created and still marked by this helper
        # may be repaired forcibly; unknown or user-edited checkouts are refused.
        if setup_in_progress and dirty:
            checkout.append("--force")
        run([*checkout, "--detach", NINFER_COMMIT])

    commit = run(["git", "-C", str(source), "rev-parse", "HEAD"], capture=True).stdout.strip()
    if commit != NINFER_COMMIT:
        raise StackError(f"NInfer is at {commit}; expected {NINFER_COMMIT}")
    status = run(
        ["git", "-C", str(source), "status", "--porcelain", "--untracked-files=all"],
        capture=True,
    ).stdout.strip()
    if status:
        raise StackError("The NInfer source has local or untracked changes")
    if setup_in_progress:
        try:
            marker.unlink()
        except OSError as exc:
            raise StackError("Could not finish recording the NInfer source setup") from exc


def initialize_local_state(detected_gpu_device: str | None = None) -> None:
    if not ENV_EXAMPLE.is_file():
        raise StackError("Missing .env.example")
    initialize_ninfer_source()

    (ROOT / "models").mkdir(parents=True, exist_ok=True)
    merge_env(detected_gpu_device)
    validate_env()
    compose("config", "--quiet")
    print("Local configuration initialized. No global Python packages were installed.")


def confirm_model_download() -> bool:
    print()
    print("Hermes needs one local AI model before it can answer you.")
    print(
        f"Source download: approximately {MODEL_SOURCE_GIB} GiB; "
        f"temporary workspace: approximately {MODEL_BUILD_GIB} GiB"
    )
    print(f"Final local artifact: {MODEL_SIZE_GIB} GiB at models/{MODEL_FILE}")
    print("Pinned inputs are downloaded with uv in an isolated container, then converted locally.")
    print("You can interrupt and rerun setup later; completed downloads are preserved.")
    answer = input("Download and build the uncensored model now? [Y/n]: ").strip().lower()
    return answer in {"", "y", "yes"}


def confirm(prompt: str, *, default: bool) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    answer = input(f"{prompt} {suffix}: ").strip().lower()
    if not answer:
        return default
    return answer in {"y", "yes"}


def file_sha256(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def require_local_model_artifact() -> dict[str, object]:
    model_path = ROOT / "models" / MODEL_FILE
    manifest_path = ROOT / "models" / MODEL_MANIFEST_FILE
    if not model_path.is_file() or not manifest_path.is_file():
        raise StackError(
            f"The locally built {MODEL_FILE} or its provenance manifest is missing. "
            "Run 'python ninfer.py prepare-model'."
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StackError("The local model provenance manifest is invalid") from exc
    if model_path.stat().st_size != MODEL_EXPECTED_BYTES:
        raise StackError(
            f"The local model has {model_path.stat().st_size:,} bytes; "
            f"expected {MODEL_EXPECTED_BYTES:,}"
        )
    actual = file_sha256(model_path)
    if manifest.get("sha256") != actual:
        raise StackError(
            f"The local model checksum is {actual}, but its manifest records "
            f"{manifest.get('sha256')}"
        )
    return manifest


def ninfer_is_running() -> bool:
    result = compose("ps", "--status", "running", "--services", check=False, capture=True)
    return "ninfer" in {line.strip() for line in result.stdout.splitlines()}


def prepare_model(args: argparse.Namespace) -> None:
    merge_env()
    validate_env()
    # Create bind-mount sources as the host user. Letting Docker create them can
    # leave root-owned directories that the non-root utility containers cannot use.
    (ROOT / "model-build").mkdir(parents=True, exist_ok=True)
    (ROOT / "models").mkdir(parents=True, exist_ok=True)
    model_path = ROOT / "models" / MODEL_FILE
    if model_path.is_file() and (ROOT / "models" / MODEL_MANIFEST_FILE).is_file():
        print("The uncensored model artifact already exists; verifying its local checksum...")
        manifest = require_local_model_artifact()
        print(f"Verified {MODEL_FILE}: {manifest['sha256']}")
        return
    if not args.yes and not confirm_model_download():
        print("Model preparation cancelled. Existing models and build downloads were preserved.")
        return

    print("Downloading and verifying the pinned model-build inputs...")
    compose("--profile", "tools", "run", "--rm", "--build", "model-fetcher")
    was_running = ninfer_is_running()
    if was_running:
        print("Stopping NInfer temporarily so the converter can use the GPU...")
        compose("stop", "ninfer")
    try:
        print("Building the local NInfer artifact. Existing model files will not be overwritten.")
        compose("--profile", "tools", "run", "--rm", "--build", "model-converter")
        manifest = require_local_model_artifact()
        print(f"Model build verified: {manifest['sha256']}")
    finally:
        if was_running and not getattr(args, "leave_stopped", False):
            print("Restarting the previously selected model...")
            compose("up", "-d", "ninfer")


def replace_env_values(replacements: dict[str, str]) -> Path | None:
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    current = read_env()
    if all(current.get(key) == value for key, value in replacements.items()):
        return None
    backup = ENV_FILE.with_name(f".env.backup-before-{int(time.time())}")
    shutil.copy2(ENV_FILE, backup)
    output: list[str] = []
    seen: set[str] = set()
    for line in lines:
        match = re.match(r"^([A-Z][A-Z0-9_]*)=", line)
        if match and match.group(1) in replacements:
            key = match.group(1)
            if key not in seen:
                output.append(f"{key}={replacements[key]}")
                seen.add(key)
            continue
        output.append(line)
    for key, value in replacements.items():
        if key not in seen:
            output.append(f"{key}={value}")
    atomic_write(ENV_FILE, "\n".join(output).rstrip() + "\n")
    return backup


def activate_uncensored_model() -> Path | None:
    require_local_model_artifact()
    return replace_env_values(
        {
            "NINFER_MODEL_FILE": MODEL_FILE,
            "NINFER_MODEL_ID": "qwen-local",
            "NINFER_CONTEXT_LENGTH": "131072",
            "NINFER_KV_CAPACITY": "131072",
            "NINFER_MAX_CONCURRENCY": "1",
            "HERMES_COMPRESSION_ENABLED": "true",
            "HERMES_COMPRESSION_THRESHOLD_TOKENS": "100000",
        }
    )


def ninfer_endpoint(values: dict[str, str]) -> str:
    return f"http://127.0.0.1:{values['NINFER_HOST_PORT']}/v1"


def require_ninfer_api(values: dict[str, str]) -> None:
    endpoint = ninfer_endpoint(values)
    request = urllib.request.Request(
        f"{endpoint}/models",
        headers={"Authorization": f"Bearer {values['NINFER_API_KEY']}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read())
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise StackError(
            f"NInfer is not reachable at {endpoint}. Run 'python ninfer.py up' and try again: {exc}"
        ) from exc
    advertised = [item.get("id") for item in payload.get("data", [])]
    if values["NINFER_MODEL_ID"] not in advertised:
        raise StackError(
            f"NInfer does not advertise the configured model {values['NINFER_MODEL_ID']!r}"
        )


def require_ninfer_generation(values: dict[str, str]) -> None:
    endpoint = ninfer_endpoint(values)
    body = json.dumps(
        {
            "model": values["NINFER_MODEL_ID"],
            "messages": [
                {
                    "role": "user",
                    "content": "Reply with one short sentence confirming you are ready.",
                }
            ],
            "max_tokens": 32,
            "temperature": 0,
            "enable_thinking": False,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{endpoint}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {values['NINFER_API_KEY']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=900) as response:
            payload = json.loads(response.read())
        answer = payload["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as exc:
        raise StackError(f"NInfer's test answer failed with HTTP {exc.code}") from exc
    except (
        urllib.error.URLError,
        json.JSONDecodeError,
        KeyError,
        IndexError,
        TypeError,
        AttributeError,
    ) as exc:
        raise StackError("NInfer did not return a valid test answer") from exc
    if not answer:
        raise StackError("NInfer returned an empty test answer")


def hermes_home() -> Path:
    configured = os.environ.get("HERMES_HOME")
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "hermes"
    return Path.home() / ".hermes"


def native_hermes_command() -> tuple[list[str], dict[str, str]] | None:
    """Return a shell-free command for the stock Hermes installation."""
    home = hermes_home()
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


def windows_hermes_desktop_executable() -> Path | None:
    """Return the stock installer's standard managed Windows desktop artifact."""
    if os.name != "nt":
        return None
    candidate = (
        hermes_home()
        / "hermes-agent"
        / "apps"
        / "desktop"
        / "release"
        / "win-unpacked"
        / "Hermes.exe"
    )
    return candidate if candidate.is_file() else None


def launch_windows_hermes_desktop() -> bool:
    executable = windows_hermes_desktop_executable()
    if executable is None:
        return False
    try:
        subprocess.Popen(
            [str(executable)],
            cwd=executable.parent,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except OSError:
        return False
    return True


def configure_native_hermes(command: list[str], process_env: dict[str, str], values: dict[str, str]) -> None:
    model_id = values["NINFER_MODEL_ID"]
    context = values["NINFER_CONTEXT_LENGTH"]
    workspace = (ROOT / "workspace").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    profile_home = Path(process_env["HERMES_HOME"]).expanduser().resolve()
    write_safe_roots = os.pathsep.join((str(workspace), str(profile_home)))
    provider = json.dumps(
        {
            "api": ninfer_endpoint(values),
            "key_env": "NINFER_API_KEY",
            "transport": "chat_completions",
            "default_model": model_id,
            "models": {
                model_id: {
                    "context_length": int(context),
                    "supports_vision": False,
                }
            },
        },
        separators=(",", ":"),
    )
    settings = [
        ("providers.ninfer", provider),
        ("model.provider", "custom:ninfer"),
        ("model.default", model_id),
        ("model.context_length", context),
        ("model.supports_vision", "false"),
        ("compression.enabled", values["HERMES_COMPRESSION_ENABLED"]),
        ("compression.threshold", "0.9"),
        (
            "compression.threshold_tokens",
            values["HERMES_COMPRESSION_THRESHOLD_TOKENS"],
        ),
        ("agent.max_turns", values["HERMES_MAX_TURNS"]),
        ("terminal.backend", "local"),
        ("terminal.cwd", str(workspace)),
        ("approvals.mode", "manual"),
    ]

    # Hermes stores uppercase secret keys in its private .env. Capture and
    # redact this invocation so the bearer key never appears in setup output.
    run(
        [*command, "config", "set", "NINFER_API_KEY", values["NINFER_API_KEY"]],
        capture=True,
        env=process_env,
        redact={-1},
    )
    set_private_env_value(profile_home / ".env", "HERMES_WRITE_SAFE_ROOT", write_safe_roots)
    process_env["HERMES_WRITE_SAFE_ROOT"] = write_safe_roots
    for key, value in settings:
        run([*command, "config", "set", key, value], env=process_env)
    run([*command, "config", "check"], env=process_env)

    expected = {
        "providers.ninfer.api": ninfer_endpoint(values),
        "model.provider": "custom:ninfer",
        "model.default": model_id,
        "model.context_length": context,
        "model.supports_vision": "false",
        "compression.threshold": "0.9",
        "compression.threshold_tokens": values["HERMES_COMPRESSION_THRESHOLD_TOKENS"],
        "terminal.backend": "local",
        "terminal.cwd": str(workspace),
        "approvals.mode": "manual",
    }
    for key, wanted in expected.items():
        actual = run(
            [*command, "config", "get", key],
            capture=True,
            env=process_env,
        ).stdout.strip().strip('"')
        if actual.lower() != wanted.lower():
            raise StackError(f"Hermes {key} is {actual!r}; expected {wanted!r}")


def install_hermes(args: argparse.Namespace) -> None:
    standalone = not getattr(args, "from_setup", False)
    if standalone:
        print("Hermes Desktop connection setup")
        stage(1, 2, "Check the local AI service")
    if not ENV_FILE.is_file():
        raise StackError(
            f"The local AI service has not been set up yet. Start with '{SETUP_COMMAND}'."
        )
    validate_env()
    values = read_env()
    try:
        require_ninfer_api(values)
    except StackError:
        model_path = ROOT / "models" / values["NINFER_MODEL_FILE"]
        if not model_path.is_file() or model_path.stat().st_size == 0:
            raise StackError(
                f"The local AI model has not been downloaded yet. Run '{SETUP_COMMAND}' first."
            )
        print("The local AI service is stopped or not ready. Starting it now...")
        check_setup_prerequisites()
        start_ninfer(values)
    else:
        print("Asking the model for a short connection test...")
        try:
            require_ninfer_generation(values)
        except StackError as exc:
            raise StackError(
                "The local AI service is visible but could not answer. Run "
                "'python ninfer.py up', then rerun 'python ninfer.py install-hermes'."
            ) from exc
    if standalone:
        print("The local AI service is ready.")
        stage(2, 2, "Install and connect Hermes Desktop")
    resolved = native_hermes_command()
    if resolved is None:
        print()
        print("Hermes Desktop is not installed yet.")
        if not args.no_open:
            open_official_page(HERMES_DESKTOP_URL, "Hermes Desktop download")
        else:
            print(f"Official stock installer: {HERMES_DESKTOP_URL}")
        if args.no_wait or not sys.stdin.isatty():
            raise StackError(
                "Install stock Hermes Desktop, finish its first launch, then rerun "
                "'python ninfer.py install-hermes'"
            )
        print("1. Download and run the stock installer from the page that opened.")
        print("2. Launch Hermes Desktop once and let it finish installing its components.")
        print("3. If asked for a provider, choose 'Choose provider later'.")
        input("Press Enter here after those three steps are finished...")
        resolved = native_hermes_command()
        if resolved is None:
            raise StackError(
                "Hermes was not detected in its stock location. Finish the installer and first "
                "launch, then rerun 'python ninfer.py install-hermes'. Your NInfer setup is safe."
            )

    command, process_env = resolved
    print(f"Configuring the stock Hermes installation under {hermes_home()}...")
    configure_native_hermes(command, process_env, values)
    print("Hermes Desktop is configured for the authenticated local NInfer endpoint.")
    print(f"  Endpoint: {ninfer_endpoint(values)}")
    print(f"  Model: {values['NINFER_MODEL_ID']}")
    print(f"  Context: {values['NINFER_CONTEXT_LENGTH']} tokens")
    print(f"  Automatic compression: {values['HERMES_COMPRESSION_THRESHOLD_TOKENS']} tokens")
    print("  Vision: disabled")
    print(f"  Tool starting folder: {ROOT / 'workspace'}")
    print("  File-write guard: workspace and the Hermes profile")
    print("  Command approvals: manual")
    print("The API key was stored privately by Hermes and was not printed.")
    print("No username or password is required for this local connection.")
    print()
    print("Hermes must reload once to use this new connection.")
    desktop_executable = windows_hermes_desktop_executable()
    if desktop_executable is not None and not args.no_wait and sys.stdin.isatty():
        input("Close Hermes Desktop if it is open, then press Enter to reopen it...")
        if launch_windows_hermes_desktop():
            print("Hermes Desktop is opening now.")
        else:
            print("Open Hermes Desktop from the Start menu.")
    else:
        print("Close Hermes Desktop if it is open, then open it from your application menu.")
    print()
    print("SAFETY: direct file-write tools are limited to the workspace and Hermes profile,")
    print("but terminal commands still have your normal user access. UAC does not protect")
    print("those files; review every tool approval and keep important files backed up.")
    print("SETUP COMPLETE: start a new chat in Hermes Desktop and type a message.")
    print("Keep Docker running while you use Hermes; it runs the model on your RTX 5090.")


def setup(args: argparse.Namespace) -> None:
    print("Hermes Desktop + RTX 5090 local AI setup")
    print("This setup is safe to rerun. Completed downloads and configuration are reused.")

    stage(1, 5, "Check this computer")
    detected_gpu_device = check_setup_prerequisites()

    stage(2, 5, "Prepare the private local configuration")
    initialize_local_state(detected_gpu_device)

    stage(3, 5, "Download, build, and verify the AI model")
    model_path = ROOT / "models" / MODEL_FILE
    manifest_path = ROOT / "models" / MODEL_MANIFEST_FILE
    if not (
        model_path.is_file()
        and model_path.stat().st_size == MODEL_EXPECTED_BYTES
        and manifest_path.is_file()
    ):
        if not confirm_model_download():
            print(f"Setup paused before the model build. Run '{SETUP_COMMAND}' when ready.")
            return
    try:
        prepare_model(argparse.Namespace(yes=True, leave_stopped=True))
    except StackError as exc:
        raise StackError(
            "The model build did not finish. Read the message above, check Docker, the internet "
            "connection, GPU availability, and free disk space, then rerun setup. Downloaded "
            "source data was preserved for resumption; the previous model was not deleted."
        ) from exc

    env_backup = activate_uncensored_model()
    validate_env()

    stage(4, 5, "Build and start the local AI service")
    print("Building the local AI service. The first build can take several minutes...")
    try:
        compose("build", "ninfer")
    except StackError as exc:
        raise StackError(
            f"The local AI service could not be built. Check the internet connection and Docker "
            f"Desktop, then rerun '{SETUP_COMMAND}'."
        ) from exc
    try:
        start_ninfer(read_env())
    except StackError as new_model_error:
        legacy_path = ROOT / "models" / LEGACY_MODEL_FILE
        if env_backup is not None and legacy_path.is_file():
            print("The new model did not pass startup. Restoring the previous local profile...")
            failed_env = ENV_FILE.with_name(f".env.failed-uncensored-{int(time.time())}")
            shutil.copy2(ENV_FILE, failed_env)
            atomic_write(ENV_FILE, env_backup.read_text(encoding="utf-8"))
            try:
                start_ninfer(read_env())
            except StackError as rollback_error:
                raise StackError(
                    "The new model failed and the previous configuration was restored, but the "
                    "old service also needs attention. Run 'python ninfer.py logs'."
                ) from rollback_error
            raise StackError(
                "The new model failed its live test. The old model and configuration were "
                "restored successfully."
            ) from new_model_error
        raise
    print("The local AI service is ready.")

    stage(5, 5, "Install and connect Hermes Desktop")
    if args.skip_hermes:
        print("Hermes Desktop was skipped. Install it later with: python ninfer.py install-hermes")
    elif confirm("Install and configure stock Hermes Desktop now?", default=True):
        install_hermes(argparse.Namespace(no_open=False, no_wait=False, from_setup=True))
    else:
        print("Hermes Desktop was skipped. Install it later with: python ninfer.py install-hermes")


def start_ninfer(values: dict[str, str]) -> None:
    print("Starting the model. This can take several minutes the first time...")
    up_command = (
        "up",
        "-d",
        "--remove-orphans",
        "--wait",
        "--wait-timeout",
        "900",
        "ninfer",
    )
    try:
        compose(*up_command)
    except StackError as exc:
        raise StackError(
            "The local AI service did not become ready. Docker Desktop shows the container "
            "details, or run 'python ninfer.py logs' to see the cause. After fixing it, rerun "
            f"'{SETUP_COMMAND}'."
        ) from exc
    try:
        require_ninfer_api(values)
    except StackError:
        # Docker Desktop can occasionally create a healthy container without
        # activating its requested host-port forwarding. A former internal
        # network configuration can also remain until its network is removed.
        print("The model is healthy but its private localhost connection is missing.")
        print("Recreating the Docker network once to repair port forwarding...")
        try:
            compose("down", "--remove-orphans")
            compose(*up_command)
            require_ninfer_api(values)
        except StackError as exc:
            raise StackError(
                f"The model is healthy inside Docker but is not reachable at "
                f"{ninfer_endpoint(values)}. Restart Docker Desktop, then rerun "
                "'python ninfer.py up'."
            ) from exc
    try:
        print("Asking the model for a short test answer...")
        require_ninfer_generation(values)
    except StackError as exc:
        raise StackError(
            "The model container started but did not complete its authenticated answer test. "
            "Run 'python ninfer.py logs', then rerun 'python ninfer.py up'."
        ) from exc
    print("The model returned a test answer successfully.")


def up(_: argparse.Namespace) -> None:
    print("Starting the RTX 5090 local AI service")
    check_setup_prerequisites()
    if not ENV_FILE.is_file():
        raise StackError(f"Setup has not been completed. Start with '{SETUP_COMMAND}'.")
    validate_env()
    values = read_env()
    start_ninfer(values)
    print("READY: the model is loaded and Hermes Desktop can use it now.")


def download_model(args: argparse.Namespace) -> None:
    print("'download-model' is retained as an alias for 'prepare-model'.")
    prepare_model(args)


def shell(_: argparse.Namespace) -> None:
    compose("exec", "ninfer", "bash")


def benchmark(args: argparse.Namespace) -> None:
    run(
        [
            sys.executable,
            str(ROOT / "scripts" / "benchmark.py"),
            "--runs",
            str(args.runs),
            "--max-tokens",
            str(args.max_tokens),
        ]
    )


def passthrough(command: tuple[str, ...]):
    def handler(_: argparse.Namespace) -> None:
        compose(*command)
    return handler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    setup_parser = sub.add_parser(
        "setup",
        help="set up NInfer, then offer stock Hermes Desktop installation",
    )
    setup_parser.add_argument(
        "--skip-hermes",
        action="store_true",
        help="set up only NInfer without offering Hermes Desktop",
    )
    setup_parser.set_defaults(func=setup)
    prepare = sub.add_parser(
        "prepare-model",
        help="download pinned inputs with uv and build the local NInfer artifact",
    )
    prepare.add_argument("--yes", action="store_true", help="skip the model-build confirmation")
    prepare.set_defaults(func=prepare_model, leave_stopped=False)
    download = sub.add_parser(
        "download-model",
        help="compatibility alias for prepare-model",
    )
    download.add_argument("--yes", action="store_true", help="skip the model-build confirmation")
    download.set_defaults(leave_stopped=False)
    download.set_defaults(func=download_model)
    install = sub.add_parser(
        "install-hermes",
        aliases=["install-hermes-desktop"],
        help="install/configure stock Hermes Desktop after NInfer is ready",
    )
    install.add_argument(
        "--no-open",
        action="store_true",
        help="do not open the official installer page when Hermes is absent",
    )
    install.add_argument(
        "--no-wait",
        action="store_true",
        help="do not wait for an installation that is not yet present",
    )
    install.set_defaults(func=install_hermes)
    sub.add_parser("build", help="build the NInfer image").set_defaults(func=passthrough(("build", "ninfer")))
    sub.add_parser("up", help="start NInfer and wait until the model is ready").set_defaults(func=up)
    sub.add_parser("down", help="stop NInfer while preserving the model").set_defaults(
        func=passthrough(("down", "--remove-orphans"))
    )
    sub.add_parser("status", help="show NInfer service status").set_defaults(func=passthrough(("ps",)))
    sub.add_parser("logs", help="follow NInfer logs").set_defaults(func=passthrough(("logs", "-f", "ninfer")))
    sub.add_parser("shell", help="open Bash inside the NInfer container").set_defaults(func=shell)
    sub.add_parser("validate", help="run hardware-independent repository checks").set_defaults(
        func=lambda _: run([sys.executable, str(ROOT / "scripts" / "validate.py")])
    )
    sub.add_parser("verify", help="run cross-platform local GPU integration checks").set_defaults(
        func=lambda _: run([sys.executable, str(ROOT / "scripts" / "verify.py")])
    )
    benchmark_parser = sub.add_parser("benchmark", help="collect direct-NInfer RTX 5090 measurements")
    benchmark_parser.add_argument("--runs", type=int, default=3)
    benchmark_parser.add_argument("--max-tokens", type=int, default=512)
    benchmark_parser.set_defaults(func=benchmark)

    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        raise SystemExit(130)
    except StackError as exc:
        print(f"ninfer: {exc}", file=sys.stderr)
        raise SystemExit(1)
