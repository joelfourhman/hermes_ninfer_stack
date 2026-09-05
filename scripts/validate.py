#!/usr/bin/env python3
"""Hardware-independent repository validation for local use and CI."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parent.parent
EXPECTED_NINFER_COMMIT = "feaf4dd0983fdaeb2ba4c06eec6da350e644fb3a"
EXPECTED_CONVERTER_COMMIT = "b2b96bae4dd88f95b9ea8126d68fae3b88caa374"
EXPECTED_SOURCE_REVISION = "5bb7aa90f0efef548e87005b1fb7658e522b6b7f"
EXPECTED_STOCK_MODEL_FILE = "qwen3_8_27b_nvfp4.ninfer"
EXPECTED_UNCENSORED_MODEL_FILE = "qwen3_8_27b_uncensored.ninfer"
EXPECTED_MODEL_ID = "qwen-local"
EXPECTED_CONTEXT = "131072"
EXPECTED_KV_CAPACITY = "131072"
EXPECTED_CONCURRENCY = "1"
EXPECTED_REFERENCE_SHA256 = "714565ed29db4415322e9bc13a3464dc1fd8fcc911234740a79af67934e49969"

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
    "model-builder/frontend.sha256",
    "model-builder/fetcher/Dockerfile",
    "model-builder/fetcher/fetch_stock.py",
    "model-builder/fetcher/fetch_sources.py",
    "model-builder/fetcher/pyproject.toml",
    "model-builder/fetcher/uv.lock",
    "model-builder/converter/Dockerfile",
    "model-builder/converter/convert_model.py",
    "model-builder/converter/pyproject.toml",
    "model-builder/converter/uv.lock",
    "Makefile",
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
for secret_name in ("NINFER_API_KEY", "HF_TOKEN"):
    if env_values.get(secret_name) != "":
        error(f"{secret_name} must be empty in the reviewed .env.example template")

expected_env = {
    "NINFER_API_KEY": "",
    "HF_TOKEN": "",
    "NINFER_HOST_PORT": "8080",
    "NINFER_GPU_DEVICE": "0",
    "NINFER_MODEL_PROFILE": "stock",
    "NINFER_MODEL_FILE": EXPECTED_STOCK_MODEL_FILE,
    "NINFER_MODEL_ID": EXPECTED_MODEL_ID,
    "NINFER_CONTEXT_LENGTH": EXPECTED_CONTEXT,
    "NINFER_KV_CAPACITY": EXPECTED_KV_CAPACITY,
    "NINFER_MAX_CONCURRENCY": EXPECTED_CONCURRENCY,
    "HERMES_COMPRESSION_ENABLED": "true",
    "HERMES_COMPRESSION_THRESHOLD_TOKENS": "100000",
    "HERMES_MAX_TURNS": "40",
    "MODEL_BUILD_UID": "1000",
    "MODEL_BUILD_GID": "1000",
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
    expected_services = {"stock-model-fetcher", "model-fetcher", "model-converter", "ninfer"}
    if services != expected_services:
        error(
            "Compose services must be the two fetchers, model-converter, and ninfer; found "
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


stock_fetcher_service = service_block("stock-model-fetcher")
fetcher_service = service_block("model-fetcher")
converter_service = service_block("model-converter")
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
if "127.0.0.1:${NINFER_HOST_PORT:-8080}:8080" not in compose_text:
    error("NInfer must publish its authenticated API on host loopback only")
if "profiles: [tools]" not in compose_text:
    error("model build utilities must remain isolated behind the tools profile")
if "profiles:" in ninfer_service:
    error("NInfer must start normally without requiring a Compose profile")
if (
    "ports:" in stock_fetcher_service
    or "ports:" in fetcher_service
    or "ports:" in converter_service
    or compose_text.count("    ports:") != 1
):
    error("only NInfer may publish a host port")
if "./model-build:/work" not in fetcher_service:
    error("model-fetcher must write only to the ignored model-build directory")
if "./models:/models" not in stock_fetcher_service:
    error("stock-model-fetcher must write only to the local models directory")
if "./model-build:/work:ro" not in converter_service or "./models:/models" not in converter_service:
    error("model-converter must read build inputs and write only local model output")
if "./models:/models:ro" not in ninfer_service:
    error("NInfer must mount the local models directory read-only")
host_bind_mounts = re.findall(r"(?m)^\s+- (\./[^\s]+)\s*$", compose_text)
if sorted(host_bind_mounts) != sorted([
    "./model-build:/work",
    "./model-build:/work:ro",
    "./models:/models",
    "./models:/models",
    "./models:/models:ro",
]):
    error("containers have unexpected bind mounts")
if (
    "capabilities: [gpu]" not in ninfer_service
    or "device_ids: [\"${NINFER_GPU_DEVICE:-0}\"]" not in ninfer_service
):
    error("NInfer must request only the selected NVIDIA GPU")
if "capabilities: [gpu]" in fetcher_service:
    error("model-fetcher must not receive GPU access")
if "capabilities: [gpu]" in stock_fetcher_service:
    error("stock-model-fetcher must not receive GPU access")
if "capabilities: [gpu]" not in converter_service or "network_mode: none" not in converter_service:
    error("model-converter must receive the selected GPU without runtime network access")
if "${NINFER_API_KEY:?Run python ninfer.py setup to create .env}" not in ninfer_service:
    error("NInfer API authentication must fail closed until setup generates a key")
if compose_text.count("no-new-privileges:true") != 4 or compose_text.count("      - ALL") != 4:
    error("all four containers must drop Linux capabilities and forbid privilege escalation")
if compose_text.count("    init: true") != 4:
    error("all four containers must use a minimal init process for reliable shutdown")
if (
    "driver: local" not in ninfer_service
    or 'max-size: "10m"' not in ninfer_service
    or 'max-file: "3"' not in ninfer_service
):
    error("NInfer logs must be bounded to avoid silently filling the Docker disk")
if "internal: true" in compose_text:
    error("NInfer's host-loopback port cannot use an internal Docker network")

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


consistency_requirements = {
    "ninfer.py": [
        EXPECTED_NINFER_COMMIT,
        EXPECTED_STOCK_MODEL_FILE,
        EXPECTED_UNCENSORED_MODEL_FILE,
        "Choose a model:",
        "select-model",
        "install-hermes",
        "https://hermes-agent.nousresearch.com/desktop",
        "providers.ninfer",
        "custom:ninfer",
        "approvals.mode",
        "HERMES_WRITE_SAFE_ROOT",
        "terminal.cwd",
        "HERMES_COMPRESSION_ENABLED",
        "HERMES_COMPRESSION_THRESHOLD_TOKENS",
        "HERMES_MAX_TURNS",
    ],
    "docker-compose.yml": [
        EXPECTED_NINFER_COMMIT,
        EXPECTED_STOCK_MODEL_FILE,
        EXPECTED_MODEL_ID,
        EXPECTED_CONTEXT,
        EXPECTED_KV_CAPACITY,
        "13.1.2-runtime-ubuntu24.04",
        "127.0.0.1:${NINFER_HOST_PORT:-8080}:8080",
        "profiles: [tools]",
    ],
    "Makefile": ["install-hermes:", "python3 ninfer.py install-hermes"],
    "model-builder/fetcher/fetch_sources.py": [
        EXPECTED_SOURCE_REVISION,
        EXPECTED_CONVERTER_COMMIT,
    ],
    "model-builder/fetcher/fetch_stock.py": [
        EXPECTED_STOCK_MODEL_FILE,
        "204e3d92c30d9d05f3300d2f52e443ad1edf6ddf",
        "bb3360522a06e136e0367f5703414d26272b7285c8a6ab6194135c17dbd81b32",
    ],
    "model-builder/converter/Dockerfile": [
        "COPY --from=uv /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/",
        "nvidia/cuda:13.1.2-runtime-ubuntu24.04",
        "uv sync --no-dev --no-install-project",
    ],
    "model-builder/converter/convert_model.py": [
        EXPECTED_UNCENSORED_MODEL_FILE,
        EXPECTED_REFERENCE_SHA256,
        EXPECTED_SOURCE_REVISION,
        EXPECTED_CONVERTER_COMMIT,
    ],
    "scripts/verify.py": [
        EXPECTED_NINFER_COMMIT,
        EXPECTED_STOCK_MODEL_FILE,
        EXPECTED_UNCENSORED_MODEL_FILE,
        EXPECTED_REFERENCE_SHA256,
        "Optional native Hermes config",
        "providers.ninfer.api",
        "custom:ninfer",
        "approvals.mode",
        "HERMES_WRITE_SAFE_ROOT",
    ],
    "scripts/benchmark.py": [
        EXPECTED_NINFER_COMMIT,
        EXPECTED_STOCK_MODEL_FILE,
        EXPECTED_UNCENSORED_MODEL_FILE,
    ],
    "tests/test_ninfer.py": [
        "providers.ninfer.api",
        "custom:ninfer",
        "approvals.mode",
        "HERMES_WRITE_SAFE_ROOT",
        "terminal.cwd",
        "HERMES_COMPRESSION_ENABLED",
        "HERMES_COMPRESSION_THRESHOLD_TOKENS",
        "HERMES_MAX_TURNS",
    ],
    "docs/models.md": [
        EXPECTED_STOCK_MODEL_FILE,
        EXPECTED_UNCENSORED_MODEL_FILE,
        EXPECTED_MODEL_ID,
        EXPECTED_REFERENCE_SHA256,
        EXPECTED_SOURCE_REVISION,
        EXPECTED_CONVERTER_COMMIT,
    ],
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


if errors:
    print(f"Repository validation failed with {len(errors)} issue(s):", file=sys.stderr)
    for item in errors:
        print(f"  - {item}", file=sys.stderr)
    raise SystemExit(1)

print(f"Repository validation passed ({len(required_paths)} required files, {len(markdown_files)} documentation files).")
