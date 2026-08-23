# Performance

## Result status

No formal local end-to-end benchmark result has been collected. The model is now present and the
complete live verifier passes, but verification traffic is not a controlled benchmark campaign.
This repository therefore does not claim local time-to-first-token or sustained throughput numbers.

| Measurement scope | Status |
|---|---|
| Pinned NInfer and Qwen3.8-27B NVFP4 upstream campaign | Published upstream |
| This Docker Compose stack on the audited host | Integration verified; formal benchmark not collected |
| Hermes orchestration overhead | Not collected |
| SSH tool-execution latency | Not collected |

This distinction is intentional. Upstream NInfer measurements are useful selection evidence but are
not substitutes for measurements of the complete stack.

## Tuned allocation validation

The 2026-08-23 live startup with the default single-user profile reported the following operational
figures. These validate that the requested allocation is active; they are not throughput results.

| Setting or observation | Value |
|---|---:|
| Context / explicit INT8 KV capacity | 65,536 / 65,536 tokens |
| Maximum concurrency | 1 |
| NInfer-reported KV runtime allocation | 2.75 GiB |
| NInfer-reported free VRAM after startup | 7.24 GiB |
| NInfer-reported allocation slack | 7.72 GiB |
| Model load time for the verified restart | 85.5181 s |
| `nvidia-smi` after full verification | 24,914 MiB used / 7,274 MiB free |

Hermes compression was enabled and its agent turn cap was set to 40 for this validation. The full
verifier exercised authenticated direct generation, Hermes-routed generation, and SSH-sandbox tool
execution successfully.

## Upstream same-model evidence

The pinned NInfer documentation publishes RTX 5090 results for the same
`qwen3_8_27b_nvfp4.ninfer` artifact profile. The relevant campaigns used:

- one NVIDIA GeForce RTX 5090 with 32 GiB VRAM;
- CUDA 13.1 compile/runtime and CUDA driver API 13.3;
- INT8 group-64 KV cache and CUDA Graphs;
- a 1,024-token prefill chunk;
- prefix reuse disabled;
- MTP with three draft tokens and a 131,072-token context for the MTP3 campaign.

Selected upstream MTP-disabled context-profile results were:

| Prompt tokens | Samples | Prefill tok/s | Server TTFT | Decode tok/s |
|---:|---:|---:|---:|---:|
| 7,680 | 5 | 8,340.4 ± 13.0 | 931.6 ± 1.6 ms | 71.2 ± 0.1 |
| 64,512 | 5 | 5,297.9 ± 259.2 | 12,281.1 ± 561.5 ms | 65.7 ± 0.8 |
| 130,048 | 5 | 3,544.7 ± 25.3 | 36,853.5 ± 259.4 ms | 59.6 ± 0.9 |
| 260,096 | 5 | 2,203.1 ± 13.4 | 118,354.8 ± 717.2 ms | 52.9 ± 2.3 |

Selected upstream MTP3 cross-scenario decode results were:

| Category | Samples | Decode tok/s | MTP acceptance | MTP tokens/round |
|---|---:|---:|---:|---:|
| Code | 15 | 194.3 ± 6.1 | 76.4% ± 3.9% | 3.29 ± 0.12 |
| Story | 15 | 126.1 ± 10.9 | 37.4% ± 5.8% | 2.12 ± 0.17 |
| Translation | 15 | 192.3 ± 11.9 | 75.0% ± 6.5% | 3.25 ± 0.19 |
| Structured | 15 | 219.8 ± 8.6 | 90.8% ± 5.1% | 3.72 ± 0.15 |

These values are reproduced from the
[NInfer performance document at the pinned source revision](https://github.com/Neroued/ninfer/blob/feaf4dd0983fdaeb2ba4c06eec6da350e644fb3a/docs/performance.md).
The individual campaigns identify their own runtime revisions and methodology. They must be cited as
upstream NInfer results, not as measurements from this repository or the audited host.

## Run a local stack benchmark

First require the complete integration test to pass:

```bash
python stack.py verify
```

Then run the benchmark:

```bash
python stack.py benchmark
```

For a longer run or output cap, use `python stack.py benchmark --runs 5
--max-tokens 1024`.

The benchmark is a local GPU integration workload and is intentionally excluded from GitHub-hosted
CI. It warms the persistent server with a separate request, then starts each measured user prompt
with a different word so the first run is not mixed with later full-prompt cache hits. Compatible
shared chat-template prefixes can still be reused and are disclosed in the report. Missing GPU
samples, an early sampler exit, a model checksum mismatch, or incomplete SSE usage data makes the
run fail instead of producing zero-valued measurements. Preserve the complete report—including
per-run prompts, finish reasons, raw SSE timing, GPU samples, and NInfer logs—for any result you
publish. The harness also requires the running image's OCI revision and CUDA-base labels to match
the clean pinned NInfer worktree before it records that commit as provenance.

## Required result metadata

A reproducible result must record, at minimum:

- date and measurement scope (direct NInfer or through Hermes);
- GPU name and total VRAM;
- NVIDIA driver and CUDA compile/runtime versions;
- Docker Engine and Compose versions;
- pinned NInfer commit and Hermes image tag;
- exact model filename, artifact SHA-256, and deployment alias;
- context length, KV type/capacity mode, concurrency, speculative settings, and prefill chunk;
- prompt and committed output token counts;
- cold or warm state and number of samples;
- server time-to-first-token and committed generation tokens per second;
- GPU utilization and peak/observed VRAM;
- failures, early stops, and whether the output limit was reached.

Do not compare results that differ in speculative acceptance, prompt length, concurrency, sampling,
or warm-up policy as if they measured the same workload.

## Interpretation notes

- **TTFT** includes prompt processing and therefore grows with prompt length. Record whether client
  transport or Hermes overhead is included.
- **Decode tokens/s** must use committed output tokens. Draft tokens rejected by MTP are not user
  output.
- **MTP acceptance** changes with workload and sampling. Higher acceptance can raise throughput
  without changing kernel speed.
- **Concurrency** may improve aggregate throughput while worsening individual latency or exhausting
  KV capacity.
- **KV capacity** changes available context, concurrency, and VRAM headroom. Record whether it was
  explicit or automatic and include NInfer's resolved startup value.
- **Warm results** exclude image pull, compilation, model upload, and first-server startup unless
  explicitly stated otherwise.

When a valid local campaign is available, add a dated table here with its exact command and retain
the “upstream” label on the reference results above. See [Compatibility](compatibility.md) for the
audited platform facts that do not by themselves establish a performance result.
