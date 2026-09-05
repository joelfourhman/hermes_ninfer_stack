#!/usr/bin/env python3
"""Download and verify a pinned NInfer artifact for a supported profile."""

from __future__ import annotations

import argparse
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from huggingface_hub import hf_hub_download


MODELS = Path("/models")


@dataclass(frozen=True)
class Artifact:
    filename: str
    repository: str
    revision: str
    expected_bytes: int
    expected_sha256: str


ARTIFACTS = {
    "stock": Artifact(
        filename="qwen3_8_27b_nvfp4.ninfer",
        repository="neroued/Qwen3.8-27B-nvfp4-NInfer",
        revision="204e3d92c30d9d05f3300d2f52e443ad1edf6ddf",
        expected_bytes=21_492_695_040,
        expected_sha256="bb3360522a06e136e0367f5703414d26272b7285c8a6ab6194135c17dbd81b32",
    ),
    "uncensored": Artifact(
        filename="qwen3_8_27b_uncensored.ninfer",
        repository="DogOnKeyboard/Qwen3.8-27B-Uncensored-NInfer",
        revision="1e15b5919b796bcd96621f13572ad92b5555b641",
        expected_bytes=18_210_531_328,
        expected_sha256="714565ed29db4415322e9bc13a3464dc1fd8fcc911234740a79af67934e49969",
    ),
}


def digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def verify(artifact: Artifact) -> str:
    model_file = MODELS / artifact.filename
    if not model_file.is_file():
        raise SystemExit(f"Download completed without producing {model_file}")
    if model_file.stat().st_size != artifact.expected_bytes:
        raise SystemExit(
            f"Artifact has {model_file.stat().st_size:,} bytes; "
            f"expected {artifact.expected_bytes:,}. Move the invalid file aside and retry."
        )
    actual = digest(model_file)
    if actual != artifact.expected_sha256:
        raise SystemExit(
            f"Artifact checksum is {actual}; expected {artifact.expected_sha256}. "
            "Move the invalid file aside and retry."
        )
    return actual


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=tuple(ARTIFACTS))
    args = parser.parse_args()
    artifact = ARTIFACTS[args.profile]
    model_file = MODELS / artifact.filename

    MODELS.mkdir(parents=True, exist_ok=True)
    if model_file.exists():
        print(f"{artifact.filename} already exists; verifying it instead of downloading again.")
    else:
        print(
            f"Downloading {artifact.repository}/{artifact.filename}@{artifact.revision}"
        )
        hf_hub_download(
            repo_id=artifact.repository,
            filename=artifact.filename,
            revision=artifact.revision,
            local_dir=MODELS,
            token=os.environ.get("HF_TOKEN") or None,
        )

    actual = verify(artifact)
    print(f"{args.profile.capitalize()} model checksum verified: {actual}")


if __name__ == "__main__":
    main()
