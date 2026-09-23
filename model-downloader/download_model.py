#!/usr/bin/env python3
"""Download and verify a pinned NInfer artifact for a supported profile."""

from __future__ import annotations

import argparse
import hashlib
import json
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


_manifest_path = Path(__file__).with_name("manifest.json")
if not _manifest_path.exists():
    _manifest_path = Path(__file__).resolve().parents[1] / "stack/manifest.json"
_models = json.loads(_manifest_path.read_text(encoding="utf-8"))["models"]
ARTIFACTS = {key: Artifact(p["filename"], p["repository"], p["revision"], p["expected_bytes"], p["sha256"])
             for key, p in _models.items()}


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
        migration = _models[args.profile].get("migration")
        source_file = MODELS / (migration["filename"] if migration else artifact.filename)
        source_size = migration["expected_bytes"] if migration else artifact.expected_bytes
        source_sha = migration["sha256"] if migration else artifact.expected_sha256
        print(
            f"Preparing {artifact.repository}/{_models[args.profile]['source_filename']}@{artifact.revision} as {artifact.filename}"
        )
        downloaded = source_file if source_file.exists() else Path(hf_hub_download(
                repo_id=artifact.repository,
                filename=_models[args.profile]["source_filename"],
                revision=artifact.revision,
                local_dir=MODELS / ".downloads" / args.profile,
                token=os.environ.get("HF_TOKEN") or None,
            ))
        if downloaded.stat().st_size != source_size or digest(downloaded) != source_sha:
            raise SystemExit("Downloaded artifact failed manifest size/checksum verification")
        if downloaded != source_file:
            downloaded.replace(source_file)
        if migration:
            from artifacts import upgrade
            upgrade(source_file, model_file, Path(__file__).parent / "tools", source_sha)

    actual = verify(artifact)
    print(f"{args.profile.capitalize()} model checksum verified: {actual}")


if __name__ == "__main__":
    main()
