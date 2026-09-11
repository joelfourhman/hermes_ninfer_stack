# Implementation state

Implementation, self-review and live validation are complete. See FINAL_REPORT.md
for architecture, exact changed files, tests and limitations; BENCHMARK_RESULTS.md
and benchmarks/measured-summary.json contain the measured evidence.

- Follow-up adds manifest-defined one-command deployment presets: `use default`,
  `coding`, `coding-fast`, `research`, `low-vram` and `uncensored`. Each applies
  model/runtime/decoder together with one restart and transactional rollback.
  Each preset now creates and activates a separate native `ninfer-*` Hermes
  profile. `configure-client` securely provisions the same profile mapping on a
  trusted LAN computer and verifies its authenticated endpoint before writing;
  `configure-client all` provisions every native profile with one command.
  The full suite contains 67 tests: 63 pass and 4 GPU-only tests skip. Repository,
  generated-documentation, lint and whitespace checks pass.

- Source authority: stack/manifest.json. NInfer upgraded ad0f3d3 -> d492968.
  Original baseline: 37d57b2. Audit/config/benchmark/jobs/recovery checkpoints
  precede the final documentation, CI and measurement milestone.
- Defaults remain stock/balanced/MTP3. The current active selection is
  stock/autonomous/MTP3 with 196,608 context tokens. The matching native
  `ninfer-autonomous` profile is active with both agent and goal limits at
  100,000 turns; restart Desktop to load it in the running app.
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
