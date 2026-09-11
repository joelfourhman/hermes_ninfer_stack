from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from stack.execution import execution_argv, terminal_settings
from stack.jobs import init_job, load_state, manage_job, record_failure, resume_job
from stack.storage import atomic_json, checked_json, exclusive
from stack.supervisor import DisabledSupervisor, packet_for


class JobTests(unittest.TestCase):
    def init(self, root):
        subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
        (root / "README.md").write_text("fixture")
        subprocess.run(
            ["git", "-C", str(root), "add", "README.md"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit",
                "-m",
                "fixture",
            ],
            check=True,
            capture_output=True,
        )
        args = argparse.Namespace(
            repo=str(root),
            state=None,
            goal="Complete fixture",
            test_command='["git","status","--porcelain"]',
            backend="local",
            image=None,
            network="none",
            host=None,
            remote_workspace=None,
            max_retries=3,
            max_epochs_total=5,
        )
        init_job(args)
        return root / "PROJECT_STATE.json"

    def test_checkpoint_corruption_and_explicit_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.init(Path(directory))
            original = load_state(path)
            snapshot = next((Path(original["job_dir"]) / "checkpoints").glob("*.json"))
            path.write_text("{broken")
            with self.assertRaisesRegex(ValueError, "corrupt"):
                load_state(path)
            manage_job(
                argparse.Namespace(
                    state=str(path), action="recover", snapshot=str(snapshot)
                )
            )
            self.assertEqual(load_state(path)["goal"], "Complete fixture")
            self.assertTrue(list(path.parent.glob("PROJECT_STATE.json.corrupt-*")))

    def test_resume_persists_session_and_requires_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self.init(root)

            def run(*args, **kwargs):
                args[-1](987654321)
                (root / "EPOCH_REPORT.json").write_text(
                    json.dumps(
                        {
                            "goal_complete": True,
                            "current_milestone": "Done",
                            "completed_tasks": ["fixture"],
                            "important_findings": ["verified"],
                            "next_actions": [],
                            "current_blocker": None,
                        }
                    )
                )
                return {
                    "returncode": 0,
                    "timed_out": False,
                    "session_id": "hermes-session-1",
                }

            args = argparse.Namespace(
                state=str(path), epochs=1, max_turns=2, timeout=30
            )
            with (
                patch("stack.jobs.prepare_home", return_value=(["hermes"], {})),
                patch("stack.jobs.run_epoch", side_effect=run),
            ):
                resume_job(args)
            state = load_state(path)
            self.assertEqual(state["status"], "complete")
            self.assertEqual(state["session_id"], "hermes-session-1")
            self.assertEqual(state["agent_epoch"], 1)
            self.assertEqual(state["tests_status"]["returncode"], 0)

    def test_repeated_failure_forces_replan(self):
        state = {
            "approach": "first",
            "failed_attempts": [],
            "agent_epoch": 1,
            "max_retries": 3,
        }
        for _ in range(3):
            record_failure(state, 1, "same failing assertion")
        self.assertEqual(state["status"], "needs_replan")
        self.assertIn("re-plan", state["next_actions"][0])

    def test_exclusive_lock_and_checksum_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.json"
            atomic_json(path, {"a": 1}, checksum=True)
            self.assertEqual(checked_json(path), {"a": 1})
            path.write_text(path.read_text().replace('"a": 1', '"a": 2'))
            with self.assertRaises(ValueError):
                checked_json(path)
            lock = Path(d) / "lock"
            with exclusive(lock):
                with self.assertRaises(ValueError):
                    with exclusive(lock):
                        pass

    def test_backend_mapping_network_and_remote_quoting(self):
        workspace = Path("/fixture")
        config = {
            "mode": "container",
            "image": "hermes-agent-worker:local",
            "network": "none",
        }
        args = execution_argv(config, workspace, ["python", "-m", "unittest"])
        self.assertEqual(args[args.index("--network") + 1], "none")
        self.assertNotIn("docker.sock", " ".join(args))
        settings = terminal_settings(config, workspace)
        self.assertFalse(settings["docker_network"])
        self.assertEqual(len(settings["docker_volumes"]), 1)
        remote = execution_argv(
            {"mode": "remote", "host": "worker", "workspace": "/work/a b"},
            workspace,
            ["echo", "literal; value"],
        )
        self.assertIn("'/work/a b'", remote[-1])
        self.assertIn("'literal; value'", remote[-1])
        with self.assertRaises(ValueError):
            execution_argv(
                {"mode": "remote", "host": "-oBad", "workspace": "/work"},
                workspace,
                ["true"],
            )

    def test_supervisor_disabled_and_compact_packet(self):
        with self.assertRaises(ValueError):
            DisabledSupervisor().review({})
        state = {
            key: []
            for key in (
                "goal",
                "current_milestone",
                "completed_tasks",
                "important_findings",
                "current_blocker",
                "next_actions",
                "failed_attempts",
            )
        }
        state["secret"] = "not-for-review"
        packet = packet_for(state, "stuck")
        self.assertNotIn("secret", packet)
        with self.assertRaises(ValueError):
            packet_for(state, "every-turn")
