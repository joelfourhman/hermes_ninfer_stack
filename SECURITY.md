# Security policy

This repository runs a tool-capable agent and a GPU inference service. Treat
model output, tool requests, downloaded content, and persistent agent state as
untrusted. Docker narrows the blast radius, but it does not make autonomous
execution inherently safe.

## Supported versions

Before the first stable release, security fixes are applied to the default
branch. After releases begin, only the latest minor release line and the
default branch are expected to receive security fixes.

| Version | Supported |
| --- | --- |
| Default branch | Yes |
| Latest minor release | Yes |
| Older releases | No |

## Report a vulnerability privately

Use this repository's GitHub **Security** tab and select **Report a
vulnerability** to open a private vulnerability report. Do not include
vulnerability details, secrets, private logs, or proof-of-concept exploits in a
public issue or discussion.

Include, when available:

- the affected commit or release;
- the affected service and configuration;
- prerequisites and reproduction steps;
- observed and expected behavior;
- the potential impact and affected trust boundary;
- a minimal proof of concept with secrets and personal data removed; and
- any mitigation already tested.

Reports about the stack's integration, Compose policy, sandbox boundary, or
stack-authored scripts belong here. Report vulnerabilities wholly within
Hermes Agent, NInfer, NVIDIA CUDA images, Qwen artifacts, or another dependency
to that upstream project. If an upstream issue becomes exploitable specifically
because of this stack's configuration, report it here as well.

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
