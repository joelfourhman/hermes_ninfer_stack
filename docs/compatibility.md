# Compatibility

This project has a deliberately narrow hardware target. The table below separates facts inspected
on the host from components merely selected in configuration. It does not imply that a complete
model load, inference request, or benchmark passed during the audit.

## Audited host and selected stack

Audit date: 2026-08-23.

| Component | Audited value | Evidence scope |
|---|---|---|
| GPU | NVIDIA GeForce RTX 5090, 32,607 MiB reported | Host and NInfer-container queries |
| NVIDIA driver | 610.88 | Host driver query |
| Windows | 10.0.26200.9168 | Host OS query |
| WSL | 2.7.10.0 | Host WSL query |
| Docker Desktop Linux kernel | 6.18.33.2 | Docker Desktop WSL2 environment query |
| Docker Engine | 29.6.1 | Docker daemon version query |
| Docker Compose | 5.3.0 | Compose version query |
| NInfer CUDA images | CUDA 13.1.2 on Ubuntu 24.04 | Pinned upstream Dockerfile |
| Sandbox base | Ubuntu 24.04, `sha256:33ceb719…` | Digest-pinned Dockerfile base |
| NInfer source | `feaf4dd0983fdaeb2ba4c06eec6da350e644fb3a` | Clean submodule; image build and OCI revision-label check passed |
| Hermes Agent | 0.20.5, tag/image `v2026.8.19` | Exact digest pulled; container CLI version checked |
| Model | Qwen3.8-27B NVFP4 NInfer v2 artifact | Pinned download metadata |
| Model SHA-256 | `bb3360522a06e136e0367f5703414d26272b7285c8a6ab6194135c17dbd81b32` | Published artifact metadata |
| SSH sandbox | Healthy, read-only root; key-authenticated command ran as UID/GID 1000 | Local Compose smoke test |

The exact NInfer and sandbox images built successfully (with reusable Docker layers already cached),
the NInfer image saw the RTX 5090, and a real key-only SSH sandbox command created a verified
workspace side effect as the unprivileged `agent` user. No local model artifact was available, so
the audit does **not** claim that the model loaded, NInfer served a completion, Hermes completed a
request, or a local benchmark passed on this exact host. Those remaining claims require
`python stack.py verify` and, for performance, `python stack.py benchmark` after model acquisition.

## Required compatibility envelope

NInfer currently requires:

- 64-bit Linux execution, including Linux containers under the tested Docker Desktop WSL2 path;
- NVIDIA GeForce RTX 5090 (`sm_120a`);
- a driver capable of CUDA 13.1 containers;
- the pinned NInfer source revision or a deliberately reviewed replacement;
- a registered version-2 `.ninfer` artifact;
- one CUDA device and one resident model instance.

The source build rejects CUDA architectures other than `120a`. RTX 4090, other Ada GPUs, older CUDA
toolchains, CPU-only execution, multi-GPU sharding, and non-NVIDIA accelerators are not supported by
this repository.

The pinned NInfer commit's upstream Dockerfile names its CUDA build and runtime bases by versioned
tag rather than digest. The audited build resolved those tags to platform manifests
`sha256:b9f64abf…` (devel) and `sha256:bff001d3…` (runtime). A future registry retag can therefore
change lower layers even while the NInfer source pin remains fixed; review build provenance on
rebuilds. The stack-owned sandbox base is digest-pinned, although its `apt` package transaction is
still a time-varying supply-chain input.

## What is Blackwell-specific

- NInfer's CUDA kernels and build configuration target `sm_120a`.
- The selected mixed NVFP4/FP8 artifact and its optimized execution profiles are NInfer-specific.
- The CUDA 13.1.2 build/runtime images and driver requirement follow the NInfer target.
- GPU reservation belongs only to the NInfer service.

Hermes orchestration, the OpenAI-compatible HTTP boundary, the SSH sandbox, internal networks, and
persistent-state layout are not inherently Blackwell-specific. They are nevertheless verified here
only as part of this RTX 5090 deployment design.

## WSL2 status

NInfer documents 64-bit Linux and RTX 5090; it does not separately certify every WSL2 or Docker
Desktop release. The audited environment uses Docker Desktop's WSL2 Linux backend. The decisive
compatibility checks are therefore container-level GPU visibility, a successful NInfer build and
model load, and the full integration verifier.

Prefer a native WSL2/Linux filesystem for build performance when practical. If the checkout remains
on a Windows-mounted path, verify Docker file sharing and model readability; do not embed an
absolute Windows username or drive path in repository configuration.

## Reproduce the compatibility check

Collect platform evidence without exposing secrets:

```bash
nvidia-smi
docker version
docker compose version
docker info
uname -r
git -C ninfer rev-parse HEAD
```

From PowerShell, WSL version information is available with:

```powershell
wsl --version
```

Then validate the Docker GPU path and full stack:

```bash
docker run --rm --gpus all \
  nvidia/cuda:13.1.2-base-ubuntu24.04 \
  nvidia-smi
python stack.py verify
```

Record a component as “tested” only when the relevant command actually succeeds. Update this
document after dependency upgrades rather than assuming a newer driver, Docker release, Hermes
image, NInfer commit, or artifact remains compatible.

See [Installation](installation.md) for the supported setup sequence and
[Performance](performance.md) for the separate benchmark evidence standard.
