# Implementation state

Goal: purpose-built Windows/RTX 5090 NInfer platform for stock Hermes agents.

- Audit complete; see AUDIT.md. Baseline: 35 tests and repository validation pass.
- User's pre-existing HERMES_LONG_RUN_RULES.md is preserved without alteration.
- Source upgrade target: d492968; original source/artifacts and MTP3 remain recoverable.
- New artifact selection must be explicit; no silent model/security changes.
- Config authority implemented in stack/manifest.json; source checkout upgraded.
- Added explicit stock-dflash2 artifact, legal draft counts, five candidate workload
  profiles and generated reference. Existing 35 + five new tests pass.
- Current milestone: finalize config/provenance validation and commit; build may
  run concurrently but the baseline container must remain until measured.
- Following milestones: protocol metrics/agent benchmarks; durable Hermes epochs,
  optional supervisor and native backend integration; docs/CI/live validation.
- GPU and baseline container are available. No new performance results yet.
- Audit-only upstream Hermes checkout is ignored under out/.
