# ADR 0007: Offer fixed stock and uncensored model profiles

- Status: accepted
- Date: 2026-09-05

## Context

First-time RTX 5090 users need the quickest reliable route to Hermes Desktop,
while some operators explicitly want the uncensored model. The original
uncensored path imposed a 55 GiB source download, 90 GiB workspace requirement,
GPU conversion, and a model-behavior tradeoff on every
new user. Accepting arbitrary model URLs would make compatibility, provenance,
storage estimates, and safe rollback impossible to promise.

## Decision

Setup offers exactly two reviewed profiles:

1. `stock`, the recommended default, downloads the pinned
   `neroued/Qwen3.8-27B-nvfp4-NInfer` artifact and verifies its exact size and
   SHA-256.
2. `uncensored` downloads a pinned, checksum-verified NInfer artifact as defined
   by ADR 0009.

The selection occurs before the profile-specific disk check and before the
explicit large-transfer confirmation. `NINFER_MODEL_PROFILE` and
`NINFER_MODEL_FILE` form a validated fixed mapping; users cannot select an
unreviewed path by editing a URL.

`python ninfer.py select-model` provides the same choice after setup. Both
artifacts are retained. The helper verifies a selection, backs up `.env`, and
requires NInfer health plus a real authenticated generation. When that live
test fails and the previous artifact exists, it restores and starts the former
profile.

Both profiles advertise `qwen-local`, so Hermes configuration and chat history
do not require migration when the weights change.

## Consequences

- Enter at the model menu gives beginners the lower-friction stock path.
- Selecting uncensored is an informed, explicit action.
- Keeping both artifacts consumes about 37 GiB, excluding Docker images;
  deletion remains a separate manual operation.
- Verification and benchmarking must record and validate the active profile.
- New profiles require code and documentation changes rather than arbitrary
  runtime input.
