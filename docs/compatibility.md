# Compatibility

This project has a deliberately narrow inference target and a deliberately
loose Hermes lifecycle. NInfer, CUDA, and the model are pinned as one reviewed
profile; Hermes Desktop is the stock per-user application maintained by its
official installer.

## Audited host

Original runtime audit: 2026-08-23. Model-swap and resource-aware runtime
implementation review: 2026-09-05.

| Component | Audited value | Evidence scope |
| --- | --- | --- |
| GPU | NVIDIA GeForce RTX 5090, 32,607 MiB reported | Host and NInfer-container queries |
| NVIDIA driver | 610.88 | Host driver query |
| Windows | 10.0.26200.9168 | Host OS query |
| WSL | 2.7.10.0 | Docker Desktop backend evidence; not a required user shell |
| Docker Desktop Linux kernel | 6.18.33.2 | Docker-managed environment query |
| Docker Engine | 29.6.1 | Docker daemon query |
| Docker Compose | 5.3.0 | Compose query |
| NInfer CUDA base | CUDA 13.1.2 on Ubuntu 24.04 | Pinned upstream Dockerfile |
| NInfer source | `ad0f3d384b5cbcec4a48a3951c287b4e9831443e` | Clean submodule, image build, OCI revision-label check, and live generation |
| Model source | `JonathanColetti/Qwen3.8-27B-Uncensored` at `5bb7aa90f0efef548e87005b1fb7658e522b6b7f` | Recorded provenance for the uncensored conversion |
| Artifact download | `DogOnKeyboard/Qwen3.8-27B-Uncensored-NInfer` at `1e15b5919b796bcd96621f13572ad92b5555b641` | Immutable Hugging Face revision, byte size, and SHA-256 pinned |
| Model artifact | Qwen3.8-27B Uncensored groupwise-int | Hosted artifact exactly matches the locally built reference SHA-256 |
| Native client target | Official Hermes Desktop for Windows | Upstream installer/config documentation; native route not rerun during this refactor |

The current image built successfully, loaded the hosted uncensored artifact,
and completed all 11 verification layers through the native Hermes route. The
balanced profile reported 196,608 tokens of FP8 device KV, two active lanes,
two additional Device State slots, eight Host State slots, 8 GiB Host KV, and
5.12 GiB free device memory after startup. A two-request live check admitted
both requests concurrently. Formal comparable throughput evidence is
documented separately in [Performance](performance.md).

## Required NInfer envelope

NInfer currently requires:

- a 64-bit Linux container environment;
- NVIDIA GeForce RTX 5090 (`sm_120a`);
- a driver capable of running CUDA 13.1 containers;
- the pinned NInfer source revision or a deliberately reviewed replacement;
- the registered version-2 `.ninfer` artifact;
- one CUDA device and one resident model instance.

The source build rejects CUDA architectures other than `120a`. RTX 4090 and
other Ada GPUs, older CUDA toolchains, CPU-only execution, multi-GPU sharding,
and non-NVIDIA accelerators are outside this repository's supported profile.

## Native Hermes envelope

Use the official Hermes Desktop distribution for the host operating system.
The helper depends on stock Hermes capabilities that support:

- `hermes config set`, `get`, and `check`;
- named entries beneath `providers:`;
- `key_env` secret references;
- `transport: chat_completions`;
- durable `custom:<name>` provider selection.

If an old Hermes installation lacks those capabilities, update it through the
official Desktop lifecycle and rerun:

```text
python ninfer.py install-hermes
```

This repository does not pin, replace, or downgrade stock Hermes. Run complete
verification after a Hermes update because provider behavior can evolve even
when NInfer is unchanged.

On Windows, the official native installation is supported on Windows 10/11 and
normally stores its shared runtime and user data under
`%LOCALAPPDATA%\hermes`. The project's helper checks the installed CLI there as
well as on `PATH`.

## Docker Desktop and WSL2

NInfer documents 64-bit Linux and RTX 5090; it does not separately certify
every Docker Desktop or WSL2 release. The audited Windows environment uses
Docker Desktop's WSL2 Linux backend. The decisive checks are container-level
GPU visibility, a successful NInfer build and load, and authenticated
generation.

The Docker backend does not create a requirement for the user to open a WSL
shell. `python ninfer.py setup` is a host Python command, and stock Hermes runs
natively. If the checkout is on a Windows path, Docker Desktop must be able to
read it and the large model file.

## Blackwell-specific pieces

- NInfer's CUDA kernels and build target are `sm_120a`.
- The groupwise-int artifact, MTP proposal head, and execution profile are NInfer-specific.
- CUDA 13.1.2 build/runtime images follow the NInfer target.
- Only the NInfer container receives GPU access.

The OpenAI-compatible protocol and native Hermes provider are not inherently
Blackwell-specific, but this repository verifies them only with the stated
RTX 5090 profile.

## Supply-chain variability

The pinned NInfer commit's upstream Dockerfile names CUDA images by versioned
tag rather than full digest. The audited build resolved specific platform
manifests, but a future registry retag can change lower layers while the source
pin stays fixed. Review image provenance when rebuilding.

Stock Hermes is another independently updated input. Using the official
installer establishes distribution ownership, not permanent compatibility.
Keep the provider configuration narrow and rerun verification after updates.

## Reproduce the checks

Use the project-level Python commands so the user does not have to operate the
Docker, Git, NVIDIA, or Linux tools directly:

```text
python ninfer.py validate
python ninfer.py verify
```

Record a component as tested only when the relevant check actually succeeds.
Do not infer NInfer compatibility from host `nvidia-smi` alone, or Hermes
compatibility from a successful Desktop launch alone.
