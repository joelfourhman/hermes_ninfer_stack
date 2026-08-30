# Local benchmark results

`python ninfer.py benchmark` writes timestamped result directories here. Results
include prompts, model responses, raw SSE timing, and GPU samples, so everything
under this directory except this file is ignored by Git.

These measurements exercise the NInfer API directly. They do not measure Hermes
Desktop startup, host tool execution, or end-to-end agent latency.

Do not publish a result until its environment metadata and generated content
have been reviewed. See [the performance guide](../docs/performance.md) for the
methodology and reporting rules.
