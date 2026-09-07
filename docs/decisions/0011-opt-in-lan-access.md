# ADR 0011: Provide opt-in authenticated LAN access

- Status: Accepted
- Date: 2026-09-06

## Context

Fresh installs should not expose a large local inference service to other
machines. Some operators nevertheless need a second computer on the same
trusted LAN to use the RTX 5090 host. Editing Compose to bind `0.0.0.0` would
expose every host interface and bypass the project's configuration, testing,
rollback, and Hermes synchronization paths.

## Decision

Keep `local` mode on `127.0.0.1` as the default. Provide
`python ninfer.py network --mode lan`, which prefers the host's default-route
RFC1918 IPv4 address and publishes only that address. An explicit `--address`
supports deliberate multi-interface selection. Continue requiring the
generated bearer key for every request.

The command warns before enabling LAN access, backs up `.env`, recreates and
live-tests NInfer, restores the previous configuration on failure, and updates
the local Hermes provider. It displays connection metadata without the secret;
`--show-key` is required to reveal the bearer key deliberately. Switching back
to `--mode local` restores loopback publication.

LAN mode does not provide TLS and cannot override router or host-firewall
policy. Documentation therefore requires a trusted LAN, forbids router port
forwarding, and recommends a Private/local-subnet firewall scope. The project
does not invoke platform-specific administrative firewall commands.

## Consequences

- Default installations retain the existing local-only boundary.
- A remote OpenAI-compatible client can connect without adding a proxy or
  placing Hermes in Docker.
- Binding one private interface is narrower than `0.0.0.0`, but it is not an
  internet security boundary.
- The bearer key must be transferred to the remote client through a trusted
  channel and treated as a password.
- DHCP or interface changes can invalidate the selected address; rerunning the
  selector safely chooses and tests the replacement.
- TLS, untrusted-network access, multi-user authorization, rate limiting, and
  router configuration remain outside this project's supported scope.
