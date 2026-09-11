# Configuration ownership

`stack/manifest.json` owns source/image revision, immutable artifacts and workload
profiles. `stack/config.py` validates it and projects profile values into Compose
and Hermes. Do not edit the same pin in several files. Update the submodule,
manifest and generated projections together, then run:

```text
python ninfer.py docs
python ninfer.py docs --check
python ninfer.py validate
```

The [generated reference](generated-config.md) contains exact values. CI checks
that the README table and reference match the manifest. `.env.example` contains
the generated source pin and reviewed defaults; local `.env` contains the key,
chosen artifact/runtime/decoder and host networking settings. It is ignored.
Compose requires the source revision interpolation and the helper always supplies
the authoritative revision to builds. `validate` checks the staged gitlink and
actual clean submodule HEAD; `verify` checks image metadata and binary flags.

Workload selection uses `profile NAME` or `select-runtime --profile NAME`.
Model selection uses `select-model --model NAME`. Decoder selection uses
`spec mtp3`, `spec dflash2-7`, or `spec dflash2 --draft-tokens N`. These are separate
choices; DFlash2 is accepted only on the companion artifact. Hand-editing a
profile-controlled capacity produces a clear drift failure. Add a reviewed
manifest profile for reproducible custom settings instead.

Profile changes update the backend and native Hermes provider context,
compression threshold and turn limit. They preserve terminal/approval settings,
back up local config and restore both sides when startup or synchronization fails.
Restart Desktop after profile changes. The initial `install-hermes` setup retains
the existing project behavior: native local tools and manual approvals, removing
obsolete project-imposed working-directory overrides.

Ordinary Desktop data stays in the standard Hermes home. Durable jobs alone
create `.ninfer-jobs/JOB/hermes/`, with private provider configuration, session
database and observer plugin. Resuming a job regenerates its provider context
from the active backend configuration. Its explicit backend is job-scoped.

Network inputs remain `NINFER_ACCESS_MODE`, `NINFER_BIND_ADDRESS`, host port,
GPU selection and API key. `network --mode local` uses loopback; `network --mode lan` verifies
an assigned RFC1918 address and tests the authenticated endpoint before accepting
the change. `network --show-key` deliberately reveals the credential; do not
paste that output into issues or benchmark reports.
