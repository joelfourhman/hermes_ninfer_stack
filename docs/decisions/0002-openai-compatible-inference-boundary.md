# ADR 0002: Use an OpenAI-compatible inference boundary

- Status: Accepted, amended for native Hermes and by ADR 0011
- Date: 2026-08-23

The protocol decision remains active. The original internal Compose network is
historical; native Hermes now reaches authenticated NInfer at its selected
host address. Loopback remains the default, while ADR 0011 defines opt-in LAN
publication.

## Context

Hermes supports custom model providers through a chat-completions transport. NInfer exposes a local
HTTP API for its registered artifacts, including model discovery, chat completions, reasoning
content, and structured tool-call output. The integration needs a stable contract without making
Hermes depend on NInfer's internal C++ API or command-line output.

The native model identity embedded in a `.ninfer` artifact is an execution-selection fact. Hermes
instead needs a stable provider-facing name that can remain simple and local to this deployment.

## Decision

Connect native Hermes to NInfer through NInfer's authenticated
OpenAI-compatible chat-completions API at
`http://${NINFER_BIND_ADDRESS}:${NINFER_HOST_PORT}/v1`. Use `NINFER_MODEL_ID` as a shared
HTTP alias, `qwen-local` by default, while leaving the artifact's embedded
model identity unchanged.

Use only the protocol surface exercised by the repository's verification workflow. NInfer may
render tool definitions and return parsed tool calls, but Hermes owns validation and execution of
those calls. “OpenAI-compatible” does not imply support for every OpenAI endpoint or behavior.

## Alternatives considered

- **Call a NInfer CLI subprocess for every request.** Rejected because it would repeatedly load the
  model or require an ad hoc stream protocol, and it would make health and concurrency behavior
  harder to observe.
- **Integrate against NInfer's C++ Engine API.** Rejected because Hermes and NInfer are independently
  released products in different implementation ecosystems, and NInfer does not provide a packaged
  SDK contract for this use.
- **Create a repository-specific RPC protocol.** Rejected because the existing chat-completions
  boundary already represents the required messages, sampling options, and tool calls.
- **Expose the artifact's native identity directly to Hermes.** Rejected because provider aliases
  and artifact execution identities serve different purposes. Conflating them would make model
  replacement and client configuration less explicit.

## Consequences

- The integration is testable with ordinary authenticated HTTP requests at each side of the Hermes
  boundary.
- Hermes and NInfer can evolve independently as long as the verified protocol subset remains
  compatible.
- A future router or remote inference host could occupy the same provider boundary without moving
  agent logic into the inference process.
- The API key, model alias, context metadata, and supported request fields must
  agree across the native Hermes and NInfer processes.
- Protocol compatibility must be verified at runtime; a successful TCP connection or model load
  does not prove that generated tool calls are usable by Hermes.
