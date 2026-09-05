# Model profiles

The project offers two fixed, reviewed Qwen3.8-27B profiles. Fresh setup
recommends stock; selecting uncensored is always deliberate. Both are
ready-to-run NInfer artifacts downloaded from immutable Hugging Face revisions.
The setup does not download source checkpoints or convert weights locally.

Model files and Hugging Face download metadata are runtime data under
`models/`. Git ignores them, and the NInfer image never contains them.

## Choose during setup

```text
python ninfer.py setup
```

Press Enter for stock or enter `2` for uncensored. Setup describes the selected
transfer and asks for confirmation before downloading anything large. The
non-interactive equivalents are:

```text
python ninfer.py setup --model stock
python ninfer.py setup --model uncensored
```

## Profile comparison

| Field | Stock (default) | Uncensored (optional) |
| --- | --- | --- |
| Artifact repository | `neroued/Qwen3.8-27B-nvfp4-NInfer` | `DogOnKeyboard/Qwen3.8-27B-Uncensored-NInfer` |
| Pinned artifact revision | `204e3d92c30d9d05f3300d2f52e443ad1edf6ddf` | `1e15b5919b796bcd96621f13572ad92b5555b641` |
| Filename | `qwen3_8_27b_nvfp4.ninfer` | `qwen3_8_27b_uncensored.ninfer` |
| Bytes | 21,492,695,040 (20.02 GiB) | 18,210,531,328 (16.96 GiB) |
| Free-space check | 24 GiB | 21 GiB |
| SHA-256 | `bb3360522a06e136e0367f5703414d26272b7285c8a6ab6194135c17dbd81b32` | `714565ed29db4415322e9bc13a3464dc1fd8fcc911234740a79af67934e49969` |
| Quantization | NVFP4 | NInfer `qwen3_8_27b-v1` groupwise-int |
| Behavior | Stock behavior; recommended starting point | Substantially reduced refusals; less safety margin |

The uncensored download is bit-for-bit identical to the artifact previously
built by this project. That build used
`JonathanColetti/Qwen3.8-27B-Uncensored` revision
`5bb7aa90f0efef548e87005b1fb7658e522b6b7f`, NInfer converter revision
`b2b96bae4dd88f95b9ea8126d68fae3b88caa374`, and recipe
`qwen3_8_27b-v1`. These details are retained for reproducibility; normal users
do not need the 55 GiB source checkpoint or a local GPU conversion.

Both profiles use the stable API alias `qwen-local`; changing weights therefore
does not require Hermes reconfiguration. Runtime capacity is selected
independently with `python ninfer.py select-runtime`. Fresh setup uses the
balanced 131K-context, two-lane profile. Vision is disabled for every reviewed
profile.

## Switch later

```text
python ninfer.py select-model
```

Or select explicitly:

```text
python ninfer.py select-model --model stock
python ninfer.py select-model --model uncensored
```

The model command accepts `--model`, not `--profile`. Runtime profiles are a
separate setting and use `python ninfer.py select-runtime --profile ...`.

For software development and long autonomous work, start with the stock model
and balanced runtime:

```text
python ninfer.py select-model --model stock
python ninfer.py select-runtime --profile balanced
python ninfer.py verify
```

The command checks prerequisites and storage, asks before a missing download,
verifies the artifact, backs up `.env`, starts NInfer, and requires an
authenticated generated answer. If startup fails and the old artifact remains
available, it restores the previous configuration and model.

Switching never deletes either artifact. If both are present they use about 37
GiB together, excluding Docker images. `prepare-model` can download a profile
without selecting it:

```text
python ninfer.py prepare-model --model stock
python ninfer.py prepare-model --model uncensored
```

## What “uncensored” means

The source publisher used Heretic to reduce refusal behavior; it was not
fine-tuned on new data. Those changes do not establish coding quality,
autonomous-agent reliability, factual accuracy, or filesystem safety. Review
the [source model card](https://huggingface.co/JonathanColetti/Qwen3.8-27B-Uncensored)
before selecting it.

The model can follow requests the stock model would reject. It is not a safety
feature. Keep Hermes manual approvals enabled, review terminal commands, and
maintain backups that Hermes cannot silently overwrite.

## Download and verification policy

The uv-locked downloader pins each Hugging Face repository revision, expected
filename, byte size, and SHA-256. Interrupted Hugging Face downloads can be
resumed. A complete file is accepted only when both size and checksum match.
An existing invalid file is never overwritten automatically; move it aside
explicitly before retrying.

Do not edit `NINFER_MODEL_PROFILE` and `NINFER_MODEL_FILE` independently. The
helper validates their mapping. Use `select-model` so the new profile receives
the startup test and rollback protection.

## License

Both upstream model repositories identify their licensing as Apache-2.0.
Upstream license terms, notices, acceptable-use requirements, and applicable
law still govern use. This repository downloads the selected artifact at the
user's request; it does not commit model weights to Git or bake them into a
container image.
