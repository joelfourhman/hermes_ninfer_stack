# Models

This project is tested with one locally built NInfer artifact. Model weights,
source checkpoints, conversion output, and local provenance manifests are
runtime data: Git ignores them and they are never baked into the NInfer image.

## Selected model

| Field | Value |
| --- | --- |
| Source repository | `JonathanColetti/Qwen3.8-27B-Uncensored` |
| Source revision | `5bb7aa90f0efef548e87005b1fb7658e522b6b7f` |
| Base architecture | Qwen3.8-27B / Qwen3.5-family multimodal |
| Source precision | BF16, approximately 55 GB |
| Output filename | `qwen3_8_27b_uncensored.ninfer` |
| Output size | 18,210,531,328 bytes (approximately 16.96 GiB) |
| Conversion recipe | NInfer `qwen3_8_27b-v1` groupwise-int |
| Converter commit | `b2b96bae4dd88f95b9ea8126d68fae3b88caa374` |
| Reference SHA-256 | `714565ed29db4415322e9bc13a3464dc1fd8fcc911234740a79af67934e49969` |
| NInfer target key | `qwen3_8_27b` |
| Deployment alias | `qwen-local` |

The source is a Transformers/Safetensors checkpoint, not a GGUF or `.ninfer`
file. NInfer cannot serve it directly. The project follows the public
[`ninfer-qwen-uncensored` recipe](https://github.com/j842/ninfer-qwen-uncensored/blob/main/models/qwen3.8-27b-uncensored.md)
to create the self-contained artifact locally. The converted file contains the
text weights, tokenizer/chat-template frontend, MTP proposal head, and vision
resources.

The first reviewed runtime profile is text-only. Compose does not pass
`--vision`, and Hermes records `supports_vision: false`. This keeps the model
swap separate from a vision and maximum-context experiment.

## What “uncensored” means here

The publisher used Heretic to reduce the model's refusal behavior. It was not
fine-tuned on new data. The published checkpoint is the most aggressive point
on the reported refusal/KL tradeoff: 12 refusals on 100 held-out harmful
prompts, compared with 98 for the base model, and a first-token KL divergence
of 0.1191.

Those numbers do not measure benign over-refusal, agent reliability, or
filesystem safety. The publisher's four 0-shot capability checks average about
0.5 points below the base model, within or near their reported standard error,
but no code, math, generative, multilingual, vision, or MTP evaluation was
performed. Read the
[source model card](https://huggingface.co/JonathanColetti/Qwen3.8-27B-Uncensored)
before relying on it for sensitive work.

The model may follow instructions the base model would refuse. Do not expose it
to untrusted users or a public endpoint without an independently designed
safety layer. Hermes command approvals, limited direct-write roots, OS account
boundaries, and backups remain separate controls.

## Reproducible local build

The normal command is:

```text
python ninfer.py setup
```

Setup states the transfer and disk requirements, then asks before beginning.
To prepare only the model:

```text
python ninfer.py prepare-model
```

`download-model` remains a compatibility alias, but the operation now downloads
source weights and builds an artifact rather than downloading a finished one.

The build has two isolated stages:

1. `model-fetcher` has network access and no GPU. It downloads the exact source
   and official frontend revisions, validates six frontend SHA-256 pins, and
   checksum-verifies the pinned NInfer converter archive.
2. `model-converter` has the selected GPU and no network. It uses a committed uv
   lock, runs the groupwise-int converter, validates the conversion report and
   exact output size, then atomically promotes the artifact.

No step invokes pip. The host runs Python and Docker Compose only; Bash inside a
long-running host environment, PowerShell scripts, WSL commands, a host Hugging
Face CLI, and a host virtual environment are not required.

The checkpoint download is resumable. A failed conversion leaves its incomplete
file under a known temporary name and never selects it for NInfer.

## Checksums and provenance

The conversion recipe publishes the reference SHA-256 shown above, but also
warns that low-bit rounding can produce different bytes on another GPU or
PyTorch/CUDA build. Consequently, setup:

- records whether the build matches the reference;
- always records the actual local SHA-256 in
  `models/qwen3_8_27b_uncensored.ninfer.local-manifest.json`;
- requires subsequent verification to match that local manifest;
- validates the source revisions, recipe identity, conversion report, and exact
  byte size independently.

Do not replace the local manifest after a checksum failure. Rebuild the artifact
from the pinned inputs or restore a known-good copy.

## Runtime defaults

```dotenv
NINFER_MODEL_FILE=qwen3_8_27b_uncensored.ninfer
NINFER_MODEL_ID=qwen-local
NINFER_CONTEXT_LENGTH=131072
NINFER_KV_CAPACITY=131072
NINFER_MAX_CONCURRENCY=1
HERMES_COMPRESSION_THRESHOLD_TOKENS=100000
```

The alias intentionally remains `qwen-local`, allowing existing Hermes sessions
to continue after the underlying model changes. Their history is preserved, but
future answers will of course be generated by different weights.

INT8 KV, a 1,024-token prefill chunk, and MTP with three draft tokens remain
enabled. The public recipe describes 262K context, concurrency four, and vision,
but does not publish performance results for this artifact. Those settings are
not the default until separately tested on the target 5090.

## Safe cutover and rollback

The old `qwen3_8_27b_nvfp4.ninfer` file is not deleted. Setup builds and verifies
the new model first, backs up `.env`, changes the selected filename, and requires
a healthy server plus an authenticated generation. If the new model fails that
test and the previous artifact is available, setup restores the previous `.env`
and restarts the former model.

Build caches remain under ignored `model-build/` for resumption. Remove them or
the former model only as a separate, explicit storage-cleanup decision.

## License

The source model identifies itself as Apache-2.0, inherited from Qwen. The base
model's license, acceptable-use terms, and applicable law still govern use of
the derivative. This repository distributes orchestration and build metadata,
not the model weights or converted artifact.
