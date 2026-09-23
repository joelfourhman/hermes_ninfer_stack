# Implementation state

## Upstream v3 and network discovery — September 23, 2026

- Reviewed 44 upstream commits and selected `594930e7b609efa4bcea3ae4f24cd9d66b5f224f`;
  submodule gitlink is staged, other implementation edits remain uncommitted.
- All three existing published artifacts are retained and migrated to reproducible
  `.v3.ninfer` files. Manifest pins both source and derived hashes. Converter/template
  text is normalized to LF for Windows/Linux parity; weight bytes are copied unchanged.
- Authenticated `/v1/models` supplies the actual model/context to network clients.
  Served IDs include model profile and context; `connect` discovers before each CLI
  launch, clamps compression and leaves default profile activation unchanged.
- Source/CUDA image checks rebuild only stale images. `up` migrates the selected
  artifact when needed and synchronizes local Hermes. Model switches now synchronize
  Hermes and roll its configuration back if synchronization fails.
- CUDA runtime and downloader images built. Six real GPU API tests passed, including
  localhost/LAN discovery, stale-model rejection, tools, reasoning and exact-prefix reuse.
  Offline suite: 81 tests, 75 passing and 6 live-only skips; lint/docs/repository checks pass.
- All seven presets passed 3/3 bounded workload runs, plus original
  uncensored/autonomous 3/3, an actual Hermes coding task, and a two-lane task.
  DFlash2-11 was faster than DFlash2-7 in this short coding sample; both remain
  explicit choices. Research's 16-slot candidate had no measured benefit, so
  the profile retains 8 slots. See `BENCHMARK_RESULTS.md` and the hashed summary.
- All 11 live verification layers passed, including native Hermes generation.
  Original uncensored/autonomous/MTP3 is restored at 196,608 context/shared KV;
  the API key and LAN configuration are unchanged. Repeated startup preserves
  the resident container/cache. The isolated LAN profile was refreshed without
  activation; Desktop must restart to load its updated configuration.
- Docker startup was repaired by preserving its stopped IPC directory as
  `%LOCALAPPDATA%/Docker/run.before-ninfer-20260923`; no engine data was reset.
- Existing untracked `HERMES_LONG_RUN_RULES.md` remains untouched.

## Context reliability follow-up — September 14, 2026

- Active selection is now **uncensored / autonomous / MTP3**: 196,608 context and
  shared KV tokens, two lanes, compression at 80,000. This supersedes the older
  restored-max-context notes below. Native Hermes configuration and gateway are synchronized.
- Reproduced a current Hermes bug: NInfer HTTP 400 overflow text was classified
  as a fatal format error. Two backed-up native source additions recognize the
  error and parse its actual engine limit. `scripts/patch_hermes_context.py`
  preserves the repair; `scripts/check_hermes_context.py` tests its behavior.
- Desktop and durable jobs now share earlier compression, explicit local summary
  routing, lean tail retention and a 600-second summary timeout. Repeated live
  testing reproduced summary output exhaustion with reasoning enabled; summaries
  now disable thinking while main-agent reasoning stays unchanged.
- 71 stack tests pass (4 live-only skips); the 4 live API tests passed separately.
  Native Hermes's required isolated runner passed 281 classifier/metadata tests.
  See `docs/context-reliability.md` and ignored `out/context-*` evidence for the
  final active-profile verification and compaction measurements.
- Existing unrelated edits remain intact. No user conversation was deleted, no
  task-specific overnight work was invented, and no multi-hour soak is claimed.
- Native Hermes updates can replace the local repair. Run `python ninfer.py verify`
  after updates; it now detects the original classification regression.
- Final verification passed all 11 layers on autonomous. Two successive real
  compactions reduced 117,801 → 15,944 and 133,691 → 16,017 tokens, with checkpoint
  recall after each. The concurrent native Hermes coding task passed its three
  independent tests. NInfer and the reloaded gateway remain running; all audit
  workloads have finished.
- Restored the existing managed `ninfer-*` profile and `configure-client`
  integration while retaining the context fixes. The documented second-host
  setup uses `--no-activate`, so the existing default provider profile is untouched
  and NInfer is selected explicitly with `hermes -p ninfer-autonomous`.

## Earlier implementation record

Implementation, self-review and live validation are complete. See FINAL_REPORT.md
for architecture, exact changed files, tests and limitations; BENCHMARK_RESULTS.md
and benchmarks/measured-summary.json contain the measured evidence.

- Follow-up adds manifest-defined one-command deployment presets: `use default`,
  `coding`, `coding-fast`, `research`, `low-vram` and `uncensored`. Each applies
  model/runtime/decoder together with one restart and transactional rollback.
  Preset compatibility, one-start behavior and rollback are tested; 62 tests
  pass locally (58 passed, 4 GPU-only skips). Repository/docs/lint checks pass.

- Source authority: stack/manifest.json. NInfer upgraded ad0f3d3 -> d492968.
  Original baseline: 37d57b2. Audit/config/benchmark/jobs/recovery checkpoints
  precede the final documentation, CI and measurement milestone.
- Defaults remain stock/balanced/MTP3. The user's original active selection,
  uncensored/max-context/MTP3, is restored and healthy on the upgraded image.
  Hermes context is synchronized to 240,000; restart Desktop to reload config.
- Both original artifacts remain. The explicit companion artifact was downloaded
  and checksum verified. Baseline image: hermes-ninfer:baseline-mtp3.
- Two initial DFlash2-7 startup attempts at 240,000 KV failed. Diagnostic evidence
  captured a reservation of 9,978,952,960 bytes versus 9,469,855,232 available.
  Coding/autonomous now use 196,608 shared KV tokens. All tuned coding modes
  passed 3/3: MTP3 median 4.322s, D7 3.262s, D11 3.203s. Actual Hermes passed
  1/1 each: 29.02s, 27.03s and 26.08s. No default change from these small samples.
- Research passed 3/3 at up to 86,118 input tokens. Growing sessions passed 3/3,
  reached 235,910 input tokens and exercised one compression per run. Two-lane
  parallel workloads passed 3/3. Raw private evidence remains ignored.
- Durable local demo resumed its saved session across two processes/epochs and
  completed independent validation. Worker image, disposable clone, validation,
  artifact export and an actual native Hermes container epoch all passed.
- Final CPU suite: 59 tests on Windows and Linux, 55 passed + 4 GPU-only skips
  each. All 4 live protocol tests passed separately on stock/MTP3 and DFlash2-11.
  All 11 full verification layers passed after restoring the original profile.
  Ruff, compileall, generated docs, repository invariants, diff whitespace,
  ordinary/tools Compose configuration and downloader build passed.
- The user authorized stopping the competing chat chain (39548/10060/30092).
  Saved sessions, Desktop and gateway remain intact. No benchmark/build runs
  remain active. Native inference remains available.
- Temporary audit clone and task scripts are removed. Private results, job demo
  sessions, validation logs, exports and the local Ruff tool remain under ignored
  benchmarks/ and out/. Do not delete all out/ as generic cleanup.
- HERMES_LONG_RUN_RULES.md is pre-existing user content: not edited or committed.
- Supervisor disabled; no remote calls. SSH, actual reboot, full browser isolation,
  Responses/Anthropic live round trips and multi-hour stability remain untested.
