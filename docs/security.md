# Security model

This stack deliberately limits what Hermes and model-generated commands can
reach. It is designed for a single trusted operator on a local workstation; it
is not a multi-tenant isolation system, an internet-facing agent service, or a
security boundary against a hostile Docker administrator.

## Trust boundaries

| Component | Host access | Network access | Persistent data | Principal risk |
| --- | --- | --- | --- | --- |
| Hermes | Read/write `hermes-data`; read-only `workspace`; read-only sandbox client key | NInfer, sandbox, and outbound egress | Configuration, memory, sessions, skills, and logs | Prompt injection or plugin code can act with orchestrator privileges |
| NInfer | Read-only model directory; GPU device | Internal inference network and host-loopback published API | None in the Compose definition | Native parser/runtime or GPU-driver compromise |
| Model downloader (explicit profile) | Read/write model directory | Temporary outbound access | Hugging Face staging cache under `models/` | Supply-chain input or corrupted partial download; final artifact is checksum-verified |
| SSH sandbox | Read/write `workspace`; named home and SSH host-key volumes | Internal sandbox network only | Workspace, sandbox home, and SSH identity | Model-generated commands can alter all sandbox-visible data |
| Sandbox key generator | Named SSH key volumes only | No network | Sandbox client and authorized keys | One-shot root process creates a long-lived credential |
| Docker daemon | Full control of containers, images, networks, and volumes | Host-dependent | All Docker-managed state | Docker access is effectively host-administrator access |

Only NInfer receives GPU access. No service mounts the Docker socket, uses
privileged mode, joins the host network or PID namespace, or mounts a broad host
filesystem path. The sandbox publishes no host port. NInfer's API and Hermes's
authenticated dashboard are published on host loopback only. NInfer requires a
bearer key; the dashboard uses a separate generated username, password, and
session-signing secret.

## Request and tool flow

1. Hermes receives operator input and sends an OpenAI-compatible request to
   NInfer over the internal inference network.
2. NInfer evaluates the selected Qwen artifact on the GPU and returns model
   output or a proposed tool call.
3. Hermes validates and orchestrates tool use. Terminal and code execution are
   sent over key-only SSH to the sandbox.
4. The sandbox runs commands as the unprivileged `agent` account. It can write
   the shared workspace and its persistent home, but it has no GPU, host port,
   Docker socket, or outbound network route.

The separation protects the host and inference service from ordinary tool
commands, but it does not make tool output trustworthy. Hermes intentionally
holds the SSH client key and can direct the sandbox. All Hermes-side plugins,
hooks, connectors, and subprocesses remain inside the Hermes container rather
than the SSH sandbox.

## Filesystem and persistence

- `hermes-data` is writable by Hermes and may contain secrets, conversation
  state, memory, logs, installed skills, and user-specific configuration.
- `workspace` is read-only in Hermes and read/write in the sandbox. Any command
  accepted by the agent can create, modify, encrypt, or delete files there.
- `models` is read-only in NInfer. Model artifacts are large executable inputs
  to a native parser and should come only from the documented, checksum-pinned
  source.
- The sandbox home, client key, authorized key, and host key are Docker named
  volumes. The home is shared across sessions, so shell configuration,
  installed packages, and other state can influence later runs.

Do not place irreplaceable files or credentials in the workspace. Maintain
backups outside every mounted directory. `docker compose down -v` deletes the
sandbox home and SSH identity volumes; ordinary `docker compose down` does not.

## Network boundaries

The inference and sandbox networks are marked internal. NInfer cannot initiate
internet access through its Compose network, and the sandbox cannot download
packages or contact a LAN service by default. Hermes also joins a normal bridge
network and therefore retains outbound access for orchestrator features.

Do not change NInfer's host binding from `127.0.0.1` to `0.0.0.0` without an
authenticated reverse proxy, firewall policy, TLS, request limits, and an
explicit remote-access threat model. Never expose the SSH sandbox port to the
host or attach the sandbox to a general egress network merely to make a tool
download convenient.

## Secrets

Project-local API keys are generated into the ignored `.env` file. Hermes may
also write provider or connector credentials beneath ignored `hermes-data`.
The tracked `hermes/config.example.yaml` contains only environment-variable
references, never secret values.

The NInfer key is supplied as a server command argument and is therefore
visible to users who can inspect Docker container metadata or host process
arguments. Such users generally already have extensive control over the stack,
but the key must still not be copied into diagnostics or issue reports. The
verification scripts may briefly place authorization headers in local process
arguments and store synthetic responses in a temporary directory after a
failed check.

Recommended handling:

- never commit `.env`, Hermes state, SSH keys, model artifacts, or command logs;
- use distinct, randomly generated keys and rotate both after suspected
  disclosure;
- redact authorization headers, environment dumps, URLs with credentials, and
  private prompts before sharing diagnostics;
- do not forward environment secrets into the sandbox; and
- treat anyone with Docker-daemon access as able to read container secrets and
  named volumes.

## Prompt injection and agent-generated commands

Content from web pages, repositories, documents, issue reports, and tool output
can contain instructions intended to override the operator's goal or obtain
credentials. The model may also generate an unsafe command without malicious
input.

Before granting the agent access to untrusted content:

- remove credentials and unrelated private data from mounted directories;
- inspect proposed destructive or privilege-changing commands;
- use a disposable workspace for unfamiliar repositories;
- review new scripts, plugins, hooks, package manifests, and shell startup files
  before subsequent sessions; and
- stop the stack if behavior diverges from the requested task.

Loop guardrails reduce repeated failures; they do not determine whether an
individual command is safe.

## Native-code and GPU boundary

NInfer processes model containers and request payloads in native C++/CUDA code
and runs with GPU device access. The service currently uses the image's default
root user and does not have the sandbox's read-only-root or capability-drop
policy. Its only host bind is the read-only model directory, which limits
ordinary filesystem impact but does not eliminate parser, CUDA-runtime, or
driver risk. Use only the documented artifact revision and verify its SHA-256
digest before startup.

Hermes also uses the upstream image's root user because the image performs its
own UID/GID and state initialization. A compromise can modify all Hermes state
and use Hermes's egress or sandbox credential, though it cannot directly write
the host workspace mount.

## Supply-chain controls

The stack pins the NInfer submodule to a commit and the model download to both a
repository revision and a SHA-256 digest. These controls establish identity,
not trust. Review upstream release notes and source changes before updating
either pin.

Container tags, operating-system package repositories, the NVIDIA container
runtime, the Hermes image, developer-installed Python tools, and downloaded
packages remain supply-chain inputs. Prefer reviewed release tags or immutable
image digests, rebuild intentionally, and inspect dependency-license and
security changes during upgrades. CI does not download the model or exercise
GPU inference.

The root Apache-2.0 license covers stack-authored files. The NInfer submodule,
model artifacts, container images, system packages, and vendored dependencies
retain their own licenses and notices.

## Incident response

If compromise or secret disclosure is suspected:

1. Stop the stack without deleting evidence: `docker compose stop`.
2. Disconnect the host from untrusted networks if active exfiltration is
   possible.
3. Preserve relevant, redacted container metadata and logs outside the
   repository.
4. Rotate project API keys and every external credential available to Hermes or
   the sandbox.
5. Recreate affected containers and, when persistence is suspect, replace the
   sandbox home and SSH-key volumes after preserving needed evidence.
6. Restore workspace and Hermes state from a known-good backup.
7. Report stack vulnerabilities through GitHub private vulnerability reporting
   as described in the root `SECURITY.md`.

Do not publish live credentials or an uncoordinated proof of concept while
reporting an incident.
