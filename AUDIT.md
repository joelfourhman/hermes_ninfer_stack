# Pre-change audit — 2026-09-11

The active September 23 v3 pin and migration review are recorded in
[the upstream review](docs/upstream-review-2026-09.md). The sections below retain
the earlier deployment audit; their older pins and artifact formats are historical.

## Baseline and evidence

Stack HEAD: `37d57b2` (opt-in authenticated LAN access). The tracked checkout was
clean; the pre-existing, untracked `HERMES_LONG_RUN_RULES.md` is user material.
Inspection covered the control helper, Compose/env, downloader and uv lock,
three operational scripts, 35 tests, CI, README, operating guides, security
policy and historical decisions. Baseline unit tests and `ninfer.py validate`
pass on Windows/Python 3.14. Git's shell-based submodule wrapper fails on this
host; the existing helper intentionally uses Git plumbing instead.

| Item | Before changes |
|---|---|
| Expected source / gitlink / actual NInfer HEAD / Compose revision label | `ad0f3d384b5cbcec4a48a3951c287b4e9831443e` — agree |
| CUDA runtime label | `docker.io/nvidia/cuda:13.1.2-runtime-ubuntu24.04` |
| Stock artifact | `neroued/Qwen3.8-27B-nvfp4-NInfer` @ `204e3d92c30d9d05f3300d2f52e443ad1edf6ddf` |
| Stock bytes / SHA-256 | 21,492,695,040 / `bb3360522a06e136e0367f5703414d26272b7285c8a6ab6194135c17dbd81b32` |
| Optional artifact | `DogOnKeyboard/Qwen3.8-27B-Uncensored-NInfer` @ `1e15b5919b796bcd96621f13572ad92b5555b641` |
| Optional bytes / SHA-256 | 18,210,531,328 / `714565ed29db4415322e9bc13a3464dc1fd8fcc911234740a79af67934e49969` |
| Hermes | Independently installed native Desktop; named `custom:ninfer`, Chat Completions, manual approvals, local terminal |
| Hermes limits | Profile context; compression enabled at 0.9 or the profile token threshold; 40 turns; no durable goal coordinator |

| Runtime | Context | Shared KV tokens | Lanes | Device / host slots | Host KV MiB | Compression tokens |
|---|---:|---:|---:|---:|---:|---:|
| balanced (default) | 131072 | 196608 | 2 | 2 / 8 | 8192 | 90000 |
| single-session | 131072 | 131072 | 1 | 1 / 4 | 4096 | 100000 |
| max-context | 240000 | 240000 | 2 | 2 / 8 | 8192 | 200000 |

All use FP8 KV, prefill chunk 1024, MTP3, optimized draft head, graphs and
preserved reasoning. Admission timeout is 120 seconds. There is one resident
model; host checkpoints are memory caches, not disk persistence.

## Drift and missing coverage

The source pin is duplicated in the helper, verifier, benchmark, validator,
Compose and compatibility guide. Model identities and runtime tables are also
copied. The validator checks literal duplication rather than one authority.
README accurately describes the default profile, but performance/security prose
still sometimes describes uncensored as the selected model. Historical memory
observations do not establish current NVFP4/profile memory use. Compose hardcodes
MTP3 and preserve-thinking. There are no workload completion benchmarks,
stream/tool/reasoning integration tests, durable epochs, or request JSON metrics.
The raw streaming benchmark indexes `choices[0]` even for an empty usage chunk.

## Verified upstream target

Upstream HEAD fetched directly on the audit date:
`d49296868dcc17bd478ec185f0d3a801bcc0bf56`. This is a master commit, not a tagged
stable release. It includes DFlash2, tokenization/kernel improvements, and fixes
for BF16 compilation and host upload completion. Upgrade is provisional until
the local build/API checks pass; no speed claim follows from recency alone.

Authorities at that immutable revision:
[CLI](https://github.com/Neroued/ninfer/blob/d49296868dcc17bd478ec185f0d3a801bcc0bf56/docs/cli.md),
[serving](https://github.com/Neroued/ninfer/blob/d49296868dcc17bd478ec185f0d3a801bcc0bf56/docs/serving.md),
[cache semantics](https://github.com/Neroued/ninfer/blob/d49296868dcc17bd478ec185f0d3a801bcc0bf56/docs/maintainer/resource-scheduling-and-context-cache.md),
[artifact manifest](https://github.com/Neroued/ninfer/blob/d49296868dcc17bd478ec185f0d3a801bcc0bf56/model-cards/Qwen3.8-27B-nvfp4-NInfer/artifact-manifest.json).
Source CLI parsing, artifact capability binding, HTTP serialization, cache state
and DFlash2 implementation are the contract, not issues or proposed branches.

| Capability | Confirmed contract / integration decision |
|---|---|
| MTP | 1–5 draft tokens; preserve MTP3 default/fallback |
| DFlash2 | Qwen3.8-27B groupwise-int and NVFP4 **with companion tensors**, 1–15 drafts; 7 recommended upstream; 11 legal but unmeasured here |
| Optimized head | `--lm-head-draft` works with either selected backend |
| KV formats | bf16, int8, fp8, nvfp4, k8v4; retain FP8 until workload/quality evidence warrants a change |
| Concurrency | Startup-fixed 1–8 lanes; shared KV pool, FIFO admission, no preemption/active swapping |
| Prefix reuse | Exact rendered tokens; private and shared checkpoints include recurrent, hidden and speculative continuation state |
| Device/host | Extra device slots, pinned host state slots and host KV MiB; live-memory retention only |
| APIs | Chat Completions, Responses Core and Anthropic Messages; streaming, tools and reasoning; unsupported fields rejected |
| Responses persistence | Bounded process-local store and `previous_response_id`; not restart durability |
| Native request metrics | Usage cached tokens; terminal `timings`; `--request-log-jsonl` with request_done timings/speculation/reuse and throughput scheduler/cache gauges |
| Unavailable metric claims | No invented per-request device-hit/host-restore timing; retain native fields and interval scopes rather than attributing shared counters to individual requests |

The new upstream artifact is 23,719,496,192 bytes, SHA-256
`552c374c685dce302603b95fbe940fb04243c0cd44c083efc644ad3d980d462c`, with
conversion recipe `qwen3_8_27b_nvfp4-v2` and DFlash2 source revision
`50307d4c4cde6860d4eee73e2547cd786fe8e8a4`. Hugging Face HEAD is
`11dbbbbbc33db198afe2f02c9232c771ff7031be`. This must be an explicit new model
selection with a distinct local filename; never overwrite the original artifact.

## Hermes integration investigation

Audited upstream Hermes `bffa5f75e45f41045c000c9516f08cada3d56eb4`:
`hermes_cli/_parser.py`, `hermes_cli/plugins.py`, `agent/prompt_builder.py`,
`agent/agent_init.py`, `run_agent.py`, `tools/terminal_tool.py`,
`tools/environments/docker.py` and checkpoint/compression implementation.
Hermes already sorts the skills index, caches stable prompt material, normalizes
tool-call IDs deterministically, persists sessions, offers filesystem
checkpoints, and exposes bounded CLI turns/query files/session resume.
Dynamic state belongs in appended turns; modifying the system prompt every
epoch would defeat reuse. Keep original assistant reasoning and tool order.

Use existing Hermes sessions and filesystem checkpoints with a small durable
epoch ledger. Verify installed CLI capabilities before execution. Docker and
SSH terminal backends already exist: integrate those instead of inventing a
second tool executor. A terminal backend does not isolate every native plugin,
browser or connector; full-agent isolation still needs a separate account/VM.

## Validation availability

An RTX 5090 (32,607 MiB reported) and healthy baseline NInfer container exist.
28,078 MiB was occupied during inspection. Docker access requires execution
outside the filesystem sandbox. Measure baseline before recreating this
service. Preserve its image and env for recovery. Hardware availability alone
does not establish new-artifact availability or benchmark success.
