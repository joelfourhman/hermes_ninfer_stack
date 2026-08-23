# Contributing

Contributions that improve reproducibility, safety, documentation, or verified
RTX 5090 behavior are welcome. Keep changes focused on the stack rather than
forking the responsibilities of Hermes Agent or NInfer into this repository.

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

```bash
git clone --recurse-submodules https://github.com/joelfourhman/hermes_ninfer_stack.git hermes-ninfer-stack
cd hermes-ninfer-stack
```

If the repository was cloned without submodules:

```bash
git submodule update --init --recursive
```

Run the cross-platform Python setup helper to create local configuration and
directories:

```bash
python stack.py setup
```

Do not download the model merely to edit documentation or run static checks.
GPU integration tests require the documented model artifact, Docker GPU
passthrough, and an RTX 5090.

## Required checks

Run the checks relevant to the change. The normal non-GPU validation set is:

```bash
python3 scripts/validate.py
docker compose config --quiet
bash -n scripts/*.sh sandbox/entrypoint.sh
shellcheck scripts/*.sh sandbox/entrypoint.sh
docker compose build sandbox
```

The GitHub workflow runs equivalent lightweight checks. It checks out NInfer so
Compose can validate the build context, but it does not build NInfer, download a
model, start the stack, or run inference.

For changes that affect the running stack, also run the local integration path
on supported hardware:

```bash
docker compose build
docker compose up -d
make verify
```

Report the exact checks run and any checks that could not run. Never fabricate
GPU, latency, throughput, or compatibility results.

## Change guidelines

- Preserve the separation between orchestration, inference, and tool execution.
- Keep machine-specific paths and tunable values out of tracked runtime state.
- Do not expose new host ports, mount the Docker socket, add privileged mode,
  enable host networking, or broaden host mounts without a documented threat
  model and strong justification.
- Give GPU access only to NInfer.
- Pin externally downloaded artifacts and verify checksums where practical.
- Keep setup idempotent and avoid deleting model, workspace, Hermes, or named
  volume state implicitly.
- Update documentation, examples, validation, and changelog entries with user-
  visible behavior.
- Submit NInfer engine changes to its upstream repository. Update the submodule
  pin here only after the upstream commit is available and reviewed.

Shell scripts use Bash with `set -Eeuo pipefail`, clear error messages, and
ShellCheck-clean constructs. Python validation must remain standard-library-only
unless a dependency is justified and documented.

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
Hermes state, workspace output, SSH material, or model artifacts.

## Licensing

Unless explicitly stated otherwise, contributions to stack-authored files are
submitted under Apache License 2.0. NInfer, model artifacts, container images,
system packages, and bundled third-party components retain their own licenses
and attribution requirements. Preserve upstream license and notice files.
