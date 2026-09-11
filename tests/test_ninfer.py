from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from unittest import mock

import ninfer


def sample_values() -> dict[str, str]:
    return {
        "NINFER_API_KEY": "a" * 64,
        "NINFER_ACCESS_MODE": "local",
        "NINFER_BIND_ADDRESS": "127.0.0.1",
        "NINFER_HOST_PORT": "18080",
        "NINFER_MODEL_PROFILE": "stock",
        "NINFER_MODEL_FILE": ninfer.STOCK_MODEL_FILE,
        "NINFER_MODEL_ID": "qwen-local",
        "NINFER_RUNTIME_PROFILE": "balanced",
        "NINFER_CONTEXT_LENGTH": "131072",
        "NINFER_KV_CAPACITY": "196608",
        "NINFER_MAX_CONCURRENCY": "2",
        "NINFER_PENDING_TIMEOUT_MS": "120000",
        "NINFER_KV_DTYPE": "fp8",
        "NINFER_DEVICE_STATE_SLOTS": "2",
        "NINFER_HOST_STATE_SLOTS": "8",
        "NINFER_HOST_KV_MIB": "8192",
        "NINFER_PRESERVE_THINKING": "true",
        "HERMES_COMPRESSION_ENABLED": "true",
        "HERMES_COMPRESSION_THRESHOLD_TOKENS": "90000",
        "HERMES_MAX_TURNS": "40",
    }


class NInferSourceInitializationTests(unittest.TestCase):
    def make_origin(self, root: Path) -> tuple[Path, str]:
        origin = root / "origin"
        origin.mkdir()
        subprocess.run(["git", "init", str(origin)], check=True, capture_output=True, text=True)
        (origin / "README.md").write_text("reviewed NInfer source\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(origin), "add", "README.md"], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(origin),
                "-c",
                "user.name=NInfer Setup Test",
                "-c",
                "user.email=ninfer-setup@example.invalid",
                "commit",
                "-m",
                "test source",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        commit = subprocess.run(
            ["git", "-C", str(origin), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return origin, commit

    def test_fresh_setup_fetches_pinned_source_without_submodule_wrapper(self) -> None:
        commands: list[list[str]] = []
        original_run = ninfer.run

        def recording_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            return original_run(command, **kwargs)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            origin, commit = self.make_origin(root)
            with (
                mock.patch.object(ninfer, "ROOT", root),
                mock.patch.object(ninfer, "NINFER_URL", str(origin)),
                mock.patch.object(ninfer, "NINFER_COMMIT", commit),
                mock.patch.object(ninfer, "run", side_effect=recording_run),
                redirect_stdout(StringIO()),
            ):
                ninfer.initialize_ninfer_source()

            checked_out = subprocess.run(
                ["git", "-C", str(root / "ninfer"), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(checked_out, commit)
            self.assertFalse((root / "ninfer" / ".git" / "ninfer-setup-in-progress").exists())

        self.assertFalse(any("submodule" in command for command in commands))

    def test_interrupted_helper_checkout_is_safely_repaired(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            origin, commit = self.make_origin(root)
            source = root / "ninfer"
            subprocess.run(["git", "init", str(source)], check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "-C", str(source), "remote", "add", "origin", str(origin)],
                check=True,
            )
            marker = source / ".git" / "ninfer-setup-in-progress"
            marker.write_text("managed\n", encoding="utf-8")
            (source / "README.md").write_text("partial checkout\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(source), "add", "README.md"], check=True)

            with (
                mock.patch.object(ninfer, "ROOT", root),
                mock.patch.object(ninfer, "NINFER_URL", str(origin)),
                mock.patch.object(ninfer, "NINFER_COMMIT", commit),
                redirect_stdout(StringIO()),
            ):
                ninfer.initialize_ninfer_source()

            self.assertEqual(
                (source / "README.md").read_text(encoding="utf-8"),
                "reviewed NInfer source\n",
            )
            self.assertFalse(marker.exists())

    def test_interrupted_checkout_at_pinned_head_is_safely_repaired(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            origin, commit = self.make_origin(root)
            source = root / "ninfer"
            subprocess.run(
                ["git", "clone", "--no-local", str(origin), str(source)],
                check=True,
                capture_output=True,
                text=True,
            )
            marker = source / ".git" / "ninfer-setup-in-progress"
            marker.write_text("managed\n", encoding="utf-8")
            (source / "README.md").write_text("checkout was interrupted\n", encoding="utf-8")

            with (
                mock.patch.object(ninfer, "ROOT", root),
                mock.patch.object(ninfer, "NINFER_URL", str(origin)),
                mock.patch.object(ninfer, "NINFER_COMMIT", commit),
                redirect_stdout(StringIO()),
            ):
                ninfer.initialize_ninfer_source()

            self.assertEqual(
                (source / "README.md").read_text(encoding="utf-8"),
                "reviewed NInfer source\n",
            )
            self.assertFalse(marker.exists())

    def test_interrupted_update_with_git_file_metadata_resumes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            origin, old_commit = self.make_origin(root)
            (origin / "README.md").write_text("new reviewed revision\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(origin), "add", "README.md"], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(origin),
                    "-c",
                    "user.name=NInfer Setup Test",
                    "-c",
                    "user.email=ninfer-setup@example.invalid",
                    "commit",
                    "-m",
                    "updated source",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            new_commit = subprocess.run(
                ["git", "-C", str(origin), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            source = root / "ninfer"
            subprocess.run(
                ["git", "clone", "--no-local", str(origin), str(source)],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "-C", str(source), "checkout", "--detach", old_commit],
                check=True,
                capture_output=True,
                text=True,
            )
            external_git_dir = root / "submodule-git-dir"
            shutil.move(str(source / ".git"), external_git_dir)
            (source / ".git").write_text(
                f"gitdir: {external_git_dir.as_posix()}\n",
                encoding="utf-8",
            )
            marker = external_git_dir / "ninfer-setup-in-progress"
            marker.write_text("managed\n", encoding="utf-8")
            (source / "README.md").write_text("partial updated checkout\n", encoding="utf-8")

            with (
                mock.patch.object(ninfer, "ROOT", root),
                mock.patch.object(ninfer, "NINFER_URL", str(origin)),
                mock.patch.object(ninfer, "NINFER_COMMIT", new_commit),
                redirect_stdout(StringIO()),
            ):
                ninfer.initialize_ninfer_source()

            self.assertEqual(
                (source / "README.md").read_text(encoding="utf-8"),
                "new reviewed revision\n",
            )
            self.assertFalse(marker.exists())


class HermesDesktopConfigurationTests(unittest.TestCase):
    def test_native_configuration_uses_named_authenticated_provider(self) -> None:
        calls: list[tuple[list[str], dict[str, object]]] = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile_home = (root / "hermes-profile").resolve()
            profile_home.mkdir()
            (profile_home / ".env").write_text(
                "NINFER_API_KEY=old\nHERMES_WRITE_SAFE_ROOT=legacy-workspace\n",
                encoding="utf-8",
            )
            expected = {
                "providers.ninfer.api": "http://127.0.0.1:18080/v1",
                "model.provider": "custom:ninfer",
                "model.default": "qwen-local",
                "model.context_length": "131072",
                "model.supports_vision": "false",
                "compression.threshold": "0.9",
                "compression.threshold_tokens": "90000",
                "terminal.backend": "local",
                "approvals.mode": "manual",
            }

            def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append((command, kwargs))
                output = ""
                if command[1:3] == ["config", "get"]:
                    output = expected[command[3]] + "\n"
                returncode = 1 if command[1:4] == ["config", "unset", "terminal.cwd"] else 0
                return subprocess.CompletedProcess(command, returncode, stdout=output, stderr="")

            hermes_env = {"HERMES_HOME": str(profile_home)}
            with (
                mock.patch.object(ninfer, "ROOT", root),
                mock.patch.object(ninfer, "run", side_effect=fake_run),
            ):
                ninfer.configure_native_hermes(
                    ["hermes"],
                    hermes_env,
                    sample_values(),
                )
            private_env_text = (profile_home / ".env").read_text(encoding="utf-8")

        secret_call, secret_kwargs = calls[0]
        self.assertEqual(secret_call[:4], ["hermes", "config", "set", "NINFER_API_KEY"])
        self.assertEqual(secret_call[-1], "a" * 64)
        self.assertEqual(secret_kwargs["redact"], {-1})
        self.assertTrue(secret_kwargs["capture"])

        self.assertNotIn("HERMES_WRITE_SAFE_ROOT", hermes_env)
        self.assertNotIn("HERMES_WRITE_SAFE_ROOT", private_env_text)

        provider_call = next(
            command for command, _ in calls if command[1:4] == ["config", "set", "providers.ninfer"]
        )
        self.assertIn('"api":"http://127.0.0.1:18080/v1"', provider_call[-1])
        self.assertIn('"key_env":"NINFER_API_KEY"', provider_call[-1])
        self.assertIn('"supports_vision":false', provider_call[-1])
        self.assertNotIn("a" * 64, provider_call[-1])
        self.assertIn(
            ["hermes", "config", "set", "approvals.mode", "manual"],
            [command for command, _ in calls],
        )
        self.assertIn(
            ["hermes", "config", "set", "terminal.backend", "local"],
            [command for command, _ in calls],
        )
        self.assertIn(
            ["hermes", "config", "unset", "terminal.cwd"],
            [command for command, _ in calls],
        )
        self.assertIn(
            ["hermes", "config", "set", "compression.threshold_tokens", "90000"],
            [command for command, _ in calls],
        )
        self.assertIn(
            ["hermes", "config", "set", "agent.max_turns", "40"],
            [command for command, _ in calls],
        )
        self.assertIn(
            ["hermes", "config", "set", "goals.max_turns", "40"],
            [command for command, _ in calls],
        )

    def test_private_env_removal_preserves_unrelated_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            env_file = Path(temporary) / ".env"
            env_file.write_text(
                "NINFER_API_KEY=keep-me\n"
                "HERMES_WRITE_SAFE_ROOT=old\n"
                "export HERMES_WRITE_SAFE_ROOT=stale\n",
                encoding="utf-8",
            )
            ninfer.remove_private_env_value(env_file, "HERMES_WRITE_SAFE_ROOT")
            updated = env_file.read_text(encoding="utf-8")

        self.assertEqual(updated, "NINFER_API_KEY=keep-me\n")

    def test_failed_secret_command_is_redacted(self) -> None:
        key = "b" * 64
        failure = subprocess.CalledProcessError(2, ["hermes", "config", "set", "NINFER_API_KEY", key])
        with mock.patch.object(ninfer.subprocess, "run", side_effect=failure):
            with self.assertRaises(ninfer.StackError) as context:
                ninfer.run(
                    ["hermes", "config", "set", "NINFER_API_KEY", key],
                    capture=True,
                    redact={-1},
                )
        message = str(context.exception)
        self.assertIn("<redacted>", message)
        self.assertNotIn(key, message)


class EnvironmentValidationTests(unittest.TestCase):
    def test_lan_selection_prefers_default_route_over_virtual_adapters(self) -> None:
        with (
            mock.patch.object(ninfer, "default_route_lan_ipv4", return_value="192.168.50.115"),
            mock.patch.object(ninfer, "address_is_assigned_locally", return_value=True),
            mock.patch.object(
                ninfer,
                "discover_lan_ipv4_addresses",
                return_value=["192.168.50.115", "172.17.32.1"],
            ),
        ):
            self.assertEqual(ninfer.choose_lan_address(), "192.168.50.115")

    def test_lan_endpoint_uses_selected_private_address(self) -> None:
        values = sample_values()
        values.update({"NINFER_ACCESS_MODE": "lan", "NINFER_BIND_ADDRESS": "192.168.50.9"})
        self.assertEqual(ninfer.ninfer_endpoint(values), "http://192.168.50.9:18080/v1")

    def test_lan_mode_rejects_public_bind_address(self) -> None:
        values = sample_values()
        values.update(
            {
                "MODEL_DOWNLOAD_UID": "1000",
                "MODEL_DOWNLOAD_GID": "1000",
                "NINFER_GPU_DEVICE": "0",
                "NINFER_ACCESS_MODE": "lan",
                "NINFER_BIND_ADDRESS": "8.8.8.8",
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            env_file = Path(temporary) / ".env"
            env_file.write_text(
                "".join(f"{key}={value}\n" for key, value in values.items()),
                encoding="utf-8",
            )
            with mock.patch.object(ninfer, "ENV_FILE", env_file):
                with self.assertRaisesRegex(ninfer.StackError, "RFC1918"):
                    ninfer.validate_env()

    def test_network_info_hides_key_unless_explicitly_requested(self) -> None:
        values = sample_values()
        values.update({"NINFER_ACCESS_MODE": "lan", "NINFER_BIND_ADDRESS": "192.168.50.9"})
        with redirect_stdout(StringIO()) as hidden_output:
            ninfer.print_network_info(values)
        with redirect_stdout(StringIO()) as revealed_output:
            ninfer.print_network_info(values, show_key=True)
        self.assertNotIn("a" * 64, hidden_output.getvalue())
        self.assertIn("a" * 64, revealed_output.getvalue())

    def test_failed_lan_activation_restores_previous_network_mode(self) -> None:
        values = sample_values()
        values.update(
            {
                "MODEL_DOWNLOAD_UID": "1000",
                "MODEL_DOWNLOAD_GID": "1000",
                "NINFER_GPU_DEVICE": "0",
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            env_file = Path(temporary) / ".env"
            env_file.write_text(
                "".join(f"{key}={value}\n" for key, value in values.items()),
                encoding="utf-8",
            )
            with (
                mock.patch.object(ninfer, "ENV_FILE", env_file),
                mock.patch.object(
                    ninfer,
                    "start_ninfer",
                    side_effect=[ninfer.StackError("LAN bind failed"), None],
                ) as start,
                redirect_stdout(StringIO()),
            ):
                with self.assertRaisesRegex(ninfer.StackError, "previous network"):
                    ninfer.activate_and_start_network("lan", "192.168.50.9")
            restored = ninfer.read_env(env_file)

        self.assertEqual(restored["NINFER_ACCESS_MODE"], "local")
        self.assertEqual(restored["NINFER_BIND_ADDRESS"], "127.0.0.1")
        self.assertEqual(start.call_count, 2)

    def test_model_file_cannot_escape_models_directory(self) -> None:
        values = sample_values()
        values.update({
            "MODEL_DOWNLOAD_UID": "1000",
            "MODEL_DOWNLOAD_GID": "1000",
            "NINFER_GPU_DEVICE": "0",
            "NINFER_MODEL_FILE": "../outside.ninfer",
        })
        with tempfile.TemporaryDirectory() as temporary:
            env_file = Path(temporary) / ".env"
            env_file.write_text(
                "".join(f"{key}={value}\n" for key, value in values.items()),
                encoding="utf-8",
            )
            with mock.patch.object(ninfer, "ENV_FILE", env_file):
                with self.assertRaisesRegex(ninfer.StackError, "filename, not a path"):
                    ninfer.validate_env()

    def test_profile_and_artifact_must_match(self) -> None:
        values = sample_values()
        values.update(
            {
                "MODEL_DOWNLOAD_UID": "1000",
                "MODEL_DOWNLOAD_GID": "1000",
                "NINFER_GPU_DEVICE": "0",
                "NINFER_MODEL_FILE": ninfer.UNCENSORED_MODEL_FILE,
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            env_file = Path(temporary) / ".env"
            env_file.write_text(
                "".join(f"{key}={value}\n" for key, value in values.items()),
                encoding="utf-8",
            )
            with mock.patch.object(ninfer, "ENV_FILE", env_file):
                with self.assertRaisesRegex(ninfer.StackError, "stock model profile"):
                    ninfer.validate_env()

    def test_runtime_profile_drift_is_rejected(self) -> None:
        values = sample_values()
        values.update(
            {
                "MODEL_DOWNLOAD_UID": "1000",
                "MODEL_DOWNLOAD_GID": "1000",
                "NINFER_GPU_DEVICE": "0",
                "NINFER_MAX_CONCURRENCY": "1",
                "NINFER_KV_CAPACITY": "131072",
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            env_file = Path(temporary) / ".env"
            env_file.write_text(
                "".join(f"{key}={value}\n" for key, value in values.items()),
                encoding="utf-8",
            )
            with mock.patch.object(ninfer, "ENV_FILE", env_file):
                with self.assertRaisesRegex(ninfer.StackError, "inconsistent values"):
                    ninfer.validate_env()

    def test_legacy_environment_is_backed_up_cleaned_and_migrated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env_file = root / ".env"
            example = root / ".env.example"
            example_values = {
                "NINFER_API_KEY": "",
                "NINFER_ACCESS_MODE": "local",
                "NINFER_BIND_ADDRESS": "127.0.0.1",
                "NINFER_MODEL_PROFILE": "stock",
                "NINFER_MODEL_FILE": ninfer.STOCK_MODEL_FILE,
                **ninfer.runtime_env_values(ninfer.runtime_profile("balanced")),
            }
            example.write_text(
                "".join(f"{key}={value}\n" for key, value in example_values.items()),
                encoding="utf-8",
            )
            env_file.write_text(
                f"NINFER_API_KEY={'e' * 64}\n"
                f"NINFER_MODEL_FILE={ninfer.STOCK_MODEL_FILE}\n"
                "HERMES_DASHBOARD_PASSWORD=remove-me\n"
                "UNRELATED_SETTING=keep-me\n",
                encoding="utf-8",
            )
            with (
                mock.patch.object(ninfer, "ENV_FILE", env_file),
                mock.patch.object(ninfer, "ENV_EXAMPLE", example),
                redirect_stdout(StringIO()),
            ):
                ninfer.merge_env()

            configured = env_file.read_text(encoding="utf-8")
            backups = list(root.glob(".env.backup-before-*"))

        self.assertEqual(len(backups), 1)
        self.assertNotIn("HERMES_DASHBOARD_PASSWORD", configured)
        self.assertIn("UNRELATED_SETTING=keep-me", configured)
        self.assertIn("NINFER_RUNTIME_PROFILE=balanced", configured)
        self.assertIn("NINFER_MAX_CONCURRENCY=2", configured)


class ModelDownloadLifecycleTests(unittest.TestCase):
    def test_downloaded_artifact_is_verified_against_pinned_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / "models"
            models.mkdir()
            profile = replace(
                ninfer.model_profile("uncensored"),
                expected_bytes=len(b"test artifact"),
                sha256=ninfer.hashlib.sha256(b"test artifact").hexdigest(),
            )
            artifact = models / profile.filename
            artifact.write_bytes(b"test artifact")
            checksum = ninfer.hashlib.sha256(artifact.read_bytes()).hexdigest()
            with mock.patch.object(ninfer, "ROOT", root):
                manifest = ninfer.require_model_artifact(profile)
                self.assertEqual(manifest["sha256"], checksum)
                artifact.write_bytes(b"tampered data")
                with self.assertRaisesRegex(ninfer.StackError, "checksum"):
                    ninfer.require_model_artifact(profile)

    def test_activation_backs_up_and_preserves_private_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env_file = root / ".env"
            env_file.write_text(
                "NINFER_API_KEY=" + "d" * 64 + "\n"
                "NINFER_MODEL_FILE=qwen3_8_27b_nvfp4.ninfer\n"
                "NINFER_MODEL_ID=qwen-local\n"
                "NINFER_CONTEXT_LENGTH=65536\n"
                "NINFER_KV_CAPACITY=65536\n",
                encoding="utf-8",
            )
            with (
                mock.patch.object(ninfer, "ENV_FILE", env_file),
                mock.patch.object(ninfer, "require_model_artifact"),
            ):
                backup = ninfer.activate_model_profile(ninfer.model_profile("uncensored"))

            self.assertIsNotNone(backup)
            assert backup is not None
            self.assertIn("qwen3_8_27b_nvfp4.ninfer", backup.read_text(encoding="utf-8"))
            updated = env_file.read_text(encoding="utf-8")
            self.assertIn("NINFER_MODEL_PROFILE=uncensored", updated)
            self.assertIn("NINFER_MODEL_FILE=" + ninfer.UNCENSORED_MODEL_FILE, updated)
            self.assertIn("NINFER_CONTEXT_LENGTH=65536", updated)
            self.assertIn("NINFER_API_KEY=" + "d" * 64, updated)

    def test_runtime_activation_changes_only_reviewed_runtime_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            env_file = Path(temporary) / ".env"
            env_file.write_text(
                f"NINFER_API_KEY={'f' * 64}\n"
                "NINFER_MODEL_PROFILE=uncensored\n"
                f"NINFER_MODEL_FILE={ninfer.UNCENSORED_MODEL_FILE}\n",
                encoding="utf-8",
            )
            with mock.patch.object(ninfer, "ENV_FILE", env_file):
                ninfer.activate_runtime_profile(ninfer.runtime_profile("max-context"))
            configured = env_file.read_text(encoding="utf-8")

        self.assertIn("NINFER_RUNTIME_PROFILE=max-context", configured)
        self.assertIn("NINFER_CONTEXT_LENGTH=240000", configured)
        self.assertIn("NINFER_MODEL_PROFILE=uncensored", configured)
        self.assertIn(f"NINFER_MODEL_FILE={ninfer.UNCENSORED_MODEL_FILE}", configured)

    def test_prepare_model_uses_shared_downloader_without_stopping_ninfer(self) -> None:
        calls: list[tuple[str, ...]] = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "models").mkdir()
            env_file = root / ".env"
            env_file.write_text("configured=true\n", encoding="utf-8")

            def fake_compose(*args: str, **_: object) -> subprocess.CompletedProcess[str]:
                calls.append(args)
                return subprocess.CompletedProcess(["docker"], 0, stdout="", stderr="")

            with (
                mock.patch.object(ninfer, "ROOT", root),
                mock.patch.object(ninfer, "ENV_FILE", env_file),
                mock.patch.object(ninfer, "merge_env"),
                mock.patch.object(ninfer, "validate_env"),
                mock.patch.object(ninfer, "compose", side_effect=fake_compose),
                mock.patch.object(ninfer, "require_model_artifact", return_value={"sha256": "abc"}),
                redirect_stdout(StringIO()),
            ):
                ninfer.prepare_model(
                    type(
                        "Args",
                        (),
                        {"model": "uncensored", "yes": True},
                    )()
                )

        self.assertEqual(len(calls), 1)
        self.assertIn("model-downloader", calls[0])
        self.assertEqual(calls[0][-1], "uncensored")


class SetupOrderingTests(unittest.TestCase):
    def test_model_menu_defaults_to_stock_and_accepts_uncensored(self) -> None:
        with mock.patch("builtins.input", return_value=""):
            self.assertEqual(
                ninfer.choose_model_profile(ninfer.DEFAULT_MODEL_PROFILE).key,
                "stock",
            )
        with mock.patch("builtins.input", return_value="2"):
            self.assertEqual(ninfer.choose_model_profile().key, "uncensored")

    def test_enter_explicitly_accepts_required_model_download(self) -> None:
        input_mock = mock.Mock(return_value="")
        with (
            mock.patch("builtins.input", input_mock),
            redirect_stdout(StringIO()) as output,
        ):
            self.assertTrue(
                ninfer.confirm_model_download(ninfer.model_profile("uncensored"))
            )
        self.assertEqual(
            input_mock.call_args.args[0],
            "Download the uncensored model now? [Y/n]: ",
        )
        self.assertIn("Hermes needs one local AI model", output.getvalue())

    def test_hermes_offer_happens_after_ninfer_api_is_ready(self) -> None:
        events: list[object] = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / "models"
            models.mkdir()
            (models / ninfer.UNCENSORED_MODEL_FILE).write_bytes(b"present")

            def fake_compose(*args: str, **_: object) -> subprocess.CompletedProcess[str]:
                events.append(("compose", args))
                return subprocess.CompletedProcess(["docker"], 0, stdout="", stderr="")

            with (
                mock.patch.object(ninfer, "ROOT", root),
                mock.patch.object(
                    ninfer,
                    "check_setup_prerequisites",
                    side_effect=lambda _: (events.append("prerequisites"), "0")[1],
                ),
                mock.patch.object(
                    ninfer,
                    "initialize_local_state",
                    side_effect=lambda gpu: events.append(("initialize", gpu)),
                ),
                mock.patch.object(ninfer, "validate_env"),
                mock.patch.object(ninfer, "confirm_model_download", return_value=True),
                mock.patch.object(
                    ninfer,
                    "prepare_model",
                    side_effect=lambda _: (events.append("prepare"), True)[1],
                ),
                mock.patch.object(
                    ninfer,
                    "activate_and_start_profile",
                    side_effect=lambda *_, **__: (
                        events.append(("compose", ("up",))),
                        events.append("ninfer-ready"),
                        events.append("generation-ready"),
                    ),
                ),
                mock.patch.object(ninfer, "confirm", return_value=True),
                mock.patch.object(
                    ninfer,
                    "install_hermes",
                    side_effect=lambda _: events.append("install-hermes"),
                ),
            ):
                with redirect_stdout(StringIO()):
                    ninfer.setup(
                        type(
                            "Args",
                            (),
                            {"skip_hermes": False, "model": "uncensored"},
                        )()
                    )

        self.assertLess(events.index("prerequisites"), events.index(("initialize", "0")))
        self.assertLess(events.index("ninfer-ready"), events.index("install-hermes"))
        self.assertLess(events.index("generation-ready"), events.index("install-hermes"))
        up_event = next(
            index
            for index, event in enumerate(events)
            if isinstance(event, tuple) and event[0] == "compose" and "up" in event[1]
        )
        self.assertLess(up_event, events.index("ninfer-ready"))


class PerformanceDiagnosisTests(unittest.TestCase):
    def test_parses_current_pretty_counts_and_long_durations(self) -> None:
        self.assertEqual(ninfer._pretty_number("6,163"), 6163)
        self.assertEqual(ninfer._pretty_number("2.77k"), 2770)
        self.assertEqual(ninfer._pretty_duration_ms("1m 14.2s"), 74_200)

    def test_summarizes_old_and_current_operational_log_formats(self) -> None:
        log_text = "\n".join(
            [
                "throughput interval=5.000s running=1 waiting=1",
                "[req 1] done finish=stop prompt=100000 gen=500 cache=50000 reuse=restore_turn_checkpoint ttft=20000ms prefill=1500.0tok/s decode=110.0tok/s wall=25.0s speculative=mtp 2.5tok/round (50.0%)",
                "req#2 done | openai chat | stop | prompt 120.0K | output 600 | cache 90.0K (75.0%, device) | TTFT 30.0 s | total 35.0 s | prefill 2.00K tok/s | decode 130.0 tok/s | mtp accepted 300/500 (60.0%)",
                "request_queue_timeout inference request expired while waiting for admission",
                "status=400 code=context_length_exceeded message=prepared prompt too large",
            ]
        )

        summary = ninfer.summarize_performance_log(log_text)

        self.assertEqual(summary["completed_requests"], 2)
        self.assertEqual(summary["max_prompt_tokens"], 120_000)
        self.assertEqual(summary["ttft_p50_ms"], 25_000)
        self.assertEqual(summary["prefill_median"], 1_750)
        self.assertEqual(summary["decode_median"], 120)
        self.assertEqual(summary["cache_median_percent"], 62.5)
        self.assertEqual(summary["mtp_median_percent"], 55)
        self.assertEqual(summary["queue_timeouts"], 1)
        self.assertEqual(summary["context_rejections"], 1)
        self.assertEqual(summary["peak_waiting"], 1)


class BeginnerRecoveryTests(unittest.TestCase):
    def test_generation_readiness_uses_authenticated_chat_completion(self) -> None:
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = (
            b'{"choices":[{"message":{"content":"Ready."}}]}'
        )
        with mock.patch.object(ninfer.urllib.request, "urlopen", return_value=response) as urlopen:
            ninfer.require_ninfer_generation(sample_values())

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:18080/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer " + "a" * 64)
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 900)

    def test_daemon_probe_suppresses_expected_docker_error(self) -> None:
        failure = subprocess.CompletedProcess(
            ["docker", "info"],
            1,
            stdout="",
            stderr="technical daemon connection error",
        )
        with mock.patch.object(ninfer, "run", return_value=failure) as run_mock:
            self.assertIsNone(ninfer.docker_server_os("docker"))
        self.assertFalse(run_mock.call_args.kwargs["check"])
        self.assertTrue(run_mock.call_args.kwargs["capture"])

    def test_windows_preflight_launches_stopped_docker_desktop_and_waits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env_file = root / ".env"
            (root / "models").mkdir()
            (root / "models" / ninfer.STOCK_MODEL_FILE).write_bytes(b"present")

            def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
                if "--query-gpu=index,name,driver_version" in command:
                    output = "1, NVIDIA GeForce RTX 5090, 999.99\n"
                else:
                    output = "Docker Compose version v2.99.0\n"
                return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")

            with (
                mock.patch.object(ninfer, "ROOT", root),
                mock.patch.object(ninfer, "ENV_FILE", env_file),
                mock.patch.object(ninfer.os, "name", "nt"),
                mock.patch.object(ninfer.shutil, "which", return_value="git.exe"),
                mock.patch.object(ninfer, "nvidia_smi_executable", return_value="nvidia-smi.exe"),
                mock.patch.object(ninfer, "docker_executable", return_value="docker.exe"),
                mock.patch.object(ninfer, "run", side_effect=fake_run),
                mock.patch.object(ninfer, "docker_server_os", side_effect=[None, None, "linux"]),
                mock.patch.object(ninfer, "launch_windows_docker_desktop", return_value=True) as launch,
                mock.patch.object(ninfer.time, "sleep"),
                redirect_stdout(StringIO()) as output,
            ):
                detected_gpu = ninfer.check_setup_prerequisites()

        launch.assert_called_once_with()
        self.assertEqual(detected_gpu, "1")
        self.assertIn("Opening it now", output.getvalue())
        self.assertIn("Linux containers", output.getvalue())

    def test_fresh_environment_uses_the_detected_5090_index(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env_file = root / ".env"
            example = root / ".env.example"
            example.write_text(
                "NINFER_GPU_DEVICE=0\n"
                "NINFER_MODEL_PROFILE=stock\n"
                f"NINFER_MODEL_FILE={ninfer.STOCK_MODEL_FILE}\n"
                "NINFER_API_KEY=\n",
                encoding="utf-8",
            )
            with (
                mock.patch.object(ninfer, "ENV_FILE", env_file),
                mock.patch.object(ninfer, "ENV_EXAMPLE", example),
            ):
                ninfer.merge_env("2")

            configured = env_file.read_text(encoding="utf-8")

        self.assertIn("NINFER_GPU_DEVICE=2\n", configured)
        self.assertIn("NINFER_MODEL_PROFILE=stock\n", configured)

    def test_existing_uncensored_environment_is_migrated_to_named_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env_file = root / ".env"
            example = root / ".env.example"
            example.write_text(
                "NINFER_MODEL_PROFILE=stock\n"
                f"NINFER_MODEL_FILE={ninfer.STOCK_MODEL_FILE}\n"
                "NINFER_API_KEY=\n",
                encoding="utf-8",
            )
            env_file.write_text(
                f"NINFER_MODEL_FILE={ninfer.UNCENSORED_MODEL_FILE}\n"
                f"NINFER_API_KEY={'a' * 64}\n",
                encoding="utf-8",
            )
            with (
                mock.patch.object(ninfer, "ENV_FILE", env_file),
                mock.patch.object(ninfer, "ENV_EXAMPLE", example),
            ):
                ninfer.merge_env()

            configured = env_file.read_text(encoding="utf-8")

        self.assertIn("NINFER_MODEL_PROFILE=uncensored\n", configured)
        self.assertIn(f"NINFER_MODEL_FILE={ninfer.UNCENSORED_MODEL_FILE}\n", configured)

    def test_up_waits_for_model_and_authenticated_api(self) -> None:
        events: list[object] = []
        values = sample_values()

        def fake_compose(*args: str, **_: object) -> subprocess.CompletedProcess[str]:
            events.append(("compose", args))
            return subprocess.CompletedProcess(["docker"], 0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as temporary:
            env_file = Path(temporary) / ".env"
            env_file.write_text("configured=true\n", encoding="utf-8")
            with (
                mock.patch.object(ninfer, "ENV_FILE", env_file),
                mock.patch.object(
                    ninfer,
                    "check_setup_prerequisites",
                    side_effect=lambda: events.append("prerequisites"),
                ),
                mock.patch.object(ninfer, "validate_env", side_effect=lambda: events.append("validate")),
                mock.patch.object(ninfer, "read_env", return_value=values),
                mock.patch.object(ninfer, "compose", side_effect=fake_compose),
                mock.patch.object(
                    ninfer,
                    "require_ninfer_api",
                    side_effect=lambda _: events.append("api-ready"),
                ),
                mock.patch.object(
                    ninfer,
                    "require_ninfer_generation",
                    side_effect=lambda _: events.append("generation-ready"),
                ),
                redirect_stdout(StringIO()) as output,
            ):
                ninfer.up(type("Args", (), {})())

        compose_event = next(event for event in events if isinstance(event, tuple))
        self.assertIn("--wait", compose_event[1])
        self.assertIn("900", compose_event[1])
        self.assertLess(events.index(compose_event), events.index("api-ready"))
        self.assertLess(events.index("api-ready"), events.index("generation-ready"))
        self.assertIn("READY", output.getvalue())

    def test_start_recreates_network_once_when_loopback_api_is_missing(self) -> None:
        compose_calls: list[tuple[str, ...]] = []

        def fake_compose(*args: str, **_: object) -> subprocess.CompletedProcess[str]:
            compose_calls.append(args)
            return subprocess.CompletedProcess(["docker"], 0, stdout="", stderr="")

        api_check = mock.Mock(side_effect=[ninfer.StackError("connection refused"), None])
        with (
            mock.patch.object(ninfer, "compose", side_effect=fake_compose),
            mock.patch.object(ninfer, "require_ninfer_api", api_check),
            mock.patch.object(ninfer, "require_ninfer_generation") as generation,
            redirect_stdout(StringIO()) as output,
        ):
            ninfer.start_ninfer(sample_values())

        self.assertEqual(len(compose_calls), 3)
        self.assertEqual(compose_calls[1], ("down", "--remove-orphans"))
        self.assertEqual(compose_calls[0], compose_calls[2])
        self.assertEqual(api_check.call_count, 2)
        generation.assert_called_once_with(sample_values())
        self.assertIn("Recreating the Docker network once", output.getvalue())

    def test_hermes_is_relaunched_after_configuration_on_windows(self) -> None:
        values = sample_values()
        with tempfile.TemporaryDirectory() as temporary:
            env_file = Path(temporary) / ".env"
            env_file.write_text("configured=true\n", encoding="utf-8")
            desktop = Path(temporary) / "Hermes.exe"
            desktop.write_bytes(b"exe")
            args = type("Args", (), {"no_open": False, "no_wait": False, "from_setup": True})()
            with (
                mock.patch.object(ninfer, "ENV_FILE", env_file),
                mock.patch.object(ninfer, "validate_env"),
                mock.patch.object(ninfer, "read_env", return_value=values),
                mock.patch.object(ninfer, "require_ninfer_api"),
                mock.patch.object(ninfer, "require_ninfer_generation"),
                mock.patch.object(ninfer, "native_hermes_command", return_value=(["hermes"], {})),
                mock.patch.object(ninfer, "configure_native_hermes"),
                mock.patch.object(ninfer, "windows_hermes_desktop_executable", return_value=desktop),
                mock.patch.object(ninfer.sys.stdin, "isatty", return_value=True),
                mock.patch("builtins.input", return_value=""),
                mock.patch.object(ninfer, "launch_windows_hermes_desktop", return_value=True) as launch,
                redirect_stdout(StringIO()) as output,
            ):
                ninfer.install_hermes(args)

        launch.assert_called_once_with()
        self.assertIn("must reload", output.getvalue())
        self.assertIn("UAC does not protect", output.getvalue())
        self.assertIn("SETUP COMPLETE", output.getvalue())

    def test_install_hermes_refuses_an_api_that_cannot_generate(self) -> None:
        values = sample_values()
        args = type("Args", (), {"no_open": True, "no_wait": True, "from_setup": False})()
        with tempfile.TemporaryDirectory() as temporary:
            env_file = Path(temporary) / ".env"
            env_file.write_text("configured=true\n", encoding="utf-8")
            with (
                mock.patch.object(ninfer, "ENV_FILE", env_file),
                mock.patch.object(ninfer, "validate_env"),
                mock.patch.object(ninfer, "read_env", return_value=values),
                mock.patch.object(ninfer, "require_ninfer_api"),
                mock.patch.object(
                    ninfer,
                    "require_ninfer_generation",
                    side_effect=ninfer.StackError("generation failed"),
                ),
                mock.patch.object(ninfer, "configure_native_hermes") as configure,
                redirect_stdout(StringIO()),
            ):
                with self.assertRaisesRegex(ninfer.StackError, "could not answer"):
                    ninfer.install_hermes(args)

        configure.assert_not_called()

    def test_install_hermes_starts_a_stopped_configured_service(self) -> None:
        values = sample_values()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env_file = root / ".env"
            env_file.write_text("configured=true\n", encoding="utf-8")
            models = root / "models"
            models.mkdir()
            (models / ninfer.STOCK_MODEL_FILE).write_bytes(b"present")
            args = type("Args", (), {"no_open": False, "no_wait": True, "from_setup": False})()
            with (
                mock.patch.object(ninfer, "ROOT", root),
                mock.patch.object(ninfer, "ENV_FILE", env_file),
                mock.patch.object(ninfer, "validate_env"),
                mock.patch.object(ninfer, "read_env", return_value=values),
                mock.patch.object(ninfer, "require_ninfer_api", side_effect=ninfer.StackError("stopped")),
                mock.patch.object(ninfer, "check_setup_prerequisites") as prerequisites,
                mock.patch.object(ninfer, "start_ninfer") as start,
                mock.patch.object(ninfer, "native_hermes_command", return_value=(["hermes"], {})),
                mock.patch.object(ninfer, "configure_native_hermes"),
                mock.patch.object(ninfer, "windows_hermes_desktop_executable", return_value=None),
                redirect_stdout(StringIO()) as output,
            ):
                ninfer.install_hermes(args)

        prerequisites.assert_called_once_with()
        start.assert_called_once_with(values)
        self.assertIn("Starting it now", output.getvalue())


if __name__ == "__main__":
    unittest.main()
