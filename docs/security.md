# Security model

## Summary

The active design provides a container boundary around NInfer, not around
Hermes. It is intended for one operator on a local workstation and is not a
multi-tenant or internet-facing agent service.

Stock Hermes Desktop runs natively as the current OS user. It therefore has the
same filesystem and process authority as that user. UAC limits unapproved
elevation on Windows, but it does not stop a non-elevated Hermes process from
modifying or deleting files the current user can modify or delete.

## Trust boundaries

| Component | Host access | Network access | Persistent data | Principal risk |
| --- | --- | --- | --- | --- |
| Native Hermes Desktop/runtime | Everything allowed to the current user | Selected NInfer endpoint and any egress allowed to the user | Standard Hermes config, secrets, sessions, memory, skills, logs | Prompt injection, unsafe tools, plugins, or compromised runtime acting with user authority |
| NInfer container | Read-only model directory and GPU device | Authenticated host-published API; ordinary outbound bridge access | No application state in Compose | Native parser/runtime, LAN exposure, outbound access, or GPU-driver compromise |
| Model downloader | Read/write ignored `models/`; no GPU | Temporary outbound Hugging Face access | Resumable artifact cache | Supply-chain input, disk exhaustion, or corrupted partial download; mitigated by immutable revisions and SHA-256 |
| Docker daemon | Container, image, network, volume, and GPU control | Host-dependent | Docker-managed state | Docker access is effectively administrative for this deployment |

NInfer is the only long-running container. No Docker socket, broad host path,
host network, host PID namespace, or privileged mode is exposed to it. The
root filesystem and model mount are read-only; a bounded in-memory `/tmp` is
the only writable container filesystem. Its bridge is not an `internal` Docker network
because Docker Desktop cannot publish an internal-network service to a host
interface; therefore the container is not an egress sandbox.

Ordinary Desktop has no active SSH sandbox. Explicit durable jobs can now select the SSH backend described in [jobs](jobs.md). Historical documentation describing one is
retained only in the superseded ADR.

## Reduced-refusal model behavior

The selected source model was modified to reduce refusals. Its publisher
measured 12 refusals on 100 held-out harmful prompts versus 98 for the base
model, not zero refusals, and explicitly did not evaluate code, math,
generative, vision, or MTP behavior. This is neither a guarantee of usefulness
nor a security control.

Assume it may attempt actions a safety-trained model would decline. Keep manual
approvals, use the smallest practical toolset, and independently review commands
that delete, overwrite, install, transmit, or establish persistence. The NInfer
API boundary limits network exposure; it does not make model output safe.

## NInfer endpoint

Compose publishes NInfer as:

```text
${NINFER_BIND_ADDRESS}:${NINFER_HOST_PORT} -> ninfer:8080
```

The default `127.0.0.1` bind prevents ordinary remote clients from reaching the
service. Opt-in LAN mode binds one RFC1918 address, never `0.0.0.0`. NInfer
requires the generated bearer key in both modes. LAN traffic is HTTP without
TLS, so the endpoint and key should be used only on a trusted private network.

`configure-client` accepts only an explicit loopback or RFC1918 IPv4 HTTP URL
ending in `/v1`. It reads the key from the requested environment variable or a
hidden prompt, authenticates against `/models`, then stores it in the selected
native Hermes profile's private `.env`. Do not pass the key as a command-line
argument, commit that profile data, or copy `network --show-key` output into logs.

Do not configure router port forwarding. Scope the host firewall rule to its
Private profile and local subnet. These controls do not defend against another
LAN device that knows the key, a hostile device able to observe unencrypted
traffic, or an attacker already able to inspect the user's files, Hermes state,
Docker metadata, or processes. Return to local-only mode when remote access is
not needed.

## Native Hermes authority

Hermes can propose and execute tools. When it uses native terminal, file,
browser-control, plugin, connector, cron, or computer-use capabilities, those
actions occur with current-user authority unless the upstream tool introduces
its own stronger boundary.

Important consequences:

- files in Documents, source checkouts, cloud-synced folders, and other
  user-writable locations are within reach;
- user-readable credentials may be exposed to a compromised or
  prompt-injected tool;
- another local process launched by Hermes inherits the user's permissions;
- if the current user can control Docker, a Docker command approved for Hermes
  can control it too; the NInfer container's missing Docker socket does not
  sandbox the separate native Hermes process;
- a malicious package, plugin, hook, or repository script can persist outside
  this project;
- Hermes retains its built-in protected-path denylist, but other direct file
  operations and terminal commands run as the user;
- approval dialogs and protected-path checks reduce accidents but are not
  kernel enforcement for every possible execution path.

For stronger isolation, run Hermes under a dedicated standard OS account or in
a separately managed VM and expose only the intended work area. That is an
operator choice outside the default project setup.

## Recommended operating policy

- Keep the helper-configured `approvals.mode: manual` setting enabled. It
  requires a user decision for commands Hermes flags; it does not turn every
  tool call into a prompt or create an OS sandbox.
- Add `HERMES_WRITE_SAFE_ROOT` yourself only if you deliberately want direct
  file tools confined to chosen folders. It does not restrict terminal commands.
- Do not enable YOLO or unattended broad command approval for sensitive work.
- Use the smallest practical tool and plugin set.
- Treat content from websites, documents, issue reports, repositories, and
  tool output as potentially prompt-injected.
- Use disposable copies for unfamiliar projects and generated experiments.
- Keep important work in version control.
- Maintain backups under a different identity or medium that the active user
  and Hermes cannot silently overwrite.
- Review commands that delete, overwrite, change permissions, install
  packages, add startup persistence, or transmit data.

Controlled Folder Access or similar endpoint controls can add protection on
Windows, but only if Hermes and its interpreters are not broadly allowlisted.
Such controls need independent testing; this repository does not configure or
claim them.

## Filesystem and persistence

- `.env` contains the NInfer key and must remain ignored.
- `models/` contains a large native artifact mounted read-only into NInfer.
- Stock Hermes's per-user home contains provider secrets, conversations,
  memory, skills, installed integrations, and logs.
- NInfer container recreation does not clear native Hermes state.
- Hermes uninstall and data removal are controlled by the official Hermes
  lifecycle, not by this project.

Do not place secrets or irreplaceable data in a location merely because it is
outside this repository. Native Hermes is not restricted to the project tree.

## Secrets

`python ninfer.py setup` generates a random NInfer bearer key in the ignored
project `.env`. `python ninfer.py install-hermes` stores the same value through
Hermes's supported secret writer and configures `key_env: NINFER_API_KEY`.
The key is not embedded in provider YAML.

Recommended handling:

- never commit project `.env` or Hermes user data;
- do not post environment dumps, authorization headers, or URLs containing
  credentials;
- do not include the bearer key in benchmark reports;
- treat users with Docker-daemon access or access to Hermes's secret file as
  able to recover the key;
- rotate the key after suspected disclosure, recreate NInfer, and rerun the
  Hermes helper;
- rotate every other credential available to Hermes if the native runtime may
  have been compromised.

## Native-code and GPU boundary

NInfer parses the model container and request payloads in native C++/CUDA code
with GPU-device access. Its read-only model mount reduces ordinary filesystem
impact but does not eliminate parser, CUDA-runtime, or driver risk. Use only the
documented artifact revision and verify its SHA-256 before startup.

Hermes is also executable code with a broader user-level attack surface:
Electron, Python, dependencies, integrations, browser automation, and any tools
the operator enables. Keep it updated through the official distribution and
review release notes for security-relevant changes.

## Supply chain

The project pins the NInfer source commit and the model repository revision and
SHA-256. These controls establish identity, not trust. CUDA images, operating
system packages, Docker, the NVIDIA driver, Python dependencies, and stock
Hermes remain supply-chain inputs.

The helper always directs installation to the official Hermes site. It does not
mirror, wrap, or sign an alternative Desktop executable. Confirm publisher and
download origin using normal platform controls.

## Incident response

If compromise or secret disclosure is suspected:

1. Stop NInfer without deleting evidence: `python ninfer.py down`.
2. Close Hermes Desktop and stop its native background processes.
3. Disconnect the host from untrusted networks if active exfiltration is
   possible.
4. Preserve relevant, redacted Docker and Hermes logs outside the repository.
5. Rotate the NInfer key and every external credential available to Hermes.
6. Inspect native persistence, installed plugins, skills, hooks, scheduled
   tasks, browser state, and modified user files.
7. Reinstall or restore Hermes and user data from a known-good source when
   integrity is uncertain.
8. Restore affected work from protected backups and run full verification.
9. Report project vulnerabilities through the process in the root
   `SECURITY.md`.

Do not publish live credentials or unredacted private prompts while reporting
an incident.

## Optional job execution and supervision

Durable local jobs retain user authority and manual approvals. Private Hermes
homes prevent job provider/backend/plugin changes from rewriting Desktop config.
Container jobs opt into one disposable clone mount, explicit image/toolchain,
CPU/RAM bounds, dropped capabilities, no privilege escalation and default no
network. SSH jobs use an explicitly provisioned Linux workspace. The native
Hermes process remains on the host; browser/connector containment is not claimed.
No broad host mounts, Docker socket or inference credentials are forwarded to the
worker container. Docker itself remains a privileged host dependency.

Checkpoint hashes detect accidental corruption, not a hostile same-user actor.
Native tool filesystem checkpoints and epoch ledgers do not undo network actions.
Private logs/reports/session databases can contain project information and must
not be committed. An opt-in supervisor sends only after explicit `--send`, using
an environment credential and a reviewable compact packet. See [jobs](jobs.md).
