# Models

This project is tested with one exact NInfer artifact. Model weights are
external runtime data: they are never committed and are not baked into the
NInfer image.

## Tested artifact

| Field | Value |
| --- | --- |
| Hugging Face repository | `neroued/Qwen3.8-27B-nvfp4-NInfer` |
| Repository revision | `204e3d92c30d9d05f3300d2f52e443ad1edf6ddf` |
| Filename | `qwen3_8_27b_nvfp4.ninfer` |
| Size | 21,492,695,040 bytes (20.02 GiB) |
| SHA-256 | `bb3360522a06e136e0367f5703414d26272b7285c8a6ab6194135c17dbd81b32` |
| Artifact container | NInfer version 2 |
| Native model ID | `qwen3.8-27b` |
| Weights ID | `nvfp4` |
| NInfer target key | `qwen3_8_27b` |
| Deployment alias | `qwen-local` |

The artifact is a registered mixed NVFP4/FP8 Qwen3.8-27B profile. It is not a
GGUF file, Safetensors distribution, or generic Transformers checkpoint. It
contains the weights and frontend resources NInfer needs at runtime.

The deployment is text-only. Although the artifact contains vision resources,
NInfer does not start with vision enabled and the Hermes provider declares
`supports_vision: false`. This avoids additional fixed allocations on a 32 GiB
card.

## Download through setup

The normal first run shows the exact artifact and approximately 20.02 GiB size,
then asks before transferring data:

```text
python ninfer.py setup
```

Answering no exits cleanly before the model download and before NInfer or
Hermes setup continues. Answering yes uses the isolated downloader workflow,
supports resumption, and verifies the final SHA-256 before the artifact is
accepted.

The acquisition step is independently rerunnable:

```text
python ninfer.py download-model
```

An existing complete file is verified rather than downloaded again. Explicitly
approved automation can use:

```text
python ninfer.py download-model --yes
```

Do not use that bypass in ordinary CI. Public runners should not acquire the
large artifact.

## Pinned acquisition identity

The downloader fetches `qwen3_8_27b_nvfp4.ninfer` from
`neroued/Qwen3.8-27B-nvfp4-NInfer` at revision
`204e3d92c30d9d05f3300d2f52e443ad1edf6ddf`, then requires the SHA-256 above.
It runs `huggingface-hub` through a pinned `uv` tool inside the one-shot
Compose utility. No host Hugging Face CLI, virtual environment, `pip`, Bash,
or PowerShell setup is required.

The default project values are:

```dotenv
NINFER_MODEL_FILE=qwen3_8_27b_nvfp4.ninfer
NINFER_MODEL_ID=qwen-local
NINFER_CONTEXT_LENGTH=65536
NINFER_KV_CAPACITY=65536
NINFER_MAX_CONCURRENCY=1
```

## Storage and Git safety

Compose mounts `models/` read-only at `/models`. The artifact remains outside
image layers, so rebuilding or removing the NInfer image does not duplicate or
delete it.

Repository ignore rules cover common model formats. Before a public push,
still confirm no artifact is staged:

```text
git status --short
git ls-files *.ninfer *.safetensors *.gguf *.bin
```

Deleting the NInfer container or running `python ninfer.py down` is not model
cleanup. Delete the known host artifact only when model removal is intentional.

## Model IDs must match

NInfer advertises `NINFER_MODEL_ID` through `/v1/models`. Stock Hermes must
request the same alias. A mismatch can leave NInfer healthy while every Hermes
request receives a model-not-found response.

After changing the alias or context:

```text
python ninfer.py down
python ninfer.py up
python ninfer.py install-hermes
python ninfer.py verify
```

The Hermes helper updates the named native provider at the host endpoint
`http://127.0.0.1:${NINFER_HOST_PORT}/v1` and preserves unrelated Hermes state.

## Replacing the artifact

NInfer accepts registered `.ninfer` identities. Replacing the default is not a
generic filename or format conversion.

Before selecting another artifact:

1. Confirm the pinned NInfer revision registers it.
2. Read its model card and minimum-runtime requirement.
3. Record the exact repository revision, byte size, and SHA-256.
4. Confirm its VRAM profile supports the desired context and concurrency on
   one RTX 5090.
5. Update the downloader's reviewed metadata and project defaults together.
6. Review startup flags; vision or another speculative backend is not enabled
   by changing a filename.
7. Recreate NInfer, reapply native Hermes configuration, and run full
   verification.

Treat a different artifact as a new compatibility profile. Do not call it
tested until local GPU verification and a controlled benchmark have run.
