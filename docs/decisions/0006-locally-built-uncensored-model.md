# ADR 0006: Build the uncensored model locally from pinned inputs

- Status: Superseded by [ADR 0009](0009-direct-model-downloads.md)
- Date: 2026-09-05

## Context

The selected model is
[`JonathanColetti/Qwen3.8-27B-Uncensored`](https://huggingface.co/JonathanColetti/Qwen3.8-27B-Uncensored).
Its Hugging Face repository contains approximately 55 GB of BF16 Safetensors,
not a file that NInfer can serve directly. The public
[`ninfer-qwen-uncensored`](https://github.com/j842/ninfer-qwen-uncensored)
recipe deliberately does not redistribute its converted artifact.

NInfer requires one self-contained `.ninfer` artifact. A normal installation
therefore needs a conversion step, but the project must retain its Python-only
host interface, uv-only Python dependency policy, resumability, and explicit
consent before a large transfer.

The conversion is not byte-identical across every GPU and PyTorch/CUDA build
because low-bit rounding can differ. A universal output checksum would reject
functionally equivalent builds.

## Decision

`python ninfer.py setup` asks before acquiring the source checkpoint, then runs
two short-lived Compose services:

1. `model-fetcher` has network access but no GPU. It downloads immutable
   Hugging Face revisions, grafts and checksum-verifies the official Qwen
   frontend, and fetches a checksum-pinned NInfer converter archive.
2. `model-converter` has the selected GPU but `network_mode: none`. It reads the
   prepared inputs, executes the pinned groupwise-int recipe, validates the
   conversion report and exact artifact size, calculates the local SHA-256,
   and atomically promotes the result.

Both images use committed uv lock files. No host or container step invokes
pip. The host launches only `ninfer.py`; it does not require Bash, PowerShell,
WSL, a Hugging Face CLI, or a Python virtual environment.

The local SHA-256 and build identity are written beside the ignored artifact.
Subsequent verification uses that manifest. An exact match with the published
reference checksum is recorded when obtained but is not required by itself.

The API alias remains `qwen-local` so existing Hermes sessions do not need a
model-ID migration. The first supported runtime profile remains text-only,
131,072 context tokens, matching INT8 KV capacity, concurrency one, and MTP
with three draft tokens. Vision and a 262K profile require separate evidence.

## Consequences

- Initial setup downloads about 55 GB and needs about 90 GB of temporary free
  disk instead of downloading one 20 GB artifact.
- Setup may stop NInfer briefly so conversion has enough GPU memory.
- Downloads survive interruption; incomplete conversion output is never used.
- The old model is retained for rollback and is removed only by an explicit
  operator action.
- CI validates orchestration, pins, locks, and Compose structure without
  downloading or converting model weights.
- Documentation must distinguish source-model measurements, conversion
  provenance, and measurements collected from this deployment.

## Safety consequence

Reduced refusal behavior is not an execution sandbox. Hermes keeps manual
approvals, limited direct-write roots, and its lean tool profile. Native
terminal commands still run with the signed-in user's authority; the model's
name or training behavior provides no filesystem protection.
