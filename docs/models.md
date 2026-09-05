# Model profiles

The project offers two fixed, reviewed Qwen3.8-27B profiles. Fresh setup
recommends the stock profile; choosing the uncensored profile is deliberate and
never happens merely because a URL or filename was placed in `.env`.

Model weights, conversion output, and provenance manifests are runtime data.
Git ignores them, and the NInfer image never contains them.

## Choose during setup

Run the normal one-command setup:

```text
python ninfer.py setup
```

It displays this choice before its disk check or model transfer:

```text
1. Stock Qwen3.8-27B (recommended)
2. Qwen3.8-27B Uncensored
```

Press Enter for stock or enter `2` for uncensored. Setup then describes the
selected transfer and asks for confirmation before downloading it. For
non-interactive use, the equivalent commands are:

```text
python ninfer.py setup --model stock
python ninfer.py setup --model uncensored
```

## Profile comparison

| Field | Stock (default) | Uncensored (optional) |
| --- | --- | --- |
| Source | `neroued/Qwen3.8-27B-nvfp4-NInfer` | `JonathanColetti/Qwen3.8-27B-Uncensored` |
| Pinned source revision | `204e3d92c30d9d05f3300d2f52e443ad1edf6ddf` | `5bb7aa90f0efef548e87005b1fb7658e522b6b7f` |
| Input | Ready NInfer artifact | BF16 Transformers/Safetensors weights |
| Output filename | `qwen3_8_27b_nvfp4.ninfer` | `qwen3_8_27b_uncensored.ninfer` |
| Final bytes | 21,492,695,040 (20.02 GiB) | 18,210,531,328 (16.96 GiB) |
| Preparation | Download and checksum | Download, offline GPU conversion, local checksum |
| Free space check | 24 GiB | 90 GiB during conversion |
| Quantization | NVFP4 | NInfer `qwen3_8_27b-v1` groupwise-int |
| Behavior | Stock model behavior; recommended starting point | Substantially reduced refusals; less safety margin |

The uncensored converter is pinned at
`b2b96bae4dd88f95b9ea8126d68fae3b88caa374`.

The stock artifact's pinned SHA-256 is
`bb3360522a06e136e0367f5703414d26272b7285c8a6ab6194135c17dbd81b32`.
The uncensored recipe's reference SHA-256 is
`714565ed29db4415322e9bc13a3464dc1fd8fcc911234740a79af67934e49969`;
low-bit rounding can differ between converter environments, so the project
records and subsequently verifies the actual local result.

Both profiles use the public API alias `qwen-local`, 131,072-token context and
KV capacity, concurrency one, INT8 KV, a 1,024-token prefill chunk, and MTP with
three draft tokens. Vision is disabled. Keeping the alias stable means Hermes
does not need reconfiguration just because the underlying profile changes.

## Switch later

Use the interactive selector:

```text
python ninfer.py select-model
```

Or select explicitly:

```text
python ninfer.py select-model --model stock
python ninfer.py select-model --model uncensored
```

The command checks storage and prerequisites for that profile, asks before a
missing large download, verifies the artifact, backs up `.env`, starts NInfer,
and requires an authenticated generated answer. If startup fails and the old
artifact is still available, it restores the previous configuration and model.

Switching never deletes either artifact or the resumable uncensored build
cache. Disk cleanup is a separate manual decision. If both artifacts are
present they use about 37 GiB together, excluding `model-build/` and Docker
images.

`prepare-model` can download or build a profile without selecting it:

```text
python ninfer.py prepare-model --model stock
python ninfer.py prepare-model --model uncensored
```

## What “uncensored” means

The uncensored publisher used Heretic to reduce refusal behavior; it was not
fine-tuned on new data. Its model card reports 12 refusals on 100 held-out
harmful prompts, compared with 98 for the base model, and first-token KL
divergence of 0.1191. Those numbers do not measure coding quality, autonomous
agent reliability, or filesystem safety. Review the
[source model card](https://huggingface.co/JonathanColetti/Qwen3.8-27B-Uncensored)
before selecting it.

The model can follow requests the stock model would reject. It is not a safety
feature. Keep Hermes manual approvals enabled, review terminal commands, and
maintain backups that Hermes cannot silently overwrite.

## Provenance and replacement policy

The stock downloader checks its exact pinned byte size and published checksum.
The uncensored path uses a networked, uv-locked fetcher and a separate
network-disabled GPU converter, then validates the conversion report and local
manifest. Neither path overwrites a file that already exists but fails
verification; move a bad artifact aside explicitly before retrying.

Do not edit `NINFER_MODEL_PROFILE` and `NINFER_MODEL_FILE` independently. The
helper validates their mapping. Use `select-model` so the new profile receives
the startup test and rollback protection.

## License

Both model sources identify their licensing as Apache-2.0 inherited from Qwen.
Their license terms, acceptable-use requirements, and applicable law still
govern use. This repository distributes orchestration and build metadata, not
model weights or converted artifacts.
