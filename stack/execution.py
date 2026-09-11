"""Job-scoped mappings to Hermes's existing local/Docker/SSH terminal backends."""

from __future__ import annotations

import os
import re
import shlex
import signal
import subprocess
import uuid
from pathlib import Path


def validate_backend(config: dict) -> None:
    mode = config.get("mode", "local")
    if mode not in {"local", "container", "remote"}:
        raise ValueError("Execution mode must be local, container or remote")
    if mode == "container":
        if not config.get("image") or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_./:@-]*", config["image"]
        ):
            raise ValueError("Container jobs require an explicit worker image")
        if config.get("network", "none") not in {"none", "bridge"}:
            raise ValueError("Container network policy must be none or bridge")
    if mode == "remote":
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]*", config.get("host", "")):
            raise ValueError("Remote jobs require an SSH host alias or user@host")
        if not config.get("workspace", "").startswith("/"):
            raise ValueError("Remote workspace must be an absolute Linux path")


def terminal_settings(config: dict, workspace: Path) -> dict:
    validate_backend(config)
    mode = config["mode"]
    if mode == "local":
        return {"backend": "local", "cwd": str(workspace)}
    if mode == "container":
        return {
            "backend": "docker",
            "cwd": "/workspace",
            "docker_image": config["image"],
            "docker_volumes": [f"{workspace.as_posix()}:/workspace"],
            "docker_mount_cwd_to_workspace": False,
            "docker_network": config.get("network", "none") == "bridge",
            "docker_forward_env": [],
            "docker_env": {},
            "docker_extra_args": ["--cap-drop=ALL", "--security-opt=no-new-privileges"],
            "docker_persist_across_processes": False,
            "container_memory": 4096,
            "container_cpu": 4,
        }
    host = config["host"]
    user, separator, hostname = host.partition("@")
    return {
        "backend": "ssh",
        "cwd": config["workspace"],
        "ssh_host": hostname if separator else host,
        "ssh_user": user if separator else config.get("user", ""),
        "ssh_port": config.get("port", 22),
        "ssh_key": os.environ.get(config.get("key_env", "HERMES_WORKER_SSH_KEY"), ""),
    }


def execution_argv(config: dict, workspace: Path, argv: list[str]) -> list[str]:
    validate_backend(config)
    if not argv or any(not isinstance(arg, str) or "\x00" in arg for arg in argv):
        raise ValueError("Validation command must be a nonempty JSON array of strings")
    if config["mode"] == "local":
        return argv
    if config["mode"] == "container":
        return [
            "docker",
            "run",
            "--rm",
            "--network",
            config.get("network", "none"),
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--memory",
            "4g",
            "--cpus",
            "4",
            "--pids-limit",
            "256",
            "--mount",
            f"type=bind,source={workspace},target=/workspace",
            "--workdir",
            "/workspace",
            config["image"],
            *argv,
        ]
    command = "cd -- " + shlex.quote(config["workspace"]) + " && " + shlex.join(argv)
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        config["host"],
        command,
    ]


def stop_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait(timeout=10)


def execute(
    config: dict, workspace: Path, argv: list[str], timeout: int = 120
) -> subprocess.CompletedProcess:
    command = execution_argv(config, workspace, argv)
    container_name = None
    if config["mode"] == "container":
        container_name = "ninfer-validation-" + uuid.uuid4().hex
        command[2:2] = ["--name", container_name]
    process = subprocess.Popen(
        command,
        cwd=workspace,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=os.name != "nt",
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    except BaseException:
        stop_tree(process)
        if container_name:
            subprocess.run(
                ["docker", "rm", "-f", container_name], capture_output=True, timeout=30, check=False
            )
        raise


def repo_snapshot(config: dict, workspace: Path) -> dict:
    def git(*args):
        result = execute(config, workspace, ["git", *args], 30)
        if result.returncode:
            raise ValueError("Cannot validate job repository state with git")
        return result.stdout.strip()

    return {
        "repo_head": git("rev-parse", "HEAD"),
        "files_changed": git("status", "--porcelain").splitlines(),
        "diff": git("diff", "--binary", "HEAD"),
    }
