#!/usr/bin/env python3
"""Exercise installed Hermes recovery and real repeated local compaction.

Run with Hermes's venv Python. --live uses only synthetic history and the
configured NInfer endpoint; no user sessions are read or modified.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ninfer
from stack.config import hermes_context_settings
from stack.api import Client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cycles", type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.cycles <= 20:
        parser.error("--cycles must be between 1 and 20")
    source = ninfer.hermes_home() / "hermes-agent"
    sys.path.insert(0, str(source))
    import httpx
    from openai import BadRequestError
    from agent.error_classifier import classify_api_error
    from agent.model_metadata import parse_context_limit_from_error

    for message in (
        "prepared prompt has 66627 tokens, exceeding Engine max_context 65536",
        "prepared prompt exceeds Engine max_context 240000",
    ):
        for wrapped in (False, True):
            body = {"code": "context_length_exceeded", "message": message,
                    "param": "messages", "type": "invalid_request_error"}
            error = BadRequestError(message, response=httpx.Response(
                400, request=httpx.Request("POST", "http://localhost/v1/chat/completions")
            ), body={"error": body} if wrapped else body)
            result = classify_api_error(error, provider="custom", model="qwen-local")
            assert result.should_compress, result
        expected_limit = 65536 if "65536" in message else 240000
        assert parse_context_limit_from_error(message) == expected_limit
    print("PASS: all four NInfer overflow error shapes request compression", flush=True)
    if not args.live:
        return
    values = ninfer.read_env()
    directory = ROOT / "out" / f"context-audit-{time.time_ns()}"
    directory.mkdir(parents=True)
    config = {
        "model": {"provider": "custom:ninfer", "default": values["NINFER_MODEL_ID"],
                  "context_length": int(values["NINFER_CONTEXT_LENGTH"])},
        "providers": {"ninfer": {"api": ninfer.ninfer_endpoint(values),
                                  "key_env": "NINFER_API_KEY", "transport": "chat_completions"}},
        **hermes_context_settings(values),
        "telemetry": {"shared_metrics": {"enabled": False}},
    }
    (directory / "config.yaml").write_text(json.dumps(config), encoding="utf-8")
    os.environ.update(HERMES_HOME=str(directory), NINFER_API_KEY=values["NINFER_API_KEY"])
    for key in ("HERMES_PROFILE", "HERMES_CONFIG", "HERMES_CONFIG_PATH", "HERMES_ENV", "HERMES_ENV_PATH"):
        os.environ.pop(key, None)
    from agent.context_compressor import ContextCompressor

    compressor = ContextCompressor(
        model=values["NINFER_MODEL_ID"], provider="custom:ninfer",
        base_url=ninfer.ninfer_endpoint(values), api_key=values["NINFER_API_KEY"],
        api_mode="chat_completions", config_context_length=int(values["NINFER_CONTEXT_LENGTH"]),
        threshold_percent=0.5, threshold_tokens_cap=int(values["HERMES_COMPRESSION_THRESHOLD_TOKENS"]),
        protect_first_n=0, protect_last_n=4, tail_mode="lean", abort_on_summary_failure=True,
    )
    client = Client(ninfer.ninfer_endpoint(values), values["NINFER_API_KEY"], values["NINFER_MODEL_ID"])
    messages = [
        {"role": "system", "content": "Follow the user's checkpoint instructions. Be concise."},
        {"role": "user", "content": "The checkpoint identifier is ORCHID-731. Keep it in every handoff."},
        {"role": "assistant", "content": "I will preserve the checkpoint and next action."},
    ]
    evidence = []
    for cycle in range(args.cycles):
        for step in range(min(60, max(8, int(values["NINFER_CONTEXT_LENGTH"]) // 4000))):
            messages.extend([
                {"role": "user", "content": f"Review phase {cycle}, step {step}."},
                {"role": "assistant", "content": (
                    f"Step {step}: checked src/cache.py; tests passed; preserve the checkpoint identifier; "
                    "next validate restart recovery.\n") * 100},
            ])
        messages.append({"role": "user", "content": "Keep the checkpoint identifier and next action in the handoff. Reply OK."})
        before = client.complete(messages, max_tokens=16, thinking=False)
        tokens = before.metrics["input_tokens"]
        assert tokens >= compressor.threshold_tokens, (tokens, compressor.threshold_tokens)
        started = time.monotonic()
        compacted = compressor.compress(messages, current_tokens=tokens)
        assert len(compacted) < len(messages), getattr(compressor, "_last_compression_telemetry", {})
        assert not getattr(compressor, "_last_summary_error", None), compressor._last_summary_error
        after = client.complete(compacted, max_tokens=16, thinking=False)
        assert after.metrics["input_tokens"] < tokens / 2, after.metrics
        assert "ORCHID-731" in json.dumps(compacted)
        recall = client.complete(compacted + [after.message, {
            "role": "user", "content": "What is the checkpoint identifier? Reply with the identifier only."
        }], max_tokens=32, thinking=False)
        assert "ORCHID-731" in recall.message.get("content", ""), recall.message
        item = {"cycle": cycle + 1, "before_tokens": tokens,
                "after_tokens": after.metrics["input_tokens"],
                "seconds": round(time.monotonic() - started, 2),
                "compression": getattr(compressor, "_last_compression_telemetry", {})}
        evidence.append(item)
        (directory / "results.json").write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
        print(json.dumps({k: v for k, v in item.items() if k != "compression"}), flush=True)
        messages = compacted + [after.message]
    print(f"PASS: {len(evidence)} real compression cycles; evidence: {directory / 'results.json'}")


if __name__ == "__main__":
    main()
