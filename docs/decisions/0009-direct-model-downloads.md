# ADR 0009: Download both model artifacts directly

- Status: accepted
- Date: 2026-09-05

## Context

The original uncensored profile downloaded approximately 55 GiB of source
weights, required about 90 GiB of temporary disk space, stopped a running model
to claim the GPU, and converted the weights locally. The completed output is
18,210,531,328 bytes with SHA-256
`714565ed29db4415322e9bc13a3464dc1fd8fcc911234740a79af67934e49969`.

An artifact hosted at
`DogOnKeyboard/Qwen3.8-27B-Uncensored-NInfer` is bit-for-bit identical to that
completed build. Downloading it provides the same inference artifact without
the large source transfer, conversion time, or GPU build authority.

## Decision

Both profiles use one uv-locked, CPU-only model downloader. Each profile pins
an immutable Hugging Face revision, filename, byte size, and SHA-256. The
downloader writes only to the ignored `models/` directory, supports the Hugging
Face client's resumable cache, and does not replace an existing invalid file.

The uncensored profile pins repository revision
`1e15b5919b796bcd96621f13572ad92b5555b641`. The previous conversion source,
converter revision, recipe, and checksum remain documented in
[Models](../models.md) so the artifact's provenance is auditable.

The source fetcher, GPU converter, conversion-only Compose services, and
`model-build/` runtime workflow are removed. Existing valid locally built
artifacts continue to work because their expected filename, size, and checksum
are unchanged.

## Consequences

- Uncensored setup transfers 16.96 GiB rather than approximately 55 GiB.
- Its free-space preflight falls from 90 GiB to 21 GiB.
- Model preparation no longer interrupts a running NInfer service or needs a
  GPU.
- Normal deployment has fewer containers, dependency locks, and failure modes.
- Availability depends on the pinned public repository. The checksum prevents
  silently accepting changed bytes, but cannot prevent the repository owner
  from removing the file.
- The project may mirror the identical artifact under project-controlled
  ownership later without changing its verification identity.
