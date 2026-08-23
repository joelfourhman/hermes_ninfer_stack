# Models

This stack is tested with one exact NInfer artifact. Model weights are external runtime data and are
never committed or baked into the NInfer image.

## Tested artifact

| Field | Value |
|---|---|
| Hugging Face repository | `neroued/Qwen3.8-27B-nvfp4-NInfer` |
| Repository revision | `204e3d92c30d9d05f3300d2f52e443ad1edf6ddf` |
| Filename | `qwen3_8_27b_nvfp4.ninfer` |
| Size | 21,492,695,040 bytes (20.02 GiB) |
| SHA-256 | `bb3360522a06e136e0367f5703414d26272b7285c8a6ab6194135c17dbd81b32` |
| Artifact container | NInfer version 2 |
| Native model ID | `qwen3.8-27b` |
| Weights ID | `nvfp4` |
| NInfer target key | `qwen3_8_27b` |
| Stack deployment alias | `qwen-local` |

The artifact is a registered mixed NVFP4/FP8 Qwen3.8-27B profile. It is not a GGUF file,
Safetensors distribution, or Transformers checkpoint. It contains the weights and frontend
resources NInfer needs at runtime.

The stack runs this artifact as text-only. Although the artifact also contains vision resources,
NInfer is not started with vision enabled and Hermes advertises `supports_vision: false`. This avoids
reserving the additional fixed vision allocations on a 32 GiB card.

## Why this model

The selected artifact has published upstream measurements on a 32 GiB RTX 5090 with the same
important NInfer profile used here: CUDA 13.1, INT8 KV cache, 1,024-token prefill chunks,
131,072-token MTP3 context, and automatic KV sizing. NVFP4 reduces weight storage while retaining a
complete registered NInfer execution path.

Those measurements establish upstream model/runtime evidence, not performance of this complete
Hermes stack. See [Performance](performance.md) for the distinction.

## Download through setup

The normal first-run command displays the artifact identity and size, then asks
for explicit consent before downloading:

```text
python stack.py setup
```

Answering no pauses setup without transferring model data. Answering yes uses pinned `uv` and
Hugging Face client versions inside a Compose utility container; it installs nothing on the host.
The helper reports the destination and available space and fails if the final checksum differs from
the value above.

The acquisition step is also available independently for recovery or checksum verification:

```text
python stack.py download-model
```

An existing file is verified rather than downloaded again.

For explicitly approved non-interactive automation, the helper accepts:

```bash
python stack.py download-model --yes
```

Do not use that option in CI. Public runners must not download the model.

## Manual pinned download

The equivalent pinned command is:

```bash
hf download neroued/Qwen3.8-27B-nvfp4-NInfer \
  qwen3_8_27b_nvfp4.ninfer \
  --revision 204e3d92c30d9d05f3300d2f52e443ad1edf6ddf \
  --local-dir models
```

Verify it independently:

```bash
printf '%s  %s\n' \
  'bb3360522a06e136e0367f5703414d26272b7285c8a6ab6194135c17dbd81b32' \
  'models/qwen3_8_27b_nvfp4.ninfer' | sha256sum --check
```

The default `.env` values must then be:

```dotenv
NINFER_MODEL_FILE=qwen3_8_27b_nvfp4.ninfer
NINFER_MODEL_ID=qwen-local
NINFER_CONTEXT_LENGTH=65536
NINFER_KV_CAPACITY=65536
NINFER_MAX_CONCURRENCY=1
```

## Storage and Git safety

Compose mounts the host `models/` directory read-only at `/models`. The model remains outside image
layers, so rebuilding or updating containers does not duplicate or delete it.

Global ignore rules protect common model formats, including `.ninfer`, `.safetensors`, `.gguf`, and
`.bin`. Before any public push, still confirm that no artifact is staged:

```bash
git status --short
git ls-files '*.ninfer' '*.safetensors' '*.gguf' '*.bin'
```

Do not use `docker compose down -v` as model cleanup. The model is a bind-mounted host file, while
`-v` removes unrelated sandbox identity and home volumes.

## Model IDs must match

NInfer publishes `NINFER_MODEL_ID` through its OpenAI-compatible API. Hermes is configured to
request the same alias. A mismatch can produce a healthy NInfer container and a working
`GET /v1/models` response while Hermes requests an unknown model.

After changing the alias:

```bash
docker compose stop hermes
python stack.py configure-hermes
docker compose up -d --force-recreate --wait --wait-timeout 900 ninfer
docker compose up -d hermes
python stack.py verify
```

## Replacing the model

NInfer accepts only registered `.ninfer` artifact identities. Replacing the default is not a generic
file-format conversion and cannot be done with an arbitrary GGUF or Safetensors checkpoint.

Before selecting another artifact:

1. Confirm it is registered by the pinned NInfer revision.
2. Read its versioned model card and minimum-runtime requirement.
3. Record its exact repository revision, size, and SHA-256.
4. Confirm its VRAM profile supports the desired context and concurrency on one RTX 5090.
5. Update `NINFER_MODEL_FILE`, `NINFER_MODEL_ID`, and, if required, `NINFER_CONTEXT_LENGTH`.
6. Review NInfer startup flags; vision or another speculative backend is not enabled by a filename
   change.
7. Reconfigure Hermes, recreate NInfer, and run full verification.

Treat a new artifact as a new compatibility profile. Do not describe it as tested until the local
GPU verification and benchmark have actually run.
