# Implementation state

- Audit, config/provenance, benchmark/API and durable jobs committed through
  0c0b8cc. Original baseline: 37d57b2; audit checkpoint: 3104b6e.
- Single authority: stack/manifest.json. NInfer ad0f3d3 -> d492968. Baseline
  image preserved as hermes-ninfer:baseline-mtp3; original artifacts retained.
- Defaults remain stock/balanced/MTP3. Original user active selection was
  uncensored/max-context/MTP3: restore after benchmarks.
- Self-review fixes: transactional profile/Hermes rollback, explicit MTP
  fallback, atomic report validation, live-worker recovery guard, process-tree
  timeout cleanup, artifact export and richer benchmark summaries. 58 tests
  pass (4 GPU skips); four GPU protocol tests separately passed. Ruff and
  repository validation pass. Commit fixes before documentation milestone.
- Real Hermes coding fixture passed in43.56s. Durable demo completed epoch2
  in a separate process, resumed saved session and passed independent tests.
- Clean stock/coding MTP3:3/3 median5.56s; stock/balanced:3/3 median4.05s.
  Original uncensored/max-context baseline35.02s vs newuncensored/coding7.88s
  are single confounded samples: do not claim controlled speedup.
- Companion artifact downloaded and SHA256 verified, balanced/MTP3 starts.
  Coding startup in session80173, log out/profile-dflash-coding.log. Next
  companion codingMTP3/D7/D11, research, growing and parallel benchmarks.
- User authorized stopping competing Hermes chat; stopped only identified
  TCP-owner39548, parent10060, launcher30092. Sessions intact; Desktop/gateway
  preserved. No builds/downloads currently active.
- Next: generated README/reference, docs/CI, results/final report, full checks,
  self-review, cleanup and final logical commits.
- HERMES_LONG_RUN_RULES.md is pre-existing user content: do not edit/commit.
- Temporary audit/demo code is ignored under out/. Do not delete all out/.
- Supervisor disabled; no remote calls. Local durable execution tested;
  container/SSH integrations still need qualification.
