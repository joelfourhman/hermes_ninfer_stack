# Compatibility

Exact source/artifact pins are in the [generated reference](generated-config.md).
The selected NInfer master commit supports Qwen3.8-27B NVFP4, MTP1–5, DFlash2
with matching companion weights, FP8/BF16/INT8/NVFP4/K8V4 KV options, shared
capacity across 1–8 lanes, continuation state and host KV. This stack validates
FP8 profiles; alternative KV formats have not been performance-qualified here.

The pinned server implements OpenAI Chat Completions, Responses and Anthropic
Messages. Hermes is configured for Chat Completions. Live tests cover Chat JSON,
SSE including empty-choice usage events, tool round trips, thinking preservation
and exact-prefix reuse. Responses/Anthropic existence is source-verified but their
full protocol semantics are not covered by these live tests. Responses IDs are
process-local. Vision is disabled in the deployed profile.

Hermes is installed through its official distribution rather than pinned/forked
here. Durable jobs probe required chat flags at runtime and use native resume,
run-budget, checkpoints and hook APIs. Missing required flags fail clearly;
optional hook metrics may remain unavailable on older builds. The audited Hermes
source commit and observed live build are recorded in AUDIT and benchmark evidence.

Windows Python unit/lint/generated-doc checks remain in CI; Linux also validates
submodule provenance, Compose and builds the downloader. Neither requires a GPU.
The main supported hardware target is RTX 5090/sm_120a. Live GPU tests and the
benchmark matrix are manual commands, not automatic untrusted-PR workloads.
SSH targets require Linux and existing known-host/key configuration. Container
images and worker dependencies are explicitly selected by the operator.
