from __future__ import annotations

import argparse
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch

from stack.api import Client, Completion
from stack.bench_agent import run_workload
from stack.config import DEPLOYMENT_PRESETS, MODEL_PROFILES, RUNTIME_PROFILES
from stack.commands import configure_client, connect, use_preset
from stack.discovery import ServerModel
from stack.metrics import parse_native_logs
from stack.testing import fake_client
from stack.workloads import Workspace, validate_fixture_code


class BenchmarkTests(unittest.TestCase):
    def test_connect_refreshes_before_launch_without_changing_active_profile(self):
        helper = Mock()
        helper.native_hermes_command.return_value = (["hermes"], {"HERMES_HOME": "home"})
        helper.hermes_profile_name.return_value = "ninfer-coding"
        args = argparse.Namespace(preset="coding", endpoint="http://127.0.0.1:8080/v1")
        with patch("stack.commands._helper", return_value=helper), patch("stack.commands.configure_client") as refresh:
            connect(args)
            refresh.assert_called_once_with(args)
            self.assertTrue(args.no_activate)
            helper.run.assert_called_once_with(
                ["hermes", "-p", "ninfer-coding", "chat"], env={"HERMES_HOME": "home"}, cwd=Path.cwd()
            )
            helper.run.reset_mock()
            refresh.side_effect = ValueError("missing server context")
            with self.assertRaises(ValueError):
                connect(args)
            helper.run.assert_not_called()

    def test_complete_preset_uses_one_service_restart(self):
        class Helper:
            ENV_FILE = Path("configured")
            StackError = ValueError

            def __init__(self):
                self.selected = None
                self.starts = []

            model_profile = staticmethod(lambda key: MODEL_PROFILES[key])
            runtime_profile = staticmethod(lambda key: RUNTIME_PROFILES[key])
            check_setup_prerequisites = staticmethod(lambda model: "0")
            prepare_model = staticmethod(lambda args: True)
            native_hermes_command = staticmethod(lambda: None)
            validate_env = staticmethod(lambda: None)

            def read_env(self):
                return self.selected or {
                    "NINFER_MODEL_PROFILE": "stock",
                    "NINFER_SPEC_BACKEND": "mtp",
                    "NINFER_DRAFT_TOKENS": "3",
                }

            def replace_env_values(self, values):
                self.selected = dict(self.read_env(), **values)
                return None

            def start_ninfer(self, values):
                self.starts.append(values)

        helper = Helper()
        with (
            patch("stack.commands._helper", return_value=helper),
            patch.object(Path, "exists", return_value=True),
        ):
            use_preset(argparse.Namespace(preset="coding", yes=True))
        self.assertEqual(len(helper.starts), 1)
        self.assertEqual(helper.starts[0]["NINFER_MODEL_PROFILE"], "stock-dflash2")
        self.assertEqual(helper.starts[0]["NINFER_RUNTIME_PROFILE"], "coding")
        self.assertEqual(helper.starts[0]["NINFER_SPEC_BACKEND"], "dflash2")
        self.assertEqual(helper.starts[0]["NINFER_DRAFT_TOKENS"], "7")

    def test_complete_preset_restores_previous_environment_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env_file = root / ".env"
            env_file.write_text("selected")
            backup = root / ".env.backup"
            backup.write_text("previous")
            previous = {
                "NINFER_MODEL_PROFILE": "uncensored",
                "NINFER_RUNTIME_PROFILE": "max-context",
                "NINFER_SPEC_BACKEND": "mtp",
                "NINFER_DRAFT_TOKENS": "3",
            }
            selected = {
                "NINFER_MODEL_PROFILE": "stock-dflash2",
                "NINFER_RUNTIME_PROFILE": "coding",
                "NINFER_SPEC_BACKEND": "dflash2",
                "NINFER_DRAFT_TOKENS": "7",
            }
            helper = Mock()
            helper.ENV_FILE = env_file
            helper.StackError = ValueError
            helper.model_profile.side_effect = lambda key: MODEL_PROFILES[key]
            helper.runtime_profile.side_effect = lambda key: RUNTIME_PROFILES[key]
            helper.prepare_model.return_value = True
            helper.read_env.side_effect = [previous, selected]
            helper.native_hermes_command.return_value = None
            helper.replace_env_values.return_value = backup
            helper.start_ninfer.side_effect = [ValueError("failed startup"), None]
            with patch("stack.commands._helper", return_value=helper):
                with self.assertRaisesRegex(ValueError, "previous model"):
                    use_preset(argparse.Namespace(preset="coding", yes=True))
            helper.atomic_write.assert_called_once_with(env_file, "previous")
            self.assertEqual(helper.start_ninfer.call_count, 2)
            self.assertEqual(helper.start_ninfer.call_args_list[-1].args[0], previous)

    def test_complete_preset_activates_matching_native_hermes_profile(self):
        helper = Mock()
        helper.ENV_FILE = Mock()
        helper.ENV_FILE.exists.return_value = True
        helper.StackError = ValueError
        helper.model_profile.side_effect = lambda key: MODEL_PROFILES[key]
        helper.runtime_profile.side_effect = lambda key: RUNTIME_PROFILES[key]
        helper.prepare_model.return_value = True
        helper.read_env.return_value = {
            "NINFER_MODEL_PROFILE": "stock-dflash2",
            "NINFER_RUNTIME_PROFILE": "autonomous",
            "NINFER_SPEC_BACKEND": "dflash2",
            "NINFER_DRAFT_TOKENS": "7",
        }
        resolved = (["hermes"], {"HERMES_HOME": "hermes-home"})
        helper.native_hermes_command.return_value = resolved
        helper.configure_hermes_preset_profile.return_value = "ninfer-autonomous"

        with patch("stack.commands._helper", return_value=helper):
            use_preset(argparse.Namespace(preset="autonomous", yes=True))

        helper.configure_hermes_preset_profile.assert_called_once_with(
            *resolved,
            "autonomous",
            helper.read_env.return_value,
        )

    def test_lan_client_configures_matching_profile_with_environment_key(self):
        helper = Mock()
        helper.require_ninfer_endpoint.return_value = ServerModel("qwen3.8-27b-uncensored-ctx65536", 65536)
        helper.normalize_ninfer_client_endpoint.return_value = "http://192.168.1.20:8080/v1"
        helper.native_hermes_command.return_value = (
            ["hermes"],
            {"HERMES_HOME": "hermes-home"},
        )
        helper.model_profile.side_effect = lambda key: MODEL_PROFILES[key]
        helper.runtime_profile.side_effect = lambda key: RUNTIME_PROFILES[key]
        helper.configure_hermes_preset_profile.return_value = "ninfer-coding"
        args = argparse.Namespace(
            preset="coding",
            endpoint="http://192.168.1.20:8080/v1",
            key_env="TEST_NINFER_KEY",
            no_activate=False,
        )

        with (
            patch("stack.commands._helper", return_value=helper),
            patch.dict("os.environ", {"TEST_NINFER_KEY": "secret-key"}),
        ):
            configure_client(args)

        helper.require_ninfer_endpoint.assert_called_once_with(
            "http://192.168.1.20:8080/v1",
            "secret-key",
        )
        call = helper.configure_hermes_preset_profile.call_args
        self.assertEqual(call.args[2], "coding")
        self.assertEqual(call.kwargs["endpoint"], "http://192.168.1.20:8080/v1")
        self.assertEqual(call.kwargs["api_key"], "secret-key")
        self.assertTrue(call.kwargs["activate"])
        self.assertEqual(call.args[3]["NINFER_CONTEXT_LENGTH"], "65536")
        self.assertEqual(call.args[3]["HERMES_COMPRESSION_THRESHOLD_TOKENS"], "32768")
        self.assertEqual(call.args[3]["NINFER_MODEL_ID"], "qwen3.8-27b-uncensored-ctx65536")
        self.assertNotIn("NINFER_SPEC_BACKEND", call.args[3])

    def test_lan_client_configures_all_profiles_and_activates_selected_one(self):
        helper = Mock()
        helper.require_ninfer_endpoint.return_value = ServerModel("served-model", 65536)
        helper.normalize_ninfer_client_endpoint.return_value = "http://192.168.1.20:8080/v1"
        helper.native_hermes_command.return_value = (
            ["hermes"],
            {"HERMES_HOME": "hermes-home"},
        )
        helper.model_profile.side_effect = lambda key: MODEL_PROFILES[key]
        helper.runtime_profile.side_effect = lambda key: RUNTIME_PROFILES[key]
        helper.configure_hermes_preset_profile.side_effect = (
            lambda _command, _environment, preset, _values, **_kwargs: f"ninfer-{preset}"
        )
        args = argparse.Namespace(
            preset="all",
            endpoint="http://192.168.1.20:8080/v1",
            key_env="TEST_NINFER_KEY",
            no_activate=False,
            activate="autonomous",
        )

        with (
            patch("stack.commands._helper", return_value=helper),
            patch.dict("os.environ", {"TEST_NINFER_KEY": "secret-key"}),
        ):
            configure_client(args)

        calls = helper.configure_hermes_preset_profile.call_args_list
        self.assertEqual(len(calls), 7)
        self.assertEqual([call.args[2] for call in calls], list(DEPLOYMENT_PRESETS))
        self.assertEqual(
            [call.args[2] for call in calls if call.kwargs["activate"]],
            ["autonomous"],
        )

    def test_lan_client_no_activate_leaves_default_profile_selected(self):
        helper = Mock()
        helper.require_ninfer_endpoint.return_value = ServerModel("served-model", 131072)
        helper.normalize_ninfer_client_endpoint.return_value = "http://192.168.1.20:8080/v1"
        helper.native_hermes_command.return_value = (
            ["hermes"],
            {"HERMES_HOME": "hermes-home"},
        )
        helper.model_profile.side_effect = lambda key: MODEL_PROFILES[key]
        helper.runtime_profile.side_effect = lambda key: RUNTIME_PROFILES[key]
        helper.configure_hermes_preset_profile.return_value = "ninfer-autonomous"
        args = argparse.Namespace(
            preset="autonomous",
            endpoint="http://192.168.1.20:8080/v1",
            key_env="TEST_NINFER_KEY",
            no_activate=True,
        )

        with (
            patch("stack.commands._helper", return_value=helper),
            patch.dict("os.environ", {"TEST_NINFER_KEY": "secret-key"}),
        ):
            configure_client(args)

        call = helper.configure_hermes_preset_profile.call_args
        self.assertFalse(call.kwargs["activate"])

    def test_compression_failure_retains_completed_request_evidence(self):
        class FailingSummary:
            calls = 0

            def complete(self, *args, **kwargs):
                self.calls += 1
                if self.calls > 1:
                    raise ValueError("Summary rejected")
                return Completion(
                    {"role": "assistant", "content": "A finding"},
                    {"input_tokens": 100, "request_seconds_client": 0.1},
                    "stop",
                )

        with tempfile.TemporaryDirectory() as d:
            result = run_workload(
                FailingSummary(), Workspace(Path(d)), "long-session", compression_tokens=50
            )
        self.assertFalse(result["success"])
        self.assertEqual(len(result["requests"]), 1)
        self.assertEqual(result["failures"][0]["phase"], "compression")

    def test_coding_fixture_requires_two_real_edit_test_cycles(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))
            result = run_workload(fake_client(), workspace, "coding")
            self.assertTrue(result["success"])
            self.assertEqual(
                [event["failed"] for event in result["tools"] if event["tool"] == "run_tests"],
                [True, False],
            )
            self.assertEqual(len(result["requests"]), 8)

    def test_tool_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))
            self.assertIn("error", workspace.execute("read_file", {"path": "../secret"}))
            self.assertIn(
                "error",
                workspace.execute("write_file", {"path": "test_ledger.py", "content": "pass"}),
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
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                received.append(payload)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                events = [
                    {"choices": [{"delta": {"role": "assistant"}}]},
                    {"choices": [{"delta": {"reasoning_content": "Preserved reasoning"}}]},
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
                                            "function": {"arguments": 'th":"README.md"}'},
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
