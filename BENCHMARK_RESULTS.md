# RTX 5090 measured results

## Current v3 runtime — 2026-09-23

NInfer `594930e` and reproducibly upgraded artifacts ran on Windows, RTX 5090
(32,607 MiB), NVIDIA 617.14 and CUDA 13.1.2. All seven presets passed three
bounded fixture runs; DFlash2-7 also passed one actual Hermes CLI coding task
with independent acceptance. Original uncensored/autonomous passed three more
coding fixtures. Results and raw-file hashes are preserved in
[measured-v3-summary.json](benchmarks/measured-v3-summary.json).

| Preset / workload | Accepted | Median completion s | Peak GPU MiB |
|---|---:|---:|---:|
| default / coding | 3/3 | 3.468 | 29,143 |
| low-vram / coding | 3/3 | 3.719 | 24,448 |
| autonomous / coding | 3/3 | 4.765 | 29,085 |
| coding, DFlash2-7 / coding | 3/3 | 3.916 | 30,638 |
| coding-fast, DFlash2-11 / coding | 3/3 | 3.455 | 30,657 |
| research / 256 KiB fixture | 3/3 | 30.878 | 30,536 |
| uncensored, 240K / coding | 3/3 | 5.502 | 27,373 |
| original uncensored/autonomous / coding | 3/3 | 4.306 | 26,012 |
| coding, DFlash2-7 / actual Hermes | 1/1 | 34.401 | 30,644 |
| original uncensored/autonomous / two lanes | 1/1 | 19.539 | 25,949 |

DFlash2-11 was faster than DFlash2-7 on the same companion/coding configuration
in this short sample; both remain explicit choices. Stock/balanced/MTP3 remains
the general default. Different artifacts and capacity profiles do not isolate
decoder performance. Actual Hermes includes its process/tool overhead and uses
its native defaults; its wall time should not be ranked with the bounded harness.
The two-lane fixture passed concurrent independent work, with acceptance checked
for both lanes; it does not establish two simultaneous maximum-sized contexts.

The server was warmed by startup validation; repeated workloads shared caches.
Presets ran sequentially without randomized order or locked GPU clocks. These
are small samples, with no same-day v2 baseline, so they establish readiness and
observed workload behavior rather than an overall upgrade speedup. Whole-device
memory was sampled once per second. Startup does not establish two simultaneous
full-sized sessions or multi-hour stability.

Research reached 86,058 input tokens, not the 240,000-token ceiling. Its three
runs each recomputed the large document prefix: cached input was 1,031,784 of
1,287,651 cumulative input tokens. The host-state cache reached all eight slots.
Historical September 11 results used different templates, cache behavior and
driver; the lower historical research wall time is retained below and is not
represented as a like-for-like comparison.

A configuration comparison changed only research's host-state slots from 8 to
16, keeping model, decoder, context, KV and fixture parameters fixed. All three
runs passed, but median completion was 31.524 s and cached tokens were identical.
The larger cache did not improve this fixture, so **research retains 8 slots**.
Both the candidate and baseline remain in the v3 summary. Other working sets may
behave differently.

## Historical v2 runtime — 2026-09-11

**Keep stock/balanced/MTP3 as the default.** DFlash2 is a useful opt-in candidate
with a verified companion artifact. Short, warmed coding fixtures do not establish
multi-hour performance, broad correctness or a universal best decoder.

Measurements ran on Windows with RTX 5090 (32,607 MiB reported), NVIDIA 616.92,
CUDA 13.1 runtime, the audited upgraded source and immutable manifest artifacts.
The table distinguishes bounded fixture work from actual Hermes CLI epochs.
Three repeats are a small sample; one Hermes run per decoder is a smoke measurement.

The original active deployment used uncensored/max-context/MTP3. Its old-image
baseline and the early upgraded uncensored sample had different context settings
and competing traffic. The new uncensored window contains 15 native completions
for 7 harness completions. They cannot establish a controlled upgrade speedup.
The competing chat was subsequently stopped with permission; saved sessions,
Desktop and gateway were preserved.

## Completed measurements

| Dataset | Driver | KV tokens | Accepted | Median s | Peak VRAM MiB |
|---|---|---:|---:|---:|---:|
| `baseline-mtp3-coding` | bounded-agent | 240,000 | 1/1 | 35.02 | 28,155 |
| `coding-uncensored-mtp3` | bounded-agent | 240,000 | 1/1 | 7.88 | 28,086 |
| `companion-coding-mtp3` | bounded-agent | 240,000 | 3/3 | 4.15 | 31,123 |
| `companion-coding-tuned-d11` | bounded-agent | 196,608 | 3/3 | 3.20 | 31,229 |
| `companion-coding-tuned-d7` | bounded-agent | 196,608 | 3/3 | 3.26 | 31,229 |
| `companion-coding-tuned-mtp3` | bounded-agent | 196,608 | 3/3 | 4.32 | 29,673 |
| `hermes-coding-smoke` | hermes | 240,000 | 1/1 | 43.56 | 28,108 |
| `hermes-companion-d11` | hermes | 196,608 | 1/1 | 26.08 | 31,231 |
| `hermes-companion-d7` | hermes | 196,608 | 1/1 | 27.03 | 31,226 |
| `hermes-companion-mtp3` | hermes | 196,608 | 1/1 | 29.02 | 29,670 |
| `stock-balanced-mtp3` | bounded-agent | 196,608 | 3/3 | 4.05 | 29,673 |
| `stock-coding-mtp3` | bounded-agent | 240,000 | 3/3 | 5.56 | 31,224 |
| `stock-long-session-256` | bounded-agent | 240,000 | 3/3 | 295.59 | 31,146 |
| `stock-parallel-64` | bounded-agent | 240,000 | 3/3 | 17.99 | 31,101 |
| `stock-research-256` | bounded-agent | 240,000 | 3/3 | 8.39 | 31,130 |

`coding` rows without `tuned` used the initial 240,000 KV candidate. `tuned` rows
use the final 196,608 KV coding profile. Compare B2/C/D only within the tuned rows
on the same companion artifact. Different recipes/artifacts cannot isolate a
decoder's effect. The original stock/balanced sample remains the default-capacity
reference. No successful sample is substituted for a failed attempt.

## Controlled short coding comparison

| Decoder, same companion/coding configuration | Samples s | Median TTFT s | Median decode tok/s | Cache / input tokens |
|---|---|---:|---:|---:|
| mtp-3 | 4.45, 4.32, 3.96 | 0.212 | 169.9 | 21,811 / 24,234 |
| dflash 2-7 | 3.26, 3.43, 3.23 | 0.167 | 216.9 | 21,805 / 24,225 |
| dflash 2-11 | 3.20, 3.38, 2.88 | 0.204 | 220.1 | 21,811 / 24,234 |

All bounded coding runs require two model edits, two test invocations and final
independent acceptance. Model/tool timing, generated/fresh tokens, native reuse
paths, speculative acceptance counts, context and host RAM peaks are retained in
[measured-summary.json](benchmarks/measured-summary.json). Raw per-request logs,
fixture outputs and private Hermes sessions remain in local ignored directories.
The summary includes a SHA-256 identifying each raw results file.

Startup validation warmed the server. Repetitions share one cache; startup/model
hashing are outside workload timing. Native request counts match the bounded
client counts in the clean coding windows, but this is not proof of controlled
cold caches or randomized order. Hermes uses its native sampling/thinking/output
defaults; its CLI epoch wall time excludes private-home preparation/capability
checks and includes CLI process startup. Each companion Hermes run recorded one
consistent system-prompt hash across its API calls; tool schemas are not included
in that hash because the hook does not expose them.
Do not rank bounded and Hermes drivers together. A single Hermes timing is not
enough to select a default even when the fixture passes.

## Memory qualification and failure

Initial DFlash2-7 with 240,000 shared KV failed startup. Native diagnostics report
a required runtime reservation of 9,978,952,960 bytes versus 9,469,855,232available.
Both attempts failed readiness; the diagnostic repeat captured this reservation
failure before rollback. The service restored
MTP3 and passed its live generation probe. The first attempt lacked retained
container logs; failure capture now saves redacted configuration/logs before
rollback. It is not counted as a successful benchmark.

Coding and autonomous now use 196,608 shared KV tokens while retaining a 196,608
per-request ceiling. Research/max-context retain 240,000 KV for the MTP path.
DFlash2 plus research 240K is not qualified. VRAM figures are one-second whole-GPU
samples, not hard peak bounds. The profiles require headroom for other GPU use;
the longest allowed context and two simultaneous full-length requests are not
guaranteed simply because startup succeeds.

## Long-context interpretation

- `stock-research-256`: 3/3 accepted; maximum observed input 86,118 tokens; cached 1,201,394 of 1,288,013 cumulative input tokens; 0 bounded-driver compression events. Native reuse paths: root, private_endpoint, shared_stable_prefix, private_response_replay.
- `stock-long-session-256`: 3/3 accepted; maximum observed input 235,910 tokens; cached 5,029,599 of 6,906,589 cumulative input tokens; 3 bounded-driver compression events. Native reuse paths: root, private_endpoint.
- `stock-parallel-64`: 3/3 accepted; maximum observed input 32,865 tokens; cached 520,160 of 692,500 cumulative input tokens; 0 bounded-driver compression events. Native reuse paths: root, shared_stable_prefix, private_endpoint, private_response_replay.

Fixture KiB are approximate source bytes, not tokens. Research uses four fictional
sources; it tests ingestion/tool/synthesis behavior, not real CVE accuracy.
Long-session grows history and explicitly summarizes when its configured threshold
is crossed. That compression is harness behavior, not a native Hermes compression
measurement. Parallel measures two concurrent lanes and overlapping model time.

Not established: day-long stability, actual Windows reboot recovery, every
host-state restore path/latency, full 240K quality, DFlash2 research 240K, alternate
KV quality, remote SSH workers, browser isolation, Responses/Anthropic round trips,
remote supervisor performance or statistically robust Desktop speedups.
Use [BENCHMARK_PLAN.md](BENCHMARK_PLAN.md) to repeat in reversed order, at larger
contexts and with more actual Hermes runs before changing daily defaults.
