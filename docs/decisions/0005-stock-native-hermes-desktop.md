# ADR 0005: Run stock Hermes Desktop natively

- Status: Accepted; workspace policy amended by ADR 0008
- Date: 2026-08-30

## Context

The project needs a local Hermes user experience backed by the RTX 5090 NInfer
server. The former design packaged Hermes, a dashboard, and an SSH tool sandbox
inside one Compose project. That increased project-owned configuration and did
not use the ordinary Hermes Desktop lifecycle as the source of truth.

The operator wants the stock Hermes Desktop installation, not a repository
fork, wrapper GUI, or custom executable.

## Decision

Run NInfer as the only long-running container. Install Hermes Desktop through
the official Hermes distribution and run it natively as the signed-in user.

After NInfer is healthy, `python ninfer.py install-hermes` finds or directs the
user to the stock installer and uses the supported Hermes CLI to create a named
`ninfer` provider. Native Hermes connects to the authenticated host-loopback
endpoint at `http://127.0.0.1:${NINFER_HOST_PORT}/v1`.

Because native Hermes has the user's filesystem authority, the helper also
sets `approvals.mode: manual` rather than accepting the stock smart-approval
default, sets the local terminal starting directory to `workspace/`, and uses
`HERMES_WRITE_SAFE_ROOT` to block direct file tools outside that folder and the
Hermes profile. These are guardrails, not a sandbox around native terminal
commands.

The helper preserves unrelated Hermes state and does not own Hermes updates or
uninstallation.

## Consequences

- Hermes Desktop follows its official install, update, data, and support path.
- The Compose definition and operational surface are smaller.
- No relay, dashboard publication, SSH network, or sandbox identity lifecycle
  is required.
- NInfer and Hermes can be upgraded and diagnosed independently across the
  OpenAI-compatible boundary.
- Native tools run with current-user authority. The former SSH containment no
  longer exists, and UAC is not a same-user filesystem sandbox.
- Operators requiring stronger isolation must add an OS account, VM, or other
  separately managed boundary.

## Alternatives

- **Keep Hermes in Compose.** Rejected because it is not the requested stock
  Desktop lifecycle and retains unnecessary project-owned services.
- **Build a custom Desktop installer.** Rejected because it creates a
  downstream package and update responsibility.
- **Install Hermes before NInfer is healthy.** Not selected for the default
  flow because provider discovery and verification should target a reachable
  endpoint. Hermes can still be installed independently and configured later.
- **Claim approvals or UAC as containment.** Rejected because both are useful
  guardrails but neither restricts ordinary files already writable by the
  current user.
