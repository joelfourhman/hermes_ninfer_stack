# Configuration

## Configuration owners

Two independent systems are configured:

- `.env.example` documents the NInfer deployment inputs.
- `.env` is generated locally by `python ninfer.py setup`, contains the
  NInfer bearer key, and is ignored by Git.
- Stock Hermes owns its normal per-user `config.yaml`, `.env`, sessions,
  skills, memory, and other application data.

This repository does not maintain a second Hermes configuration tree. The
`install-hermes` helper changes the NInfer provider, selected model, the two
documented long-session controls, and command approval mode through Hermes's
supported configuration command.

## NInfer settings

| Variable | Default | Meaning |
| --- | --- | --- |
| `NINFER_API_KEY` | generated | Bearer secret required by NInfer and stored in the native Hermes secret file |
| `HF_TOKEN` | empty | Optional Hugging Face token used only by the explicit model downloader |
| `MODEL_DOWNLOAD_UID` / `MODEL_DOWNLOAD_GID` | `1000` | Downloader identity; setup uses the creating user's IDs on POSIX hosts |
| `NINFER_ACCESS_MODE` | `local` | Network policy selected by `python ninfer.py network`: `local` or `lan` |
| `NINFER_BIND_ADDRESS` | `127.0.0.1` | Exact host IPv4 address mapped to NInfer's container port 8080 |
| `NINFER_HOST_PORT` | `8080` | Host port mapped to NInfer's container port 8080 |
| `NINFER_GPU_DEVICE` | detected (`0` normally) | NVIDIA device reserved for NInfer; fresh setup saves the detected 5090 index |
| `NINFER_MODEL_PROFILE` | `stock` | Fixed profile selected by `setup` or `select-model` |
| `NINFER_MODEL_FILE` | `qwen3_8_27b_nvfp4.ninfer` | Profile-controlled filename beneath `models/`, mounted read-only |
| `NINFER_MODEL_ID` | `qwen-local` | Public API alias selected in Hermes |
| `NINFER_RUNTIME_PROFILE` | `balanced` | Reviewed resource allocation selected by `select-runtime` |
| `NINFER_CONTEXT_LENGTH` | `131072` | Maximum sequence length for one request |
| `NINFER_KV_CAPACITY` | `196608` | Shared device KV-token allocation |
| `NINFER_MAX_CONCURRENCY` | `2` | Maximum simultaneous requests |
| `NINFER_PENDING_TIMEOUT_MS` | `120000` | Absolute preparation-plus-admission wait |
| `NINFER_KV_DTYPE` | `fp8` | Device KV storage format |
| `NINFER_DEVICE_STATE_SLOTS` | `2` | Extra device-resident prefix checkpoints |
| `NINFER_HOST_STATE_SLOTS` | `8` | Pinned host state checkpoints |
| `NINFER_HOST_KV_MIB` | `8192` | Pinned host KV checkpoint budget |
| `NINFER_PRESERVE_THINKING` | `true` | Profile contract for retaining closed-turn reasoning |
| `HERMES_COMPRESSION_ENABLED` | `true` | Compression setting applied to native Hermes |
| `HERMES_COMPRESSION_THRESHOLD_TOKENS` | `90000` | Balanced cap that limits long-prompt latency |
| `HERMES_MAX_TURNS` | `40` | Agent turn cap applied to native Hermes |

`.env.example` deliberately leaves `NINFER_API_KEY` empty. Setup generates a
random value so Compose fails closed when local initialization has not run.

The Python control command validates that:

- the key has the expected secret format;
- local mode uses loopback and LAN mode uses an RFC1918 IPv4 address;
- the port is from 1 through 65535;
- the GPU selection is valid for the supported shape;
- the model file is a filename rather than an arbitrary host path;
- the model ID contains only supported alias characters;
- all memory-sensitive values exactly match the named runtime profile.

When upgrading an older checkout, setup backs up `.env`, removes only the
reviewed allowlist of obsolete container-Hermes/model-builder variables, and
preserves unrelated settings and the existing bearer key.

## Endpoint mapping

NInfer's internal address is fixed at port 8080. Compose publishes the exact
host address selected by the network command. Fresh setup uses:

```text
http://127.0.0.1:${NINFER_HOST_PORT}/v1
```

LAN mode replaces `127.0.0.1` with one address in `10/8`, `172.16/12`, or
`192.168/16`. Native Hermes must use the selected host address.
`http://ninfer:8080/v1` was valid
only when Hermes shared a Compose network and is not valid in the current
architecture. Do not replace `127.0.0.1` with `0.0.0.0`; the latter is a listen
address, not an appropriate client destination, and broad host publication
would change the exposure boundary.

The exact-interface bind and bearer key serve different purposes. The bind
limits which host interface accepts connections; authentication rejects clients
without the secret. Use `python ninfer.py network --mode lan` or
`python ninfer.py network --mode local` rather than editing the coupled values.
The selector backs up `.env`, tests the new endpoint, rolls back on failure,
and updates local Hermes.

## Hermes provider lifecycle

Run the native integration step with:

```text
python ninfer.py install-hermes
```

If stock Hermes Desktop is missing, the helper opens the official download
page and asks the user to complete that installation. It does not download or
build a project-specific executable.

Once the stock `hermes` command is available, the helper stores
`NINFER_API_KEY` through Hermes's secret writer and applies a named provider
equivalent to:

```yaml
providers:
  ninfer:
    api: http://127.0.0.1:8080/v1
    key_env: NINFER_API_KEY
    transport: chat_completions
    default_model: qwen-local
    models:
      qwen-local:
        context_length: 131072
        supports_vision: false

model:
  provider: custom:ninfer
  default: qwen-local
  context_length: 131072
  supports_vision: false

compression:
  enabled: true
  threshold: 0.9
  threshold_tokens: 90000

agent:
  max_turns: 40

terminal:
  backend: local

approvals:
  mode: manual
```

The shown port and model values are examples of the defaults; the helper reads
the actual `.env` values. The key stays in Hermes's secret file because the
provider references `key_env`. It is not embedded in provider YAML or emitted
in normal output.

The operation is narrow and idempotent. It preserves unrelated providers,
tool selections, gateway integrations, sessions, skills, and user preferences.
It intentionally changes `approvals.mode` to `manual` because Hermes's stock
`smart` default can automatically approve commands it classifies as low risk;
this native same-user setup requires the operator to decide on flagged
commands. It also sets `terminal.backend: local`, but removes this project's
older `terminal.cwd` and `HERMES_WRITE_SAFE_ROOT` overrides. Desktop/gateway
sessions therefore use Hermes's stock home-directory start, CLI sessions use
their launch directory, and the built-in protected-path denylist remains
active. Stock Hermes remains free to migrate its own schema during updates.

## Coupled settings

The following values must agree across NInfer and Hermes:

1. `NINFER_MODEL_ID` is returned by NInfer's model API and selected by Hermes.
2. `NINFER_CONTEXT_LENGTH` is NInfer's request ceiling and Hermes's model
   metadata.
3. `NINFER_API_KEY` is the server bearer key and the secret referenced by the
   `ninfer` provider.
4. `NINFER_HOST_PORT` determines the base URL saved in the provider.
5. Vision remains disabled because the tested NInfer profile is text-only.

The KV, concurrency, timeout, cache-format, and checkpoint-tier values are one
runtime profile. They are not independent Hermes context settings. Use the
selector instead of hand-editing individual fields:

```text
python ninfer.py select-runtime
```

Explicit selectors use different option names because they control independent
settings:

```text
python ninfer.py select-model --model stock
python ninfer.py select-runtime --profile balanced
```

`select-model --profile stock` is not valid.

The selector recreates NInfer, performs an authenticated generation test,
restores the previous `.env` and service on failure, and updates Hermes's
context/compression metadata when Hermes is installed.

After changing a coupled value, recreate NInfer as needed and reapply Hermes:

```text
python ninfer.py down
python ninfer.py up
python ninfer.py install-hermes
python ninfer.py verify
```

## Runtime profiles

| Profile | Context | Device KV | Lanes | Device/host state slots | Host KV | Compression |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `balanced` | 131,072 | 196,608 | 2 | 2 / 8 | 8,192 MiB | 90,000 |
| `single-session` | 131,072 | 131,072 | 1 | 1 / 4 | 4,096 MiB | 100,000 |
| `max-context` | 240,000 | 240,000 | 2 | 2 / 8 | 8,192 MiB | 200,000 |

All three use FP8 KV, a 1,024-token prefill chunk, CUDA Graphs, prefix reuse,
MTP with three draft tokens and the optimized proposal head, and retained
closed-turn reasoning. Host caches retain reusable prefixes; they do not swap
active requests or model weights. The shared device KV budget still determines
whether two particular requests can run together.

`balanced` is the default because one long AFK request can coexist with a
smaller interactive request while Hermes compresses before prompt ingestion
becomes extreme. `max-context` raises the ceiling, not the speed: a 200K prompt
will still have substantially more first-token latency than a compressed 90K
prompt.

## Model artifact setting

`NINFER_MODEL_PROFILE` must be `stock` or `uncensored`, and
`NINFER_MODEL_FILE` must match that profile. Use `python ninfer.py select-model`
instead of editing these values by hand so startup is tested and rollback is
available.
Compose mounts `./models` read-only at `/models` for the long-running server.
The short-lived, CPU-only downloader alone receives a read/write model mount.
Using an arbitrary absolute path would make the setup machine-specific and
bypass the reviewed artifact pins and checksum.

Model bytes remain outside image layers. Building or removing the NInfer image
does not remove them.

## Secret handling

- Never commit `.env` or the stock Hermes secret file.
- Do not paste the NInfer key into screenshots, bug reports, or benchmark
  metadata.
- Do not put the key inline in `config.yaml`; keep `key_env: NINFER_API_KEY`.
- Anyone with access to the user's Hermes state or Docker container metadata
  may be able to recover the local key.
- Rotate the key after suspected disclosure, recreate NInfer, and rerun
  `python ninfer.py install-hermes`.

## Inspecting configuration

Safe project-side checks include:

```text
python ninfer.py status
docker compose --env-file .env config --quiet
python ninfer.py verify
```

Use stock Hermes's own commands to inspect non-secret provider values. Avoid
commands that print complete environments or request headers.
