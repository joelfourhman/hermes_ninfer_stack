"""Bounded stock-Hermes CLI execution in a private, persistent job home."""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path

from stack.execution import terminal_settings
from stack.storage import atomic_json
from stack.workloads import CODING_PROMPT


def prepare_home(
    helper, directory: Path, workspace: Path, backend: dict
) -> tuple[list[str], dict]:
    resolved = helper.native_hermes_command()
    if resolved is None:
        raise ValueError("Stock Hermes CLI is not installed; run install-hermes")
    command, env = resolved
    result = subprocess.run(
        [*command, "chat", "--help"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    for flag in (
        "--query-file",
        "--max-turns",
        "--resume",
        "--checkpoints",
        "--run-budget",
        "--quiet",
    ):
        if flag not in result.stdout:
            raise ValueError(
                f"Installed Hermes lacks {flag}; update through the official installer"
            )
    directory.mkdir(parents=True, exist_ok=True)
    values = helper.read_env()
    model = values["NINFER_MODEL_ID"]
    context = int(values["NINFER_CONTEXT_LENGTH"])
    config = {
        "model": {
            "provider": "custom:ninfer",
            "default": model,
            "context_length": context,
            "supports_vision": False,
        },
        "providers": {
            "ninfer": {
                "api": helper.ninfer_endpoint(values),
                "key_env": "NINFER_API_KEY",
                "transport": "chat_completions",
                "default_model": model,
                "models": {
                    model: {"context_length": context, "supports_vision": False}
                },
            }
        },
        "compression": {
            "enabled": True,
            "threshold": 0.9,
            "threshold_tokens": int(values["HERMES_COMPRESSION_THRESHOLD_TOKENS"]),
        },
        "agent": {"max_turns": int(values["HERMES_MAX_TURNS"])},
        "approvals": {"mode": "manual"},
        "terminal": terminal_settings(backend, workspace),
        "plugins": {"enabled": ["ninfer-job-observer"]},
        "toolsets": ["terminal", "file"],
        "memory": {"provider": "builtin"},
    }
    # JSON is valid YAML; avoid a host PyYAML dependency. This directory belongs
    # exclusively to the job, never to the user's Desktop profile.
    atomic_json(directory / "config.yaml", config)
    helper.atomic_write(
        directory / ".env", "NINFER_API_KEY=" + values["NINFER_API_KEY"] + "\n"
    )
    plugin = directory / "plugins/ninfer-job-observer"
    plugin.mkdir(parents=True, exist_ok=True)
    for name in ("__init__.py", "plugin.yaml"):
        shutil.copyfile(Path(__file__).parent / "hermes_plugin" / name, plugin / name)
    env = dict(
        env,
        HERMES_HOME=str(directory),
        PYTHONUTF8="1",
        NINFER_JOB_EVENTS=str(directory.parent / "events"),
    )
    # Inherited selectors may otherwise point at the Desktop config instead of this home.
    for key in (
        "HERMES_PROFILE",
        "HERMES_CONFIG",
        "HERMES_CONFIG_PATH",
        "HERMES_ENV",
        "HERMES_ENV_PATH",
        "HERMES_YOLO",
        "HERMES_KANBAN_GOAL_MODE",
        "HERMES_KANBAN_TASK",
    ):
        env.pop(key, None)
    return command, env


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


def run_epoch(
    command: list[str],
    env: dict,
    workspace: Path,
    directory: Path,
    prompt: str,
    session_id: str | None,
    max_turns: int,
    timeout: int,
    on_start=None,
) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    query = directory / "query.txt"
    query.write_text(prompt, encoding="utf-8")
    argv = [
        *command,
        "chat",
        "--query-file",
        str(query),
        "--quiet",
        "--checkpoints",
        "--max-turns",
        str(max_turns),
        "--run-budget",
        str(timeout),
        "--toolsets",
        "terminal,file",
    ]
    if session_id:
        argv += ["--resume", session_id, "--no-restore-cwd"]
    start = time.perf_counter()
    timed_out = False
    with (
        (directory / "stdout.txt").open("w", encoding="utf-8") as stdout,
        (directory / "stderr.txt").open("w", encoding="utf-8") as stderr,
    ):
        process = subprocess.Popen(
            argv,
            cwd=workspace,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            start_new_session=os.name != "nt",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            if on_start:
                on_start(process.pid)
            process.wait(timeout=timeout + 15)
        except subprocess.TimeoutExpired:
            timed_out = True
            stop_tree(process)
        except BaseException:
            stop_tree(process)
            raise
    stderr = (directory / "stderr.txt").read_text(encoding="utf-8", errors="replace")[
        -100000:
    ]
    stdout = (directory / "stdout.txt").read_text(encoding="utf-8", errors="replace")[
        -100000:
    ]
    sessions = re.findall(r"(?m)^session_id:\s*([A-Za-z0-9_.:-]+)\s*$", stderr)
    current = sessions[-1] if sessions else session_id
    event_session = Path(env["NINFER_JOB_EVENTS"]) / "session.json"
    if not sessions and event_session.exists():
        current = json.loads(event_session.read_text()).get("session_id") or current
    return {
        "returncode": process.returncode,
        "timed_out": timed_out,
        "session_id": current,
        "wall_seconds": time.perf_counter() - start,
        "answer": stdout,
        "stderr_tail": stderr[-2000:],
    }


def benchmark_hermes(helper, workspace, kind, args):
    home = workspace.root / ".ninfer-bench/hermes"
    home.parent.mkdir(parents=True, exist_ok=True)
    (home.parent / ".gitignore").write_text("*\n", encoding="utf-8")
    command, env = prepare_home(helper, home, workspace.root, {"mode": "local"})
    prompt = (
        CODING_PROMPT
        if kind == "coding"
        else "Read source-0.txt through source-3.txt, compare evidence and summarize all FIXTURE-N tokens. Use several tool calls."
    )
    rows = []
    session = None
    count = args.session_turns if kind == "long-session" else 1
    for i in range(count):
        query = (
            prompt
            if i == 0
            else f"Continue the same investigation, read source-{i % 4}.txt again, and connect its finding to earlier evidence."
        )
        row = run_epoch(
            command,
            env,
            workspace.root,
            home.parent / f"epoch-{i}",
            query,
            session,
            args.max_turns,
            int(args.timeout),
        )
        rows.append(row)
        session = row["session_id"]
        if row["returncode"]:
            break
    validation = workspace.test() if kind == "coding" else None
    success = len(rows) == count and all(
        row["returncode"] == 0 and not row["timed_out"] for row in rows
    )
    if kind == "coding":
        success = success and validation["passed"]
    else:
        success = success and all(
            f"FIXTURE-{i}" in rows[-1]["answer"] for i in range(4)
        )
    events_path = home.parent / "events/events.jsonl"
    events = (
        [json.loads(line) for line in events_path.read_text().splitlines()]
        if events_path.exists()
        else []
    )
    return {
        "workload": kind,
        "driver": "hermes",
        "success": success,
        "wall_seconds": sum(row["wall_seconds"] for row in rows),
        "epochs": rows,
        "hermes_session_id": session,
        "validation": validation,
        "hook_events": events,
        "tool_seconds": sum(
            e.get("duration_seconds", 0)
            for e in events
            if e["event"] == "post_tool_call"
        ),
        "model_request_seconds": sum(
            e.get("duration_seconds") or 0
            for e in events
            if e["event"] == "post_api_request"
        )
        if any(e["event"] == "post_api_request" for e in events)
        else None,
        "compression_events": None,
        "notes": "Actual stock Hermes CLI, isolated job home, native local tools and manual approvals. Hook timings may be unavailable on older builds; native NInfer records remain separate.",
    }
