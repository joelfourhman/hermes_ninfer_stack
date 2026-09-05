# Security policy

This repository connects a tool-capable native agent to a GPU inference service.
Treat model output, tool requests, downloaded content, and persistent agent state
as untrusted. NInfer is containerized; Hermes Desktop/native Hermes is not.

## Supported versions

Before the first stable release, security fixes are applied to the default
branch. After releases begin, only the latest minor release line and the default
branch are expected to receive security fixes.

| Version | Supported |
| --- | --- |
| Default branch | Yes |
| Latest minor release | Yes |
| Older releases | No |

## Trust boundaries

- **Hermes Desktop/native Hermes runs as the signed-in host user.** It can read,
  modify, or delete anything that user can access. UAC can stop an unapproved
  administrator elevation, but it does not protect ordinary same-user files.
  Limit the folders and tools you grant to Hermes, review sensitive actions, and
  maintain tested backups or snapshots.
- **NInfer is the only long-running application container.** Its API is bound to
  host loopback and requires the generated bearer key. It receives GPU access
  and a read-only model mount, but no Docker socket or broad host-filesystem
  access. Its normal Docker bridge permits outbound traffic; it is not an
  egress sandbox.
- **Model preparation uses two one-shot utility containers.** The networked
  fetcher writes only ignored build data and receives no GPU. The converter
  receives the selected GPU and model output directory but has no runtime
  network. Inputs, uv dependencies, frontend files, and converter source are
  pinned; operators should still treat them as third-party code or data.
- **Reduced refusal behavior is not a safety boundary.** The selected model may
  attempt requests the base model declines. Manual approvals, OS permissions,
  narrow tools, and protected backups remain the relevant controls.
- **Docker remains a privileged trust dependency.** Anyone who controls the
  Docker daemon or can change this repository's Compose files can change the
  container boundary.

Run Hermes from a normal, non-administrator account. Keep NInfer on loopback,
use a unique generated API key, and do not weaken mounts, capabilities, or
networking merely to work around a configuration problem.

## Report a vulnerability privately

Use this repository's GitHub **Security** tab and select **Report a
vulnerability** to open a private vulnerability report. Do not include
vulnerability details, secrets, private logs, or proof-of-concept exploits in a
public issue or discussion.

Include, when available:

- the affected commit or release;
- the affected component and configuration;
- prerequisites and reproduction steps;
- observed and expected behavior;
- the potential impact and affected trust boundary;
- a minimal proof of concept with secrets and personal data removed; and
- any mitigation already tested.

Reports about the Hermes-to-NInfer integration, Compose policy, loopback API, or
stack-authored Python belong here. Report vulnerabilities wholly within Hermes,
NInfer, NVIDIA CUDA images, Qwen artifacts, or another dependency to that
upstream project. If an upstream issue becomes exploitable specifically because
of this project's configuration, report it here as well.

Maintainers will acknowledge a complete report as practical, investigate it,
coordinate remediation and disclosure, and credit reporters who request credit.
Please allow time for a fix to be prepared before publishing details.

## Secrets exposed during testing

If a credential is accidentally committed, attached to an issue, or included
in logs, revoke or rotate it immediately. Removing it from the latest commit is
not sufficient because Git history and notification copies may retain it. Do
not rewrite repository history or invalidate shared credentials without first
coordinating with the maintainers.

See [the security model](docs/security.md) for boundaries, residual risks, and
operator guidance.
