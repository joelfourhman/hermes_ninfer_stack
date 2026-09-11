"""Optional job-scoped Hermes hooks: observations and pre-tool durable handoffs.

Installed only into the private home of an explicitly started job/benchmark.
Never inserts dynamic text into the system prompt or modifies API requests.
"""

import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time

_lock = threading.Lock()
_starts = {}


def _write_json(path, value):
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def record(kind, **kwargs):
    directory = os.environ.get("NINFER_JOB_EVENTS")
    if not directory:
        return
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    now = time.monotonic()
    session = kwargs.get("session_id") or ""
    tool = kwargs.get("tool_name") or kwargs.get("function_name") or ""
    identifier = kwargs.get("tool_call_id") or kwargs.get("api_request_id") or session
    row = {
        "event": kind,
        "time_unix": time.time(),
        "session_id": session,
        "tool": tool,
        "agent_epoch": os.environ.get("NINFER_JOB_EPOCH"),
    }
    with _lock:
        if kind.startswith("pre_"):
            _starts[(kind[4:], identifier)] = now
        elif kind.startswith("post_"):
            started = _starts.pop((kind[5:], identifier), None)
            if started is not None:
                row["duration_seconds"] = now - started
        if kind == "pre_api_request":
            row["system_prompt_sha256"] = hashlib.sha256(
                json.dumps(kwargs.get("system_prompt"), sort_keys=True, default=str).encode()
            ).hexdigest()
            for key in (
                "api_request_id",
                "tool_count",
                "message_count",
                "approx_input_tokens",
                "retry_count",
            ):
                row[key] = kwargs.get(key)
        if kind == "post_api_request":
            row["duration_seconds"] = kwargs.get("api_duration")
            first = kwargs.get("first_chunk_at")
            start = kwargs.get("started_at")
            row["ttfb_seconds"] = first - start if first is not None and start is not None else None
            # Hermes exposes first stream chunk, not necessarily first output token.
            response = kwargs.get("response") or {}
            if isinstance(response, dict):
                for key in ("usage", "timings"):
                    if isinstance(response.get(key), dict):
                        row[key] = response[key]
        if session:
            _write_json(root / "session.json", {"session_id": session})
        if kind == "pre_tool_call":
            state = os.environ.get("NINFER_JOB_STATE")
            if state and Path(state).exists():
                # Parent ledger is immutable during this tool call; fsync the last
                # validated handoff before allowing any tool, including terminal.
                _write_json(
                    root / "before-tool.json",
                    json.loads(Path(state).read_text(encoding="utf-8")),
                )
        with (root / "events.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
            f.flush()
            os.fsync(f.fileno())


def before_tool(**kwargs):
    try:
        record("pre_tool_call", **kwargs)
    except Exception:
        return {
            "action": "block",
            "reason": "Durable job checkpoint write failed; repair storage before continuing.",
        }


def register(ctx):
    ctx.register_hook("pre_tool_call", before_tool)
    for event in (
        "post_tool_call",
        "pre_llm_call",
        "post_llm_call",
        "pre_api_request",
        "post_api_request",
        "on_session_start",
        "on_session_end",
    ):
        ctx.register_hook(event, lambda _event=event, **kwargs: record(_event, **kwargs))
