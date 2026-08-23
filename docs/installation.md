# Installation

This guide installs the tested single-GPU stack: Hermes Agent for orchestration, NInfer for local
OpenAI-compatible inference, Qwen3.8-27B NVFP4 as the model artifact, and an isolated SSH sandbox
for terminal and file tools.

The stack targets one NVIDIA GeForce RTX 5090. NInfer is compiled for Blackwell `sm_120a`; this is
not a generic CUDA or CPU deployment.

## Prerequisites

- A 64-bit Linux container environment:
  - native Linux with Docker Engine and NVIDIA Container Toolkit; or
  - Docker Desktop (its Linux backend is managed by Docker Desktop; no WSL shell is required).
- NVIDIA GeForce RTX 5090 with a driver capable of running CUDA 13.1 containers.
- Docker Engine and Docker Compose. Compose 2.17.0 or newer is required for `up --wait-timeout`;
  Compose 5.3.0 is the locally audited version.
- Python 3.11 or newer and Git. The host does not need Bash, PowerShell, `pip`, `uv`, `curl`,
  `jq`, or `make`.
- About 24 GiB of free disk space for the 20.02 GiB model plus download staging.

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

## 3. Run the complete interactive setup

One cross-platform Python command performs the complete first run:

```text
python stack.py setup
```

The command is resumable and performs these stages in order:

1. Initialize the pinned NInfer submodule, ignored local directories, `.env`, random secrets, and
   the reviewed Hermes baseline without replacing existing local state.
2. Display the exact 20.02 GiB model transfer and ask whether to download it. Nothing is downloaded
   unless the owner answers `y` or `yes`. Declining pauses setup safely; rerun the same command later.
3. Download through a digest-pinned, uv-managed Compose utility and verify the final SHA-256.
4. Build the pinned images, start NInfer and the SSH sandbox, and wait for application health.
5. Open the official Hermes wizard, restore the stack-owned provider and terminal fields afterward,
   and start the complete stack.

Nothing is installed into the host Python environment. CI and ordinary image builds never download
the model. The standalone `python stack.py download-model` command remains available for recovery,
checksum verification, or manually resuming model acquisition.

Use these choices when the Hermes wizard opens:

1. **Blank Slate**
2. **ninfer (currently active)**
3. **qwen-local**
4. **Keep current (ssh)**
5. **Start with everything disabled — finish now**

Blank Slate deliberately clears the provider during the wizard and may finish with a “no inference
provider is configured” warning. This is expected. Do not enter a Nous Portal or external-provider
API key: `python stack.py setup` immediately reapplies `http://ninfer:8080/v1`, `qwen-local`, and the
SSH sandbox through Hermes's supported configuration interface after the wizard exits.

Choose **Walk through all configurations** at the final prompt only when intentionally enabling a
messaging integration or optional tool. Those choices remain in ignored `hermes-data/`; the setup
command still restores only the fields owned by this stack.

Once setup has completed, later runs preserve the wizard choices and skip it. Use
`python stack.py setup --rerun-wizard` to intentionally run it again. Existing `.env`, Hermes data,
model bytes, and workspace content remain preserved.

The following paths are local runtime data and must remain outside Git:

- `.env`
- `hermes-data/`
- downloaded files under `models/`
- generated content under `workspace/`

## 4. Verify the complete stack

```text
python stack.py verify
```

Verification checks the GPU, model checksum, NInfer health and API, Hermes-to-NInfer inference,
sandbox networking, and a real terminal tool side effect. A healthy container alone is not treated
as proof that inference or tool execution works. NInfer's initial model load can take several
minutes; use `python stack.py logs` if setup is waiting on readiness.

## Shell and web dashboard access

Open Bash inside Hermes while remaining in the host's normal terminal:

```text
python stack.py shell
```

Start and open the authenticated Hermes dashboard:

```text
python stack.py gui
```

The dashboard maps `127.0.0.1:9119` to the container by default. Setup generates its independent
username, password, and session-signing secret in the ignored `.env` file. It is not exposed to the
LAN.

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
