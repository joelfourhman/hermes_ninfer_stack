## Summary

<!-- What changed? Keep this focused on the observable result. -->

## Motivation

<!-- What problem does this solve, and why does it belong in this stack? -->

## Validation

<!-- Check the commands you ran. Explain skipped checks. Do not report unmeasured GPU results. -->

- [ ] `python3 scripts/validate.py`
- [ ] `docker compose config --quiet`
- [ ] Bash syntax and ShellCheck
- [ ] `docker compose build sandbox`
- [ ] Local GPU build and `make verify` (required only for runtime/GPU changes)
- [ ] Other focused checks described below

Validation details:

## Security and persistence

- [ ] No secret, private state, model weight, log, SSH material, or personal path is included.
- [ ] Port, network, mount, capability, GPU, and Docker-daemon access are unchanged or justified below.
- [ ] Destructive commands and cleanup behavior preserve models, Hermes state, and workspace data by default.
- [ ] New downloads or dependencies are pinned and license-compatible where practical.

Security or persistence notes:

## Documentation and compatibility

- [ ] User-facing commands and referenced paths match the implementation.
- [ ] Documentation and `CHANGELOG.md` are updated when behavior changes.
- [ ] RTX 5090, driver, CUDA, model, and NInfer compatibility claims are based on verified evidence.

## Upstream and licensing

<!-- Identify an upstream issue/commit when updating Hermes, NInfer, model, image, or package pins. Preserve dependency licenses and notices. -->
