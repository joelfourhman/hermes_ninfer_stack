from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from stack.api import Client
from stack.bench_agent import run_workload
from stack.metrics import parse_native_logs
from stack.testing import fake_client
from stack.workloads import Workspace, validate_fixture_code


class BenchmarkTests(unittest.TestCase):
    def test_coding_fixture_requires_two_real_edit_test_cycles(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))
            result = run_workload(fake_client(), workspace, "coding")
            self.assertTrue(result["success"])
            self.assertEqual(
                [
                    event["failed"]
                    for event in result["tools"]
                    if event["tool"] == "run_tests"
                ],
                [True, False],
            )
            self.assertEqual(len(result["requests"]), 8)

    def test_tool_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))
            self.assertIn(
                "error", workspace.execute("read_file", {"path": "../secret"})
            )
            self.assertIn(
                "error",
                workspace.execute(
                    "write_file", {"path": "test_ledger.py", "content": "pass"}
                ),
            )
        with self.assertRaises(ValueError):
            validate_fixture_code('import os\nos.remove("file")')

    def test_native_jsonl_ignores_pretty_text_and_partial_lines(self):
        text = 'pretty log\nservice | {"event":"throughput","context_cache":{"occupancy":{}}}\n{"event":'
        self.assertEqual(len(parse_native_logs(text)), 1)

    def test_stream_reasoning_tool_fragments_empty_usage_and_roundtrip(self):
        received = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                payload = json.loads(
                    self.rfile.read(int(self.headers["Content-Length"]))
                )
                received.append(payload)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                events = [
                    {"choices": [{"delta": {"role": "assistant"}}]},
                    {
                        "choices": [
                            {"delta": {"reasoning_content": "Preserved reasoning"}}
                        ]
                    },
                    {
                        "choices": [
                            {
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": 0,
                                            "id": "call_1",
                                            "function": {
                                                "name": "read_file",
                                                "arguments": '{"pa',
                                            },
                                        }
                                    ]
                                }
                            }
                        ]
                    },
                    {
                        "choices": [
                            {
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": 0,
                                            "function": {
                                                "arguments": 'th":"README.md"}'
                                            },
                                        }
                                    ]
                                }
                            }
                        ]
                    },
                    {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
                    {
                        "choices": [],
                        "usage": {
                            "prompt_tokens": 100,
                            "completion_tokens": 10,
                            "prompt_tokens_details": {"cached_tokens": 80},
                        },
                        "timings": {
                            "cache_n": 80,
                            "prompt_n": 20,
                            "prompt_ms": 50,
                            "predicted_ms": 20,
                            "predicted_per_second": 450,
                        },
                    },
                ]
                for event in events:
                    self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode())
                self.wfile.write(b"data: [DONE]\n\n")

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = Client(f"http://127.0.0.1:{server.server_port}/v1", "test", "test")
            first = client.complete([{"role": "user", "content": "Read file"}])
            self.assertEqual(first.metrics["fresh_prefill_tokens"], 20)
            self.assertEqual(first.message["reasoning_content"], "Preserved reasoning")
            self.assertEqual(
                json.loads(first.message["tool_calls"][0]["function"]["arguments"]),
                {"path": "README.md"},
            )
            client.complete(
                [
                    {"role": "user", "content": "Read file"},
                    first.message,
                    {"role": "tool", "tool_call_id": "call_1", "content": "ok"},
                ]
            )
            self.assertEqual(received[1]["messages"][1], first.message)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
