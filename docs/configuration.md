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
| `NINFER_HOST_PORT` | `8080` | Host-loopback port mapped to NInfer's container port 8080 |
| `NINFER_GPU_DEVICE` | detected (`0` normally) | NVIDIA device reserved for NInfer; fresh setup saves the detected 5090 index |
| `NINFER_MODEL_PROFILE` | `stock` | Fixed profile selected by `setup` or `select-model` |
| `NINFER_MODEL_FILE` | `qwen3_8_27b_nvfp4.ninfer` | Profile-controlled filename beneath `models/`, mounted read-only |
| `NINFER_MODEL_ID` | `qwen-local` | Public API alias selected in Hermes |
| `NINFER_CONTEXT_LENGTH` | `131072` | Maximum sequence length for one request |
| `NINFER_KV_CAPACITY` | `131072` | Total resident KV-token allocation |
| `NINFER_MAX_CONCURRENCY` | `1` | Maximum simultaneous requests |
| `HERMES_COMPRESSION_ENABLED` | `true` | Compression setting applied to native Hermes |
| `HERMES_COMPRESSION_THRESHOLD_TOKENS` | `100000` | Absolute compression cap that preserves request headroom |
| `HERMES_MAX_TURNS` | `40` | Agent turn cap applied to native Hermes |

`.env.example` deliberately leaves `NINFER_API_KEY` empty. Setup generates a
random value so Compose fails closed when local initialization has not run.

The Python control command validates that:

- the key has the expected secret format;
- the port is from 1 through 65535;
- the GPU selection is valid for the supported shape;
- the model file is a filename rather than an arbitrary host path;
- the model ID contains only supported alias characters;
- context, KV capacity, and concurrency form a valid allocation.

## Endpoint mapping

NInfer's internal address is fixed at port 8080. Compose publishes only host
loopback:

```text
http://127.0.0.1:${NINFER_HOST_PORT}/v1
```

Native Hermes must use this host address. `http://ninfer:8080/v1` was valid
only when Hermes shared a Compose network and is not valid in the current
architecture. Do not replace `127.0.0.1` with `0.0.0.0`; the latter is a listen
address, not an appropriate client destination, and broad host publication
would change the exposure boundary.

The loopback bind and bearer key serve different purposes. Loopback limits
network reachability; authentication rejects unauthorized local requests.

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
  threshold_tokens: 100000

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

`NINFER_KV_CAPACITY` and `NINFER_MAX_CONCURRENCY` affect server memory but are
not independent Hermes context settings. With concurrency one, the default KV
capacity equals the full context ceiling.

After changing a coupled value, recreate NInfer as needed and reapply Hermes:

```text
python ninfer.py down
python ninfer.py up
python ninfer.py install-hermes
python ninfer.py verify
```

## Memory-sensitive NInfer settings

The reviewed profile includes:

- INT8 KV cache;
- a 1,024-token prefill chunk;
- MTP speculation with three draft tokens;
- the optimized draft head;
- one active request;
- explicit 131,072-token context and KV capacity;
- Hermes compression capped at 100,000 tokens.

These are a group, not isolated tuning switches. Increasing context,
concurrency, or KV capacity can exhaust VRAM even when the model loads. Changing
KV dtype or speculative settings changes both memory and performance. Record
the complete resolved startup profile for any benchmark comparison.

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
