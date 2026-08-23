# ADR 0004: Execute tools through a constrained SSH sandbox

- Status: Accepted
- Date: 2026-08-23

## Context

Hermes can ask a model to use terminal, file, and code-execution tools. Those commands are derived
from model output and may be influenced by prompt injection or untrusted content. They need a
writable working directory and common development utilities, but they do not need the host Docker
daemon, the GPU, model weights, or the complete host filesystem.

Using Hermes's Docker terminal backend for an already-running sidecar would require access to the
Docker socket. Access to that socket is effectively host-level container control and would defeat
the intended boundary. Executing commands directly inside Hermes would mix tool effects with
orchestrator credentials, integrations, and persistent state.

## Decision

Run tool commands in a dedicated SSH sandbox service and configure Hermes's terminal backend to
connect as the unprivileged `agent` user over the internal `sandbox-net`.

The sandbox:

- publishes no host port and has no ordinary egress network;
- receives no GPU, Docker socket, privileged mode, or broad host mount;
- uses key-only SSH with forwarding and tunneling disabled;
- has a read-only root filesystem and bounded temporary filesystems;
- drops Linux capabilities, enables `no-new-privileges`, and applies CPU, memory, and PID limits;
- mounts only `./workspace` as a writable host path; and
- keeps its home and SSH host identity in project-scoped named volumes.

A one-shot, networkless initializer creates the persistent client key and authorized key. Hermes
receives the client key read-only, while the sandbox receives the authorized key read-only. Hermes
itself sees the shared workspace read-only; mutations occur through the SSH boundary.

A second networkless, unprivileged one-shot service runs after sandbox health. It validates the
ED25519 public host key from the persistent `sandbox-host-keys` volume, removes only the stale
`[sandbox]:2222` record from Hermes's `known_hosts`, and installs the persisted public key. Hermes
waits for this reconciliation and retains strict host-key checking. The reconciler receives neither
network access nor read permission to the private host key.

## Alternatives considered

- **Mount `/var/run/docker.sock` into Hermes.** Rejected because model-directed behavior could then
  create privileged containers, mount arbitrary host paths, or interfere with unrelated workloads.
- **Run tools in the Hermes container.** Rejected because tool commands would share the
  orchestrator's state, credentials, dependencies, and egress boundary.
- **Run commands directly on the host.** Rejected because it would provide broad filesystem and
  process access and introduce machine-specific setup.
- **Publish sandbox SSH to the host.** Rejected because Hermes is its only intended client; an
  internal network is sufficient.
- **Create a disposable container for every tool call.** Not selected for this single-owner stack
  because Hermes benefits from a persistent shell, workspace, and user-installed tooling. It would
  also require a trusted external container controller. Per-request isolation remains a different
  architecture for a stronger threat model.

## Consequences

- Tool execution is separated from Hermes credentials, NInfer, and the Docker control plane.
- The workspace is the explicit host-side blast radius for ordinary tool writes.
- The sandbox cannot fetch dependencies from the internet by default; enabling egress is a conscious
  policy change.
- SSH client and host identities survive container recreation, avoiding silent trust resets.
- The sandbox is shared across Hermes sessions and retains `/home/agent`; it is not a multi-tenant
  or per-conversation isolation boundary.
- Generated commands can still delete workspace data, corrupt sandbox-home state, or exhaust the
  resources allowed by the configured limits.
- Hermes plugins, hooks, integrations, MCP subprocesses, and other orchestrator-side code do not
  automatically pass through this SSH boundary and must be assessed separately.
- `docker compose down -v` is destructive because it removes the persistent sandbox home and SSH
  identities; normal shutdown must omit `-v`.
