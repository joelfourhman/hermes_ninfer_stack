# Design rationale

Keep stock Hermes and its tools/session format. Improve the surrounding platform
through verified NInfer capabilities, an authoritative manifest, whole-workload
benchmarks and a small durable epoch wrapper. Preserve original stock/uncensored
artifacts and MTP3. Add DFlash2 only with an explicit companion artifact selection.

Larger contexts are workload choices. Shared KV, pinned host state and preserved
thinking improve reuse opportunities but cannot guarantee every prefix remains
resident. Separate durable state from these volatile caches. Prefer evidence of
accepted work per second to raw token throughput. Keep supervisor and execution
isolation opt-in, and state what their boundaries actually cover.

See [architecture](architecture.md), [audit](../AUDIT.md),
[new decision record](decisions/0012-durable-measured-agent-platform.md),
[measured results](../BENCHMARK_RESULTS.md) and [jobs](jobs.md).
Earlier decision records describe historical deployments, not current pins.
