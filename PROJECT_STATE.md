# Implementation state

Goal: purpose-built Windows/RTX 5090 NInfer platform for stock Hermes agents.

- Audit complete; see AUDIT.md. Baseline: 35 tests and repository validation pass.
- User's pre-existing HERMES_LONG_RUN_RULES.md is preserved without alteration.
- Source upgrade target: d492968; original source/artifacts and MTP3 remain recoverable.
- New artifact selection must be explicit; no silent model/security changes.
- Config authority implemented in stack/manifest.json; source checkout upgraded.
- Added explicit stock-dflash2 artifact, legal draft counts, five candidate workload
  profiles and generated reference. Existing 35 + five new tests pass.
- Config milestone committed as f115cc1. Upgraded NInfer image builds successfully.
- Benchmark/API modules implemented; 44 tests pass, including real bounded fixture
  edits/tests and mocked streaming reasoning/tool/usage round trip. Baseline GPU
  coding measurement is in progress; preserve baseline container until it finishes.
- Durable epochs implemented, including checksummed snapshots, lock/recovery,
  per-approach retry bounds, private Hermes home and native tool checkpoints.
  Six new job tests pass (50 total). Real Hermes CLI fixture passed in 43.56s
  with 21 observed hook events and persisted session ID.
- Optional supervisor is disabled, sends only by explicit command after enabling.
  Container/SSH mappings added; full-agent isolation is not claimed.
- Current live environment: stock original NVFP4, coding profile, upgraded image.
  Original active environment was uncensored/max-context/MTP3 (not default stock).
- Measured original active baseline: benchmarks/baseline-mtp3-coding (35.02s,
  1 successful sample). New source uncensored/coding: coding-uncensored-mtp3
  (7.88s, 1 successful sample). Different contexts and possible external traffic:
  do not claim a controlled speedup.
- New stock-dflash2 artifact downloaded and checksum verified, originals retained.
- Baseline image tag: hermes-ninfer:baseline-mtp3. No processes currently building.
- User explicitly authorized stopping the external Hermes job for clean benchmarks.
  Identified its TCP owner PID 39548, parent 10060, launcher 30092; only that chat
  process chain is being stopped. Desktop and gateway remain running.
- Four real GPU protocol tests pass on stock NVFP4 (chat/stream/prefix/tools/reasoning).
- Ruff 0.15.6 installed under ignored out/lint; formatter + all lint checks passed
  after five unused-import fixes. 54 unittest cases pass with four live tests skipped
  in the ordinary suite; the four live tests were also run separately and passed.
- Real durable demo: out/run_job_demo.py launches one epoch per invocation,
  first currently running (process session 90961). This ignored fixture needs a
  per-process safe.directory exception due sandbox/user ownership difference.
- Remaining: real durable two-epoch smoke; lint (out/lint/bin/ruff.exe requires
  escalation due installed-file permissions); API live tests; benchmark matrix
  stock/new artifact; docs/CI consistency and self-review; milestone commits.
- Subsystem changes since 0aa7480 are not committed yet. Temporary code-generation
  scripts and upstream Hermes audit clone live ignored under out/.
- Following milestones: protocol metrics/agent benchmarks; durable Hermes epochs,
  optional supervisor and native backend integration; docs/CI/live validation.
- GPU and baseline container are available. No new performance results yet.
- Audit-only upstream Hermes checkout is ignored under out/.
