# 0012: Verified decoding, measured work and durable epochs

Status: accepted; performance candidates remain subject to measurement.

Centralize source/artifact/profile definitions in one manifest and fail on drift.
Preserve MTP3 and the original artifacts. Expose DFlash2 only with explicitly
verified companion weights, and compare decoders on the same artifact. Retain
balanced as the default until accepted agent-workload evidence supports a change.

Extend stock Hermes sessions with bounded epochs, atomic handoffs, native hooks,
independent validation and retry budgets. Keep volatile inference caches separate
from durable project/session state. Execution backends reuse native Hermes tools;
supervision stays disabled and requires an explicit send. Publish metric scope
and unknowns, generate mechanical documentation and keep Windows CPU-only CI.

This supersedes the fixed source/profile mechanics in earlier records, while
preserving the native Desktop boundary, local authenticated API and optional LAN.
