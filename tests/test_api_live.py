"""Optional real-GPU protocol checks; normal Windows/Linux CI skips these."""

import os
import unittest

import ninfer
from stack.api import Client
from stack.workloads import TOOLS


@unittest.skipUnless(
    os.environ.get("NINFER_LIVE_TESTS") == "1", "requires running authenticated NInfer GPU service"
)
class LiveApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        values = ninfer.read_env()
        cls.client = Client(
            ninfer.ninfer_endpoint(values), values["NINFER_API_KEY"], values["NINFER_MODEL_ID"]
        )

    def test_model_and_context_discovery_local_and_lan(self):
        from stack.discovery import discover
        values = ninfer.read_env()
        endpoints = [ninfer.ninfer_endpoint(values)]
        if values.get("NINFER_ACCESS_MODE") == "lan":
            address = ninfer.lan_endpoint(values)
            self.assertIsNotNone(address)
            endpoints.append(address)
        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                model = discover(endpoint, values["NINFER_API_KEY"])
                self.assertEqual(model.id, values["NINFER_MODEL_ID"])
                self.assertEqual(model.context_length, int(values["NINFER_CONTEXT_LENGTH"]))

    def test_stale_model_is_rejected(self):
        from urllib.error import HTTPError
        with self.assertRaises(HTTPError) as caught:
            self.client.json("/chat/completions", {
                "model": "stale-profile-model",
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 8,
            })
        self.assertEqual(caught.exception.code, 404)
        caught.exception.close()

    def test_aggregate_chat(self):
        result = self.client.json(
            "/chat/completions",
            {
                "model": self.client.model,
                "messages": [{"role": "user", "content": "Reply only READY."}],
                "max_tokens": 32,
                "enable_thinking": False,
                "temperature": 0,
            },
        )
        self.assertTrue(result["choices"][0]["message"]["content"])
        self.assertIn("timings", result)

    def test_stream_and_exact_prefix_reuse(self):
        messages = [
            {
                "role": "system",
                "content": "Reference passage: "
                + ("Stable project context with exact prefix reuse. " * 200),
            },
            {"role": "user", "content": "Reply only READY."},
        ]
        first = self.client.complete(messages, max_tokens=32)
        second = self.client.complete(messages, max_tokens=32)
        self.assertTrue(first.message["content"])
        self.assertGreater(second.metrics["cached_prefix_tokens"], 0)
        self.assertEqual(
            second.metrics["input_tokens"],
            second.metrics["cached_prefix_tokens"] + second.metrics["fresh_prefill_tokens"],
        )

    def test_tool_call_roundtrip(self):
        messages = [
            {
                "role": "user",
                "content": "Call read_file with path README.md. Do not guess file contents.",
            }
        ]
        first = self.client.complete(messages, tools=TOOLS, max_tokens=256)
        calls = first.message.get("tool_calls") or []
        self.assertTrue(calls, "Model did not produce a structured tool call")
        messages.append(first.message)
        for call in calls:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": "The fixture project is called ALPHA.",
                }
            )
        messages.append(
            {
                "role": "user",
                "content": "Now state the project name from the tool result without another tool call.",
            }
        )
        final = self.client.complete(messages, max_tokens=128)
        self.assertIn("ALPHA", final.message["content"])

    def test_reasoning_preserved_in_followup(self):
        messages = [{"role": "user", "content": "Think briefly: what is 17 times 19?"}]
        first = self.client.complete(messages, max_tokens=512, thinking=True)
        self.assertTrue(first.message.get("reasoning_content"))
        messages.extend(
            [first.message, {"role": "user", "content": "Confirm your arithmetic in one sentence."}]
        )
        final = self.client.complete(messages, max_tokens=256)
        self.assertTrue(final.message.get("content"))
