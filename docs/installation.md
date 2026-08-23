# Installation

This guide installs the tested single-GPU stack: Hermes Agent for orchestration, NInfer for local
OpenAI-compatible inference, Qwen3.8-27B NVFP4 as the model artifact, and an isolated SSH sandbox
for terminal and file tools.

The stack targets one NVIDIA GeForce RTX 5090. NInfer is compiled for Blackwell `sm_120a`; this is
not a generic CUDA or CPU deployment.

## Prerequisites

- A 64-bit Linux container environment:
  - native Linux with Docker Engine and NVIDIA Container Toolkit; or
  - Docker Desktop using its WSL2 backend.
- NVIDIA GeForce RTX 5090 with a driver capable of running CUDA 13.1 containers.
- Docker Engine and Docker Compose. Compose 2.17.0 or newer is required for `up --wait-timeout`;
  Compose 5.3.0 is the locally audited version.
- Bash, Git, `curl`, `jq`, `make` (optional), and either OpenSSL or Python 3.
- About 24 GiB of free disk space for the 20.02 GiB model plus download staging.
- A Hugging Face `hf` CLI installation only for model download.

See [Compatibility](compatibility.md) for the exact host versions that were inspected.

## 1. Clone the repository and NInfer

NInfer is a pinned Git submodule. Clone it with the stack:

```bash
git clone --recurse-submodules https://github.com/joelfourhman/hermes_ninfer_stack.git hermes-ninfer-stack
cd hermes-ninfer-stack
```

For an existing clone that does not contain the NInfer source:

```bash
git submodule update --init --recursive
```

Confirm the pinned NInfer revision:

```bash
git -C ninfer rev-parse HEAD
```

Expected output:

```text
feaf4dd0983fdaeb2ba4c06eec6da350e644fb3a
```

Do not replace the submodule with an unpinned checkout. The Compose build uses the source at
`./ninfer` directly.

## 2. Verify Docker GPU access

Test the Docker-to-GPU path before building NInfer:

```bash
docker run --rm --gpus all \
  nvidia/cuda:13.1.2-base-ubuntu24.04 \
  nvidia-smi
```

The output must identify an RTX 5090. A successful host-side `nvidia-smi` is not sufficient: this
check also exercises Docker's NVIDIA runtime integration.

## 3. Initialize local configuration

Run the idempotent setup helper:

```bash
./scripts/setup.sh
```

The helper prepares the local directories, creates `.env` from the reviewed example, generates two
distinct API secrets, and copies `hermes/config.example.yaml` to the ignored live path
`hermes-data/config.yaml` when that file does not already exist. Existing `.env` and Hermes
configuration are preserved rather than silently replaced.

The following paths are local runtime data and must remain outside Git:

- `.env`
- `hermes-data/`
- downloaded files under `models/`
- generated content under `workspace/`

Review user-tunable values before building:

```bash
${EDITOR:-vi} .env
```

The defaults select GPU 0, model alias `qwen-local`, a 131,072-token context, and two active NInfer
requests. See [Configuration](configuration.md) before changing any of those coupled values.

## 4. Download the model

The helper displays the exact artifact, destination, size, and available disk space before asking
for confirmation:

```bash
./scripts/download-model.sh
```

If the `hf` command is not installed, create an isolated environment rather than installing a
project-wide Python dependency:

```bash
python3 -m venv .venv-hf
source .venv-hf/bin/activate
python -m pip install --upgrade huggingface_hub
./scripts/download-model.sh
```

The helper pins the Hugging Face revision and verifies the final SHA-256 checksum. No model is
downloaded by setup, image build, or CI. See [Models](models.md) for exact provenance and manual
download instructions.

## 5. Build the images

```bash
docker compose build
```

This compiles the pinned NInfer source with its CUDA 13.1.2 build image and builds the SSH sandbox.
Compose stamps the NInfer image with the pinned source revision and runtime-base provenance; the
verifier rejects a stale or differently labeled image. The model is mounted read-only at runtime
and is not copied into either image.

## 6. Start NInfer and the sandbox

Start the prerequisites first and wait for application health, not just container creation:

```bash
docker compose up -d --wait --wait-timeout 900 ninfer sandbox
docker compose ps
```

NInfer's first model load may take several minutes. Follow startup without changing the service:

```bash
docker compose logs -f ninfer
```

## 7. Complete the Hermes first-run setup

Run the official Hermes wizard once:

```bash
docker compose run --rm --no-deps hermes setup
```

Use the wizard for Hermes identity and any messaging integration you intentionally want to enable.
Those answers are written under ignored `hermes-data/` and are not repository configuration.

The wizard may update model settings. Reapply the stack-owned NInfer and SSH sandbox fields:

```bash
./scripts/configure-hermes.sh
```

The helper uses the supported `hermes config` interface and checks the result. Run it while the
long-running Hermes service is stopped.

## 8. Start and verify the complete stack

```bash
docker compose up -d
./scripts/verify.sh
```

Verification checks the GPU, model checksum, NInfer health and API, Hermes-to-NInfer inference,
sandbox networking, and a real terminal tool side effect. A healthy container alone is not treated
as proof that inference or tool execution works.

## Routine operation

```bash
docker compose up -d
docker compose ps
docker compose logs -f
docker compose down
```

`docker compose down` preserves bind-mounted data and named volumes. Do not add `-v` unless you
intend to delete the sandbox home, SSH client identity, and SSH host identity.

For installation failures, continue with [Troubleshooting](troubleshooting.md).
