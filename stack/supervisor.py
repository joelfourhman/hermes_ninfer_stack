"""Optional, explicit escalation of a compact checkpoint to a compatible provider."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from stack.api import Client
from stack.jobs import load_state
from stack.storage import atomic_json

REASONS = (
    "initial-architecture",
    "major-plan",
    "stuck",
    "failing-tests",
    "design-decision",
    "milestone-review",
    "final-review",
)


class Supervisor(Protocol):
    def review(self, packet: dict) -> str: ...


class DisabledSupervisor:
    def review(self, packet: dict) -> str:
        raise ValueError("Supervisor is disabled; local work remains the default")


class CompatibleSupervisor:
    def __init__(self, endpoint: str, token: str, model: str):
        parsed = urlsplit(endpoint)
        if parsed.scheme != "https" and parsed.hostname not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise ValueError("Remote supervisor endpoint must use HTTPS")
        self.client = Client(endpoint, token, model, 120)

    def review(self, packet: dict) -> str:
        response = self.client.json(
            "/chat/completions",
            {
                "model": self.client.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "Review this agent checkpoint. Identify a focused next approach, missing validation, and risks. Do not execute tools.",
                    },
                    {"role": "user", "content": json.dumps(packet)},
                ],
                "max_tokens": 2048,
            },
        )
        return response["choices"][0]["message"]["content"]


def packet_for(state: dict, reason: str) -> dict:
    if reason not in REASONS:
        raise ValueError("Unsupported supervisor trigger")
    return {
        "reason": reason,
        **{
            key: state[key]
            for key in (
                "goal",
                "current_milestone",
                "completed_tasks",
                "important_findings",
                "current_blocker",
                "next_actions",
            )
        },
        "failed_attempt_count": len(state["failed_attempts"]),
    }


def supervise(args) -> None:
    state = load_state(Path(args.state))
    packet = packet_for(state, args.reason)
    packet_path = Path(state["job_dir"]) / "supervisor-request.json"
    atomic_json(packet_path, packet)
    if not args.send:
        print(f"Reviewable escalation packet: {packet_path}. Nothing was sent.")
        return
    if not state["supervisor"].get("enabled"):
        raise ValueError(
            "Supervisor is disabled; use job supervisor-config with an explicit enabled configuration first"
        )
    config = state["supervisor"]
    if config.get("provider") not in {"openai", "openai-compatible"}:
        raise ValueError(
            "Provider requires a Supervisor implementation; compatible OpenAI-style APIs are supported"
        )
    endpoint = os.environ.get(config.get("endpoint_env", "SUPERVISOR_BASE_URL"), "")
    token = os.environ.get(config.get("key_env", "SUPERVISOR_API_KEY"), "")
    model = os.environ.get(config.get("model_env", "SUPERVISOR_MODEL"), "")
    if not all((endpoint, token, model)):
        raise ValueError("Set supervisor endpoint, key and model environment variables")
    reply = CompatibleSupervisor(endpoint, token, model).review(packet)
    (packet_path.parent / "supervisor-review.txt").write_text(reply, encoding="utf-8")
    print("Supervisor review saved. Apply the advice through a deliberate job replan.")


def configure(args) -> None:
    from stack.jobs import checkpoint, worker_alive
    from stack.storage import exclusive

    path = Path(args.state)
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    allowed = {
        "enabled",
        "provider",
        "escalation_after_failures",
        "milestone_review",
        "final_review",
        "endpoint_env",
        "key_env",
        "model_env",
    }
    if (
        not isinstance(config, dict)
        or set(config) - allowed
        or not isinstance(config.get("enabled"), bool)
    ):
        raise ValueError(
            "Supervisor config accepts only documented fields and environment variable names, never inline credentials"
        )
    with exclusive(path.with_suffix(".lock")):
        state = load_state(path)
        if worker_alive(state.get("worker_pid")):
            raise ValueError("Do not change supervisor policy during an active epoch")
        state["supervisor"].update(config)
        checkpoint(path, state, "supervisor-config")
