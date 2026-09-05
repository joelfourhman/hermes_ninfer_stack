# Performance

## Current result status

No comparable throughput campaign has yet been collected for both selectable
profiles. Published measurements must identify the exact profile and cannot be
generalized between stock NVFP4 and the uncensored groupwise-int artifact.
The source model's capability checks do not establish serving speed or agent
quality.

| Measurement scope | Status |
| --- | --- |
| Source-model refusal and four 0-shot capability checks | Published by the source-model author |
| Conversion recipe and RTX 5090 serving example | Published; no throughput figures |
| Direct NInfer on this repository's RTX 5090 profile | Required before a performance claim |
| Native Hermes orchestration overhead | Not collected |

The artifact's public conversion notes describe a full-context, vision-enabled launch on
one RTX 5090 but explicitly label the dense model as not benchmarked. This
repository therefore begins with a conservative first-test profile:
131,072 context tokens, equal INT8 KV capacity, concurrency one, text-only, a
1,024-token prefill chunk, and MTP with three draft tokens.

## Historical baseline—not a same-model comparison

The previous `qwen3_8_27b_nvfp4.ninfer` artifact was observed at 65,536 context
and KV capacity on this host:

| Observation | Previous NVFP4 artifact |
| --- | ---: |
| NInfer-reported KV runtime allocation | 2.75 GiB |
| Free VRAM after startup | 7.24 GiB |
| Model load time | 85.5181 s |
| `nvidia-smi` after verification | 24,914 MiB used / 7,274 MiB free |

These figures are retained only as rollback-era evidence. The new artifact is
groupwise-int, includes different weights, is smaller on disk, and runs with a
larger 131K KV allocation. Do not infer throughput or memory use from the old
numbers.

## Collect a local result

Require full integration verification first:

```text
python ninfer.py verify
```

Then run:

```text
python ninfer.py benchmark
python ninfer.py benchmark --runs 5 --max-tokens 1024
```

The benchmark verifies the active artifact's pinned SHA-256 before measuring.
It uses a warm persistent server, changes each prompt to avoid counting an
identical full-prompt cache hit as an independent run, records raw streaming
timing, and samples the GPU. Results remain ignored because prompts and model
responses may be private.

Before calling the model a successful replacement, collect at least:

- a short-prompt decode sample;
- a 64K-class prefill sample;
- a near-120K prefill sample;
- model load time and idle VRAM;
- MTP acceptance and committed decode speed where available;
- a native Hermes task representative of the intended AFK workload.

## Required result metadata

A reproducible result must include:

- date and direct-NInfer or Hermes-routed scope;
- GPU, VRAM, driver, CUDA image, Docker, and Compose versions;
- NInfer runtime commit and local model SHA-256;
- model artifact revision and SHA-256;
- context, KV dtype/capacity, concurrency, prefill chunk, and speculation;
- prompt and committed output token counts;
- cold or warm state and sample count;
- time to first token and committed generation tokens per second;
- GPU utilization, observed VRAM, failures, and output-limit behavior.

Do not compare results with different prompt lengths, context allocations,
sampling, speculation, or warm-up policies as if they measured the same thing.
Hermes-routed measurements also include prompt construction and agent overhead.
