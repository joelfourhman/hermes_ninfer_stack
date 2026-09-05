#!/usr/bin/env python3
"""Fetch and verify every pinned input for the local model conversion."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from huggingface_hub import hf_hub_download, snapshot_download


WORK = Path("/work")
CHECKPOINT = WORK / "checkpoint"
NINFER_SOURCE = WORK / "ninfer-converter"
FRONTEND_PINS = Path("/app/frontend.sha256")

BASE_REPO = "JonathanColetti/Qwen3.8-27B-Uncensored"
BASE_REVISION = "5bb7aa90f0efef548e87005b1fb7658e522b6b7f"
FRONTEND_REPO = "Qwen/Qwen3.8-27B"
FRONTEND_REVISION = "1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0"
NINFER_COMMIT = "b2b96bae4dd88f95b9ea8126d68fae3b88caa374"
NINFER_ARCHIVE_SHA256 = "d357b1c587936562a03134b40a31266cff6dd5d8541a6eb4eed5fe930f44c819"
NINFER_ARCHIVE_URL = f"https://github.com/Neroued/ninfer/archive/{NINFER_COMMIT}.tar.gz"


def digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def load_frontend_pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    for raw in FRONTEND_PINS.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        wanted, name = line.split()
        pins[name] = wanted
    return pins


def fetch_checkpoint() -> None:
    marker = CHECKPOINT / ".hermes-ninfer-source.json"
    identity = {"repository": BASE_REPO, "revision": BASE_REVISION}
    if marker.is_file():
        try:
            recorded = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            recorded = None
        if recorded != identity:
            raise SystemExit(
                "The checkpoint cache belongs to different source inputs. "
                "Move model-build/checkpoint aside and rerun setup."
            )
    CHECKPOINT.mkdir(parents=True, exist_ok=True)
    print(f"Downloading pinned source weights: {BASE_REPO}@{BASE_REVISION}")
    snapshot_download(
        repo_id=BASE_REPO,
        revision=BASE_REVISION,
        local_dir=CHECKPOINT,
        allow_patterns=["*.safetensors", "*.json", "*.jinja", "*.txt"],
        token=os.environ.get("HF_TOKEN") or None,
    )
    marker.write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")


def graft_and_verify_frontend() -> None:
    pins = load_frontend_pins()
    for name, wanted in pins.items():
        cached = Path(
            hf_hub_download(
                repo_id=FRONTEND_REPO,
                filename=name,
                revision=FRONTEND_REVISION,
                token=os.environ.get("HF_TOKEN") or None,
            )
        )
        target = CHECKPOINT / name
        shutil.copyfile(cached, target)
        actual = digest(target)
        if actual != wanted:
            raise SystemExit(
                f"Official frontend checksum mismatch for {name}: expected {wanted}, got {actual}"
            )
        print(f"Verified official frontend: {name}")


def safe_extract(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            path = Path(member.name)
            if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
                raise SystemExit(f"Unsafe path in NInfer source archive: {member.name}")
        bundle.extractall(destination, filter="data")


def fetch_ninfer_converter() -> None:
    marker = NINFER_SOURCE / ".hermes-ninfer-revision"
    if marker.is_file() and marker.read_text(encoding="utf-8").strip() == NINFER_COMMIT:
        converter = NINFER_SOURCE / "tools" / "convert" / "qwen3_8_27b" / "convert.py"
        if converter.is_file():
            print(f"Pinned NInfer converter is already present: {NINFER_COMMIT}")
            return
    if NINFER_SOURCE.exists():
        raise SystemExit(
            "The converter cache is incomplete or belongs to another revision. "
            "Move model-build/ninfer-converter aside and rerun setup."
        )

    archive = WORK / f"ninfer-{NINFER_COMMIT}.tar.gz"
    if not archive.is_file() or digest(archive) != NINFER_ARCHIVE_SHA256:
        partial = archive.with_suffix(archive.suffix + ".partial")
        partial.unlink(missing_ok=True)
        print(f"Downloading pinned NInfer converter: {NINFER_COMMIT}")
        with urllib.request.urlopen(NINFER_ARCHIVE_URL, timeout=120) as response, partial.open("wb") as out:
            shutil.copyfileobj(response, out, length=1024 * 1024)
        if digest(partial) != NINFER_ARCHIVE_SHA256:
            raise SystemExit("The downloaded NInfer converter archive failed checksum verification")
        os.replace(partial, archive)

    with tempfile.TemporaryDirectory(prefix="ninfer-source-", dir=WORK) as temp_name:
        temp = Path(temp_name)
        safe_extract(archive, temp)
        roots = [path for path in temp.iterdir() if path.is_dir()]
        if len(roots) != 1:
            raise SystemExit("The NInfer source archive has an unexpected layout")
        shutil.move(str(roots[0]), NINFER_SOURCE)
    marker.write_text(NINFER_COMMIT + "\n", encoding="utf-8")


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    fetch_checkpoint()
    graft_and_verify_frontend()
    fetch_ninfer_converter()
    manifest = {
        "base_repository": BASE_REPO,
        "base_revision": BASE_REVISION,
        "frontend_repository": FRONTEND_REPO,
        "frontend_revision": FRONTEND_REVISION,
        "ninfer_converter_commit": NINFER_COMMIT,
        "ninfer_archive_sha256": NINFER_ARCHIVE_SHA256,
        "frontend_sha256": load_frontend_pins(),
    }
    (WORK / "source-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("All pinned model-build inputs are ready.")


if __name__ == "__main__":
    main()
