from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import ninfer
from stack.config import (
    DEPLOYMENT_PRESETS,
    MANIFEST,
    MODEL_PROFILES,
    RUNTIME_PROFILES,
    runtime_env_values,
    spec_values,
    validate_manifest,
    validate_spec,
)
from stack.documentation import generate
from stack.provenance import verify_cli_help, verify_image, verify_model


class ConfigurationTests(unittest.TestCase):
    def test_deployment_presets_are_complete_and_compatible(self):
        self.assertEqual(
            set(DEPLOYMENT_PRESETS),
            {"default", "coding", "coding-fast", "research", "autonomous", "low-vram", "uncensored"},
        )
        for preset in DEPLOYMENT_PRESETS.values():
            values = dict(spec_values(preset.spec), NINFER_MODEL_PROFILE=preset.model)
            validate_spec(values)

    def test_runtime_rolls_back_backend_and_hermes_on_sync_failure(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            env = root / ".env"
            config = root / "hermes/config.yaml"
            config.parent.mkdir()
            config.write_text("old config")
            env.write_text("NINFER_RUNTIME_PROFILE=balanced\n")

            def failed_sync(*args, **kwargs):
                self.assertTrue(kwargs["preserve_execution"])
                config.write_text("partial config")
                raise ninfer.StackError("failed sync")

            with (
                patch.object(ninfer, "ENV_FILE", env),
                patch.object(
                    ninfer,
                    "native_hermes_command",
                    return_value=(["hermes"], {"HERMES_HOME": str(config.parent)}),
                ),
                patch.object(ninfer, "validate_env"),
                patch.object(ninfer, "start_ninfer") as start,
                patch.object(ninfer, "configure_native_hermes", side_effect=failed_sync),
            ):
                with self.assertRaisesRegex(ninfer.StackError, "restored"):
                    ninfer.activate_and_start_runtime(RUNTIME_PROFILES["coding"])
            self.assertEqual(config.read_text(), "old config")
            self.assertEqual(env.read_text(), "NINFER_RUNTIME_PROFILE=balanced\n")
            self.assertEqual(start.call_count, 2)

    def test_explicit_model_fallback_resets_incompatible_decoder(self):
        with tempfile.TemporaryDirectory() as d:
            env = Path(d) / ".env"
            env.write_text("NINFER_SPEC_BACKEND=dflash2\nNINFER_DRAFT_TOKENS=11\n")
            with (
                patch.object(ninfer, "ENV_FILE", env),
                patch.object(ninfer, "require_model_artifact"),
            ):
                ninfer.activate_model_profile(MODEL_PROFILES["stock"])
                values = ninfer.read_env()
            self.assertEqual(values["NINFER_SPEC_BACKEND"], "mtp")
            self.assertEqual(values["NINFER_DRAFT_TOKENS"], "3")

    def test_manifest_profiles_context_and_generated_docs(self):
        validate_manifest()
        self.assertEqual(MANIFEST["defaults"]["goal_max_turns"], 100000)
        generate(check=True)
        self.assertTrue(all(profile.max_turns == 100000 for profile in RUNTIME_PROFILES.values()))
        for profile in RUNTIME_PROFILES.values():
            values = runtime_env_values(profile)
            self.assertLess(
                int(values["HERMES_COMPRESSION_THRESHOLD_TOKENS"]),
                int(values["NINFER_CONTEXT_LENGTH"]) - 8191,
            )
            self.assertEqual(int(values["HERMES_MAX_TURNS"]), profile.max_turns)

    def test_spec_modes_and_capability_gate(self):
        for mode, count in [("mtp3", 3), ("dflash2-7", 7), ("dflash2-11", 11)]:
            values = spec_values(mode)
            self.assertEqual(int(values["NINFER_DRAFT_TOKENS"]), count)
            validate_spec(dict(values, NINFER_MODEL_PROFILE="stock-dflash2"))
        with self.assertRaisesRegex(ValueError, "companion"):
            validate_spec(dict(spec_values("dflash2-7"), NINFER_MODEL_PROFILE="stock"))
        for backend, count in [
            ("mtp", 6),
            ("dflash2", 16),
            ("dflash2", 0),
            ("unknown", 3),
        ]:
            with self.assertRaises(ValueError):
                spec_values(backend, count)

    def test_cli_flag_disappearance_and_image_drift(self):
        help_text = " ".join(MANIFEST["ninfer"]["required_cli_flags"]) + " mtp dflash2 fp8"
        verify_cli_help(help_text)
        with self.assertRaisesRegex(ValueError, "host-kv-mib"):
            verify_cli_help(help_text.replace("--host-kv-mib", "--old-host-kv"))
        with self.assertRaises(ValueError):
            verify_image({"org.opencontainers.image.revision": "wrong"})

    def test_corrupt_model_and_manifest_mismatch(self):
        import hashlib

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / MODEL_PROFILES["stock"].filename
            path.write_bytes(b"valid")
            model = replace(
                MODEL_PROFILES["stock"],
                expected_bytes=5,
                sha256=hashlib.sha256(b"valid").hexdigest(),
            )
            with patch.dict(MODEL_PROFILES, stock=model):
                verify_model(path, "stock")
                path.write_bytes(b"wrong")
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    verify_model(path, "stock")

    def test_profile_composition_maps_memory_and_spec(self):
        compose = (ninfer.ROOT / "docker-compose.yml").read_text()
        for key in [
            "NINFER_CONTEXT_LENGTH",
            "NINFER_KV_CAPACITY",
            "NINFER_DEVICE_STATE_SLOTS",
            "NINFER_HOST_STATE_SLOTS",
            "NINFER_HOST_KV_MIB",
            "NINFER_SPEC_BACKEND",
            "NINFER_DRAFT_TOKENS",
        ]:
            self.assertIn("${" + key, compose)
        self.assertIn("/dev/stdout", compose)
        self.assertIn("no-new-privileges:true", compose)
