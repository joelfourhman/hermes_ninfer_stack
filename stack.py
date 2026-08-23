#!/usr/bin/env python3
"""Cross-platform control plane for the Hermes + NInfer Compose stack."""

from __future__ import annotations

import argparse
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
MODEL_FILE = "qwen3_8_27b_nvfp4.ninfer"
MODEL_SIZE_GIB = "20.02"
SETUP_MARKER = ROOT / "hermes-data" / ".stack-setup-complete"
LEGACY_HERMES_IMAGE = "nousresearch/hermes-agent:v2026.8.19"
PINNED_HERMES_IMAGE = (
    "nousresearch/hermes-agent:v2026.8.19@"
    "sha256:f3cba6abf5ed80d47a271498d663ace5dda87f45000552afb8be8370a35df1b5"
)


class StackError(RuntimeError):
    pass


def run(command: list[str], *, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=ROOT,
            check=check,
            text=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
        )
    except FileNotFoundError as exc:
        raise StackError(f"Required command is not installed or not on PATH: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        if capture and exc.stderr:
            print(exc.stderr.rstrip(), file=sys.stderr)
        raise StackError(f"Command failed with exit code {exc.returncode}: {' '.join(command)}") from exc


def compose(*args: str, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess[str]:
    command = ["docker", "compose", "--project-directory", str(ROOT)]
    if ENV_FILE.is_file():
        command += ["--env-file", str(ENV_FILE)]
    command += ["-f", str(COMPOSE_FILE), *args]
    return run(command, check=check, capture=capture)


def read_env(path: Path = ENV_FILE) -> dict[str, str]:
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


def merge_env() -> None:
    example_lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    existing = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.is_file() else []
    existing_keys = {
        line.split("=", 1)[0]
        for line in existing
        if re.match(r"^[A-Z][A-Z0-9_]*=", line)
    }
    merged = list(existing)
    for line in example_lines:
        match = re.match(r"^([A-Z][A-Z0-9_]*)=", line)
        if match and match.group(1) not in existing_keys:
            merged.append(line)
            existing_keys.add(match.group(1))
    if not ENV_FILE.is_file():
        merged = list(example_lines)

    replacements = {
        "NINFER_API_KEY": secrets.token_hex(32),
        "HERMES_API_SERVER_KEY": secrets.token_hex(32),
        "HERMES_DASHBOARD_PASSWORD": secrets.token_urlsafe(24),
        "HERMES_DASHBOARD_SECRET": secrets.token_hex(32),
    }
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
            if key in replacements:
                line = f"{key}={replacements[key]}"
            elif key == "HERMES_IMAGE" and line == f"HERMES_IMAGE={LEGACY_HERMES_IMAGE}":
                line = f"HERMES_IMAGE={PINNED_HERMES_IMAGE}"
        output.append(line)
    atomic_write(ENV_FILE, "\n".join(output).rstrip() + "\n")


def validate_env() -> None:
    values = read_env()
    required = [
        "HERMES_IMAGE",
        "NINFER_API_KEY",
        "HERMES_API_SERVER_KEY",
        "HERMES_DASHBOARD_USERNAME",
        "HERMES_DASHBOARD_PASSWORD",
        "HERMES_DASHBOARD_SECRET",
        "NINFER_MODEL_FILE",
        "NINFER_MODEL_ID",
        "NINFER_CONTEXT_LENGTH",
    ]
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise StackError("Missing required .env values: " + ", ".join(missing))
    for key in ("NINFER_API_KEY", "HERMES_API_SERVER_KEY", "HERMES_DASHBOARD_SECRET"):
        if not re.fullmatch(r"[0-9a-fA-F]{64}", values[key]):
            raise StackError(f"{key} must be a 64-character hexadecimal secret")
    if values["NINFER_API_KEY"] == values["HERMES_API_SERVER_KEY"]:
        raise StackError("NINFER_API_KEY and HERMES_API_SERVER_KEY must be distinct")


def initialize_local_state() -> None:
    if not ENV_EXAMPLE.is_file():
        raise StackError("Missing .env.example")
    if not (ROOT / "ninfer" / ".git").exists():
        print("Initializing the pinned NInfer submodule...")
        run(["git", "submodule", "update", "--init", "--recursive", "--depth", "1"])
    commit = run(["git", "-C", str(ROOT / "ninfer"), "rev-parse", "HEAD"], capture=True).stdout.strip()
    if commit != NINFER_COMMIT:
        raise StackError(f"NInfer is at {commit}; expected {NINFER_COMMIT}")
    status = run(
        ["git", "-C", str(ROOT / "ninfer"), "status", "--porcelain", "--untracked-files=all"],
        capture=True,
    ).stdout.strip()
    if status:
        raise StackError("The NInfer submodule has local or untracked changes")

    for directory in (ROOT / "hermes-data", ROOT / "workspace", ROOT / "models"):
        directory.mkdir(parents=True, exist_ok=True)
    trust_directory = ROOT / "hermes-data" / ".ssh"
    trust_directory.mkdir(exist_ok=True)
    try:
        trust_directory.chmod(0o700)
    except OSError:
        # Docker Desktop bind mounts may not implement POSIX mode changes.
        pass
    config = ROOT / "hermes-data" / "config.yaml"
    if not config.exists():
        shutil.copy2(ROOT / "hermes" / "config.example.yaml", config)
        print("Created hermes-data/config.yaml from the reviewed template.")
    hermes_env = ROOT / "hermes-data" / ".env"
    hermes_env.touch(exist_ok=True)
    merge_env()
    validate_env()
    compose("config", "--quiet")
    print("Local configuration initialized. No global Python packages were installed.")


def confirm_model_download() -> bool:
    print()
    print(f"The pinned model is not present: models/{MODEL_FILE}")
    print(f"Download size: {MODEL_SIZE_GIB} GiB (at least 24 GiB free space required).")
    print("The download runs through uv in an isolated Compose utility container.")
    answer = input("Download and verify the model now? [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def run_hermes_wizard() -> None:
    print()
    print("Hermes setup wizard choices for this stack:")
    print("  1. Blank Slate")
    print("  2. ninfer (currently active)")
    print("  3. qwen-local")
    print("  4. Keep current (ssh)")
    print("  5. Start with everything disabled - finish now")
    print("The wizard may warn that no provider is configured; setup restores it afterward.")
    input("Press Enter to open the Hermes wizard...")
    compose("run", "--rm", "--no-deps", "hermes", "setup")


def setup(args: argparse.Namespace) -> None:
    initialize_local_state()

    model_path = ROOT / "models" / MODEL_FILE
    if not model_path.is_file() or model_path.stat().st_size == 0:
        if not confirm_model_download():
            print("Setup paused before the model download. Run 'python stack.py setup' when ready.")
            return
    # This downloads only after the explicit prompt above. If the artifact is
    # already present, the utility verifies its checksum instead.
    download_model(argparse.Namespace(yes=True))

    # A prior completed installation may already have the long-running Hermes
    # service active. The wizard and managed configuration both require it off.
    compose("stop", "hermes")
    print("Building the pinned stack images...")
    compose("build")
    print("Starting NInfer and the SSH sandbox; initial model loading can take several minutes...")
    compose("up", "-d", "--wait", "--wait-timeout", "900", "ninfer", "sandbox")
    compose("run", "--rm", "--no-deps", "sandbox-trust")

    if args.rerun_wizard or not SETUP_MARKER.is_file():
        run_hermes_wizard()
    else:
        print("Hermes first-run wizard already completed; preserving its local choices.")

    # The wizard deliberately resets provider and terminal fields in Blank Slate
    # mode. Always reapply the reviewed integration boundary before startup.
    configure_hermes(argparse.Namespace())
    compose("up", "-d", "--wait", "--wait-timeout", "900")
    atomic_write(SETUP_MARKER, "completed\n")
    print()
    print("Setup complete. Hermes, NInfer, and the SSH sandbox are running.")
    print("Open Hermes with: python stack.py gui")


def download_model(args: argparse.Namespace) -> None:
    validate_env()
    configured_model = read_env().get("NINFER_MODEL_FILE")
    if configured_model != MODEL_FILE:
        raise StackError(
            f"The downloader provides only the tested {MODEL_FILE}; .env selects {configured_model!r}."
        )
    command = ["--profile", "tools", "run", "--rm", "--build", "model-downloader"]
    if args.yes:
        command.append("--yes")
    compose(*command)


def configure_hermes(_: argparse.Namespace) -> None:
    validate_env()
    running = compose("ps", "--status", "running", "-q", "hermes", capture=True).stdout.strip()
    if running:
        raise StackError("Hermes is running. Run 'python stack.py stop-hermes' first.")
    values = read_env()
    model_id = values["NINFER_MODEL_ID"]
    context = values["NINFER_CONTEXT_LENGTH"]
    if not re.fullmatch(r"[A-Za-z0-9._-]+", model_id):
        raise StackError("NINFER_MODEL_ID contains unsupported characters")
    if not context.isdigit() or not 1024 <= int(context) <= 262144:
        raise StackError("NINFER_CONTEXT_LENGTH must be from 1024 through 262144")
    config_file = ROOT / "hermes-data" / "config.yaml"
    hermes_env = ROOT / "hermes-data" / ".env"
    if not config_file.is_file():
        raise StackError("Missing hermes-data/config.yaml; run 'python stack.py setup'")
    config_backup = config_file.read_bytes()
    env_backup = hermes_env.read_bytes() if hermes_env.is_file() else None
    provider = json.dumps(
        {
            "api": "http://ninfer:8080/v1",
            "key_env": "NINFER_API_KEY",
            "transport": "chat_completions",
            "default_model": model_id,
            "models": {model_id: {"context_length": int(context), "supports_vision": False}},
        },
        separators=(",", ":"),
    )
    settings = [
        ("providers.ninfer", provider),
        ("model.provider", "custom:ninfer"),
        ("model.default", model_id),
        ("model.context_length", context),
        ("model.supports_vision", "false"),
        ("terminal.backend", "ssh"),
        ("terminal.cwd", "/workspace"),
        ("terminal.timeout", "180"),
        ("terminal.persistent_shell", "true"),
        ("terminal.env_passthrough", "[]"),
        ("TERMINAL_SSH_HOST", "sandbox"),
        ("TERMINAL_SSH_USER", "agent"),
        ("TERMINAL_SSH_PORT", "2222"),
        ("TERMINAL_SSH_KEY", "/ssh/id_ed25519"),
        ("tool_loop_guardrails.hard_stop_enabled", "true"),
        ("tool_loop_guardrails.hard_stop_after.exact_failure", "5"),
        ("tool_loop_guardrails.hard_stop_after.idempotent_no_progress", "5"),
    ]
    try:
        flat_settings = [item for pair in settings for item in pair]
        container_script = (
            'set -eu; while [ "$#" -gt 0 ]; do '
            'hermes config set "$1" "$2"; shift 2; done; hermes config check'
        )
        compose(
            "run",
            "--rm",
            "--no-deps",
            "hermes",
            "sh",
            "-euc",
            container_script,
            "sh",
            *flat_settings,
        )
    except Exception:
        config_file.write_bytes(config_backup)
        if env_backup is None:
            hermes_env.unlink(missing_ok=True)
        else:
            hermes_env.write_bytes(env_backup)
        raise
    print(f"Hermes is configured for {model_id} through NInfer and the SSH sandbox.")


def gui(args: argparse.Namespace) -> None:
    validate_env()
    compose("up", "-d", "hermes")
    values = read_env()
    port = values.get("HERMES_DASHBOARD_HOST_PORT", "9119")
    url = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    break
        except urllib.error.URLError:
            time.sleep(2)
    else:
        raise StackError("Hermes started, but its dashboard did not become ready within 120 seconds")
    print(f"Hermes dashboard: {url}")
    print(f"Username: {values['HERMES_DASHBOARD_USERNAME']}")
    print(f"Password: {values['HERMES_DASHBOARD_PASSWORD']}")
    if not args.no_open:
        webbrowser.open(url)


def shell(args: argparse.Namespace) -> None:
    service = args.service
    if service == "sandbox":
        compose("exec", "--user", "agent", service, "bash")
    else:
        compose("exec", service, "bash")


def repair_sandbox_trust(_: argparse.Namespace) -> None:
    validate_env()
    print("Stopping Hermes while its sandbox host trust is reconciled...", flush=True)
    compose("stop", "hermes")
    compose("build", "sandbox", "sandbox-trust")
    compose("up", "-d", "--wait", "--wait-timeout", "120", "--force-recreate", "sandbox")
    compose("run", "--rm", "--no-deps", "sandbox-trust")
    compose("up", "-d", "hermes")
    print("Sandbox host trust repaired. Hermes is starting again.", flush=True)


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
        help="run the complete interactive first-run workflow",
    )
    setup_parser.add_argument(
        "--rerun-wizard",
        action="store_true",
        help="run the Hermes wizard again while preserving stack-managed fields afterward",
    )
    setup_parser.set_defaults(func=setup)
    download = sub.add_parser("download-model", help="download with uv inside a Compose utility container")
    download.add_argument("--yes", action="store_true", help="skip the 20 GiB confirmation")
    download.set_defaults(func=download_model)
    sub.add_parser("build", help="build the stack images").set_defaults(func=passthrough(("build",)))
    sub.add_parser("up", help="start the complete stack").set_defaults(func=passthrough(("up", "-d")))
    sub.add_parser("down", help="stop the stack while preserving data").set_defaults(func=passthrough(("down",)))
    sub.add_parser("status", help="show Compose service status").set_defaults(func=passthrough(("ps",)))
    sub.add_parser("logs", help="follow all service logs").set_defaults(func=passthrough(("logs", "-f")))
    sub.add_parser("stop-hermes", help="stop Hermes before reconfiguration").set_defaults(func=passthrough(("stop", "hermes")))
    sub.add_parser("setup-hermes", help="rerun only the Hermes wizard for advanced recovery").set_defaults(
        func=passthrough(("run", "--rm", "--no-deps", "hermes", "setup"))
    )
    sub.add_parser("configure-hermes", help="apply the reviewed NInfer and sandbox settings").set_defaults(
        func=configure_hermes
    )
    sub.add_parser(
        "repair-sandbox-trust",
        help="safely refresh Hermes's persisted SSH host-key entry",
    ).set_defaults(func=repair_sandbox_trust)
    shell_parser = sub.add_parser("shell", help="open Bash inside a running service")
    shell_parser.add_argument("service", nargs="?", choices=("hermes", "ninfer", "sandbox"), default="hermes")
    shell_parser.set_defaults(func=shell)
    gui_parser = sub.add_parser("gui", help="start and open the authenticated Hermes dashboard")
    gui_parser.add_argument("--no-open", action="store_true", help="print the URL without opening a browser")
    gui_parser.set_defaults(func=gui)
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
        print(f"stack: {exc}", file=sys.stderr)
        raise SystemExit(1)
