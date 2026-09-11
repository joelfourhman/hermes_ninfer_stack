# Cache semantics and measurements

The pinned source was inspected directly; see [AUDIT.md](../AUDIT.md). NInfer uses
a shared KV pool across lanes, FP8 KV in these profiles, and retained recurrent,
hidden and speculative continuation state. Device state slots avoid transfer;
host state and pinned host KV extend retained histories with transfer costs.
Eviction, admission and capacity planning affect whether a prefix can be reused.
There is no enabled durable disk KV store, active swap or arbitrary preemption.

The profile's device slots are retained cache slots in addition to active lane
state. Native total device-state capacity is `max_concurrency + device_state_slots`;
the two-lane/two-cache-slot profiles therefore allocate four device state slots.
The benchmark retains native startup/interval definitions rather than treating
configured cache slots as the engine's entire state-memory footprint.

`max-context` is the per-request total token ceiling; `kv-capacity` is shared pool
capacity. Two lanes do not each reserve half the pool, and they do not guarantee
two simultaneous maximum-context requests. Host KV is backing/retention capacity,
not extra active GPU token capacity. Research/max-context have 240,000 tokens,
not 240 Ki tokens. Leave room for outputs, tools and compression before the ceiling.

The initial coding/autonomous candidate used a 240,000-token KV pool. Actual
DFlash2-7 startup on the RTX 5090 could not reserve that runtime footprint.
These two profiles now use 196,608 shared tokens while retaining their 196,608
per-request ceiling. Research/max-context stay at 240,000 and should use the
qualified MTP path; larger DFlash2 reservations are not claimed to fit.

Stock Hermes sorts/caches stable skills and tools and preserves conversation
order. This integration does not rebuild/reorder its system prefix. Durable
handoffs are appended in user turns; changing timestamps never enters the stable
system prefix. Native Hermes compression changes history and therefore has a
cache cost. Keep reasoning messages and tool-call/result order intact. The
observer hashes the system prompt at real API hooks; it does not claim to hash
tool schemas that the hook does not expose.

## Metric definitions

| Output | Source and scope |
|---|---|
| Input/output tokens | Native Chat usage |
| Cached prefix tokens | Native usage details or terminal timings.cache_n |
| Fresh prefill tokens | Derived input minus cached; native request_done computed_prefill_tokens also retained |
| Client TTFT | Send to first content/reasoning/tool delta; includes queue/transport |
| Hermes TTFB | Hook start to first stream chunk; not necessarily first token |
| Prefill/decode seconds and tok/s | Terminal native timings; prompt time includes restoration and first token |
| Model request seconds | Client elapsed or actual Hermes API-hook durations, not whole-agent turn duration |
| Tool seconds | Bounded tool events or Hermes pre/post-tool hooks |
| Context/compression | Per-request input tokens; bounded-driver compression events; Hermes compression unknown unless exposed |
| KV/state/host cache | Native throughput interval context_cache gauges/counters |
| Restore path/time, speculation | Native request_done result/timings/speculative/materialization records when present |
| VRAM/RAM | One-second whole-device/whole-host samples, not process-private allocations |

Unavailable values stay null. Raw events preserve upstream fields rather than
inventing hit ratios. Interval records include other clients and are never joined
to a request by guess. The opaque HTTP x-request-id differs from the numeric
native request ID; no false join is made. Native speculative accepted/drafted
counts are retained, not conflated with tokens/sec. Docker log retention is bounded.

`observe` combines hardware, active verified configuration and recent native
events. `observe --state PATH` adds job epoch, milestone, session and checkpoint
plus the latest private hook event. No Prometheus/Grafana services are required.

## Benchmark protocol

Use [BENCHMARK_PLAN.md](../BENCHMARK_PLAN.md) and
[BENCHMARK_RESULTS.md](../BENCHMARK_RESULTS.md). The primary metric is accepted
workload completion time with failures in the denominator. Report TTFT, cache,
context, quality and stability alongside throughput. A small fixture does not
establish multi-hour agent performance or justify maximizing context by default.

The bounded coding driver requires two edits and two test invocations plus final
independent fixture acceptance. It restricts edits/tests to fixture operations.
The actual Hermes driver uses native terminal/file tools and manual approvals;
it measures real orchestration and validates the final fixture, but does not
require an identical number of tool calls. Private-home preparation and CLI
capability checks are outside epoch wall time; CLI process startup is included.
Compare only matching drivers.
The Hermes driver uses installed Hermes defaults for output cap, thinking and
sampling; `--max-tokens`/`--thinking` control the bounded driver. Native request
records retain the actual resolved settings for reviewing Hermes comparisons.

The server is warmed by startup validation. Repetitions reuse one running server
and can share prefixes. Report first and subsequent samples; these are neither
pure cold-cache nor random-order experiments. For cold-cache comparisons restart
before every sample, keeping the same startup probe, and record that protocol.
For long-context tests `--context-kib` means approximate fixture bytes, not input
tokens. Measure actual usage. Long-session compression in the bounded harness is
an explicit summary/reset simulation, not a claim about native Hermes compression.
