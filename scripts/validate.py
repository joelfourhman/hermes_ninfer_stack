#!/usr/bin/env python3
"""Hardware-independent repository validation for local use and CI."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from stack.config import MANIFEST, MODEL_PROFILES, RUNTIME_PROFILES, runtime_env_values, validate_manifest
from stack.documentation import generate
from stack.provenance import verify_source
EXPECTED_NINFER_COMMIT = MANIFEST["ninfer"]["commit"]
EXPECTED_STOCK_MODEL_FILE = MODEL_PROFILES["stock"].filename
EXPECTED_UNCENSORED_MODEL_FILE = MODEL_PROFILES["uncensored"].filename
EXPECTED_MODEL_ID = "qwen3.8-27b-stock-ctx131072"
DEFAULT_RUNTIME = runtime_env_values(RUNTIME_PROFILES[MANIFEST["defaults"]["runtime"]])

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
    "ninfer.py",
    "model-downloader/Dockerfile",
    "model-downloader/download_model.py",
    "model-downloader/pyproject.toml",
    "model-downloader/uv.lock",
    "scripts/verify.py",
    "scripts/benchmark.py",
    "tests/test_ninfer.py",
    "docs/architecture.md",
    "docs/installation.md",
    "docs/configuration.md",
    "docs/models.md",
    "docs/troubleshooting.md",
    "docs/security.md",
    "docs/performance.md",
    "docs/compatibility.md",
    "docs/design-overview.md",
    "docs/decisions/0005-stock-native-hermes-desktop.md",
    "docs/decisions/0006-locally-built-uncensored-model.md",
    "docs/decisions/0007-selectable-model-profiles.md",
    "docs/decisions/0008-stock-hermes-working-directory.md",
    "docs/decisions/0009-direct-model-downloads.md",
    "docs/decisions/0010-runtime-profiles-and-context-cache.md",
    ".github/workflows/ci.yml",
    "stack/manifest.json",
    "stack/config.py",
    "stack/jobs.py",
    "docs/generated-config.md",
    "docs/jobs.md",
    "AUDIT.md",
    "BENCHMARK_PLAN.md",
    "BENCHMARK_RESULTS.md",
    "FINAL_REPORT.md",
    "pyproject.toml",
    "requirements-dev.txt",
    "benchmarks/measured-summary.json",
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
for secret_name in ("NINFER_API_KEY", "HF_TOKEN"):
    if env_values.get(secret_name) != "":
        error(f"{secret_name} must be empty in the reviewed .env.example template")

expected_env = {
    "NINFER_API_KEY": "",
    "HF_TOKEN": "",
    "NINFER_ACCESS_MODE": "local",
    "NINFER_BIND_ADDRESS": "127.0.0.1",
    "NINFER_HOST_PORT": "8080",
    "NINFER_GPU_DEVICE": "0",
    "NINFER_MODEL_PROFILE": "stock",
    "NINFER_MODEL_FILE": EXPECTED_STOCK_MODEL_FILE,
    "NINFER_MODEL_ID": EXPECTED_MODEL_ID,
    "NINFER_RUNTIME_PROFILE": "balanced",
    "NINFER_CONTEXT_LENGTH": DEFAULT_RUNTIME["NINFER_CONTEXT_LENGTH"],
    "NINFER_KV_CAPACITY": DEFAULT_RUNTIME["NINFER_KV_CAPACITY"],
    "NINFER_MAX_CONCURRENCY": DEFAULT_RUNTIME["NINFER_MAX_CONCURRENCY"],
    "NINFER_PENDING_TIMEOUT_MS": "120000",
    "NINFER_KV_DTYPE": "fp8",
    "NINFER_DEVICE_STATE_SLOTS": "2",
    "NINFER_HOST_STATE_SLOTS": "8",
    "NINFER_HOST_KV_MIB": "8192",
    "NINFER_PRESERVE_THINKING": "true",
    "HERMES_COMPRESSION_ENABLED": "true",
    "HERMES_COMPRESSION_THRESHOLD_TOKENS": DEFAULT_RUNTIME["HERMES_COMPRESSION_THRESHOLD_TOKENS"],
    "HERMES_MAX_TURNS": DEFAULT_RUNTIME["HERMES_MAX_TURNS"],
    "NINFER_SOURCE_REVISION": EXPECTED_NINFER_COMMIT,
    "NINFER_SPEC_BACKEND": "mtp",
    "NINFER_DRAFT_TOKENS": "3",
    "MODEL_DOWNLOAD_UID": "1000",
    "MODEL_DOWNLOAD_GID": "1000",
}
for key, expected in expected_env.items():
    if env_values.get(key) != expected:
        error(f".env.example {key} must be {expected!r}")
if set(env_keys) != set(expected_env):
    unexpected = sorted(set(env_keys) - set(expected_env))
    omitted = sorted(set(expected_env) - set(env_keys))
    details = []
    if unexpected:
        details.append("unexpected: " + ", ".join(unexpected))
    if omitted:
        details.append("missing: " + ", ".join(omitted))
    error(".env.example must contain only the reviewed setup keys (" + "; ".join(details) + ")")


services_match = re.search(r"(?ms)^services:\s*\n(.*?)(?=^[^ \t\r\n]|\Z)", compose_text)
if services_match is None:
    error("docker-compose.yml has no services block")
else:
    services = set(re.findall(r"(?m)^  ([a-z0-9][a-z0-9-]*):\s*$", services_match.group(1)))
    expected_services = {"model-downloader", "ninfer"}
    if services != expected_services:
        error(
            "Compose services must be model-downloader and ninfer; found "
            + ", ".join(sorted(services))
        )


def service_block(name: str) -> str:
    if services_match is None:
        return ""
    match = re.search(
        rf"(?ms)^  {re.escape(name)}:\s*\n(.*?)(?=^  [a-z0-9][a-z0-9-]*:\s*$|\Z)",
        services_match.group(1),
    )
    if match is None:
        error(f"cannot inspect Compose service: {name}")
        return ""
    return match.group(1)


downloader_service = service_block("model-downloader")
ninfer_service = service_block("ninfer")

networks_match = re.search(r"(?ms)^networks:\s*\n(.*?)(?=^[^ \t\r\n]|\Z)", compose_text)
if networks_match is None:
    error("docker-compose.yml has no networks block")
else:
    networks = set(re.findall(r"(?m)^  ([a-z0-9][a-z0-9-]*):\s*$", networks_match.group(1)))
    if networks != {"inference-net"}:
        error("Compose networks must contain only inference-net")

if re.search(r"(?m)^volumes:\s*$", compose_text):
    error("Compose must not declare container-era named volumes")
if "HERMES_" in compose_text or re.search(r"(?im)^\s*(?:hermes|sandbox|sandbox-[a-z0-9-]*|ninfer-loopback):\s*$", compose_text):
    error("Compose still contains a Hermes, relay, or SSH-sandbox runtime dependency")
if "${NINFER_BIND_ADDRESS:-127.0.0.1}:${NINFER_HOST_PORT:-8080}:8080" not in compose_text:
    error("NInfer must publish its authenticated API on the selected host address")
if "profiles: [tools]" not in compose_text:
    error("the model downloader must remain isolated behind the tools profile")
if "profiles:" in ninfer_service:
    error("NInfer must start normally without requiring a Compose profile")
if "ports:" in downloader_service or compose_text.count("    ports:") != 1:
    error("only NInfer may publish a host port")
if "./models:/models" not in downloader_service:
    error("model-downloader must write only to the local models directory")
if "./models:/models:ro" not in ninfer_service:
    error("NInfer must mount the local models directory read-only")
host_bind_mounts = re.findall(r"(?m)^\s+- (\./[^\s]+)\s*$", compose_text)
if sorted(host_bind_mounts) != sorted([
    "./models:/models",
    "./models:/models:ro",
]):
    error("containers have unexpected bind mounts")
if (
    "capabilities: [gpu]" not in ninfer_service
    or "device_ids: [\"${NINFER_GPU_DEVICE:-0}\"]" not in ninfer_service
):
    error("NInfer must request only the selected NVIDIA GPU")
if "capabilities: [gpu]" in downloader_service:
    error("model-downloader must not receive GPU access")
if "${NINFER_API_KEY:?Run python ninfer.py setup to create .env}" not in ninfer_service:
    error("NInfer API authentication must fail closed until setup generates a key")
if compose_text.count("no-new-privileges:true") != 2 or compose_text.count("      - ALL") != 2:
    error("both containers must drop Linux capabilities and forbid privilege escalation")
if compose_text.count("    init: true") != 2:
    error("both containers must use a minimal init process for reliable shutdown")
if compose_text.count("    read_only: true") != 2:
    error("both containers must use read-only root filesystems")
if "/tmp:size=256m,mode=1777" not in ninfer_service:
    error("NInfer must receive only a bounded temporary writable filesystem")
if (
    "driver: local" not in ninfer_service
    or 'max-size: "10m"' not in ninfer_service
    or 'max-file: "3"' not in ninfer_service
):
    error("NInfer logs must be bounded to avoid silently filling the Docker disk")
if "internal: true" in compose_text:
    error("NInfer's published host port cannot use an internal Docker network")

unsafe_compose_patterns = {
    r"(?m)^\s*privileged:\s*true\s*$": "privileged containers",
    r"(?m)^\s*network_mode:\s*host\s*$": "host networking",
    r"(?m)^\s*pid:\s*host\s*$": "host PID access",
    r"(?m)^\s*ipc:\s*host\s*$": "host IPC access",
    r"(?:/var/run/docker\.sock|docker_engine)": "Docker daemon access",
}
for pattern, description in unsafe_compose_patterns.items():
    if re.search(pattern, compose_text, flags=re.IGNORECASE):
        error(f"Compose must not grant {description}")


try:
    validate_manifest()
    generate(check=True)
    verify_source(ROOT)
except (ValueError, OSError, subprocess.CalledProcessError) as exc:
    error(str(exc))
for key, value in DEFAULT_RUNTIME.items():
    if env_values.get(key) != value:
        error(f"Default profile/env drift: {key}")
if "${NINFER_SOURCE_REVISION:?" not in ninfer_service:
    error("Image revision must derive from generated manifest projection")
for flag in MANIFEST["ninfer"]["required_cli_flags"]:
    if f"      - {flag}\n" not in ninfer_service:
        error(f"Compose is missing required flag {flag}")
for flag, key in {"--spec": "NINFER_SPEC_BACKEND", "--draft-tokens": "NINFER_DRAFT_TOKENS"}.items():
    if not re.search(re.escape("- " + flag) + r"\s+- \$\{" + key, ninfer_service):
        error(f"Compose {flag} must use {key}")

markdown_files = [ROOT / "README.md", ROOT / "CONTRIBUTING.md", ROOT / "SECURITY.md", ROOT / "CHANGELOG.md"]
markdown_files.extend(ROOT / name for name in (
    "AUDIT.md", "BENCHMARK_PLAN.md", "BENCHMARK_RESULTS.md", "FINAL_REPORT.md", "PROJECT_STATE.md"
))
markdown_files.extend(sorted((ROOT / "docs").rglob("*.md")))
markdown_files.extend(sorted((ROOT / ".github").rglob("*.md")))
markdown_files.append(ROOT / "benchmarks/README.md")
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

native_helper_test = ROOT / "tests" / "test_ninfer.py"
if native_helper_test.is_file() and native_helper_test not in public_text_files:
    public_text_files.append(native_helper_test)

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

submodule_stage = git("ls-files", "--stage", "--", "ninfer", check=False)
if not submodule_stage.stdout.strip():
    error("ninfer is not recorded in the Git index")
elif not submodule_stage.stdout.startswith("160000 "):
    error("ninfer must be recorded as a Git submodule (mode 160000)")
elif submodule_stage.stdout.split()[1] != EXPECTED_NINFER_COMMIT:
    error("Staged NInfer gitlink differs from stack/manifest.json")


if errors:
    print(f"Repository validation failed with {len(errors)} issue(s):", file=sys.stderr)
    for item in errors:
        print(f"  - {item}", file=sys.stderr)
    raise SystemExit(1)

print(f"Repository validation passed ({len(required_paths)} required files, {len(markdown_files)} documentation files).")
