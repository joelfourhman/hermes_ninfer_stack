# Performance

## Result status

No formal local throughput campaign has been collected for the current
NInfer-only container plus native Hermes Desktop architecture. Verification
traffic is not a controlled benchmark, so this repository does not claim a
local time-to-first-token or sustained tokens-per-second result.

| Measurement scope | Status |
| --- | --- |
| Pinned NInfer and Qwen3.8-27B NVFP4 upstream campaign | Published upstream |
| Direct NInfer on the audited RTX 5090 host | Integration verified; formal benchmark not collected |
| Native Hermes orchestration overhead | Not collected |

Upstream NInfer measurements are useful selection evidence, but they are not
measurements of this deployment.

## Observed allocation

A verified NInfer startup on 2026-08-23 used the same model artifact and server
allocation retained by the current project. These figures confirm that the
profile fit on the audited RTX 5090; they are not throughput results.

| Setting or observation | Value |
| --- | ---: |
| Context / explicit INT8 KV capacity | 65,536 / 65,536 tokens |
| Maximum concurrency | 1 |
| NInfer-reported KV runtime allocation | 2.75 GiB |
| NInfer-reported free VRAM after startup | 7.24 GiB |
| NInfer-reported allocation slack | 7.72 GiB |
| Model load time for the verified restart | 85.5181 s |
| `nvidia-smi` after verification | 24,914 MiB used / 7,274 MiB free |

That observation predates the switch from containerized Hermes to stock native
Hermes Desktop. The NInfer model and memory settings are unchanged, but native
Hermes overhead has not been remeasured. Hermes compression is enabled and its
agent turn cap is 40 by default; those values affect long-session behavior, not
NInfer kernel throughput.

## Upstream same-model evidence

The pinned NInfer documentation publishes RTX 5090 results for the same
`qwen3_8_27b_nvfp4.ninfer` artifact profile. The relevant campaigns used one
32 GiB RTX 5090, CUDA 13.1 compile/runtime, INT8 group-64 KV cache, CUDA Graphs,
a 1,024-token prefill chunk, and MTP with three draft tokens where noted.

Selected upstream MTP-disabled context-profile results were:

| Prompt tokens | Samples | Prefill tok/s | Server TTFT | Decode tok/s |
| ---: | ---: | ---: | ---: | ---: |
| 7,680 | 5 | 8,340.4 ± 13.0 | 931.6 ± 1.6 ms | 71.2 ± 0.1 |
| 64,512 | 5 | 5,297.9 ± 259.2 | 12,281.1 ± 561.5 ms | 65.7 ± 0.8 |
| 130,048 | 5 | 3,544.7 ± 25.3 | 36,853.5 ± 259.4 ms | 59.6 ± 0.9 |
| 260,096 | 5 | 2,203.1 ± 13.4 | 118,354.8 ± 717.2 ms | 52.9 ± 2.3 |

Selected upstream MTP3 cross-scenario decode results were:

| Category | Samples | Decode tok/s | MTP acceptance | MTP tokens/round |
| --- | ---: | ---: | ---: | ---: |
| Code | 15 | 194.3 ± 6.1 | 76.4% ± 3.9% | 3.29 ± 0.12 |
| Story | 15 | 126.1 ± 10.9 | 37.4% ± 5.8% | 2.12 ± 0.17 |
| Translation | 15 | 192.3 ± 11.9 | 75.0% ± 6.5% | 3.25 ± 0.19 |
| Structured | 15 | 219.8 ± 8.6 | 90.8% ± 5.1% | 3.72 ± 0.15 |

These values come from the
[NInfer performance document at the pinned revision](https://github.com/Neroued/ninfer/blob/feaf4dd0983fdaeb2ba4c06eec6da350e644fb3a/docs/performance.md).
They must be labeled as upstream results, not measurements from this repository.

## Run a local benchmark

First require the integration verifier to pass:

```text
python ninfer.py verify
```

Then collect direct-NInfer measurements:

```text
python ninfer.py benchmark
python ninfer.py benchmark --runs 5 --max-tokens 1024
```

The benchmark is excluded from GitHub-hosted CI because it requires the local
RTX 5090, the full model, and a running NInfer server. It performs a separate
warm-up request, varies measured prompts to avoid treating identical full-prompt
cache hits as independent runs, records GPU samples and raw streaming timing,
and refuses to publish zero-valued measurements when sampling is incomplete.
The running image's provenance labels must match the clean pinned NInfer source.

## Required result metadata

A reproducible result should include:

- date and scope: direct NInfer or native Hermes-to-NInfer;
- GPU, total VRAM, NVIDIA driver, and CUDA versions;
- Docker Engine and Compose versions;
- pinned NInfer commit and, for routed tests, stock Hermes version;
- model filename, SHA-256, and deployment alias;
- context, KV type and capacity, concurrency, speculation, and prefill chunk;
- prompt and committed output token counts;
- cold or warm state and number of samples;
- server time-to-first-token and committed generation tokens per second;
- GPU utilization and observed VRAM;
- failures, early stops, and output-limit behavior.

Do not compare results with different prompt lengths, concurrency, sampling,
speculative acceptance, or warm-up policy as if they measured the same workload.
Hermes-routed measurements include agent prompt construction and client overhead;
direct NInfer measurements do not.

See [Compatibility](compatibility.md) for audited platform facts that do not,
by themselves, establish a performance result.
