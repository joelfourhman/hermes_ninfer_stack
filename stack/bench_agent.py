"""Measure complete multi-turn agent workflows, not just decode speed."""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import statistics
import time
import uuid
from pathlib import Path

from stack.api import Client
from stack.metrics import Sampler, parse_native_logs, runtime_metadata
from stack.workloads import CODING_PROMPT, SYSTEM, TOOLS, WORKLOAD_VERSION, Workspace


def run_workload(
    client: Client,
    workspace: Workspace,
    workload: str,
    *,
    max_turns: int = 24,
    max_tokens: int = 1024,
    session_turns: int = 12,
    thinking: bool = False,
    compression_tokens: int = 90000,
) -> dict:
    start = time.perf_counter()
    messages = [{"role": "system", "content": SYSTEM}]
    if workload == "coding":
        prompt = CODING_PROMPT
    elif workload == "research":
        prompt = "Read all four source-0.txt through source-3.txt files using tools. Compare their evidence and synthesize remediation. Include all four FIXTURE-N boundary tokens in your final answer. These are fictional benchmark data."
    else:
        prompt = "We will inspect a growing fictional repository in several turns. Read source-0.txt now and retain its key finding."
    messages.append({"role": "user", "content": prompt})
    requests = []
    failures = []
    compressions = []
    continuations = 0
    answer = ""
    finished = False
    for turn in range(max_turns):
        if (
            requests
            and (requests[-1].get("input_tokens") or 0) > compression_tokens
            and workload == "long-session"
        ):
            summary = client.complete(
                messages
                + [
                    {
                        "role": "user",
                        "content": "Summarize the essential findings for continuation. No tools.",
                    }
                ],
                max_tokens=512,
            )
            requests.append(dict(summary.metrics, kind="compression"))
            compressions.append(
                {"turn": turn, "input_tokens": summary.metrics["input_tokens"]}
            )
            messages = [
                messages[0],
                {
                    "role": "user",
                    "content": "Retained session findings: "
                    + (summary.message.get("content") or ""),
                },
            ]
        try:
            response = client.complete(
                messages, tools=TOOLS, max_tokens=max_tokens, thinking=thinking
            )
        except Exception as exc:
            # Persist failure type, never headers or credential-bearing exception text.
            failures.append({"turn": turn, "type": type(exc).__name__})
            break
        requests.append(dict(response.metrics, turn=turn, kind="agent"))
        messages.append(response.message)
        calls = response.message.get("tool_calls") or []
        if calls:
            for call in calls:
                try:
                    arguments = json.loads(call["function"]["arguments"])
                    if not isinstance(arguments, dict):
                        raise ValueError("Tool arguments must be an object")
                    result = workspace.execute(call["function"]["name"], arguments)
                except (ValueError, KeyError, TypeError):
                    result = json.dumps({"error": "Invalid tool arguments"})
                    failures.append({"turn": turn, "type": "invalid_tool_arguments"})
                messages.append(
                    {"role": "tool", "tool_call_id": call["id"], "content": result}
                )
            continue
        answer = response.message.get("content") or ""
        if response.finish_reason == "length":
            failures.append({"turn": turn, "type": "output_limit"})
            break
        if workload == "long-session" and continuations < session_turns - 1:
            continuations += 1
            # Append a different source shard after every turn, preserving old messages byte-for-byte.
            source = (workspace.root / f"source-{continuations % 4}.txt").read_text(
                encoding="utf-8"
            )
            messages.append(
                {
                    "role": "user",
                    "content": f"Epoch {continuations}: inspect this new evidence and give one concise finding.\n{source}",
                }
            )
            continue
        finished = True
        break
    validation = None
    if workload == "coding":
        validation = workspace.test()
        success = (
            finished
            and validation["passed"]
            and sum(e["tool"] == "write_file" for e in workspace.events) >= 2
            and sum(e["tool"] == "run_tests" for e in workspace.events) >= 2
        )
    elif workload == "research":
        success = (
            finished
            and all(f"FIXTURE-{i}" in answer for i in range(4))
            and sum(e["tool"] == "read_file" for e in workspace.events) >= 4
        )
    else:
        success = finished and continuations == session_turns - 1
    elapsed = time.perf_counter() - start
    return {
        "workload": workload,
        "driver": "bounded-agent",
        "success": success,
        "wall_seconds": elapsed,
        "model_request_seconds": sum(r["request_seconds_client"] for r in requests),
        "tool_seconds": sum(e["duration_seconds"] for e in workspace.events),
        "requests": requests,
        "tools": workspace.events,
        "compression_events": compressions,
        "failures": failures,
        "retries": 0,
        "validation": validation,
        "answer": answer,
        "system_tools_sha256": hashlib.sha256(
            json.dumps([SYSTEM, TOOLS], separators=(",", ":")).encode()
        ).hexdigest(),
        "notes": "Model-driven fixture with real reads/edits/tests; excludes Hermes Desktop orchestration. Success requires acceptance tests and two edit/test cycles.",
    }


def summary(result: dict) -> str:
    runs = result["runs"]
    successful = [r["wall_seconds"] for r in runs if r["success"]]
    return (
        "# Agent benchmark\n\n"
        f"Workload: {result['workload']}; driver: {result['driver']}; fixture version: {WORKLOAD_VERSION}.\n\n"
        f"Successful workloads: {len(successful)}/{len(runs)}. Failures remain in the denominator.\n\n"
        f"Median successful completion: {statistics.median(successful):.3f} seconds.\n"
        if successful
        else f"# Agent benchmark\n\nNo successful workloads ({len(runs)} attempts). Do not rank this configuration by speed.\n"
    )


def benchmark(args) -> None:
    from stack.commands import _helper

    helper = _helper()
    if (
        not 1 <= args.runs <= 20
        or not 1 <= args.max_turns <= 200
        or not 32 <= args.max_tokens <= 8192
        or not 1 <= args.context_kib <= 16384
        or not 2 <= args.session_turns <= 100
    ):
        raise ValueError(
            "Benchmark limits: runs 1..20, turns 1..200, output 32..8192, context KiB 1..16384, session turns 2..100"
        )
    if args.smoke:
        from stack.testing import fake_client

        client = fake_client()
        metadata = {"smoke": True, "timing_valid": False}
        values = {"HERMES_COMPRESSION_THRESHOLD_TOKENS": "90000"}
    else:
        metadata = runtime_metadata(helper, baseline=args.baseline)
        values = helper.read_env()
        client = Client(
            helper.ninfer_endpoint(values),
            values["NINFER_API_KEY"],
            values["NINFER_MODEL_ID"],
            args.timeout,
        )
    result_dir = (
        Path(args.output).resolve()
        if args.output
        else helper.ROOT
        / "benchmarks"
        / ("agent-" + time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6])
    )
    result_dir.mkdir(parents=True, exist_ok=False)
    result = {
        "schema_version": 1,
        "fixture_version": WORKLOAD_VERSION,
        "workload": args.workload,
        "driver": "mock" if args.smoke else args.driver,
        "parameters": {
            k: v for k, v in vars(args).items() if k not in {"func", "command"}
        },
        "environment": metadata,
        "runs": [],
        "resource_samples": [],
        "native_records": [],
        "started_at_unix": time.time(),
        "metric_scope": "Model request time includes transport/queueing; parallel sums overlap. Native interval cache counters are not attributed to a single request.",
    }
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def one(index, lane=0):
        workspace = Workspace(
            result_dir / f"run-{index}-lane-{lane}", context_kib=args.context_kib
        )
        kind = "long-session" if args.workload == "parallel" else args.workload
        if args.driver == "hermes" and not args.smoke:
            from stack.hermes_runner import benchmark_hermes

            return benchmark_hermes(helper, workspace, kind, args)
        return run_workload(
            client,
            workspace,
            kind,
            max_turns=args.max_turns,
            max_tokens=args.max_tokens,
            session_turns=args.session_turns,
            thinking=args.thinking,
            compression_tokens=int(values["HERMES_COMPRESSION_THRESHOLD_TOKENS"]),
        )

    sampler = Sampler(
        None if args.smoke else helper.nvidia_smi_executable(),
        values.get("NINFER_GPU_DEVICE", "0"),
    )
    try:
        with sampler:
            for index in range(args.runs):
                start = time.perf_counter()
                if args.workload == "parallel":
                    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                        lanes = list(pool.map(lambda lane: one(index, lane), range(2)))
                    row = {
                        "workload": "parallel",
                        "success": all(r["success"] for r in lanes),
                        "wall_seconds": time.perf_counter() - start,
                        "lanes": lanes,
                    }
                else:
                    row = one(index)
                result["runs"].append(row)
                (result_dir / "results.json").write_text(
                    json.dumps(result, indent=2) + "\n", encoding="utf-8"
                )
                print(
                    f"Run {index + 1}/{args.runs}: {'PASS' if row['success'] else 'FAIL'}, {row['wall_seconds']:.2f}s"
                )
    finally:
        result["resource_samples"] = sampler.samples
        if not args.smoke:
            logs = helper.compose(
                "logs",
                "--no-color",
                "--since",
                started,
                "ninfer",
                capture=True,
                check=False,
            )
            result["native_records"] = parse_native_logs(logs.stdout + logs.stderr)
        (result_dir / "results.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
        (result_dir / "summary.md").write_text(summary(result), encoding="utf-8")
    print(f"Results: {result_dir}")
    if not all(row["success"] for row in result["runs"]):
        raise ValueError("One or more workloads failed acceptance; results were saved")


def compare(args) -> None:
    results = [
        json.loads(Path(path).read_text(encoding="utf-8")) for path in args.results
    ]
    first = results[0]
    for result in results:
        if result["driver"] == "mock":
            raise ValueError(
                "Mock smoke measurements cannot be compared for performance"
            )
        if any(
            result.get(key) != first.get(key)
            for key in ("fixture_version", "workload", "driver")
        ):
            raise ValueError(
                "Comparison requires identical fixture version, workload and driver"
            )
        for key in (
            "max_turns",
            "max_tokens",
            "context_kib",
            "session_turns",
            "thinking",
        ):
            if result["parameters"].get(key) != first["parameters"].get(key):
                raise ValueError(f"Comparison workload parameter differs: {key}")
    print("| Profile / speculation | Success | Median successful wall seconds |")
    print("|---|---:|---:|")
    for result in results:
        config = result["environment"]["config"]
        passed = [r["wall_seconds"] for r in result["runs"] if r["success"]]
        median = f"{statistics.median(passed):.3f}" if passed else "unranked"
        print(
            f"| {config['NINFER_RUNTIME_PROFILE']} / {config.get('NINFER_SPEC_BACKEND', 'mtp')}-{config.get('NINFER_DRAFT_TOKENS', '3')} | {len(passed)}/{len(result['runs'])} | {median} |"
        )
