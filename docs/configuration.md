# Configuration

The repository separates reviewed defaults from live state:

- `.env.example` documents the supported Compose inputs and contains no secrets.
- `.env` is generated locally by `python stack.py setup` and ignored by Git.
- `hermes/config.example.yaml` is the reviewed Hermes baseline.
- `hermes-data/config.yaml` is the live, ignored copy that Hermes may migrate or personalize.
- `hermes-data/.env` contains Hermes-managed secrets and SSH backend values and is also ignored.

Do not commit either live file under `hermes-data/`.

## Environment variables

The setup helper populates `.env`. The values below are the supported public tuning surface.

| Variable | Default | Purpose |
|---|---|---|
| `HERMES_IMAGE` | `nousresearch/hermes-agent:v2026.8.19@sha256:f3cba6ab...` | Digest-pinned linux/amd64 Hermes image, version 0.20.5. |
| `HERMES_UID` | `1000` | Linux UID used for bind-mounted workspace ownership. |
| `HERMES_GID` | `1000` | Linux GID used for bind-mounted workspace ownership. |
| `NINFER_API_KEY` | generated | Bearer secret shared only by Hermes and NInfer. |
| `HERMES_API_SERVER_KEY` | generated | Secret for Hermes's loopback API used by verification. |
| `HERMES_DASHBOARD_ENABLED` | `true` | Enables the built-in authenticated Hermes dashboard. |
| `HERMES_DASHBOARD_HOST_PORT` | `9119` | Host-loopback dashboard port. |
| `HERMES_DASHBOARD_USERNAME` | `hermes` | Local dashboard login name. |
| `HERMES_DASHBOARD_PASSWORD` | generated | Independent local dashboard password. |
| `HERMES_DASHBOARD_SECRET` | generated | Dashboard session-signing secret. |
| `HF_TOKEN` | empty | Optional token passed only to the model-downloader utility. |
| `NINFER_HOST_PORT` | `8080` | Host-loopback port mapped to NInfer's fixed internal port 8080. |
| `NINFER_GPU_DEVICE` | `0` | Single NVIDIA device ID assigned to NInfer. |
| `NINFER_MODEL_FILE` | `qwen3_8_27b_nvfp4.ninfer` | Filename expected under `./models`. |
| `NINFER_MODEL_ID` | `qwen-local` | Deployment alias advertised by NInfer and requested by Hermes. |
| `NINFER_CONTEXT_LENGTH` | `131072` | NInfer sequence ceiling and matching Hermes context metadata. |
| `NINFER_MAX_CONCURRENCY` | `2` | Startup-fixed maximum number of active NInfer requests. |
| `HERMES_CPUS` | `4.0` | Compose CPU limit for Hermes. |
| `HERMES_MEMORY` | `8g` | Compose memory limit for Hermes. |
| `HERMES_PIDS` | `512` | Compose PID limit for Hermes. |
| `SANDBOX_CPUS` | `4.0` | Compose CPU limit for the SSH sandbox. |
| `SANDBOX_MEMORY` | `8g` | Compose memory limit for the SSH sandbox. |
| `SANDBOX_PIDS` | `512` | Compose PID limit for the SSH sandbox. |

The API keys and dashboard secrets are intentionally empty in `.env.example`. `python stack.py
setup` fills them with independent random values. Do not reuse any of them for a messaging
integration or external service.

## Coupled NInfer and Hermes settings

Three values must remain consistent across the inference and orchestration boundary:

1. `NINFER_MODEL_ID` is the HTTP alias returned by `GET /v1/models`; Hermes must request that exact
   alias.
2. `NINFER_CONTEXT_LENGTH` is both NInfer's sequence limit and Hermes's model metadata.
3. `NINFER_API_KEY` must be present in the NInfer command and Hermes environment.

After changing the model alias or context length, stop Hermes, reapply its managed fields, and
recreate NInfer:

```bash
docker compose stop hermes
python stack.py configure-hermes
docker compose up -d --force-recreate --wait --wait-timeout 900 ninfer
docker compose up -d hermes
python stack.py verify
```

The artifact's native identity is `qwen3.8-27b`; `qwen-local` is only a deployment alias. Changing
the alias does not convert the artifact or select another NInfer execution target.

## Ports and networking

`NINFER_HOST_PORT` changes only the host-side loopback mapping:

```text
127.0.0.1:${NINFER_HOST_PORT} -> ninfer:8080
```

Hermes must continue to use `http://ninfer:8080/v1` on the internal Compose network. Never replace
that address with `localhost`: inside the Hermes container, `localhost` is Hermes itself.

`HERMES_DASHBOARD_HOST_PORT` maps host loopback to the dashboard's fixed internal port:

```text
127.0.0.1:${HERMES_DASHBOARD_HOST_PORT} -> hermes:9119
```

The container listens on all of its own interfaces so Docker can publish the port, which activates
Hermes's fail-closed authentication gate. Do not change the host bind to `0.0.0.0` without a
separate remote-access threat model and TLS termination.

Hermes's verification API listens on container loopback and is not published to the host. The
sandbox and inference networks are internal; only Hermes also joins the egress-capable control
network.

## GPU selection

`NINFER_GPU_DEVICE` selects one Docker-visible GPU by device ID. NInfer's current product model is
one resident model on one RTX 5090; comma-separated devices and multi-GPU execution are not
supported by this stack.

Changing the device requires NInfer recreation:

```bash
docker compose up -d --force-recreate --wait --wait-timeout 900 ninfer
```

Only NInfer receives GPU access. Hermes and the sandbox must not be granted a GPU reservation.

## Context length and concurrency

The default profile combines:

- 131,072 maximum tokens per sequence;
- automatic shared KV-capacity sizing;
- INT8 group-64 KV cache;
- two active requests;
- a 1,024-token prefill chunk;
- MTP with three draft tokens.

Context and concurrency compete for the VRAM left after model and runtime allocations. If startup
fails with an out-of-memory error, first reduce `NINFER_MAX_CONCURRENCY` to `1`. If context must be
reduced, update `NINFER_CONTEXT_LENGTH`, rerun `python stack.py configure-hermes`, recreate NInfer, and
verify the entire route.

Do not raise either value solely because NInfer accepts the flag. The resolved automatic KV
capacity printed at startup is the authority for the selected GPU and software versions.

## Model file

`NINFER_MODEL_FILE` is a filename, not an arbitrary host path. Compose mounts `./models` read-only
at `/models`, and NInfer opens `/models/${NINFER_MODEL_FILE}`.

Keep model files under `models/`; absolute paths and Windows-user-specific paths are intentionally
unsupported. See [Models](models.md) before selecting a different artifact.

## Hermes configuration lifecycle

`python stack.py setup` copies the reviewed template only when live configuration is absent, then
runs the first-run wizard as part of the complete workflow. The wizard may add identity, messaging,
pairing, or provider information to the ignored live tree. Setup automatically invokes the same
managed configuration step exposed separately as `python stack.py configure-hermes`; it owns only
the fields required by this stack:

- custom NInfer provider endpoint and API-key environment name;
- model alias, context length, and text-only capability metadata;
- SSH terminal backend host, user, port, and key path;
- terminal working directory and timeout;
- hard stops for repeated or no-progress tool loops.

Do not replace live configuration with the example after completing the wizard. To inspect a value,
use the supported Hermes CLI rather than editing generated schema fields blindly.

## Validate changes safely

Check interpolation without printing the rendered configuration, which can contain secrets:

```bash
docker compose --env-file .env config --quiet
```

Then recreate only affected services and run:

```bash
python stack.py verify
```

For common configuration failures, see [Troubleshooting](troubleshooting.md).
