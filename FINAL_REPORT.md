# Implementation report

The stack now has authoritative provenance, explicit DFlash2 support, coherent
workload profiles, actual agent-work measurements and durable bounded Hermes
jobs. Stock/balanced/MTP3 remains the recommended default. No remote supervisor
call was made, no changes were pushed, and original artifacts were retained.

## Architecture before and after

Before: stock native Hermes Desktop, one hardened Compose NInfer service, an
optional downloader, three fixed runtime profiles and duplicated configuration
facts. Hermes sessions were native but there was no project epoch ledger or
repeatable whole-agent benchmark suite. The original suite contained 35 tests.

After: keep that native Desktop/API/container boundary, with `stack/manifest.json`
as authority for source, artifacts and resource profiles. Add small modules for
API/metrics/workloads, durable epochs, native hook observations, backend mapping,
optional review and generated documentation. The stock Hermes distribution is
not forked. Jobs use a private home and existing CLI session/checkpoint mechanisms.
See [architecture](docs/architecture.md) and [audit](AUDIT.md).

A follow-up adds `use` presets so daily switching takes one command. These
manifest-defined presets apply model, runtime and decoder together, start NInfer
once, synchronize Hermes, retain download confirmation and roll the whole
selection back if startup fails. Native `ninfer-*` profiles isolate these local
settings from other providers, and `configure-client` provisions the same
profiles on a trusted LAN host. Granular controls remain for experiments.

## Exact provenance and profiles

NInfer before: `ad0f3d384b5cbcec4a48a3951c287b4e9831443e`.

NInfer after: `d49296868dcc17bd478ec185f0d3a801bcc0bf56` (audited master commit, not a tagged stable release).

The original stock and uncensored artifact bytes/checksums are unchanged.
The additional stock-dflash 2 NVFP4 v 2 artifact was explicitly downloaded,
SHA-256 verified and stored under a different local filename. Exact immutable
revisions, filenames, byte counts, hashes and profile definitions are in the
[generated reference](docs/generated-config.md), derived from the manifest.

Original balanced/single-session/max-context names remain. Added interactive,
coding, research, autonomous and low-vram profiles. The final coding/autonomous
KV pool was reduced to 196,608 after a reproduced DFlash2 memory reservation
failure at 240,000; the per-request limit stays 196,608. Research/max-context stay
240,000. Profile changes synchronize Hermes context/compression/turns while
preserving execution/approval preferences, and restore both configs on failure.

MTP1–5 (including MTP3) and DFlash2-1–15 (including 7 and 11) are configurable;
DFlash2 is capability-gated to the companion artifact. `--lm-head-draft` and
preserved thinking remain enabled. Selecting an incompatible older artifact
explicitly restores MTP3 with a notice. No universal DFlash2 default was adopted.

## Cache, metrics and performance evidence

FP8 KV, shared lane capacity, device/host state and pinned host KV are configured
using verified upstream semantics. Stable Hermes system/tool/history ordering is
preserved; dynamic handoffs are appended in user turns. Native reasoning and tool
messages survive the benchmark client. Caches/Responses IDs are process-local.

Benchmarks include real fixture reads, two edits/test cycles, research ingestion,
growing history, two concurrent lanes and an actual Hermes CLI driver. Outputs
include acceptance, wall/model/tool time, token/cache/TTFT/prefill/decode metrics,
memory samples and native reuse/speculative records. Unknown metrics remain null;
interval counters are not falsely attributed to one request. `observe` adds
active runtime and optional job/session/epoch/milestone/latest-hook information.

See [measured results](BENCHMARK_RESULTS.md),
[machine-readable evidence](benchmarks/measured-summary.json) and
[exact RTX 5090 commands](BENCHMARK_PLAN.md). Those documents separate initial
failed candidates, different artifacts, warm repetitions and small sample limits.

## Durable jobs, supervision and execution

`job init/resume/status/checkpoint/recover/replan/export` wraps bounded stock
Hermes epochs. Checksummed atomic state, snapshot retention, a controller lock,
fresh typed reports and independent validation provide restartable handoffs.
Repeated identical failures or exhausted retries force re-planning. Epoch/turn/time
budgets prevent an unbounded loop. Native filesystem checkpoints and a pre-tool
handoff write are enabled. Startup failures save redacted evidence before rollback.

Two real local epochs ran in separate processes, resumed the saved Hermes session
and completed the independently validated fixture.14 actual API hooks recorded
durations. Corruption recovery and live-worker guards are unit-tested. An actual
reboot was not performed; recovery is epoch/session-based, not a rollback of
arbitrary in-flight external effects. See [jobs](docs/jobs.md).

Local execution remains unchanged. Optional container jobs clone committed HEAD
into a disposable workspace and use an explicit toolchain image, one bounded
mount, CPU/RAM limits, dropped capabilities, no privilege escalation and default
no network. The worker image built; its clone, isolated command and artifact
extraction passed. A real Hermes container epoch also completed with independent
validation. SSH maps to an explicitly provisioned Linux host; no remote
host was available. The native Hermes process and arbitrary browsers/connectors
are not fully isolated. Remote child cleanup needs operator inspection on timeout.

The compatible supervisor is disabled and uses environment credentials. Packets
are allowlisted, previewable and sent only by an explicit enabled `--send` action
for a documented escalation reason. Reviews are advisory. No API keys were
committed and no remote model was invoked.

## Verification and CI

Windows/Linux CI now compiles all Python modules, runs unit tests, pinned Ruff,
generated-document checks and a mock agent fixture. Linux additionally checks
clean submodule/gitlink provenance, Compose and downloader build. GPU work stays
manual; CI does not require an RTX 5090 or expose it to untrusted pull requests.

Local verification executed:

- 59 Python tests on Windows and Linux (55 passed, 4 GPU-only skips in each CPU
  run); all 4 live protocol tests also passed separately on stock/MTP3 and on
  companion/DFlash2-11.
- Ruff static checks, compileall, generated docs, repository invariants and
  `git diff --check`; explicit Compose ordinary/tools configuration checks.
- Full upgraded NInfer CUDA image build and optional downloader/worker builds.
- Published model SHA-256 checks, image revision and real binary CLI help.
- Real stock GPU chat/SSE/tool/thinking/prefix tests; actual Hermes local epochs
  and the measured RTX 5090 workload matrix.

The final validation counts and live/service status are recorded in
[PROJECT_STATE.md](PROJECT_STATE.md). No GitHub Actions run is claimed: CI files
were changed locally, and the work was not pushed. Responses/Anthropic support
was source-audited but not given live round-trip tests. No remote supervisor,
SSH worker, browser isolation or multi-hour stability test was performed.

## Local system changes and recovery

The original image is retained as `hermes-ninfer:baseline-mtp3`. The new companion
artifact adds about 22 GiB; both original model files remain. The optional worker
image is `hermes-agent-worker:local`. Ruff was installed only into ignored
`out/lint`; no host-global package installation was required for these modules.
Private raw benchmarks, demo sessions, validation logs and exports remain ignored.
Temporary code-generation/debug scripts are removed after final verification.

The competing chat process chain was stopped with explicit permission; saved
sessions remain intact. Desktop and gateway were not stopped. After measurement,
the original uncensored/max-context/MTP3 selection is restored on the upgraded
image, and Hermes receives the matching context settings. Restart Desktop to
reload them; resuming the former long chat is left to the operator.

## Exact changed files

The following paths are relative to the repository, compared with the original
`37d57b2` baseline. The pre-existing untracked `HERMES_LONG_RUN_RULES.md` is excluded
and was not edited or committed.

- `.dockerignore`
- `.env.example`
- `.github/workflows/ci.yml`
- `.gitignore`
- `AUDIT.md`
- `BENCHMARK_PLAN.md`
- `BENCHMARK_RESULTS.md`
- `CHANGELOG.md`
- `CONTRIBUTING.md`
- `FINAL_REPORT.md`
- `PROJECT_STATE.md`
- `README.md`
- `benchmarks/README.md`
- `benchmarks/measured-summary.json`
- `docker-compose.yml`
- `docs/architecture.md`
- `docs/compatibility.md`
- `docs/configuration.md`
- `docs/decisions/0012-durable-measured-agent-platform.md`
- `docs/design-overview.md`
- `docs/generated-config.md`
- `docs/installation.md`
- `docs/jobs.md`
- `docs/models.md`
- `docs/performance.md`
- `docs/security.md`
- `docs/troubleshooting.md`
- `model-downloader/Dockerfile`
- `model-downloader/download_model.py`
- `ninfer`
- `ninfer.py`
- `pyproject.toml`
- `requirements-dev.txt`
- `scripts/benchmark.py`
- `scripts/validate.py`
- `scripts/verify.py`
- `stack/__init__.py`
- `stack/api.py`
- `stack/bench_agent.py`
- `stack/commands.py`
- `stack/config.py`
- `stack/documentation.py`
- `stack/execution.py`
- `stack/hermes_plugin/__init__.py`
- `stack/hermes_plugin/plugin.yaml`
- `stack/hermes_runner.py`
- `stack/jobs.py`
- `stack/manifest.json`
- `stack/metrics.py`
- `stack/provenance.py`
- `stack/storage.py`
- `stack/supervisor.py`
- `stack/testing.py`
- `stack/workloads.py`
- `supervisor.example.json`
- `tests/test_api_live.py`
- `tests/test_benchmarks.py`
- `tests/test_config.py`
- `tests/test_jobs.py`
- `worker/Dockerfile`
