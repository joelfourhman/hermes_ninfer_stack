# NInfer upstream review — October 10, 2026

## Decision

Adopt upstream `81c8ce093b2c1646a87566a8e59d807fcf0ec95c` and retain
`594930e7b609efa4bcea3ae4f24cd9d66b5f224f` as the rollback and measured
baseline. The current stock, uncensored and DFlash2 v3 artifacts remain valid;
no model conversion or Hermes protocol change is required.

## Reviewed change set

The update spans 83 commits. The material integration changes are:

- replacement of the prior context cache with incremental allocation, admission
  control, preemptive scheduling and snapshot/replay restoration;
- one unified host-context arena instead of separate host state slots and host
  KV capacity;
- XGrammar-backed constrained JSON Schema, grammar, choice, regex and strict
  tool-call output;
- Prometheus metrics and request-log schema 25, including scheduling, constraint,
  transfer, pressure and host-context occupancy fields;
- attention, linear and long-prefill performance work plus follow-up cache and
  admission correctness fixes.

The stack now configures 10,240 MiB of host context for standard profiles,
5,120 MiB for single-session and 2,560 MiB for low-VRAM. Existing `.env` files
remove `NINFER_HOST_STATE_SLOTS` and `NINFER_HOST_KV_MIB` during migration.
Hermes automatically benefits from constrained tool framing through the existing
Chat Completions endpoint; there is no Hermes-side grammar option to enable.

## Measured evidence

All tests used Windows, RTX 5090, CUDA 13.1.2, a warmed persistent server and
three repeats unless noted. Successful-run medians are reported; all failures
remain in the denominator.

| Comparison | Accepted | Median wall s |
|---|---:|---:|
| Old pin, uncensored/autonomous/MTP3 coding | 3/3 | 4.514 |
| New pin, same model/profile/decoder/workload | 3/3 | 4.410 |
| Companion coding, DFlash2-11 | 3/3 | 2.752 |
| Companion coding, DFlash2-7 | 3/3 | 2.913 |
| Companion coding, MTP3 | 3/3 | 3.667 |
| Actual Hermes, DFlash2-11 | 3/3 | 56.445 |
| Actual Hermes, DFlash2-7 | 2/3 | 59.070 |
| Actual Hermes, MTP3 | 3/3 | 56.265 |
| 256 KiB research ingestion | 3/3 | 5.487 |
| Growing session | 2/3 | 191.310 |
| Parallel two-lane work | 3/3 | 13.210 |

The matched engine upgrade improved the short coding median by about 2.3%.
DFlash2-11 was fastest in the bounded decoder comparison, but its actual Hermes
median was effectively tied with MTP3. DFlash2-7's failed Hermes run completed
its code validation; Hermes rejected the final response for repetition.

Research reached 85,346 input tokens. The growing session reached 129,246 input
tokens, filled almost all of the 10 GiB host arena, spilled retained pages and
continued checkpoint reuse. Its failed acceptance run passed tests and retained
the requested findings through five compression cycles, but declined to make
unnecessary edits to an already-correct fixture. The two-lane workload passed
3/3 and observed concurrent decode batching. No fixture triggered a preemption,
so the new snapshot/replay path is not claimed as empirically stress-qualified.

## Compatibility and verification

- All three pinned v3 artifacts loaded without rewriting.
- Six live API tests passed: aggregate chat, local/LAN discovery, reasoning
  replay, stale-model rejection, streaming prefix reuse and tool round trip.
- All 11 end-to-end verification layers passed, including authentication,
  provenance, direct generation and native Hermes generation.
- The installed Hermes update had replaced the local NInfer overflow matcher.
  `scripts/patch_hermes_context.py` restored it with timestamped backups, and
  verification confirmed compression recovery again.
- The original uncensored/autonomous/MTP3 selection, LAN binding and existing
  bearer key were restored after the matrix.

These are short qualification samples, not a multi-hour soak or a full-window
quality evaluation. The update is recommended for its scheduling correctness,
memory flexibility, structured outputs and observability; the measured speedup
on the original configuration is real but small.
