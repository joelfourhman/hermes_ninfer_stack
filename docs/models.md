# Model artifacts and fallback

The [generated manifest reference](generated-config.md) records every immutable
repository revision, remote/local filename, byte count and SHA-256. All three
profiles now use **v3 containers**, required by the current runtime. The pinned
published v2 sources are retained, authenticated and upgraded locally using the
pinned upstream copy converter. Weight bytes and quantization are unchanged;
the new framing includes the maintained Qwen3.8 chat template. DFlash2 still
requires the explicitly selected companion artifact.

The downloader resumes into a profile-specific staging directory, verifies size
and SHA-256, then upgrades it to a separate `.v3.ninfer` filename and checks the
derived SHA-256 too. Existing local sources avoid another download. The wrapper
normalizes converter/template line endings and uses a deterministic framing UUID
so Windows and Linux produce identical artifacts. Published and derived hashes
are separately recorded; no derived hash is presented as a publisher checksum.
Migration requires room for both files. `prepare-model` prepares without activating;
`select-model` prepares, activates and live-tests with rollback.

```text
python ninfer.py prepare-model --model stock-dflash2
python ninfer.py select-model --model stock-dflash2
python ninfer.py spec mtp3
python ninfer.py spec dflash2-7
```

Compare MTP3 and DFlash2 on this same companion file to isolate decoder effects.
The older stock file and companion file use different recipes; a cross-artifact
comparison is a deployment comparison, not a clean decoding comparison.

The supported daily fallback is:

```text
python ninfer.py spec mtp3
python ninfer.py select-model --model stock
python ninfer.py profile balanced
```

The source audit records the original runtime revision. During this implementation
the original image was also retained locally as `hermes-ninfer:baseline-mtp3`.
That tag is local evidence, not a published image. Before future upgrades, tag
your own known-good image and retain the previous checkout/manifest together.
The v3 runtime rejects v2 input. Returning only the source pin without its matching manifest/CLI contract is not
a supported rollback. Repository Git commits preserve the entire old contract.

Uncensored is optional and retains its publisher-defined behavior. Neither
standard refusals nor reduced refusals restrict filesystem/process authority.
