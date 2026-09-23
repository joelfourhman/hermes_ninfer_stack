"""Reproducible v2 -> v3 upgrade using the pinned upstream converter.

Weight payloads are copied unchanged. Only framing and the maintained Qwen
template change. Originals are retained, and existing outputs are never replaced.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import uuid


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def upgrade(source: Path, output: Path, tools: Path, source_sha256: str) -> None:
    """Authenticate the input, then run the unmodified upstream copy converter."""
    if output.exists():
        raise FileExistsError(f"Preserving existing artifact: {output}")
    if sha256(source) != source_sha256:
        raise ValueError("Migration input failed its pinned SHA-256 check")
    # Git for Windows may check these resources out with CRLF. Canonicalize only
    # converter/template text, never the source artifact or its weight bytes.
    with tempfile.TemporaryDirectory(prefix="ninfer-upgrade-") as directory:
        canonical = Path(directory)
        (canonical / "chat_templates").mkdir()
        for relative in ("upgrade_ninfer_v2_to_v3.py", "chat_templates/qwen3_8.jinja",
                         "chat_templates/qwen3_6.jinja"):
            (canonical / relative).write_bytes((tools / relative).read_bytes().replace(b"\r\n", b"\n"))
        _run_upgrade(source, output, canonical, source_sha256)


def _run_upgrade(source: Path, output: Path, tools: Path, source_sha256: str) -> None:
    converter = tools / "upgrade_ninfer_v2_to_v3.py"
    spec = importlib.util.spec_from_file_location("ninfer_v3_upgrade", converter)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Upstream uses a random framing UUID. Make only that field reproducible so
    # installations can verify the entire derived artifact against our manifest.
    identity = uuid.uuid5(
        uuid.NAMESPACE_URL,
        "ninfer-stack-v3:" + source_sha256 + ":" + sha256(converter)
        + ":" + sha256(tools / "chat_templates/qwen3_8.jinja"),
    )
    module.uuid = SimpleNamespace(uuid4=lambda: identity)
    # The converter's Linux cache hints are optional on Windows; retain fsync.
    module.os = SimpleNamespace(**{name: getattr(os, name) for name in dir(os)})
    if not hasattr(os, "posix_fadvise"):
        module.os.posix_fadvise = lambda *args: None
        module.os.POSIX_FADV_DONTNEED = 0
    if not hasattr(os, "fdatasync"):
        module.os.fdatasync = os.fsync
    module.upgrade(source, output)
