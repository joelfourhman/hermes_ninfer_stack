# Changelog

All notable changes to this project will be documented in this file. The format
is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Interactive `stock` or `uncensored` model profiles in first-run setup, with
  the verified stock Qwen3.8-27B NVFP4 artifact as the recommended default.
- `python ninfer.py select-model` for preparing and switching profiles while
  preserving both artifacts and restoring the previous working model after a
  failed startup test.
- Cross-platform `python ninfer.py setup` workflow that creates local
  configuration, explicitly asks before downloading the model, starts NInfer,
  and then offers to install and configure stock Hermes Desktop.
- `python ninfer.py install-hermes` helper that directs users to the official
  stock installer when needed, then configures Hermes's custom
  OpenAI-compatible provider for the local NInfer endpoint.
- Beginner preflight checks for Python, disk space, Git, the RTX 5090 driver,
  Docker Compose, a running Docker engine, and Linux-container mode. On
  Windows, setup starts an installed Docker Desktop application when needed.
- Automatic RTX 5090 device selection for fresh multi-GPU installations, with
  an early error when an existing `.env` points at another GPU.
- Pinned, resumable, checksum-verified direct downloads for both stock and
  uncensored NInfer artifacts through one uv-locked downloader.
- Layered validation, direct-NInfer verification, and RTX 5090 benchmark helpers.
- Reviewed `balanced`, `single-session`, and `max-context` runtime profiles,
  plus `select-runtime` with startup testing, rollback, and Hermes synchronization.
- `diagnose-performance` for prompt-safe summaries of TTFT, throughput, cache
  reuse, MTP acceptance, queue pressure, and context failures from bounded logs.

### Changed

- Simplified the runtime architecture so NInfer is the only long-running
  application container; stock Hermes Desktop or native Hermes now runs as the
  signed-in host user.
- Published the authenticated NInfer API on host loopback for native Hermes,
  without exposing it to the LAN.
- Removed the contradictory internal-network flag so Docker Desktop can
  actually publish that loopback port, and added one automatic network
  recreation when a healthy container has no reachable localhost endpoint.
- Updated NInfer to its resource-aware Device/Host context-cache runtime and
  made the balanced 131K-context, 196K shared-KV, two-lane FP8 profile the
  beginner default. Hermes now compresses at 90K tokens.
- Made `python ninfer.py` the single supported control surface for setup,
  lifecycle, Hermes integration, validation, verification, and benchmarking.
- Made Enter accept both normal first-run choices, added numbered progress and
  resumable error guidance, and made `up` wait until the authenticated model
  API is actually ready and returns a short generated answer.
- Added a stock Hermes close/reload handoff and automatic Windows Desktop
  relaunch when the standard executable is available. The Hermes-only recovery
  command also starts Docker and an already-configured NInfer service when
  needed.
- Removed the legacy Bash wrappers, container-Hermes configuration, loopback
  relay, and SSH-sandbox build assets.
- Removed the obsolete Unix-only Make wrapper, unused root Docker ignore file,
  legacy repository workspace placeholder, and redundant command aliases;
  `ninfer.py` is the sole host control surface.
- Updated architecture, installation, configuration, model, security,
  compatibility, performance, troubleshooting, and design documentation for the
  native-Hermes boundary.
- Simplified non-GPU continuous integration around Python validation, Compose
  rendering, and the one-shot model-downloader image.
- Replaced the uncensored 55 GiB source download and local GPU conversion with
  a pinned 16.96 GiB artifact whose checksum exactly matches the local build.
- Removed the source-fetch and conversion services, their dependency locks,
  the 90 GiB build workspace, and the runtime logic that stopped NInfer for
  conversion.

### Security

- Kept the NInfer host API on loopback and authenticated it with a generated
  bearer key.
- Restricted the NInfer service to its model mount and GPU; it receives no broad
  host-filesystem mount, Docker socket, privileged mode, or host networking.
- Dropped container capabilities, enabled no-new-privileges and init handling,
  and bounded NInfer logs so they cannot grow without limit.
- Made both container root filesystems read-only and gave NInfer only a bounded
  temporary filesystem; setup now backs up and removes obsolete legacy secrets
  and container settings from the local `.env`.
- Configured and verified Hermes `approvals.mode: manual` for the native
  beginner profile instead of relying on the stock smart-approval default.
- Kept manual command approvals but restored stock Hermes working-directory and
  file-tool behavior by removing the former `terminal.cwd` and
  `HERMES_WRITE_SAFE_ROOT` overrides.
- Documented that native Hermes has the signed-in user's filesystem authority and
  that UAC protects administrator elevation, not ordinary same-user files.
- Excluded secrets, model weights, local Hermes configuration, logs, and
  benchmark output from Git.
