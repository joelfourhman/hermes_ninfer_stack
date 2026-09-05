## Summary

<!-- What changed? Keep this focused on the observable result. -->

## Motivation

<!-- What problem does this solve, and why does it belong in this stack? -->

## Validation

<!-- Check the commands you ran. Explain skipped checks. Do not report unmeasured GPU results. -->

- [ ] `python ninfer.py validate`
- [ ] `docker compose config --quiet`
- [ ] Python syntax checks
- [ ] `docker compose --profile tools build model-fetcher`
- [ ] Local `python ninfer.py verify` (required only for runtime/GPU changes)
- [ ] Other focused checks described below

Validation details:

## Security and persistence

- [ ] No secret, local Hermes configuration, model weight, log, benchmark output, or personal path is included.
- [ ] Port, network, mount, capability, GPU, and Docker-daemon access are unchanged or justified below.
- [ ] Destructive commands and cleanup behavior preserve models and the user's Hermes configuration by default.
- [ ] Native Hermes permissions and same-user filesystem risk are documented when affected.
- [ ] New downloads or dependencies are pinned and license-compatible where practical.

Security or persistence notes:

## Documentation and compatibility

- [ ] User-facing commands and referenced paths match the implementation.
- [ ] Documentation and `CHANGELOG.md` are updated when behavior changes.
- [ ] RTX 5090, driver, CUDA, model, and NInfer compatibility claims are based on verified evidence.

## Upstream and licensing

<!-- Identify an upstream issue/commit when updating Hermes, NInfer, model, image, or package pins. Preserve dependency licenses and notices. -->
