"""Durable bounded epochs around Hermes sessions, not a second agent loop."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path, PurePosixPath

from stack.execution import execute, repo_snapshot, validate_backend
from stack.hermes_runner import prepare_home, run_epoch
from stack.storage import atomic_json, checked_json, exclusive

STATE_FIELDS = (
    "goal",
    "current_milestone",
    "completed_tasks",
    "failed_attempts",
    "important_findings",
    "repo_head",
    "tests_status",
    "files_changed",
    "current_blocker",
    "next_actions",
    "last_checkpoint_time",
    "agent_epoch",
)


def load_state(path: Path) -> dict:
    state = checked_json(path)
    if state.get("schema_version") != 1 or any(
        key not in state for key in STATE_FIELDS
    ):
        raise ValueError("Unsupported or incomplete checkpoint schema")
    if not isinstance(state["agent_epoch"], int) or not isinstance(
        state["failed_attempts"], list
    ):
        raise ValueError("Invalid checkpoint field types")
    return state


def checkpoint(path: Path, state: dict, reason: str) -> None:
    state["last_checkpoint_time"] = time.time()
    state["checkpoint_reason"] = reason
    snapshot = (
        Path(state["job_dir"])
        / "checkpoints"
        / f"{state['agent_epoch']:04d}-{time.time_ns()}-{reason}.json"
    )
    atomic_json(snapshot, state, checksum=True)
    atomic_json(path, state, checksum=True)


def failure_fingerprint(returncode: int, output: str) -> str:
    # Test durations/ANSI colors vary; test names, failure text and approach remain.
    text = re.sub(r"\x1b\[[0-9;]*m", "", output)
    text = re.sub(r"\b\d+\.\d+s\b", "<duration>", text)
    return hashlib.sha256((str(returncode) + "\n" + text.strip()).encode()).hexdigest()


def record_failure(state: dict, returncode: int, output: str) -> None:
    fingerprint = failure_fingerprint(returncode, output)
    state["failed_attempts"].append(
        {
            "approach": state["approach"],
            "fingerprint": fingerprint,
            "epoch": state["agent_epoch"],
        }
    )
    repeated = sum(
        row["approach"] == state["approach"] and row["fingerprint"] == fingerprint
        for row in state["failed_attempts"]
    )
    attempts = sum(
        row["approach"] == state["approach"] for row in state["failed_attempts"]
    )
    if repeated >= state["max_retries"] or attempts >= state["max_retries"]:
        state["status"] = "needs_replan"
        state["current_blocker"] = (
            "Retry limit reached; select a different approach with job replan"
        )
        state["next_actions"] = [
            "Inspect failed epoch evidence and re-plan before further execution"
        ]
    else:
        state["status"] = "ready"


def worker_alive(pid: int | None) -> bool:
    if not pid:
        return False
    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
        return f'"{pid}"' in result.stdout
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def init_job(args) -> None:
    repo = Path(args.repo).resolve()
    path = Path(args.state).resolve() if args.state else repo / "PROJECT_STATE.json"
    if path.exists():
        raise ValueError("State already exists; use job resume")
    validation = json.loads(args.test_command)
    if (
        not isinstance(validation, list)
        or not validation
        or any(not isinstance(x, str) for x in validation)
    ):
        raise ValueError("--test-command must be a JSON argument array")
    if not 1 <= args.max_retries <= 10:
        raise ValueError("max-retries must be 1..10")
    if not 1 <= args.max_epochs_total <= 1000:
        raise ValueError("max-epochs-total must be 1..1000")
    backend = {
        "mode": args.backend,
        "image": args.image,
        "network": args.network,
        "host": args.host,
        "workspace": args.remote_workspace,
    }
    validate_backend(backend)
    job_dir = repo / ".ninfer-jobs" / uuid.uuid4().hex[:12]
    job_dir.mkdir(parents=True, exist_ok=False)
    (repo / ".ninfer-jobs/.gitignore").write_text("*\n", encoding="utf-8")
    workspace = repo
    if args.backend == "container":
        workspace = job_dir / "workspace"
        subprocess.run(
            ["git", "clone", "--no-hardlinks", "--no-local", str(repo), str(workspace)],
            check=True,
            capture_output=True,
            text=True,
        )
    snapshot = repo_snapshot(backend, workspace)
    state = {
        "schema_version": 1,
        "goal": args.goal,
        "current_milestone": "Plan and first validated increment",
        "completed_tasks": [],
        "failed_attempts": [],
        "important_findings": [],
        "repo_head": snapshot["repo_head"],
        "tests_status": "not_run",
        "files_changed": snapshot["files_changed"],
        "current_blocker": None,
        "next_actions": ["Inspect project and establish a plan"],
        "last_checkpoint_time": None,
        "agent_epoch": 0,
        "status": "ready",
        "session_id": None,
        "worker_pid": None,
        "job_dir": str(job_dir),
        "workspace": str(workspace),
        "backend": backend,
        "validation_argv": validation,
        "approach": "initial",
        "max_retries": args.max_retries,
        "supervisor": {
            "enabled": False,
            "provider": "openai-compatible",
            "escalation_after_failures": 3,
            "milestone_review": True,
            "final_review": True,
        },
        "max_epochs_total": args.max_epochs_total,
    }
    checkpoint(path, state, "created")
    print(
        f'Job created: {path}\nWorkspace: {workspace}\nRun: python ninfer.py job resume --state "{path}"'
    )


def epoch_prompt(state: dict, report: Path) -> str:
    handoff = {key: state[key] for key in STATE_FIELDS}
    return (
        "Continue this bounded project epoch. The JSON below is the durable handoff. Inspect the repository, plan, make one useful increment and run validation. "
        "Preserve project/user security and approval settings. Before risky operations rely on enabled Hermes filesystem checkpoints. "
        "Do not modify PROJECT_STATE.json or .ninfer-jobs internals. End by writing only the following report file as JSON: "
        + str(report)
        + ". "
        "Fields: current_milestone (string), completed_tasks (string list), important_findings (string list), next_actions (string list), "
        "current_blocker (string or null), goal_complete (boolean). goal_complete must be true only when the complete goal is met. "
        "The controller independently runs validation before accepting completion.\n\n"
        + json.dumps(handoff, indent=2)
        + "\nCurrent approach: "
        + state["approach"]
        + "\nValidation argv: "
        + json.dumps(state["validation_argv"])
    )


def apply_report(state: dict, report: dict) -> bool:
    if not isinstance(report, dict) or not isinstance(
        report.get("goal_complete"), bool
    ):
        raise ValueError("Epoch report must declare goal_complete as a boolean")
    for key in ("completed_tasks", "important_findings", "next_actions"):
        value = report.get(key)
        if (
            not isinstance(value, list)
            or len(value) > 200
            or any(not isinstance(v, str) or len(v) > 8000 for v in value)
        ):
            raise ValueError(f"Invalid epoch report {key}")
        if key == "next_actions":
            state[key] = value
        else:
            state[key] = list(dict.fromkeys(state[key] + value))[-200:]
    for key in ("current_milestone", "current_blocker"):
        value = report.get(key)
        if not (isinstance(value, str) or (key == "current_blocker" and value is None)):
            raise ValueError(f"Invalid epoch report {key}")
        state[key] = value
    return report["goal_complete"]


def resume_job(args) -> None:
    from stack.commands import _helper

    helper = _helper()
    path = Path(args.state).resolve()
    if (
        not 1 <= args.epochs <= 100
        or not 1 <= args.max_turns <= 200
        or not 30 <= args.timeout <= 7200
    ):
        raise ValueError(
            "Bounds: epochs 1..100, turns 1..200, timeout 30..7200 seconds"
        )
    with exclusive(path.with_suffix(".lock")):
        state = load_state(path)
        if state["status"] == "complete":
            print("Goal is complete.")
            return
        if state["status"] == "needs_replan":
            raise ValueError(state["current_blocker"])
        if worker_alive(state.get("worker_pid")):
            raise ValueError(
                "Previous Hermes worker is still running; stop or wait for it before resume"
            )
        workspace = Path(state["workspace"])
        job_dir = Path(state["job_dir"])
        command, env = prepare_home(
            helper, job_dir / "hermes", workspace, state["backend"]
        )
        env["NINFER_JOB_STATE"] = str(path)
        for _ in range(args.epochs):
            if state["agent_epoch"] >= state["max_epochs_total"]:
                state.update(
                    status="needs_replan", current_blocker="Total epoch budget reached"
                )
                checkpoint(path, state, "budget")
                break
            before = repo_snapshot(state["backend"], workspace)
            previous_findings = list(state["important_findings"])
            previous_tasks = list(state["completed_tasks"])
            if state["repo_head"] != before["repo_head"]:
                state["important_findings"].append(
                    "Repository HEAD changed between epochs; re-inspect before editing"
                )
            state["agent_epoch"] += 1
            state["status"] = "running"
            state["worker_pid"] = None
            state["repo_head"] = before["repo_head"]
            state["files_changed"] = before["files_changed"]
            checkpoint(path, state, "before-epoch")
            directory = job_dir / f"epoch-{state['agent_epoch']:04d}"
            directory.mkdir(parents=True, exist_ok=True)
            env["NINFER_JOB_EPOCH"] = str(state["agent_epoch"])
            report_path = workspace / "EPOCH_REPORT.json"
            # A previous report must never certify a new epoch.
            if state["backend"]["mode"] == "remote":
                report_display = (
                    PurePosixPath(state["backend"]["workspace"]) / "EPOCH_REPORT.json"
                )
                execute(
                    state["backend"], workspace, ["rm", "-f", "--", "EPOCH_REPORT.json"]
                )
            else:
                report_display = (
                    PurePosixPath("/workspace/EPOCH_REPORT.json")
                    if state["backend"]["mode"] == "container"
                    else report_path
                )
                if report_path.exists():
                    report_path.rename(
                        job_dir / f"report-before-{state['agent_epoch']}.json"
                    )

            def started(pid):
                state["worker_pid"] = pid
                checkpoint(path, state, "worker-start")

            try:
                row = run_epoch(
                    command,
                    env,
                    workspace,
                    directory,
                    epoch_prompt(state, report_display),
                    state.get("session_id"),
                    args.max_turns,
                    args.timeout,
                    started,
                )
                state["worker_pid"] = None
                state["session_id"] = row["session_id"]
                validation = execute(
                    state["backend"],
                    workspace,
                    state["validation_argv"],
                    min(args.timeout, 600),
                )
                output = (validation.stdout + validation.stderr)[-32000:]
                (directory / "validation.txt").write_text(output, encoding="utf-8")
                state["tests_status"] = {
                    "returncode": validation.returncode,
                    "evidence": str(directory / "validation.txt"),
                }
                after = repo_snapshot(state["backend"], workspace)
                state["repo_head"] = after["repo_head"]
                state["files_changed"] = after["files_changed"]
                if state["backend"]["mode"] == "remote":
                    report_text = execute(
                        state["backend"], workspace, ["cat", "EPOCH_REPORT.json"]
                    ).stdout
                else:
                    report_text = report_path.read_text(encoding="utf-8")
                if len(report_text) > 128000:
                    raise ValueError("Epoch report is too large")
                complete = apply_report(state, json.loads(report_text))
                progressed = (
                    before["diff"] != after["diff"]
                    or before["repo_head"] != after["repo_head"]
                    or state["important_findings"] != previous_findings
                    or state["completed_tasks"] != previous_tasks
                )
                if row["returncode"] or row["timed_out"] or validation.returncode:
                    record_failure(
                        state,
                        validation.returncode or row["returncode"] or 1,
                        output or "Hermes worker failed",
                    )
                elif complete:
                    state.update(status="complete", current_blocker=None)
                elif not progressed:
                    record_failure(
                        state, 1, "No validated repository progress in this epoch"
                    )
                else:
                    state["status"] = "ready"
                checkpoint(path, state, "validated")
                if state["status"] == "needs_replan" and len(
                    state["failed_attempts"]
                ) >= state["supervisor"].get("escalation_after_failures", 3):
                    from stack.supervisor import packet_for

                    atomic_json(
                        job_dir / "supervisor-request.json", packet_for(state, "stuck")
                    )
                print(
                    f"Epoch {state['agent_epoch']}: {state['status']}; validation exit {validation.returncode}"
                )
            except (Exception, KeyboardInterrupt) as exc:
                state["worker_pid"] = None
                state["current_blocker"] = (
                    f"Epoch interrupted: {type(exc).__name__}; inspect private epoch evidence"
                )
                record_failure(state, 1, state["current_blocker"])
                checkpoint(path, state, "interrupted")
                raise
            if state["status"] in {"complete", "needs_replan"}:
                break


def manage_job(args) -> None:
    path = Path(args.state).resolve()
    if args.action == "status":
        print(json.dumps(load_state(path), indent=2))
        return
    with exclusive(path.with_suffix(".lock")):
        if args.action == "recover":
            recovered = load_state(Path(args.snapshot))
            if path.exists():
                shutil.copy2(
                    path, path.with_name(path.name + ".corrupt-" + str(time.time_ns()))
                )
            checkpoint(path, recovered, "recovered")
        else:
            state = load_state(path)
            if worker_alive(state.get("worker_pid")):
                raise ValueError("Worker is still active")
            if args.action == "replan":
                if args.approach == state["approach"]:
                    raise ValueError("Re-plan must name a different approach")
                state.update(
                    approach=args.approach, status="ready", current_blocker=None
                )
                checkpoint(path, state, "replan")
            elif args.action == "checkpoint":
                checkpoint(path, state, "manual")
            elif args.action == "export":
                destination = Path(args.destination).resolve()
                destination.mkdir(parents=True, exist_ok=False)
                snapshot = repo_snapshot(state["backend"], Path(state["workspace"]))
                (destination / "changes.patch").write_text(
                    snapshot["diff"], encoding="utf-8"
                )
                atomic_json(destination / "PROJECT_STATE.json", state, checksum=True)
                print(
                    "Exported tracked-file patch and state. Untracked build artifacts remain in the job workspace."
                )


def register_jobs(sub):
    parser = sub.add_parser("job", help="durable bounded Hermes epochs and recovery")
    actions = parser.add_subparsers(dest="action", required=True)
    init = actions.add_parser("init")
    init.add_argument("--goal", required=True)
    init.add_argument("--repo", default=".")
    init.add_argument("--state")
    init.add_argument(
        "--test-command",
        required=True,
        help='JSON argv, e.g. ["python","-m","unittest"]',
    )
    init.add_argument(
        "--backend", choices=("local", "container", "remote"), default="local"
    )
    init.add_argument("--image")
    init.add_argument("--network", choices=("none", "bridge"), default="none")
    init.add_argument("--host")
    init.add_argument("--remote-workspace")
    init.add_argument("--max-retries", type=int, default=3)
    init.add_argument("--max-epochs-total", type=int, default=50)
    init.set_defaults(func=init_job)
    resume = actions.add_parser("resume")
    resume.add_argument("--state", default="PROJECT_STATE.json")
    resume.add_argument("--epochs", type=int, default=1)
    resume.add_argument("--max-turns", type=int, default=24)
    resume.add_argument("--timeout", type=int, default=600)
    resume.set_defaults(func=resume_job)
    for action in ("status", "checkpoint", "replan", "recover", "export"):
        command = actions.add_parser(action)
        command.add_argument("--state", default="PROJECT_STATE.json")
        command.set_defaults(func=manage_job)
        if action == "replan":
            command.add_argument("--approach", required=True)
        if action == "recover":
            command.add_argument("--snapshot", required=True)
        if action == "export":
            command.add_argument("--destination", required=True)
    from stack.supervisor import REASONS, configure, supervise

    review = actions.add_parser("supervise")
    review.add_argument("--state", default="PROJECT_STATE.json")
    review.add_argument("--reason", choices=REASONS, required=True)
    review.add_argument("--send", action="store_true")
    review.set_defaults(func=supervise)
    config = actions.add_parser("supervisor-config")
    config.add_argument("--state", default="PROJECT_STATE.json")
    config.add_argument("--config", required=True)
    config.set_defaults(func=configure)
