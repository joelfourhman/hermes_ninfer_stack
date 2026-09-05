#!/usr/bin/env python3
"""Download and verify the pinned stock Qwen3.8 NInfer artifact."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from huggingface_hub import hf_hub_download


MODELS = Path("/models")
MODEL_NAME = "qwen3_8_27b_nvfp4.ninfer"
MODEL_FILE = MODELS / MODEL_NAME
REPOSITORY = "neroued/Qwen3.8-27B-nvfp4-NInfer"
REVISION = "204e3d92c30d9d05f3300d2f52e443ad1edf6ddf"
EXPECTED_BYTES = 21_492_695_040
EXPECTED_SHA256 = "bb3360522a06e136e0367f5703414d26272b7285c8a6ab6194135c17dbd81b32"


def digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def verify() -> None:
    if not MODEL_FILE.is_file():
        raise SystemExit(f"Download completed without producing {MODEL_FILE}")
    if MODEL_FILE.stat().st_size != EXPECTED_BYTES:
        raise SystemExit(
            f"Stock artifact has {MODEL_FILE.stat().st_size:,} bytes; "
            f"expected {EXPECTED_BYTES:,}. Move the invalid file aside explicitly and retry."
        )
    actual = digest(MODEL_FILE)
    if actual != EXPECTED_SHA256:
        raise SystemExit(
            f"Stock artifact checksum is {actual}; expected {EXPECTED_SHA256}. "
            "Move the invalid file aside explicitly and retry."
        )
    print(f"Stock model checksum verified: {actual}")


def main() -> None:
    MODELS.mkdir(parents=True, exist_ok=True)
    if MODEL_FILE.exists():
        print("The stock model already exists; verifying it instead of downloading again.")
        verify()
        return
    print(f"Downloading {REPOSITORY}/{MODEL_NAME}@{REVISION}")
    hf_hub_download(
        repo_id=REPOSITORY,
        filename=MODEL_NAME,
        revision=REVISION,
        local_dir=MODELS,
        token=os.environ.get("HF_TOKEN") or None,
    )
    verify()


if __name__ == "__main__":
    main()
