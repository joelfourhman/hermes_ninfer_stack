# Design overview

## Design target

This project optimizes for a specific local deployment: one owner, one NVIDIA GeForce RTX 5090,
one resident NInfer model, and Hermes Agent as the orchestration layer. The goal is reproducible
operation and understandable security boundaries, not a generic model-serving platform or a
multi-tenant agent service.

That constraint shapes the design. The stack prefers explicit service ownership, fixed internal
contracts, and a small set of reviewed tunables over runtime discovery or broad hardware support.

## Why orchestration and inference are separate

Hermes and NInfer have different responsibilities and lifecycles.

Hermes owns conversations, integrations, provider routing, tool selection, memory, and agent
control flow. NInfer owns an immutable model artifact, CUDA initialization, GPU memory, scheduling,
and token generation. Combining them would couple Hermes upgrades and state migrations to a costly
GPU build and model load, and it would place agent-facing code in the same process boundary as the
inference engine.

Separate containers make that ownership visible:

- Hermes can be recreated while the model server remains resident.
- NInfer can be rebuilt at a reviewed source commit without altering Hermes state.
- Only NInfer needs access to the GPU and model mount.
- Failures can be localized by calling NInfer directly before testing the complete agent route.
- Each component can retain its upstream configuration and release cadence.

The cost is an HTTP hop and another health dependency. On a local host, that overhead is negligible
relative to model inference and is outweighed by the operational separation.

## Why the inference boundary is OpenAI-compatible

Hermes already understands custom providers through a chat-completions transport. NInfer provides
the corresponding authenticated HTTP surface, including model listing, assistant content,
reasoning fields, and structured tool-call output. Using that protocol keeps the integration at a
documented product boundary instead of linking Hermes to NInfer's C++ internals or parsing a CLI
subprocess stream.

The configurable `NINFER_MODEL_ID` is an HTTP alias shared by both services. It is intentionally
separate from the native model identity embedded in the `.ninfer` artifact: the alias is provider
configuration, while the embedded identity selects NInfer's registered execution path.

“OpenAI-compatible” describes the supported request/response surface, not an assertion that NInfer
implements every OpenAI API. The stack depends only on the endpoints and fields verified by its
integration tests. NInfer can parse and return tool calls, but Hermes remains responsible for
validating and executing them.

## Why model artifacts are external

The default model is about 20 GiB, has its own upstream license and provenance, and changes on a
different cadence from the Compose project. Committing it to Git, placing it in Git LFS, or baking
it into the NInfer image would make clones and image rebuilds unnecessarily expensive and would
obscure which bytes were actually tested.

Instead, model acquisition requires explicit local consent:

1. `python stack.py setup` identifies the large transfer and asks before starting it;
   `python stack.py download-model` provides the same acquisition as a standalone recovery step.
2. The accepted download starts a uv-managed Compose utility that identifies the
   repository, revision, filename, size, and destination before downloading.
3. The helper verifies the published SHA-256 checksum.
4. Compose mounts `./models` read-only into NInfer.
5. Git ignores model formats and local download cache data.

This makes a fresh clone intentionally incomplete until the owner opts into the large download. It
also lets images be rebuilt without copying the artifact into the build context. The NInfer source
submodule is pinned independently, so source and artifact compatibility remain reviewable facts.
The utility runs from a digest-pinned official `uv` image and installs no host package.

## Why only NInfer receives the GPU

Hermes does not perform CUDA inference, and tool commands have no legitimate need for the GPU.
Restricting the device reservation to NInfer prevents accidental contention, reduces the number of
processes that can inspect device memory or affect GPU state, and makes resource ownership obvious.

The tradeoff is deliberate specialization. NInfer is compiled for `sm_120a`, and verification
rejects a different visible GPU. Supporting other accelerators would require a different inference
engine or a separately qualified NInfer target; it is not hidden behind a generic setting here.

`NINFER_GPU_DEVICE` exists for multi-GPU hosts where the RTX 5090 is not device zero. It selects the
device; it does not turn the deployment into a multi-GPU server.

## Why tool execution uses SSH

Hermes's built-in Docker terminal path would require control of the Docker daemon to manage an
existing sidecar. Mounting `/var/run/docker.sock` would effectively give model-directed code root
control over the host's Docker environment. Running commands inside the Hermes container would mix
untrusted tool effects with credentials, integrations, and persistent agent state.

The SSH sidecar provides a narrower interface. Hermes receives a read-only client key and connects
to a fixed unprivileged account over an internal network. The sandbox has a read-only root
filesystem, bounded temporary filesystems, no sudo, no GPU, no Docker socket, no host port, and no
default egress. Its only writable host bind is the project workspace; its home and SSH identity use
project-scoped named volumes.

Python package workflows inside that sandbox use digest-pinned `uv` and `uvx` binaries. The
stack-owned image does not install pip.

This is containment, not a claim that arbitrary commands are safe. A generated command can destroy
workspace files, corrupt the persistent sandbox home, consume its allowed resources, or act on data
placed there by the user. The sandbox is also shared across sessions. Strong multi-user isolation
would require per-request disposable environments and a different threat model.

## State ownership

Persistent state is separated by purpose:

- `hermes/config.example.yaml` is the reviewed public template.
- `hermes-data/` is the ignored live Hermes state root, including secrets, sessions, memory, skills,
  logs, backups, and migrated configuration.
- `models/` contains ignored, checksum-verified artifacts.
- `workspace/` contains ignored user and agent work products.
- Docker named volumes retain the sandbox home and SSH keys.

Hermes sees the workspace read-only. Tool writes happen through the sandbox, so the orchestrator
does not need a writable project bind simply to support terminal operations. Container recreation
preserves all of these stores; deleting Compose volumes is a separate, explicitly destructive act.

## Configuration philosophy

Only settings that differ legitimately between otherwise identical RTX 5090 installations are
environment variables:

- host port and GPU index;
- model filename, public alias, context ceiling, and concurrency;
- Hermes image and host UID/GID;
- local API secrets; and
- CPU, memory, and PID limits for Hermes and the sandbox.

Service DNS names and internal ports stay fixed. They are implementation contracts, not user-facing
deployment choices. The unified setup workflow generates random secrets, creates local state
directories, asks before model acquisition, builds the images, runs the Hermes wizard, and applies
shared model and SSH values through Hermes's supported configuration command so model ID and context
do not drift between the provider and server.

This division avoids a large environment surface while still covering real machine differences.
Changing the model file to an artifact outside the documented release profile is possible, but it
is an engineering change that requires confirming NInfer compatibility and re-running the full
verification suite.

## Readiness and failure isolation

The startup graph checks useful readiness rather than container existence:

- the key initializer must finish successfully before the sandbox starts;
- the sandbox must have a valid authorized key, valid SSH configuration, and running daemon;
- the networkless trust reconciler must validate the persisted sandbox public host key and update
  only Hermes's `[sandbox]:2222` entry;
- NInfer must finish loading the model and answer its HTTP health endpoint; and
- Hermes starts only after both downstream services are healthy and trust reconciliation succeeds,
  then exposes its own loopback health endpoint.

The long NInfer start period acknowledges that loading a 20 GiB artifact and initializing GPU
state can take minutes. Graceful-stop windows give inference and orchestration time to finish
shutdown work.

Compose dependency conditions apply during startup, not as a continuous service mesh. If NInfer or
the sandbox fails later, its own restart policy handles recovery while Hermes may briefly return a
provider or tool error. This behavior is preferred to automatically discarding Hermes state or
restarting the entire stack for every downstream interruption.

## Exposure decisions

The host receives a loopback-only NInfer port for direct diagnostics and a loopback-only Hermes
dashboard port for local browser access. Both are authenticated and neither is exposed to the LAN.
Hermes's verification API and the sandbox SSH endpoint are not published. User interaction can use
the dashboard, an in-container CLI session, or integrations selected during Hermes setup.

NInfer and the sandbox attach only to internal networks. Hermes has ordinary egress because
integrations and orchestrator-side services may require it. A credential-free, unprivileged relay
bridges NInfer's authenticated API to host loopback because Docker Desktop does not publish a host
port for an internal-only container. This does not make all Hermes activity
sandboxed: plugins, hooks, MCP processes, and other orchestrator-side code still run with Hermes's
own mounts and network access. Security documentation must preserve that distinction.

## Single-GPU tradeoffs

The default profile prioritizes useful long-context local-agent behavior on 32 GiB of VRAM:

- NVFP4 model weights reduce the resident model footprint.
- INT8 KV storage and an explicit 65,536-token pool preserve useful context while leaving several
  GiB of RTX 5090 headroom for desktop and runtime variability.
- MTP with three draft tokens improves the qualified decode path.
- Vision is disabled at runtime to avoid its fixed allocations.
- Concurrency is fixed at startup, matching NInfer's bounded single-model scheduler.

This is not a distributed or elastic serving design. There is no GPU failover, model hot-swap, CPU
offload, or preemptive multi-tenant scheduler. Those omissions keep the configuration and failure
model honest for the hardware being targeted.

## A path to multiple inference nodes

The HTTP provider boundary leaves room for a future deployment with multiple NInfer hosts, but the
current Compose file does not implement it. A larger design could place a health-aware router in
front of several independently pinned NInfer instances and point Hermes at that router. Each node
would still own one GPU, one model instance, and its own prefix/KV state.

That change would require explicit decisions about request affinity, authentication and TLS,
capacity reporting, failure retries, model-version consistency, and observability. Simply scaling
the current service count would be incorrect because every replica currently requests a specific
GPU and maintains process-local inference state.

## Maintainer invariants

Changes should preserve these properties unless an ADR explicitly supersedes them:

1. Hermes, NInfer, and tool execution remain separate service boundaries.
2. Only NInfer receives GPU access and a model mount.
3. Tool execution receives neither the Docker socket nor broad host filesystem access.
4. Live Hermes state, model weights, secrets, and workspace output remain outside Git.
5. The model artifact and NInfer source revision remain independently pinned and verifiable.
6. Hermes and NInfer use the same public model alias and context ceiling.
7. Healthchecks test service readiness, and the verifier tests a real end-to-end tool side effect.
8. Hermes keeps strict SSH host-key checking; trust comes from the persisted Docker volume rather
   than an unauthenticated network scan.
