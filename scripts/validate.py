#!/usr/bin/env python3
"""Hardware-independent repository validation for local use and CI."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parent.parent
EXPECTED_NINFER_COMMIT = "feaf4dd0983fdaeb2ba4c06eec6da350e644fb3a"
EXPECTED_MODEL_FILE = "qwen3_8_27b_nvfp4.ninfer"
EXPECTED_MODEL_ID = "qwen-local"
EXPECTED_CONTEXT = "131072"
EXPECTED_MODEL_SHA256 = "bb3360522a06e136e0367f5703414d26272b7285c8a6ab6194135c17dbd81b32"

errors: list[str] = []


def error(message: str) -> None:
    errors.append(message)


def read_text(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return handle.read()
    except (OSError, UnicodeDecodeError) as exc:
        error(f"cannot read {path.relative_to(ROOT)}: {exc}")
        return ""


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


required_paths = [
    "README.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CHANGELOG.md",
    ".env.example",
    ".gitignore",
    ".gitmodules",
    "docker-compose.yml",
    "stack.py",
    "model-downloader/Dockerfile",
    "model-downloader/download_model.py",
    "Makefile",
    "hermes/config.example.yaml",
    "sandbox/Dockerfile",
    "sandbox/entrypoint.sh",
    "scripts/setup.sh",
    "scripts/configure-hermes.sh",
    "scripts/download-model.sh",
    "scripts/verify.sh",
    "scripts/verify.py",
    "scripts/benchmark.sh",
    "scripts/benchmark.py",
    "docs/architecture.md",
    "docs/installation.md",
    "docs/configuration.md",
    "docs/models.md",
    "docs/troubleshooting.md",
    "docs/security.md",
    "docs/performance.md",
    "docs/compatibility.md",
    "docs/design-overview.md",
    ".github/workflows/ci.yml",
]
for relative in required_paths:
    if not (ROOT / relative).is_file():
        error(f"missing required file: {relative}")


env_text = read_text(ROOT / ".env.example")
compose_text = read_text(ROOT / "docker-compose.yml")
env_pairs = re.findall(r"^([A-Z][A-Z0-9_]*)=(.*)$", env_text, flags=re.MULTILINE)
env_keys = [key for key, _ in env_pairs]
if len(env_keys) != len(set(env_keys)):
    error(".env.example contains duplicate variable names")
compose_vars = set(re.findall(r"\$\{([A-Z][A-Z0-9_]*)", compose_text))
missing_env = sorted(compose_vars - set(env_keys))
if missing_env:
    error("Compose variables missing from .env.example: " + ", ".join(missing_env))

env_values = dict(env_pairs)
for secret_name in (
    "NINFER_API_KEY",
    "HERMES_API_SERVER_KEY",
    "HERMES_DASHBOARD_PASSWORD",
    "HERMES_DASHBOARD_SECRET",
):
    if env_values.get(secret_name) != "":
        error(f"{secret_name} must be empty in .env.example so Compose fails closed")

expected_env = {
    "NINFER_MODEL_FILE": EXPECTED_MODEL_FILE,
    "NINFER_MODEL_ID": EXPECTED_MODEL_ID,
    "NINFER_CONTEXT_LENGTH": EXPECTED_CONTEXT,
}
for key, expected in expected_env.items():
    if env_values.get(key) != expected:
        error(f".env.example {key} must be {expected!r}")


consistency_requirements = {
    "stack.py": [
        EXPECTED_NINFER_COMMIT,
        EXPECTED_MODEL_FILE,
        "Download and verify the model now?",
        "Blank Slate",
        "Keep current (ssh)",
    ],
    "docker-compose.yml": [EXPECTED_NINFER_COMMIT, EXPECTED_MODEL_FILE, EXPECTED_MODEL_ID, EXPECTED_CONTEXT, "13.1.2-runtime-ubuntu24.04"],
    "hermes/config.example.yaml": [EXPECTED_MODEL_ID, EXPECTED_CONTEXT],
    "scripts/setup.sh": [EXPECTED_NINFER_COMMIT],
    "model-downloader/download_model.py": [EXPECTED_MODEL_FILE, EXPECTED_MODEL_SHA256],
    "scripts/verify.py": [EXPECTED_NINFER_COMMIT, EXPECTED_MODEL_FILE, EXPECTED_MODEL_SHA256],
    "scripts/benchmark.py": [EXPECTED_NINFER_COMMIT, EXPECTED_MODEL_SHA256],
    "sandbox/Dockerfile": [
        "sha256:33ceb71981b602c1a7443a53469e4dba065f7503eab3078a2d7a57a2ab987517",
        "sha256:d1e005e6f5aac724b7554db95f1c128a77d8d35b59ebe70e188852b4bdad3a3d",
    ],
    "docs/models.md": [EXPECTED_MODEL_FILE, EXPECTED_MODEL_ID, EXPECTED_MODEL_SHA256],
}
for relative, values in consistency_requirements.items():
    text = read_text(ROOT / relative)
    for value in values:
        if value not in text:
            error(f"{relative} is missing pinned value {value}")


markdown_files = [ROOT / "README.md", ROOT / "CONTRIBUTING.md", ROOT / "SECURITY.md", ROOT / "CHANGELOG.md"]
markdown_files.extend(sorted((ROOT / "docs").rglob("*.md")))
markdown_files.extend(sorted((ROOT / ".github").rglob("*.md")))
markdown_files.extend([ROOT / "workspace/README.md", ROOT / "benchmarks/README.md"])
link_pattern = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
for markdown in markdown_files:
    if not markdown.is_file():
        continue
    text = read_text(markdown)
    for raw_target in link_pattern.findall(text):
        target = raw_target.strip()
        if target.startswith("<") and ">" in target:
            target = target[1 : target.index(">")]
        elif " " in target:
            target = target.split(" ", 1)[0]
        target = unquote(target)
        parsed = urlsplit(target)
        if parsed.scheme in {"http", "https", "mailto"} or target.startswith("#"):
            continue
        path_part = target.split("#", 1)[0].split("?", 1)[0]
        if not path_part:
            continue
        resolved = (markdown.parent / path_part).resolve()
        try:
            resolved.relative_to(ROOT)
        except ValueError:
            error(f"{markdown.relative_to(ROOT)} links outside the repository: {target}")
            continue
        if not resolved.exists():
            error(f"broken local link in {markdown.relative_to(ROOT)}: {target}")


tracked_result = git("ls-files", "-z", check=False)
if tracked_result.returncode != 0:
    error("could not enumerate tracked repository files")
    tracked_relatives: list[str] = []
else:
    tracked_relatives = [item for item in tracked_result.stdout.split("\0") if item]

public_text_files: list[Path] = []
text_names = {
    "Makefile",
    "LICENSE",
    "Dockerfile",
    "sshd_config",
    ".env.example",
    ".gitignore",
    ".gitattributes",
    ".gitmodules",
    ".dockerignore",
}
text_suffixes = {".md", ".yml", ".yaml", ".sh", ".py", ".txt"}
for relative_name in tracked_relatives:
    path = ROOT / relative_name
    if not path.is_file():
        continue
    if path.name in text_names or path.suffix.lower() in text_suffixes:
        public_text_files.append(path)

machine_patterns = [
    re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+", re.IGNORECASE),
    re.compile(r"/mnt/[a-z]/Users/", re.IGNORECASE),
    re.compile(r"\b" + "joe" + "lf" + r"\b", re.IGNORECASE),
]
secret_patterns = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bgh[opusr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"https?://[^\s/:]+:[^\s/@]+@", re.IGNORECASE),
]
for path in public_text_files:
    text = read_text(path)
    for pattern in machine_patterns:
        if pattern.search(text):
            error(f"machine-specific path or username in {path.relative_to(ROOT)}")
            break
    for pattern in secret_patterns:
        if pattern.search(text):
            error(f"possible credential or private key in {path.relative_to(ROOT)}")
            break
    if "\r\n" in text:
        error(f"CRLF line endings in {path.relative_to(ROOT)}")
    for number, line in enumerate(text.splitlines(), start=1):
        if line.rstrip() != line:
            error(f"trailing whitespace in {path.relative_to(ROOT)}:{number}")


for relative_name in tracked_relatives:
    path = ROOT / relative_name
    if not path.is_file():
        continue
    if path.stat().st_size > 50 * 1024 * 1024:
        error(f"unexpected tracked file larger than 50 MiB: {relative_name}")


ignore_probes = [
    ".env",
    "hermes-data/config.yaml",
    "models/test.ninfer",
    "accidental-model.gguf",
    "workspace/private.txt",
    "benchmarks/run/result.json",
    "id_ed25519",
    "private.key",
]
for probe in ignore_probes:
    result = git("check-ignore", "--quiet", "--", probe, check=False)
    if result.returncode != 0:
        error(f".gitignore does not protect representative private artifact: {probe}")


if not (ROOT / "ninfer" / ".git").exists():
    error("NInfer submodule is not initialized")

try:
    ninfer_commit = subprocess.run(
        ["git", "-C", str(ROOT / "ninfer"), "rev-parse", "HEAD"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()
    if ninfer_commit != EXPECTED_NINFER_COMMIT:
        error(f"NInfer submodule is {ninfer_commit}; expected {EXPECTED_NINFER_COMMIT}")
except (OSError, subprocess.CalledProcessError):
    error("NInfer submodule is not initialized")

ninfer_status = subprocess.run(
    ["git", "-C", str(ROOT / "ninfer"), "status", "--porcelain", "--untracked-files=all"],
    check=False,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
if ninfer_status.returncode != 0:
    error("could not inspect the NInfer submodule worktree")
elif ninfer_status.stdout.strip():
    error("NInfer submodule has local or untracked changes")

gitmodules = read_text(ROOT / ".gitmodules")
if "https://github.com/Neroued/ninfer.git" not in gitmodules:
    error(".gitmodules does not declare the canonical NInfer URL")

stage = git("ls-files", "--stage", "--", "scripts", "sandbox/entrypoint.sh", check=False)
if stage.returncode != 0 or not stage.stdout.strip():
    error("executable scripts are not recorded in the Git index")
else:
    for line in stage.stdout.splitlines():
        mode, _, _, name = line.split(maxsplit=3)
        if (name.startswith("scripts/") and name.endswith(".sh")) or name == "sandbox/entrypoint.sh":
            if mode != "100755":
                error(f"executable must be committed with mode 100755: {name} (is {mode})")

submodule_stage = git("ls-files", "--stage", "--", "ninfer", check=False)
if not submodule_stage.stdout.strip():
    error("ninfer is not recorded in the Git index")
elif not submodule_stage.stdout.startswith("160000 "):
    error("ninfer must be recorded as a Git submodule (mode 160000)")


if errors:
    print(f"Repository validation failed with {len(errors)} issue(s):", file=sys.stderr)
    for item in errors:
        print(f"  - {item}", file=sys.stderr)
    raise SystemExit(1)

print(f"Repository validation passed ({len(required_paths)} required files, {len(markdown_files)} documentation files).")
