#!/usr/bin/env python3
"""Download and verify the exact model artifact used by this stack."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path


MODEL_DIR = Path("/models")
MODEL_NAME = "qwen3_8_27b_nvfp4.ninfer"
MODEL_FILE = MODEL_DIR / MODEL_NAME
REPOSITORY = "neroued/Qwen3.8-27B-nvfp4-NInfer"
REVISION = "204e3d92c30d9d05f3300d2f52e443ad1edf6ddf"
SHA256 = "bb3360522a06e136e0367f5703414d26272b7285c8a6ab6194135c17dbd81b32"
SIZE_BYTES = 21_492_695_040
REQUIRED_FREE_BYTES = 24 * 1024**3
HUGGINGFACE_HUB_VERSION = "1.27.0"


def digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def verify() -> None:
    actual = digest(MODEL_FILE)
    if actual != SHA256:
        raise SystemExit(
            "Model checksum mismatch.\n"
            f"Expected: {SHA256}\n"
            f"Actual:   {actual}\n"
            "Remove the invalid file explicitly before trying again."
        )
    print(f"Model checksum verified: {SHA256}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="skip the DOWNLOAD confirmation")
    args = parser.parse_args()

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    if MODEL_FILE.is_file() and MODEL_FILE.stat().st_size > 0:
        print("Model already exists; verifying it instead of downloading again.")
        verify()
        return 0

    free = shutil.disk_usage(MODEL_DIR).free
    print(f"Artifact: {REPOSITORY}/{MODEL_NAME}")
    print(f"Revision: {REVISION}")
    print(f"Size:     {SIZE_BYTES:,} bytes (20.02 GiB)")
    print(f"Target:   {MODEL_FILE}")
    print(f"Free:     {free / 1024**3:.2f} GiB")
    if free < REQUIRED_FREE_BYTES:
        raise SystemExit("At least 24 GiB of free space is required for the artifact and staging.")

    if not args.yes:
        if input("Type DOWNLOAD to fetch this ~20 GiB model: ").strip() != "DOWNLOAD":
            print("Download cancelled.")
            return 0

    command = [
        "hf",
        "download",
        REPOSITORY,
        MODEL_NAME,
        "--revision",
        REVISION,
        "--local-dir",
        str(MODEL_DIR),
    ]
    print(f"Using huggingface-hub {HUGGINGFACE_HUB_VERSION}, provisioned by uv inside the utility image.")
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        return completed.returncode
    if not MODEL_FILE.is_file():
        raise SystemExit(f"Download completed without producing {MODEL_FILE}")
    verify()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nDownload interrupted; Hugging Face staging data was preserved for resume.", file=sys.stderr)
        raise SystemExit(130)
