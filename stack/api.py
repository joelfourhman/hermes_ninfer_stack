"""Dependency-free OpenAI client with native NInfer timing and tool preservation."""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class Completion:
    message: dict[str, Any]
    metrics: dict[str, Any]
    finish_reason: str | None


class Client:
    def __init__(self, endpoint: str, token: str, model: str, timeout: float = 600):
        self.endpoint = endpoint.rstrip("/")
        self.token, self.model, self.timeout = token, model, timeout

    def post(self, path: str, payload: dict):
        request = urllib.request.Request(
            self.endpoint + path,
            data=json.dumps(payload, separators=(",", ":")).encode(),
            headers={
                "Authorization": "Bearer " + self.token,
                "Content-Type": "application/json",
            },
        )
        return urllib.request.urlopen(request, timeout=self.timeout)

    def json(self, path: str, payload: dict) -> dict:
        with self.post(path, payload) as response:
            return json.load(response)

    def complete(
        self,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
        max_tokens: int = 1024,
        seed: int = 1,
        thinking: bool = False,
    ) -> Completion:
        payload = dict(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0,
            seed=seed,
            enable_thinking=thinking,
            stream=True,
            stream_options={"include_usage": True},
        )
        if tools:
            payload["tools"] = tools
        start = time.perf_counter()
        first = last = None
        usage, timings, calls = {}, {}, {}
        content, reasoning = [], []
        finish = request_id = None
        done = False
        with self.post("/chat/completions", payload) as response:
            request_id = response.headers.get("x-request-id")
            for raw in response:
                line = raw.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    done = True
                    break
                event = json.loads(data)
                if event.get("error"):
                    raise ValueError("Inference stream reported an error")
                usage = event.get("usage") or usage
                timings = event.get("timings") or timings
                for choice in event.get("choices") or []:
                    delta = choice.get("delta") or {}
                    visible = (
                        delta.get("content")
                        or delta.get("reasoning_content")
                        or delta.get("tool_calls")
                    )
                    if visible:
                        last = time.perf_counter()
                        if first is None:
                            first = last
                    content.append(delta.get("content") or "")
                    reasoning.append(delta.get("reasoning_content") or "")
                    for part in delta.get("tool_calls") or []:
                        index = part.get("index", 0)
                        call = calls.setdefault(
                            index,
                            {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            },
                        )
                        if part.get("id"):
                            call["id"] = part["id"]
                        function = part.get("function") or {}
                        for key in ("name", "arguments"):
                            call["function"][key] += function.get(key) or ""
                    finish = choice.get("finish_reason") or finish
        elapsed = time.perf_counter() - start
        if not done or finish is None or not usage:
            raise ValueError(
                "Incomplete SSE response: require terminal finish, usage and [DONE]"
            )
        message: dict[str, Any] = {
            "role": "assistant",
            "content": "".join(content) or None,
        }
        if reasoning:
            text = "".join(reasoning)
            if text:
                message["reasoning_content"] = text
        if calls:
            message["tool_calls"] = [calls[key] for key in sorted(calls)]
            if any(not call["id"] for call in calls.values()):
                raise ValueError("Streamed tool call has no ID")
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
        if cached is None:
            cached = timings.get("cache_n")
        prompt = usage.get("prompt_tokens")
        fresh = prompt - cached if prompt is not None and cached is not None else None
        metrics = {
            "request_id": request_id,
            "input_tokens": prompt,
            "generated_tokens": usage.get("completion_tokens"),
            "cached_prefix_tokens": cached,
            "fresh_prefill_tokens": fresh,
            "context_tokens": prompt,
            "ttft_seconds_client": first - start if first is not None else None,
            "request_seconds_client": elapsed,
            "prompt_seconds_native": timings.get("prompt_ms", 0) / 1000
            if "prompt_ms" in timings
            else None,
            "decode_seconds_native": timings.get("predicted_ms", 0) / 1000
            if "predicted_ms" in timings
            else None,
            "prefill_tokens_per_second_native": timings.get("prompt_per_second"),
            "decode_tokens_per_second_native": timings.get("predicted_per_second"),
            "visible_output_seconds_client": last - first if last is not None else None,
            "timings_native": timings,
            "usage_native": usage,
            "metric_notes": "TTFT starts at send and ends at first visible content/reasoning/tool delta; native prompt time includes restore and first token. No chunk-to-token inference.",
        }
        return Completion(message, metrics, finish)
