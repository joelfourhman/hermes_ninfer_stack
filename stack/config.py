"""One authoritative manifest for source, artifacts and resource profiles."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

MANIFEST_PATH = Path(__file__).with_name("manifest.json")
MANIFEST = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
NINFER_COMMIT = MANIFEST["ninfer"]["commit"]
NINFER_URL = MANIFEST["ninfer"]["repository"]
DEFAULT_MODEL_PROFILE = MANIFEST["defaults"]["model"]
DEFAULT_RUNTIME_PROFILE = MANIFEST["defaults"]["runtime"]


@dataclass(frozen=True)
class ModelProfile:
    key: str
    label: str
    filename: str
    sha256: str
    expected_bytes: int
    required_free_gib: int
    transfer_description: str
    final_size_gib: str
    repository: str
    revision: str
    source_filename: str
    quantization: str
    capabilities: list[str]


@dataclass(frozen=True)
class RuntimeProfile:
    key: str
    label: str
    description: str
    context_length: int
    kv_capacity: int
    max_concurrency: int
    pending_timeout_ms: int
    kv_dtype: str
    device_state_slots: int
    host_state_slots: int
    host_kv_mib: int
    preserve_thinking: bool
    compression_threshold_tokens: int
    max_turns: int
    qualification: str


MODEL_PROFILES = {k: ModelProfile(**v) for k, v in MANIFEST["models"].items()}
RUNTIME_PROFILES = {k: RuntimeProfile(**v) for k, v in MANIFEST["profiles"].items()}


def runtime_env_values(profile: RuntimeProfile) -> dict[str, str]:
    fields = {
        "NINFER_RUNTIME_PROFILE": profile.key,
        "NINFER_CONTEXT_LENGTH": profile.context_length,
        "NINFER_KV_CAPACITY": profile.kv_capacity,
        "NINFER_MAX_CONCURRENCY": profile.max_concurrency,
        "NINFER_PENDING_TIMEOUT_MS": profile.pending_timeout_ms,
        "NINFER_KV_DTYPE": profile.kv_dtype,
        "NINFER_DEVICE_STATE_SLOTS": profile.device_state_slots,
        "NINFER_HOST_STATE_SLOTS": profile.host_state_slots,
        "NINFER_HOST_KV_MIB": profile.host_kv_mib,
        "NINFER_PRESERVE_THINKING": "true" if profile.preserve_thinking else "false",
        "HERMES_COMPRESSION_ENABLED": "true",
        "HERMES_COMPRESSION_THRESHOLD_TOKENS": profile.compression_threshold_tokens,
        "HERMES_MAX_TURNS": profile.max_turns,
    }
    return {k: str(v) for k, v in fields.items()}


def spec_values(mode: str, draft_tokens: int | None = None) -> dict[str, str]:
    match = re.fullmatch(r"(mtp)([1-5])|dflash2-(\d+)", mode)
    if mode in {"mtp", "dflash2"} and draft_tokens is not None:
        backend, count = mode, draft_tokens
    elif match:
        backend, count = ("mtp", int(match[2])) if match[1] else ("dflash2", int(match[3]))
        if draft_tokens is not None:
            count = draft_tokens
    else:
        raise ValueError("Choose mtp3, dflash2-7, dflash2-11 or a backend with --draft-tokens")
    if not 1 <= count <= (5 if backend == "mtp" else 15):
        raise ValueError("MTP supports 1..5 drafts; DFlash2 supports 1..15")
    return {"NINFER_SPEC_BACKEND": backend, "NINFER_DRAFT_TOKENS": str(count)}


def validate_spec(values: dict[str, str]) -> None:
    backend = values.get("NINFER_SPEC_BACKEND", "mtp")
    try:
        spec_values(backend, int(values.get("NINFER_DRAFT_TOKENS", "3")))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid speculative configuration: {exc}") from exc
    model = MODEL_PROFILES[values["NINFER_MODEL_PROFILE"]]
    if backend not in model.capabilities:
        raise ValueError(
            f"{model.key} lacks {backend} companion weights. Explicitly select-model --model stock-dflash2 first; no artifact is changed automatically."
        )


def validate_manifest() -> None:
    if MANIFEST["schema_version"] != 1 or not re.fullmatch(r"[0-9a-f]{40}", NINFER_COMMIT):
        raise ValueError("Invalid manifest schema or source SHA")
    for key, model in MODEL_PROFILES.items():
        if key != model.key or not re.fullmatch(r"[0-9a-f]{64}", model.sha256):
            raise ValueError(f"Invalid model identity/checksum: {key}")
        if not re.fullmatch(r"[0-9a-f]{40}", model.revision) or model.expected_bytes <= 0:
            raise ValueError(f"Invalid model revision/size: {key}")
        if (
            Path(model.filename).name != model.filename
            or "/" in model.filename
            or "\\" in model.filename
        ):
            raise ValueError(f"Model filename escapes directory: {key}")
    for key, p in RUNTIME_PROFILES.items():
        if key != p.key or not 1024 <= p.context_length <= 262144:
            raise ValueError(f"Invalid profile context: {key}")
        if not p.context_length <= p.kv_capacity <= p.context_length * p.max_concurrency:
            raise ValueError(f"Invalid profile shared KV: {key}")
        if not 1 <= p.max_concurrency <= 8 or not 1 <= p.max_turns <= 1000:
            raise ValueError(f"Invalid profile limits: {key}")
        if not 1024 <= p.compression_threshold_tokens <= p.context_length - 8192:
            raise ValueError(f"Profile lacks output/context headroom: {key}")
        if p.kv_dtype not in {"bf16", "int8", "fp8", "nvfp4", "k8v4"}:
            raise ValueError(f"Invalid KV dtype: {key}")
        if min(p.device_state_slots, p.host_state_slots, p.host_kv_mib) < 0:
            raise ValueError(f"Invalid state capacity: {key}")
