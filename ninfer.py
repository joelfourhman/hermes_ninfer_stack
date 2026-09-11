#!/usr/bin/env python3
"""Cross-platform setup and control for NInfer plus native Hermes Desktop."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import statistics
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
from stack.config import (  # noqa: E402 - keep public compatibility exports beside paths
    MODEL_PROFILES, RUNTIME_PROFILES, ModelProfile, RuntimeProfile,
    NINFER_COMMIT, NINFER_URL, DEFAULT_MODEL_PROFILE, DEFAULT_RUNTIME_PROFILE,
    DEFAULT_GOAL_MAX_TURNS,
    runtime_env_values, validate_spec,
)

STOCK_MODEL_FILE = MODEL_PROFILES["stock"].filename
UNCENSORED_MODEL_FILE = MODEL_PROFILES["uncensored"].filename
STOCK_MODEL_SHA256 = MODEL_PROFILES["stock"].sha256
UNCENSORED_MODEL_SHA256 = MODEL_PROFILES["uncensored"].sha256

PRIVATE_LAN_NETWORKS = tuple(
    ipaddress.ip_network(cidr)
    for cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)

# These variables belonged to the removed all-container Hermes and local model-build paths.
# Setup removes only this reviewed allowlist and preserves every unrelated user setting.
OBSOLETE_ENV_KEYS = frozenset(
    {
        "HERMES_IMAGE",
        "HERMES_UID",
        "HERMES_GID",
        "HERMES_API_SERVER_KEY",
        "HERMES_CPUS",
        "HERMES_MEMORY",
        "HERMES_PIDS",
        "HERMES_DASHBOARD_ENABLED",
        "HERMES_DASHBOARD_HOST_PORT",
        "HERMES_DASHBOARD_USERNAME",
        "HERMES_DASHBOARD_PASSWORD",
        "HERMES_DASHBOARD_SECRET",
        "SANDBOX_CPUS",
        "SANDBOX_MEMORY",
        "SANDBOX_PIDS",
        "MODEL_BUILD_UID",
        "MODEL_BUILD_GID",
    }
)
HERMES_DESKTOP_URL = "https://hermes-agent.nousresearch.com/desktop"
DOCKER_DESKTOP_URL = "https://www.docker.com/products/docker-desktop/"
DOCKER_ENGINE_URL = "https://docs.docker.com/engine/install/"
PYTHON_DOWNLOAD_URL = "https://www.python.org/downloads/"
GIT_DOWNLOAD_URL = "https://git-scm.com/downloads"
NVIDIA_DRIVER_URL = "https://www.nvidia.com/Download/index.aspx"
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
    process_env = dict(os.environ, NINFER_SOURCE_REVISION=NINFER_COMMIT)
    return run(command, check=check, capture=capture, env=process_env)


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


def model_profile(key: str) -> ModelProfile:
    try:
        return MODEL_PROFILES[key]
    except KeyError as exc:
        raise StackError(
            f"Unknown model profile {key!r}; choose {', '.join(MODEL_PROFILES)}"
        ) from exc


def runtime_profile(key: str) -> RuntimeProfile:
    try:
        return RUNTIME_PROFILES[key]
    except KeyError as exc:
        choices = ", ".join(RUNTIME_PROFILES)
        raise StackError(f"Unknown runtime profile {key!r}; choose {choices}") from exc


def configured_model_profile_key() -> str:
    values = read_env() if ENV_FILE.is_file() else {}
    configured = values.get("NINFER_MODEL_PROFILE", "")
    if configured in MODEL_PROFILES:
        return configured
    filename = values.get("NINFER_MODEL_FILE", "")
    for profile in MODEL_PROFILES.values():
        if filename == profile.filename:
            return profile.key
    return DEFAULT_MODEL_PROFILE


def configured_runtime_profile_key() -> str:
    configured = read_env().get("NINFER_RUNTIME_PROFILE", "") if ENV_FILE.is_file() else ""
    return configured if configured in RUNTIME_PROFILES else DEFAULT_RUNTIME_PROFILE


def choose_model_profile(default_key: str | None = None) -> ModelProfile:
    default = default_key or configured_model_profile_key()
    keys = tuple(MODEL_PROFILES)
    default_number = str(keys.index(default) + 1)
    print()
    print("Choose a model:")
    print()
    for number, profile in enumerate(MODEL_PROFILES.values(), start=1):
        recommended = " (recommended)" if profile.key == DEFAULT_MODEL_PROFILE else ""
        print(f"  {number}. {profile.label}{recommended}")
        print(f"     Download: {profile.expected_bytes / 1024**3:.2f} GiB; capabilities: {', '.join(profile.capabilities)}")
    while True:
        answer = input(f"Selection [{default_number}]: ").strip().lower()
        if not answer:
            return model_profile(default)
        if answer.isdigit() and 1 <= int(answer) <= len(keys):
            return model_profile(keys[int(answer) - 1])
        if answer in MODEL_PROFILES:
            return model_profile(answer)
        print(f"Enter a number from 1 through {len(keys)}, or a model name.")


def choose_runtime_profile(default_key: str | None = None) -> RuntimeProfile:
    default = default_key or configured_runtime_profile_key()
    keys = tuple(RUNTIME_PROFILES)
    default_number = str(keys.index(default) + 1)
    print()
    print("Choose how NInfer should use the RTX 5090:")
    print()
    for number, profile in enumerate(RUNTIME_PROFILES.values(), start=1):
        recommended = " (recommended)" if profile.key == DEFAULT_RUNTIME_PROFILE else ""
        print(f"  {number}. {profile.label}{recommended}")
        print(f"     {profile.description}")
    while True:
        answer = input(f"Selection [{default_number}]: ").strip().lower()
        if not answer:
            return runtime_profile(default)
        if answer.isdigit() and 1 <= int(answer) <= len(keys):
            return runtime_profile(keys[int(answer) - 1])
        if answer in RUNTIME_PROFILES:
            return runtime_profile(answer)
        print(f"Enter a number from 1 through {len(keys)}, or a profile name.")


def check_setup_prerequisites(profile: ModelProfile | None = None) -> str:
    profile = profile or model_profile(configured_model_profile_key())
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

    model_path = ROOT / "models" / profile.filename
    if model_path.is_file() and model_path.stat().st_size == profile.expected_bytes:
        print(f"The {profile.label} artifact is already present; its checksum will be verified.")
    else:
        free = shutil.disk_usage(ROOT).free
        free_gib = free / 1024**3
        if free < profile.required_free_gib * 1024**3:
            raise StackError(
                f"The drive containing this project has {free_gib:.1f} GiB free; setup needs at "
                f"least {profile.required_free_gib} GiB for {profile.label}. "
                f"Free some space, then rerun '{SETUP_COMMAND}'."
            )
        print(
            f"Disk space is ready ({free_gib:.1f} GiB free; "
            f"{profile.required_free_gib} GiB required for this model profile)."
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


def env_backup_path(prefix: str = ".env.backup-before") -> Path:
    return ENV_FILE.with_name(f"{prefix}-{time.time_ns()}")


def is_private_lan_ipv4(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.version == 4 and any(address in network for network in PRIVATE_LAN_NETWORKS)


def default_route_lan_ipv4() -> str | None:
    """Return the source address selected for the host's default IPv4 route."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))
        address = probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()
    return address if is_private_lan_ipv4(address) else None


def discover_lan_ipv4_addresses() -> list[str]:
    """Return usable RFC1918 addresses without platform-specific host commands."""
    candidates: set[str] = set()
    try:
        for result in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            candidates.add(result[4][0])
    except OSError:
        pass
    preferred = default_route_lan_ipv4()
    if preferred:
        candidates.add(preferred)
    ordered = sorted(address for address in candidates if is_private_lan_ipv4(address))
    if preferred in ordered:
        ordered.remove(preferred)
        ordered.insert(0, preferred)
    return ordered


def network_env_values(mode: str, address: str | None = None) -> dict[str, str]:
    if mode == "local":
        return {"NINFER_ACCESS_MODE": "local", "NINFER_BIND_ADDRESS": "127.0.0.1"}
    if mode != "lan":
        raise StackError("Network mode must be local or lan")
    if not address or not is_private_lan_ipv4(address):
        raise StackError("LAN mode requires an RFC1918 IPv4 address on this computer")
    return {"NINFER_ACCESS_MODE": "lan", "NINFER_BIND_ADDRESS": address}


def endpoint_host(values: dict[str, str]) -> str:
    return values.get("NINFER_BIND_ADDRESS", "127.0.0.1")


def remove_private_env_value(path: Path, key: str) -> None:
    """Atomically remove one dotenv value while preserving unrelated settings."""
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
        raise StackError(f"Invalid private environment key: {key!r}")
    if not path.is_file():
        return
    output: list[str] = []
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        candidate = line.strip()
        if candidate.startswith("export "):
            candidate = candidate[7:].lstrip()
        assigned_key, separator, _ = candidate.partition("=")
        matches = bool(separator) and (
            assigned_key.upper() == key if os.name == "nt" else assigned_key == key
        )
        if not matches:
            output.append(line)
    atomic_write(path, "\n".join(output).rstrip() + ("\n" if output else ""))


def merge_env(detected_gpu_device: str | None = None) -> None:
    creating = not ENV_FILE.is_file()
    example_lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    existing = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.is_file() else []
    original_text = "\n".join(existing).rstrip() + ("\n" if existing else "")
    existing = [
        line
        for line in existing
        if not (
            re.match(r"^([A-Z][A-Z0-9_]*)=", line)
            and line.split("=", 1)[0] in OBSOLETE_ENV_KEYS
        )
    ]
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
    existing_profile = original_values.get("NINFER_MODEL_PROFILE", "")
    if existing_profile not in MODEL_PROFILES:
        existing_filename = original_values.get("NINFER_MODEL_FILE", "")
        inferred = next(
            (
                profile.key
                for profile in MODEL_PROFILES.values()
                if profile.filename == existing_filename
            ),
            DEFAULT_MODEL_PROFILE,
        )
        forced["NINFER_MODEL_PROFILE"] = inferred
    configured_runtime = original_values.get("NINFER_RUNTIME_PROFILE", "")
    selected_runtime = (
        configured_runtime
        if configured_runtime in RUNTIME_PROFILES
        else DEFAULT_RUNTIME_PROFILE
    )
    forced.update(runtime_env_values(runtime_profile(selected_runtime)))
    forced["NINFER_SOURCE_REVISION"] = NINFER_COMMIT
    configured_access = original_values.get("NINFER_ACCESS_MODE", "")
    configured_bind = original_values.get("NINFER_BIND_ADDRESS", "")
    if configured_access == "lan" and is_private_lan_ipv4(configured_bind):
        forced.update(network_env_values("lan", configured_bind))
    elif configured_access not in {"local", "lan"} or configured_bind != "127.0.0.1":
        forced.update(network_env_values("local"))
    if detected_gpu_device is not None and not original_values.get("NINFER_GPU_DEVICE"):
        forced["NINFER_GPU_DEVICE"] = detected_gpu_device
    if os.name != "nt" and hasattr(os, "getuid") and hasattr(os, "getgid"):
        if not original_values.get("MODEL_DOWNLOAD_UID"):
            forced["MODEL_DOWNLOAD_UID"] = str(os.getuid())
        if not original_values.get("MODEL_DOWNLOAD_GID"):
            forced["MODEL_DOWNLOAD_GID"] = str(os.getgid())
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
    updated_text = "\n".join(output).rstrip() + "\n"
    if not creating and updated_text != original_text:
        backup = env_backup_path()
        shutil.copy2(ENV_FILE, backup)
        print(f"Updated the local configuration; previous values are backed up in {backup.name}.")
    atomic_write(ENV_FILE, updated_text)


def validate_env() -> None:
    values = read_env()
    required = [
        "NINFER_API_KEY",
        "MODEL_DOWNLOAD_UID",
        "MODEL_DOWNLOAD_GID",
        "NINFER_ACCESS_MODE",
        "NINFER_BIND_ADDRESS",
        "NINFER_HOST_PORT",
        "NINFER_GPU_DEVICE",
        "NINFER_MODEL_PROFILE",
        "NINFER_MODEL_FILE",
        "NINFER_MODEL_ID",
        "NINFER_RUNTIME_PROFILE",
        "NINFER_CONTEXT_LENGTH",
        "NINFER_KV_CAPACITY",
        "NINFER_MAX_CONCURRENCY",
        "NINFER_PENDING_TIMEOUT_MS",
        "NINFER_KV_DTYPE",
        "NINFER_DEVICE_STATE_SLOTS",
        "NINFER_HOST_STATE_SLOTS",
        "NINFER_HOST_KV_MIB",
        "NINFER_PRESERVE_THINKING",
        "HERMES_COMPRESSION_ENABLED",
        "HERMES_COMPRESSION_THRESHOLD_TOKENS",
        "HERMES_MAX_TURNS",
    ]
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise StackError("Missing required .env values: " + ", ".join(missing))
    if not re.fullmatch(r"[0-9a-fA-F]{64}", values["NINFER_API_KEY"]):
        raise StackError("NINFER_API_KEY must be a 64-character hexadecimal secret")
    access_mode = values["NINFER_ACCESS_MODE"]
    bind_address = values["NINFER_BIND_ADDRESS"]
    if access_mode == "local" and bind_address != "127.0.0.1":
        raise StackError("Local network mode must bind NInfer to 127.0.0.1")
    if access_mode == "lan" and not is_private_lan_ipv4(bind_address):
        raise StackError("LAN network mode must bind NInfer to an RFC1918 IPv4 address")
    if access_mode not in {"local", "lan"}:
        raise StackError("NINFER_ACCESS_MODE must be local or lan")
    host_port = values["NINFER_HOST_PORT"]
    if not host_port.isdigit() or not 1 <= int(host_port) <= 65535:
        raise StackError("NINFER_HOST_PORT must be from 1 through 65535")
    if not values["NINFER_GPU_DEVICE"].isdigit():
        raise StackError("NINFER_GPU_DEVICE must be a non-negative integer")
    profile = model_profile(values["NINFER_MODEL_PROFILE"])
    for key in ("MODEL_DOWNLOAD_UID", "MODEL_DOWNLOAD_GID"):
        if not values[key].isdigit() or int(values[key]) < 0:
            raise StackError(f"{key} must be a non-negative integer")
    if not re.fullmatch(r"[A-Za-z0-9._-]+\.ninfer", values["NINFER_MODEL_FILE"]):
        raise StackError("NINFER_MODEL_FILE must be a .ninfer filename, not a path")
    if values["NINFER_MODEL_FILE"] != profile.filename:
        raise StackError(
            f"NINFER_MODEL_FILE must be {profile.filename} for the "
            f"{profile.key} model profile"
        )
    if not re.fullmatch(r"[A-Za-z0-9._-]+", values["NINFER_MODEL_ID"]):
        raise StackError("NINFER_MODEL_ID contains unsupported characters")
    context = values["NINFER_CONTEXT_LENGTH"]
    kv_capacity = values["NINFER_KV_CAPACITY"]
    concurrency = values["NINFER_MAX_CONCURRENCY"]
    max_turns = values["HERMES_MAX_TURNS"]
    selected_runtime = runtime_profile(values["NINFER_RUNTIME_PROFILE"])
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
    try:
        validate_spec(values)
    except ValueError as exc:
        raise StackError(str(exc)) from exc
    expected_runtime = runtime_env_values(selected_runtime)
    drifted = [
        key for key, expected in expected_runtime.items() if values.get(key) != expected
    ]
    if drifted:
        raise StackError(
            f"The {selected_runtime.key} runtime profile has inconsistent values: "
            + ", ".join(drifted)
            + ". Run 'python ninfer.py select-runtime'."
        )


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


def confirm_model_download(profile: ModelProfile) -> bool:
    print()
    print("Hermes needs one local AI model before it can answer you.")
    print(f"Selected: {profile.label}")
    print(f"Transfer: {profile.transfer_description}")
    print(f"Final artifact: {profile.final_size_gib} GiB at models/{profile.filename}")
    print("The published NInfer artifact is downloaded with uv and SHA-256 verified.")
    print("You can interrupt and rerun setup later; completed download data is preserved.")
    answer = input(f"Download the {profile.key} model now? [Y/n]: ").strip().lower()
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


def model_artifact_candidate_ready(profile: ModelProfile) -> bool:
    model_path = ROOT / "models" / profile.filename
    return model_path.is_file() and model_path.stat().st_size == profile.expected_bytes


def require_model_artifact(profile: ModelProfile) -> dict[str, object]:
    model_path = ROOT / "models" / profile.filename
    if not model_path.is_file():
        raise StackError(
            f"The {profile.label} artifact is missing. Run "
            f"'python ninfer.py prepare-model --model {profile.key}'."
        )
    if model_path.stat().st_size != profile.expected_bytes:
        raise StackError(
            f"The local model has {model_path.stat().st_size:,} bytes; "
            f"expected {profile.expected_bytes:,}"
        )
    actual = file_sha256(model_path)
    if actual != profile.sha256:
        raise StackError(
            f"The {profile.key} model checksum is {actual}; expected {profile.sha256}"
        )
    return {
        "artifact": profile.filename,
        "bytes": profile.expected_bytes,
        "sha256": actual,
        "profile": profile.key,
        "verified_published_artifact": True,
    }


def prepare_model(args: argparse.Namespace) -> bool:
    merge_env()
    validate_env()
    profile = model_profile(getattr(args, "model", None) or configured_model_profile_key())
    # Create the bind-mount source as the host user. Letting Docker create it can
    # leave a root-owned directory that the non-root downloader cannot use.
    (ROOT / "models").mkdir(parents=True, exist_ok=True)
    if model_artifact_candidate_ready(profile):
        print(f"The {profile.label} artifact already exists; verifying its checksum...")
        manifest = require_model_artifact(profile)
        print(f"Verified {profile.filename}: {manifest['sha256']}")
        return True
    if not args.yes and not confirm_model_download(profile):
        print("Model preparation cancelled. Existing models and partial downloads were preserved.")
        return False

    print(f"Downloading and verifying the pinned {profile.key} NInfer artifact...")
    compose(
        "--profile", "tools", "run", "--rm", "--build", "model-downloader", profile.key
    )
    manifest = require_model_artifact(profile)
    print(f"{profile.label} verified: {manifest['sha256']}")
    return True


def replace_env_values(replacements: dict[str, str]) -> Path | None:
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    current = read_env()
    if all(current.get(key) == value for key, value in replacements.items()):
        return None
    backup = env_backup_path()
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


def activate_model_profile(profile: ModelProfile) -> Path | None:
    require_model_artifact(profile)
    speculation = {}
    if read_env().get("NINFER_SPEC_BACKEND", "mtp") not in profile.capabilities:
        print("The selected artifact requires MTP; restoring the supported MTP3 fallback.")
        speculation = {"NINFER_SPEC_BACKEND": "mtp", "NINFER_DRAFT_TOKENS": "3"}
    return replace_env_values(
        {
            "NINFER_MODEL_PROFILE": profile.key,
            "NINFER_MODEL_FILE": profile.filename,
            "NINFER_MODEL_ID": "qwen-local",
            **speculation,
        }
    )


def activate_runtime_profile(profile: RuntimeProfile) -> Path | None:
    return replace_env_values(runtime_env_values(profile))


def address_is_assigned_locally(address: str) -> bool:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((address, 0))
    except OSError:
        return False
    finally:
        probe.close()
    return True


def choose_lan_address(requested: str | None = None) -> str:
    if requested:
        if not is_private_lan_ipv4(requested):
            raise StackError("--address must be an RFC1918 IPv4 address")
        if not address_is_assigned_locally(requested):
            raise StackError(
                f"{requested} is not assigned to a network interface on this computer"
            )
        return requested

    preferred = default_route_lan_ipv4()
    if preferred and address_is_assigned_locally(preferred):
        return preferred
    candidates = [
        address
        for address in discover_lan_ipv4_addresses()
        if address_is_assigned_locally(address)
    ]
    if not candidates:
        raise StackError(
            "No private LAN IPv4 address was detected. Connect this computer to the LAN, "
            "then use --address with its 10.x, 172.16-31.x, or 192.168.x address."
        )
    if len(candidates) == 1:
        return candidates[0]
    if not sys.stdin.isatty():
        raise StackError(
            "Multiple LAN addresses were detected. Rerun with --address and one of: "
            + ", ".join(candidates)
        )
    print("Choose the private network interface to publish on:")
    for index, address in enumerate(candidates, start=1):
        print(f"  {index}. {address}")
    while True:
        answer = input("LAN address number: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(candidates):
            return candidates[int(answer) - 1]
        print(f"Enter a number from 1 through {len(candidates)}.")


def print_network_info(values: dict[str, str], *, show_key: bool = False) -> None:
    mode = values["NINFER_ACCESS_MODE"]
    print("NInfer network access")
    print(f"  Mode: {mode}")
    print(f"  Endpoint: {ninfer_endpoint(values)}")
    print(f"  Model: {values['NINFER_MODEL_ID']}")
    print(f"  Context: {values['NINFER_CONTEXT_LENGTH']} tokens")
    if show_key:
        print(f"  Bearer key: {values['NINFER_API_KEY']}")
        print("Treat this key like a password and send it only through a trusted channel.")
    elif mode == "lan":
        print("  Bearer key: hidden (rerun with --show-key to reveal it deliberately)")


def activate_and_start_network(mode: str, address: str | None) -> None:
    replacements = network_env_values(mode, address)
    previous_values = read_env()
    env_backup = replace_env_values(replacements)
    validate_env()
    try:
        start_ninfer(read_env())
    except StackError as selected_error:
        if env_backup is not None:
            print(
                "The selected network mode did not pass its live test. "
                "Restoring the previous mode..."
            )
            failed_env = ENV_FILE.with_name(f".env.failed-network-{mode}-{int(time.time())}")
            shutil.copy2(ENV_FILE, failed_env)
            atomic_write(ENV_FILE, env_backup.read_text(encoding="utf-8"))
            try:
                start_ninfer(previous_values)
            except StackError as rollback_error:
                raise StackError(
                    "The selected network mode failed and the previous configuration was restored, "
                    "but the former service also needs attention. Run 'python ninfer.py logs'."
                ) from rollback_error
            raise StackError(
                "The selected network mode failed its live test. The previous network "
                "configuration was restored successfully."
            ) from selected_error
        raise


def activate_and_start_profile(profile: ModelProfile, *, build_runtime: bool) -> None:
    previous_profile = model_profile(configured_model_profile_key())
    env_backup = activate_model_profile(profile)
    try:
        validate_env()
        if build_runtime:
            print("Building the local AI service. The first build can take several minutes...")
            compose("build", "ninfer")
        start_ninfer(read_env())
    except StackError as selected_error:
        if env_backup is not None and model_artifact_candidate_ready(previous_profile):
            print("The selected model did not pass startup. Restoring the previous profile...")
            failed_env = ENV_FILE.with_name(
                f".env.failed-{profile.key}-{int(time.time())}"
            )
            shutil.copy2(ENV_FILE, failed_env)
            atomic_write(ENV_FILE, env_backup.read_text(encoding="utf-8"))
            try:
                start_ninfer(read_env())
            except StackError as rollback_error:
                raise StackError(
                    "The selected model failed and the previous configuration was restored, "
                    "but the former service also needs attention. Run 'python ninfer.py logs'."
                ) from rollback_error
            raise StackError(
                f"The {profile.label} profile failed its live test. The previous "
                "model and configuration were restored successfully."
            ) from selected_error
        raise


def activate_and_start_runtime(profile: RuntimeProfile) -> None:
    previous = runtime_profile(configured_runtime_profile_key())
    resolved = native_hermes_command()
    backups = {}
    if resolved is not None:
        profile_home = Path(resolved[1]["HERMES_HOME"]).expanduser().resolve()
        backups = {p: p.read_bytes() if p.exists() else None
                   for p in (profile_home / "config.yaml", profile_home / ".env")}
    env_backup = activate_runtime_profile(profile)
    try:
        validate_env()
        start_ninfer(read_env())
        if resolved is not None:
            configure_native_hermes(*resolved, read_env(), preserve_execution=True)
            print("Hermes was updated too. Restart Hermes Desktop to use the new context profile.")
        else:
            print("Hermes was not found. Run 'python ninfer.py install-hermes' after installing it.")
    except (StackError, OSError) as selected_error:
        for path, contents in backups.items():
            if contents is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(contents)
        if env_backup is not None:
            print("The selected runtime did not pass startup. Restoring the previous profile...")
            failed_env = ENV_FILE.with_name(
                f".env.failed-runtime-{profile.key}-{int(time.time())}"
            )
            shutil.copy2(ENV_FILE, failed_env)
            atomic_write(ENV_FILE, env_backup.read_text(encoding="utf-8"))
            try:
                start_ninfer(read_env())
            except StackError as rollback_error:
                raise StackError(
                    "The selected runtime failed and the previous configuration was restored, "
                    "but the former service also needs attention. Run 'python ninfer.py logs'."
                ) from rollback_error
            raise StackError(
                f"The {profile.label} runtime failed its live test. The previous "
                f"{previous.label} configuration was restored successfully."
            ) from selected_error
        raise


def ninfer_endpoint(values: dict[str, str]) -> str:
    return f"http://{endpoint_host(values)}:{values['NINFER_HOST_PORT']}/v1"


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


def configure_native_hermes(command: list[str], process_env: dict[str, str], values: dict[str, str], *, preserve_execution: bool = False) -> None:
    model_id = values["NINFER_MODEL_ID"]
    context = values["NINFER_CONTEXT_LENGTH"]
    profile_home = Path(process_env["HERMES_HOME"]).expanduser().resolve()
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
        ("goals.max_turns", str(DEFAULT_GOAL_MAX_TURNS)),
    ]
    if not preserve_execution:
        settings += [("terminal.backend", "local"), ("approvals.mode", "manual")]

    # Hermes stores uppercase secret keys in its private .env. Capture and
    # redact this invocation so the bearer key never appears in setup output.
    run(
        [*command, "config", "set", "NINFER_API_KEY", values["NINFER_API_KEY"]],
        capture=True,
        env=process_env,
        redact={-1},
    )
    # Earlier project releases imposed a repository-local workspace. Remove
    # those overrides so Desktop/gateway sessions use Hermes's stock home
    # directory and CLI sessions use the directory from which Hermes launches.
    # Current Hermes returns a non-zero status when the key is already absent.
    # Absence is the desired idempotent state, so do not turn that into failure.
    if not preserve_execution:
        run(
            [*command, "config", "unset", "terminal.cwd"],
            check=False,
            capture=True,
            env=process_env,
        )
        remove_private_env_value(profile_home / ".env", "HERMES_WRITE_SAFE_ROOT")
        process_env.pop("HERMES_WRITE_SAFE_ROOT", None)
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
    }
    if not preserve_execution:
        expected.update({"terminal.backend": "local", "approvals.mode": "manual"})
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
    merge_env()
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
    print(f"  Runtime profile: {values['NINFER_RUNTIME_PROFILE']}")
    print(f"  Context: {values['NINFER_CONTEXT_LENGTH']} tokens")
    print(f"  Automatic compression: {values['HERMES_COMPRESSION_THRESHOLD_TOKENS']} tokens")
    print("  Vision: disabled")
    print("  Tool starting folder: stock Hermes default")
    print("  File writes: stock Hermes protected-path rules")
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
    print("SAFETY: Hermes keeps its stock protected-path rules, but file and terminal tools")
    print("otherwise have your normal user access. UAC does not protect your user files;")
    print("review every tool approval and keep important files backed up.")
    print("SETUP COMPLETE: start a new chat in Hermes Desktop and type a message.")
    print("Keep Docker running while you use Hermes; it runs the model on your RTX 5090.")


def setup(args: argparse.Namespace) -> None:
    print("Hermes Desktop + RTX 5090 local AI setup")
    print("This setup is safe to rerun. Completed downloads and configuration are reused.")

    stage(1, 6, "Choose the local model")
    profile = (
        model_profile(args.model)
        if getattr(args, "model", None)
        else choose_model_profile()
    )
    print(f"Selected profile: {profile.label}")

    stage(2, 6, "Check this computer")
    detected_gpu_device = check_setup_prerequisites(profile)

    stage(3, 6, "Prepare the private local configuration")
    initialize_local_state(detected_gpu_device)
    active_runtime = runtime_profile(configured_runtime_profile_key())
    print(f"Runtime profile: {active_runtime.label} ({active_runtime.key})")

    stage(4, 6, "Download and verify the AI model")
    if not model_artifact_candidate_ready(profile):
        if not confirm_model_download(profile):
            print(f"Setup paused before model preparation. Run '{SETUP_COMMAND}' when ready.")
            return
    try:
        prepared = prepare_model(
            argparse.Namespace(model=profile.key, yes=True)
        )
    except StackError as exc:
        raise StackError(
            "Model preparation did not finish. Read the message above, check Docker, the internet "
            "connection, and free disk space, then rerun setup. Partial download data was "
            "preserved for resumption; the previous model was not deleted."
        ) from exc
    if not prepared:
        return

    stage(5, 6, "Build and start the local AI service")
    activate_and_start_profile(profile, build_runtime=True)
    print("The local AI service is ready.")

    stage(6, 6, "Install and connect Hermes Desktop")
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
        # Save evidence before a selection transaction replaces the failed container.
        evidence = ROOT / "benchmarks" / f"startup-failure-{time.time_ns()}"
        try:
            logs = compose("logs", "--no-color", "--tail", "300", "ninfer", capture=True, check=False)
            evidence.mkdir(parents=True)
            key = values.get("NINFER_API_KEY", "")
            text = logs.stdout + logs.stderr
            if key:
                text = text.replace(key, "<redacted>")
            (evidence / "runtime.log").write_text(text, encoding="utf-8")
            (evidence / "config.json").write_text(json.dumps({k: v for k, v in values.items() if k.startswith("NINFER_") and k != "NINFER_API_KEY"}, indent=2), encoding="utf-8")
            print(f"Startup failure evidence saved: {evidence}")
        except (OSError, StackError):
            pass
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
        print("The model is healthy but its configured host connection is missing.")
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
    merge_env()
    validate_env()
    values = read_env()
    start_ninfer(values)
    print("READY: the model is loaded and Hermes Desktop can use it now.")


def select_model(args: argparse.Namespace) -> None:
    print("NInfer model selection")
    profile = model_profile(args.model) if args.model else choose_model_profile()
    print(f"Selected profile: {profile.label}")
    detected_gpu_device = check_setup_prerequisites(profile)
    initialize_local_state(detected_gpu_device)
    prepared = prepare_model(
        argparse.Namespace(model=profile.key, yes=args.yes)
    )
    if not prepared:
        return
    activate_and_start_profile(profile, build_runtime=False)
    print(f"ACTIVE: {profile.label} is ready for Hermes Desktop.")
    print("The other model artifact, if present, was preserved for later switching.")


def select_runtime(args: argparse.Namespace) -> None:
    print("NInfer runtime profile selection")
    profile = runtime_profile(args.profile) if args.profile else choose_runtime_profile()
    print(f"Selected runtime: {profile.label}")
    check_setup_prerequisites()
    if not ENV_FILE.is_file():
        raise StackError(f"Setup has not been completed. Start with '{SETUP_COMMAND}'.")
    merge_env()
    activate_and_start_runtime(profile)
    values = read_env()
    print(f"ACTIVE: {profile.label} is serving {values['NINFER_MODEL_ID']}.")


def network(args: argparse.Namespace) -> None:
    if not ENV_FILE.is_file():
        raise StackError(f"Setup has not been completed. Start with '{SETUP_COMMAND}'.")
    merge_env()
    validate_env()
    if args.mode is None:
        if args.address:
            raise StackError("--address requires --mode lan")
        print_network_info(read_env(), show_key=args.show_key)
        return

    address = None
    if args.mode == "lan":
        address = choose_lan_address(args.address)
        print(f"Selected LAN address: {address}")
        print("This makes the authenticated NInfer API reachable by devices on that LAN.")
        print(
            "Do not forward this port on your router and do not use this mode "
            "on an untrusted LAN."
        )
        if not args.yes and not confirm("Enable LAN access now?", default=False):
            print("Network access was not changed.")
            return
    elif args.address:
        raise StackError("--address can be used only with --mode lan")

    check_setup_prerequisites()
    activate_and_start_network(args.mode, address)
    values = read_env()
    resolved = native_hermes_command()
    if resolved is not None:
        command, process_env = resolved
        configure_native_hermes(command, process_env, values)
        print("Local Hermes was updated. Restart Hermes Desktop to reload the endpoint.")
    print_network_info(values, show_key=args.show_key)
    if args.mode == "lan":
        print("If a remote connection is blocked, allow this TCP port only on Private networks")
        print(
            "and only from the local subnet in the host firewall. Never create "
            "a router port forward."
        )


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


def _pretty_number(text: str) -> float:
    normalized = text.strip().replace(",", "")
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)([KMG]?)", normalized, re.IGNORECASE)
    if not match:
        raise ValueError(text)
    scale = {"": 1.0, "K": 1_000.0, "M": 1_000_000.0, "G": 1_000_000_000.0}
    return float(match.group(1)) * scale[match.group(2).upper()]


def _pretty_duration_ms(text: str) -> float:
    normalized = text.strip().lower()
    milliseconds = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*ms", normalized)
    if milliseconds:
        return float(milliseconds.group(1))
    seconds = re.fullmatch(
        r"(?:(\d+)\s*m\s*)?([0-9]+(?:\.[0-9]+)?)\s*s", normalized
    )
    if seconds:
        return (float(seconds.group(1) or 0) * 60.0 + float(seconds.group(2))) * 1000.0
    raise ValueError(text)


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def summarize_performance_log(log_text: str) -> dict[str, object]:
    prompts: list[float] = []
    ttft_ms: list[float] = []
    prefill_rates: list[float] = []
    decode_rates: list[float] = []
    cache_percentages: list[float] = []
    mtp_acceptance: list[float] = []
    queue_timeouts = 0
    context_rejections = 0
    peak_waiting = 0

    for line in log_text.splitlines():
        if "expired while waiting for admission" in line or "request_queue_timeout" in line:
            queue_timeouts += 1
        if "context_length_exceeded" in line or "exceeding Engine max_context" in line:
            context_rejections += 1
        waiting = re.search(r"(?:waiting=|\| waiting )([0-9]+)", line)
        if waiting:
            peak_waiting = max(peak_waiting, int(waiting.group(1)))

        if " done " not in line and " done |" not in line:
            continue
        old_prompt = re.search(r"\bprompt=([0-9]+)", line)
        new_prompt = re.search(r"\| prompt ([0-9.,]+[KMG]?) \|", line, re.IGNORECASE)
        prompt = old_prompt.group(1) if old_prompt else (new_prompt.group(1) if new_prompt else None)
        if prompt:
            prompts.append(_pretty_number(prompt))

        old_ttft = re.search(r"\bttft=([0-9.]+)ms", line)
        new_ttft = re.search(r"\| TTFT ([^|]+?) \|", line, re.IGNORECASE)
        if old_ttft:
            ttft_ms.append(float(old_ttft.group(1)))
        elif new_ttft:
            try:
                ttft_ms.append(_pretty_duration_ms(new_ttft.group(1)))
            except ValueError:
                pass

        for label, target in (("prefill", prefill_rates), ("decode", decode_rates)):
            old_rate = re.search(rf"\b{label}=([0-9.]+)tok/s", line)
            new_rate = re.search(
                rf"\| {label} ([0-9.,]+[KMG]?)\s+tok/s", line, re.IGNORECASE
            )
            rate = old_rate.group(1) if old_rate else (new_rate.group(1) if new_rate else None)
            if rate:
                target.append(_pretty_number(rate))

        old_cache = re.search(r"\bprompt=([0-9]+).*?\bcache=([0-9]+)", line)
        new_cache = re.search(r"\| cache [0-9.,]+[KMG]? \(([0-9.]+)%", line, re.IGNORECASE)
        if old_cache and int(old_cache.group(1)):
            cache_percentages.append(
                100.0 * int(old_cache.group(2)) / int(old_cache.group(1))
            )
        elif new_cache:
            cache_percentages.append(float(new_cache.group(1)))

        old_mtp = re.search(r"speculative=mtp .*?\(([0-9.]+)%\)", line)
        new_mtp = re.search(r"\| mtp accepted .*?\(([0-9.]+)%\)", line, re.IGNORECASE)
        acceptance = old_mtp or new_mtp
        if acceptance:
            mtp_acceptance.append(float(acceptance.group(1)))

    return {
        "completed_requests": len(ttft_ms),
        "max_prompt_tokens": max(prompts) if prompts else None,
        "ttft_p50_ms": _percentile(ttft_ms, 0.50),
        "ttft_p95_ms": _percentile(ttft_ms, 0.95),
        "prefill_median": statistics.median(prefill_rates) if prefill_rates else None,
        "decode_median": statistics.median(decode_rates) if decode_rates else None,
        "cache_median_percent": statistics.median(cache_percentages) if cache_percentages else None,
        "mtp_median_percent": statistics.median(mtp_acceptance) if mtp_acceptance else None,
        "queue_timeouts": queue_timeouts,
        "context_rejections": context_rejections,
        "peak_waiting": peak_waiting,
    }


def _format_optional(value: object, suffix: str = "") -> str:
    return "not observed" if value is None else f"{float(value):,.1f}{suffix}"


def diagnose_performance(args: argparse.Namespace) -> None:
    if args.lines < 1 or args.lines > 100_000:
        raise StackError("--lines must be from 1 through 100000")
    if not ENV_FILE.is_file():
        raise StackError(f"Setup has not been completed. Start with '{SETUP_COMMAND}'.")
    merge_env()
    validate_env()
    values = read_env()
    result = compose(
        "logs", "--no-color", "--tail", str(args.lines), "ninfer", capture=True
    )
    summary = summarize_performance_log(result.stdout)
    profile = runtime_profile(values["NINFER_RUNTIME_PROFILE"])
    print("NInfer performance diagnosis")
    print(f"  Runtime: {profile.key} ({profile.label})")
    print(f"  Completed requests sampled: {summary['completed_requests']}")
    print(f"  Largest prompt: {_format_optional(summary['max_prompt_tokens'], ' tokens')}")
    print(f"  TTFT p50 / p95: {_format_optional(summary['ttft_p50_ms'], ' ms')} / {_format_optional(summary['ttft_p95_ms'], ' ms')}")
    print(f"  Median prefill: {_format_optional(summary['prefill_median'], ' tok/s')}")
    print(f"  Median decode: {_format_optional(summary['decode_median'], ' tok/s')}")
    print(f"  Median prefix reuse: {_format_optional(summary['cache_median_percent'], '%')}")
    print(f"  Median MTP acceptance: {_format_optional(summary['mtp_median_percent'], '%')}")
    print(f"  Queue timeouts: {summary['queue_timeouts']} (peak waiting: {summary['peak_waiting']})")
    print(f"  Context-limit rejections: {summary['context_rejections']}")

    recommendations: list[str] = []
    if int(summary["queue_timeouts"]):
        recommendations.append(
            "Queue timeouts were observed. Use the balanced or max-context runtime profile."
        )
    if int(summary["context_rejections"]):
        recommendations.append(
            "Prompts exceeded the active context. Restart Hermes after applying the runtime profile so its compression setting is current."
        )
    ttft_p95 = summary["ttft_p95_ms"]
    if isinstance(ttft_p95, (int, float)) and ttft_p95 >= 20_000:
        recommendations.append(
            "Long prompt ingestion dominates latency. The balanced profile's 90K compression threshold is the faster default."
        )
    if not recommendations:
        recommendations.append("No queue or context failure is visible in the sampled logs.")
    print("Recommendations:")
    for recommendation in recommendations:
        print(f"  - {recommendation}")


def build(_: argparse.Namespace) -> None:
    from stack.provenance import verify_source
    verify_source(ROOT)
    compose("build", "ninfer")


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
    setup_parser.add_argument(
        "--model",
        choices=tuple(MODEL_PROFILES),
        help="select a model without showing the interactive model menu",
    )
    setup_parser.set_defaults(func=setup)
    prepare = sub.add_parser(
        "prepare-model",
        help="prepare a pinned stock or uncensored NInfer artifact",
    )
    prepare.add_argument("--yes", action="store_true", help="skip the model preparation confirmation")
    prepare.add_argument("--model", choices=tuple(MODEL_PROFILES), help="model profile to prepare")
    prepare.set_defaults(func=prepare_model)
    install = sub.add_parser(
        "install-hermes",
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
    select = sub.add_parser(
        "select-model",
        help="prepare and safely switch between stock and uncensored models",
    )
    select.add_argument(
        "--model",
        choices=tuple(MODEL_PROFILES),
        help="model profile to select (runtime profiles use select-runtime --profile)",
    )
    select.add_argument("--yes", action="store_true", help="skip the download confirmation")
    select.set_defaults(func=select_model)
    runtime = sub.add_parser(
        "select-runtime",
        help="switch among reviewed RTX 5090 runtime profiles and update Hermes",
    )
    runtime.add_argument("--profile", choices=tuple(RUNTIME_PROFILES), help="runtime profile")
    runtime.set_defaults(func=select_runtime)
    network_parser = sub.add_parser(
        "network",
        help="show or change local-only/LAN access to the authenticated NInfer API",
    )
    network_parser.add_argument("--mode", choices=("local", "lan"), help="network exposure mode")
    network_parser.add_argument("--address", help="specific RFC1918 IPv4 address for LAN mode")
    network_parser.add_argument(
        "--show-key",
        action="store_true",
        help="deliberately reveal the bearer key needed by a remote client",
    )
    network_parser.add_argument(
        "--yes", action="store_true", help="skip the LAN exposure confirmation"
    )
    network_parser.set_defaults(func=network)
    sub.add_parser("build", help="build the verified NInfer source").set_defaults(func=build)
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
    diagnose = sub.add_parser(
        "diagnose-performance",
        help="summarize private performance counters from recent NInfer logs",
    )
    diagnose.add_argument(
        "--lines", type=int, default=2000, help="number of recent container log lines to inspect"
    )
    diagnose.set_defaults(func=diagnose_performance)

    from stack.commands import register_commands
    register_commands(sub)
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        raise SystemExit(130)
    except (StackError, ValueError) as exc:
        print(f"ninfer: {exc}", file=sys.stderr)
        raise SystemExit(1)
