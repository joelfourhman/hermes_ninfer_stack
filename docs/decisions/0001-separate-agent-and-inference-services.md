# ADR 0001: Separate agent orchestration and inference services

- Status: Superseded in part by the stock native Hermes architecture
- Date: 2026-08-23

The separation of agent orchestration from inference remains valid. The
Compose-specific decision to run both as long-running containers is historical:
the active deployment runs only NInfer in Docker and stock Hermes Desktop
natively. See [Architecture](../architecture.md).

## Context

Hermes Agent owns conversations, integrations, memory, tool selection, and agent control flow.
NInfer owns a large immutable model artifact, CUDA initialization, GPU memory, and token generation
on an RTX 5090. Their release cadences, resource requirements, failure modes, and security exposure
are different.

Running both responsibilities in one process or container would couple Hermes state migrations and
integration changes to a source-built GPU runtime. It would also require granting the orchestration
environment access to the GPU and model weights even though it does not use them directly.

## Decision

Run Hermes and NInfer as separate processes with independent lifecycles. NInfer
is the only long-running Compose service and exclusively owns the GPU and
read-only model mount. Stock Hermes runs natively and reaches it through an
authenticated host HTTP endpoint after NInfer is healthy. ADR 0011 retains
loopback as the default and defines the opt-in LAN mode.

Treat the OpenAI-compatible process boundary as part of the architecture.
Updates to either component are managed independently, and direct NInfer API
checks remain available to isolate inference failures from orchestration
failures.

## Alternatives considered

- **Link NInfer into Hermes.** Rejected because NInfer is a source-built C++/CUDA engine while
  Hermes is a separately released agent product. A direct integration would create unnecessary
  build, language, lifecycle, and ownership coupling.
- **Launch NInfer as a Hermes child process.** Rejected because model residency and GPU lifetime
  would then follow the orchestrator process, making restarts expensive and failure attribution
  less clear.
- **Run NInfer directly on the host.** Rejected because it would introduce undocumented host
  toolchain and process-management dependencies and weaken the reproducible Compose boundary.
- **Package Hermes in this Compose project.** Superseded because it duplicates
  the stock Desktop lifecycle and adds project-owned state and services.

## Consequences

- Hermes can be reinstalled without rebuilding NInfer or changing model state.
- NInfer source, CUDA image, and model compatibility can be pinned and verified independently.
- GPU and model access are granted to one narrowly scoped service.
- The deployment gains an HTTP hop and a readiness dependency.
- A later NInfer restart can produce transient provider errors in Hermes until
  NInfer recovers.
- Cross-service configuration—especially API key, model alias, and context ceiling—must remain
synchronized by the Python setup and native Hermes helper.
