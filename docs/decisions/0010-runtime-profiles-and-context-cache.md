# ADR 0010: Treat NInfer resource allocation as reviewed runtime profiles

- Status: Accepted
- Date: 2026-09-05

## Context

The original 131K-context, concurrency-one server was reliable for one request,
but a long Hermes task monopolized admission. Other requests reached NInfer's
30-second queue deadline, and histories near the context ceiling incurred high
first-token latency or were rejected. The RTX 5090 still had enough memory for
a larger shared KV pool.

Current NInfer adds FP8 KV and resource-aware Device/Host prefix checkpoints.
Its published long-agent configuration uses a 240K logical/device-KV ceiling,
two active lanes, two Device State slots, eight Host State slots, and 8 GiB of
pinned Host KV.

## Decision

Pin the reviewed NInfer resource-aware runtime and expose three complete
profiles instead of independent memory knobs:

| Profile | Context | Device KV | Lanes | Host KV | Hermes compression |
| --- | ---: | ---: | ---: | ---: | ---: |
| `balanced` | 131,072 | 196,608 | 2 | 8,192 MiB | 90,000 |
| `single-session` | 131,072 | 131,072 | 1 | 4,096 MiB | 100,000 |
| `max-context` | 240,000 | 240,000 | 2 | 8,192 MiB | 200,000 |

All profiles use FP8 KV, MTP3, the optimized proposal head, CUDA Graphs,
prefix reuse, retained thinking, and a 120-second preparation/admission
deadline. Setup defaults to `balanced` without adding another beginner prompt.
`select-runtime` changes the complete profile, verifies live generation,
restores the previous configuration on failure, and updates native Hermes.

## Consequences

- A long request can share the GPU with a smaller request when their combined
  reservations fit the shared KV pool.
- Concurrency improves throughput and queue behavior, not the speed of one
  compute-bound response.
- Host checkpoints improve reusable-prefix retention but do not preempt or swap
  active requests.
- `max-context` prevents larger-history rejection but does not remove the
  prompt-ingestion cost; `balanced` remains the responsive default.
- Manual edits that drift from a named runtime profile are rejected. This keeps
  the beginner path reproducible and makes benchmark reports interpretable.
