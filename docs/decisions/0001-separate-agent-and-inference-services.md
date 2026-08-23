# ADR 0001: Separate agent orchestration and inference services

- Status: Accepted
- Date: 2026-08-23

## Context

Hermes Agent owns conversations, integrations, memory, tool selection, and agent control flow.
NInfer owns a large immutable model artifact, CUDA initialization, GPU memory, and token generation
on an RTX 5090. Their release cadences, resource requirements, failure modes, and security exposure
are different.

Running both responsibilities in one process or container would couple Hermes state migrations and
integration changes to a source-built GPU runtime. It would also require granting the orchestration
environment access to the GPU and model weights even though it does not use them directly.

## Decision

Run Hermes and NInfer as separate long-running Compose services. NInfer exclusively owns the GPU
and read-only model mount. Hermes reaches it through an authenticated HTTP provider endpoint on an
internal bridge network and starts only after NInfer is healthy.

Treat the service boundary as part of the product architecture rather than a replaceable packaging
detail. Updates to either component are reviewed and deployed independently, and direct NInfer API
checks remain available to isolate inference failures from orchestration failures.

## Alternatives considered

- **Link NInfer into Hermes.** Rejected because NInfer is a source-built C++/CUDA engine while
  Hermes is a separately released agent product. A direct integration would create unnecessary
  build, language, lifecycle, and ownership coupling.
- **Launch NInfer as a Hermes child process.** Rejected because model residency and GPU lifetime
  would then follow the orchestrator process, making restarts expensive and failure attribution
  less clear.
- **Run NInfer directly on the host.** Rejected because it would introduce undocumented host
  toolchain and process-management dependencies and weaken the reproducible Compose boundary.
- **Run inference inside the tool sandbox.** Rejected because tool commands are less trusted and do
  not need access to model weights or the GPU.

## Consequences

- Hermes can be recreated without rebuilding NInfer or changing model state.
- NInfer source, CUDA image, and model compatibility can be pinned and verified independently.
- GPU and model access are granted to one narrowly scoped service.
- The stack gains an HTTP hop, another image, and a readiness dependency.
- Compose startup ordering protects initial readiness, but a later NInfer restart can still produce
  transient provider errors in Hermes until NInfer recovers.
- Cross-service configuration—especially API key, model alias, and context ceiling—must remain
  synchronized by the setup and configuration scripts.
