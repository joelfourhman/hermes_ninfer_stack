# Local benchmark results

`python ninfer.py benchmark` and `python ninfer.py bench-agent` write result directories here. Results
include prompts, model responses, raw SSE timing, and GPU samples, so everything
under this directory except this file is ignored by Git.

`benchmark` measures direct inference. `bench-agent` measures accepted multi-turn
fixture work, including real tools/tests. Its optional `--driver hermes` measures
actual stock Hermes CLI epochs. Neither measures Desktop startup. Compare only
matching driver, fixture and workload parameters; mock smoke runs have no valid
performance timing. See [the matrix](../BENCHMARK_PLAN.md).

Do not publish a result until its environment metadata and generated content
have been reviewed. See [the performance guide](../docs/performance.md) for the
methodology and reporting rules.
