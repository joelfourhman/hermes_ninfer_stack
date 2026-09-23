from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest

from stack.config import public_model_id
from stack.discovery import discover, parse_model


class DiscoveryTests(unittest.TestCase):
    def test_authenticated_discovery_reports_actual_context_and_updates_after_switch(self):
        state = {"id": "qwen3.8-27b-stock-ctx131072", "max_model_len": 131072}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.headers.get("Authorization") != "Bearer test-key":
                    self.send_error(401)
                    return
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"data": [state]}).encode())

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            endpoint = f"http://127.0.0.1:{server.server_port}/v1"
            first = discover(endpoint, "test-key")
            self.assertEqual(first.context_length, 131072)
            state.update(id="qwen3.8-27b-uncensored-ctx65536", max_model_len=65536)
            latest = discover(endpoint, "test-key")
            self.assertEqual(latest.context_length, 65536)
            values = latest.client_values({"HERMES_COMPRESSION_THRESHOLD_TOKENS": "100000"})
            self.assertEqual(values["HERMES_COMPRESSION_THRESHOLD_TOKENS"], "32768")
            self.assertEqual(values["NINFER_MODEL_ID"], state["id"])
            with self.assertRaisesRegex(ValueError, "refresh"):
                discover(endpoint, "test-key", first.id)
            from urllib.error import HTTPError
            with self.assertRaises(HTTPError) as caught:
                discover(endpoint, "wrong-key")
            caught.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_missing_ambiguous_and_malformed_metadata_never_guess(self):
        for payload in [None, [], {}, {"data": []}, {"data": [{}, {}]}]:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                parse_model(payload)
        for value in [None, True, "65536", 0, -1, 1000000]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_model({"data": [{"id": "model", "max_model_len": value}]})

    def test_model_and_context_changes_invalidate_previous_identity(self):
        self.assertNotEqual(public_model_id("stock", 65536), public_model_id("uncensored", 65536))
        self.assertNotEqual(public_model_id("stock", 65536), public_model_id("stock", 131072))
