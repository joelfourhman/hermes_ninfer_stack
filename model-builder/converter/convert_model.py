#!/usr/bin/env python3
"""Convert pinned source weights and atomically promote the verified artifact."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


WORK = Path("/work")
CHECKPOINT = WORK / "checkpoint"
NINFER_SOURCE = WORK / "ninfer-converter"
MODELS = Path("/models")
MODEL_NAME = "qwen3_8_27b_uncensored.ninfer"
MODEL_FILE = MODELS / MODEL_NAME
PARTIAL_FILE = MODELS / f".{MODEL_NAME}.partial"
MANIFEST_FILE = MODELS / f"{MODEL_NAME}.local-manifest.json"
CONVERSION_REPORT = MODELS / f"{MODEL_NAME}.conversion.json"
EXPECTED_BYTES = 18_210_531_328
REFERENCE_SHA256 = "714565ed29db4415322e9bc13a3464dc1fd8fcc911234740a79af67934e49969"
BASE_REPO = "JonathanColetti/Qwen3.8-27B-Uncensored"
BASE_REVISION = "5bb7aa90f0efef548e87005b1fb7658e522b6b7f"
NINFER_COMMIT = "b2b96bae4dd88f95b9ea8126d68fae3b88caa374"


def digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def existing_is_verified() -> bool:
    if not MODEL_FILE.is_file() or not MANIFEST_FILE.is_file():
        return False
    try:
        manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if MODEL_FILE.stat().st_size != EXPECTED_BYTES:
        return False
    actual = digest(MODEL_FILE)
    if actual != manifest.get("sha256"):
        raise SystemExit(
            f"Existing artifact checksum mismatch: manifest has {manifest.get('sha256')}, got {actual}"
        )
    print(f"Existing locally built artifact verified: {actual}")
    return True


def validate_inputs() -> None:
    source_manifest = json.loads((WORK / "source-manifest.json").read_text(encoding="utf-8"))
    expected = {
        "base_repository": BASE_REPO,
        "base_revision": BASE_REVISION,
        "ninfer_converter_commit": NINFER_COMMIT,
    }
    for key, wanted in expected.items():
        if source_manifest.get(key) != wanted:
            raise SystemExit(f"Source manifest {key} is not the pinned value {wanted}")
    if not (CHECKPOINT / "model.safetensors.index.json").is_file():
        raise SystemExit("Pinned checkpoint is incomplete; rerun the model fetch step")
    if not (NINFER_SOURCE / "tools" / "convert" / "qwen3_8_27b" / "convert.py").is_file():
        raise SystemExit("Pinned NInfer converter is incomplete; rerun the model fetch step")


def validate_report(report_path: Path) -> dict[str, object]:
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Conversion report is missing or invalid: {exc}") from exc
    flattened = json.dumps(report, sort_keys=True)
    for marker in ("qwen3_8_27b-v1", "qwen3_8_27b", "groupwise"):
        if marker not in flattened:
            raise SystemExit(f"Conversion report does not identify expected marker: {marker}")
    return report


def main() -> None:
    MODELS.mkdir(parents=True, exist_ok=True)
    if existing_is_verified():
        return
    validate_inputs()
    if MODEL_FILE.exists() and not MANIFEST_FILE.exists():
        raise SystemExit(
            f"Refusing to overwrite unverified {MODEL_FILE}. Move it aside explicitly and rerun."
        )

    PARTIAL_FILE.unlink(missing_ok=True)
    partial_report = Path(str(PARTIAL_FILE) + ".conversion.json")
    partial_report.unlink(missing_ok=True)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(NINFER_SOURCE)
    command = [
        sys.executable,
        "-m",
        "tools.convert.qwen3_8_27b.convert",
        "--model",
        str(CHECKPOINT),
        "--out",
        str(PARTIAL_FILE),
        "--device",
        "cuda",
    ]
    print("Converting the pinned checkpoint with NInfer's groupwise-int recipe...")
    subprocess.run(command, cwd=NINFER_SOURCE, env=environment, check=True)
    if not PARTIAL_FILE.is_file():
        raise SystemExit("Conversion completed without producing an artifact")
    if PARTIAL_FILE.stat().st_size != EXPECTED_BYTES:
        raise SystemExit(
            f"Converted artifact has {PARTIAL_FILE.stat().st_size:,} bytes; "
            f"expected {EXPECTED_BYTES:,}"
        )
    report = validate_report(partial_report)
    actual_sha256 = digest(PARTIAL_FILE)
    manifest = {
        "artifact": MODEL_NAME,
        "bytes": EXPECTED_BYTES,
        "sha256": actual_sha256,
        "reference_sha256": REFERENCE_SHA256,
        "matches_reference": actual_sha256 == REFERENCE_SHA256,
        "base_repository": BASE_REPO,
        "base_revision": BASE_REVISION,
        "ninfer_converter_commit": NINFER_COMMIT,
        "recipe": "qwen3_8_27b-v1",
        "conversion_device": "cuda",
    }
    temp_manifest = MANIFEST_FILE.with_suffix(MANIFEST_FILE.suffix + ".partial")
    temp_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(partial_report, CONVERSION_REPORT)
    os.replace(temp_manifest, MANIFEST_FILE)
    # The final artifact name is the commit point. Verification metadata may exist
    # briefly without an artifact, but the runtime can never see a half-promoted
    # model under its configured filename.
    os.replace(PARTIAL_FILE, MODEL_FILE)
    print(f"Built and verified {MODEL_FILE}")
    print(f"SHA-256: {actual_sha256}")
    if actual_sha256 != REFERENCE_SHA256:
        print("The checksum differs from the published reference, as permitted for GPU rounding variance.")


if __name__ == "__main__":
    main()
