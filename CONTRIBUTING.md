# Contributing

Contributions that improve reproducibility, safety, documentation, or verified
RTX 5090 behavior are welcome. Keep changes focused on the Hermes-to-NInfer
integration rather than forking Hermes or NInfer in this repository.

## Before opening an issue

- Search existing issues and the troubleshooting guide.
- Use the bug template for reproducible failures and the feature template for
  proposed behavior.
- Report vulnerabilities only through GitHub private vulnerability reporting,
  following `SECURITY.md`.
- Remove API keys, private prompts, usernames, absolute personal paths, model
  files, and unrelated environment details from all diagnostics.

## Development setup

Clone the repository with its pinned NInfer submodule:

```text
git clone --recurse-submodules https://github.com/joelfourhman/hermes_ninfer_stack.git hermes-ninfer-stack
cd hermes-ninfer-stack
```

If the repository was cloned without submodules:

```text
git submodule update --init --recursive
```

Use Python as the cross-platform host entry point. Docker Desktop or Docker
Engine must already be running:

```text
python ninfer.py setup
```

Setup explicitly asks before downloading approximately 55 GiB of source
weights and converting them. It starts the verified NInfer artifact first,
then offers to install and configure the official stock Hermes
Desktop/native package for the current host user. The Hermes-only step can be
rerun without rebuilding NInfer:

```text
python ninfer.py install-hermes
```

Do not download the model merely to edit documentation or run static checks.
GPU integration tests require the documented model artifact, Docker GPU
passthrough, and supported NVIDIA hardware.

## Required checks

Run the checks relevant to the change. The normal non-GPU validation set is:

```text
python ninfer.py validate
docker compose config --quiet
python -m py_compile ninfer.py scripts/benchmark.py scripts/validate.py scripts/verify.py
docker compose --profile tools build model-fetcher
```

The GitHub workflow runs equivalent lightweight checks. It does not build
NInfer, download a model, install Hermes, start inference, or claim GPU
compatibility.

For changes that affect the running service or Hermes integration, also run the
local integration path on supported hardware:

```text
python ninfer.py setup
python ninfer.py verify
```

Report the exact checks run and any checks that could not run. Never fabricate
GPU, latency, throughput, or compatibility results.

## Change guidelines

- Preserve the boundary between native Hermes and containerized NInfer.
- Keep machine-specific paths and tunable values out of tracked runtime state.
- Keep NInfer bound to host loopback. Do not mount the Docker socket, add
  privileged mode or host networking, or broaden host mounts without a
  documented threat model and strong justification.
- Give GPU access only to NInfer and the short-lived network-disabled converter.
- Keep Hermes installation and provider changes within the official stock
  install and configuration mechanisms.
- Pin externally downloaded inputs and verify checksums where practical.
- Keep Python dependencies uv-locked; do not introduce pip commands.
- Never treat a GPU-dependent conversion checksum as universal without evidence.
- Keep setup idempotent and avoid deleting model files or the user's Hermes
  configuration implicitly.
- Update documentation, examples, validation, and changelog entries with
  user-visible behavior.
- Submit NInfer engine changes upstream. Update the submodule pin here only after
  the upstream commit is available and reviewed.

Host automation is Python and should remain standard-library-only unless a
dependency is justified and documented. Keep it cross-platform; do not require
PowerShell, Bash, or a host-installed package manager for the normal workflow.

## Pull requests

Keep each pull request cohesive and describe:

- the problem and selected solution;
- security, persistence, networking, and compatibility effects;
- non-GPU checks run;
- local GPU checks run, when applicable; and
- documentation or migration steps.

Use concise Conventional Commit-style subjects where practical, such as
`docs: clarify model setup` or `fix(compose): restrict service exposure`.
Avoid committing generated logs, benchmark scratch data, environment files,
local Hermes configuration, or model artifacts.

## Licensing

Unless explicitly stated otherwise, contributions to stack-authored files are
submitted under Apache License 2.0. NInfer, Hermes, model artifacts, container
images, system packages, and third-party components retain their own licenses
and attribution requirements. Preserve upstream license and notice files.
