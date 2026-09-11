"""Fail-closed checks for source, executable contract, images and model bytes."""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

from stack.config import MANIFEST, MODEL_PROFILES, NINFER_COMMIT


def verify_cli_help(help_text: str) -> None:
    flags = set(re.findall(r"--[a-z][a-z0-9-]*", help_text))
    missing = set(MANIFEST["ninfer"]["required_cli_flags"]) - flags
    if missing:
        raise ValueError(
            "NInfer CLI contract changed; missing: " + ", ".join(sorted(missing))
        )
    for choice in ("mtp", "dflash2", "fp8"):
        if choice not in help_text:
            raise ValueError(f"NInfer CLI no longer advertises {choice}")


def verify_source(root: Path, *, check_index: bool = False) -> str:
    def git(*args: str) -> str:
        return subprocess.check_output(
            ["git", *args], cwd=root, text=True, stderr=subprocess.PIPE
        ).strip()

    source = root / "ninfer"
    actual = git("-C", str(source), "rev-parse", "HEAD")
    if actual != NINFER_COMMIT:
        raise ValueError(
            f"NInfer submodule HEAD is {actual}; manifest expects {NINFER_COMMIT}. Run setup."
        )
    if git("-C", str(source), "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("NInfer source is dirty; refusing a misleading image revision")
    if check_index:
        entry = git("ls-files", "--stage", "--", "ninfer").split()
        if entry[:2] != ["160000", NINFER_COMMIT]:
            raise ValueError(
                "NInfer gitlink differs from manifest; stage the audited submodule update"
            )
    # Fast offline contract check; the built binary's --help is also checked live.
    verify_cli_help(
        (source / "src/serve/serve_options.cpp").read_text(encoding="utf-8")
    )
    return actual


def verify_image(labels: dict[str, str]) -> None:
    if labels.get("org.opencontainers.image.revision") != NINFER_COMMIT:
        raise ValueError(
            "Image source revision differs from manifest; rebuild and recreate NInfer"
        )
    if (
        labels.get("org.opencontainers.image.base.name")
        != MANIFEST["ninfer"]["cuda_base"]
    ):
        raise ValueError("Image CUDA base differs from manifest")


def verify_model(path: Path, key: str) -> str:
    model = MODEL_PROFILES[key]
    if (
        path.name != model.filename
        or not path.is_file()
        or path.stat().st_size != model.expected_bytes
    ):
        raise ValueError(f"Model artifact name/size does not match {key} manifest")
    checksum = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            checksum.update(chunk)
    if checksum.hexdigest() != model.sha256:
        raise ValueError(
            f"Model SHA-256 differs from {key} manifest; existing bytes were preserved"
        )
    return checksum.hexdigest()
