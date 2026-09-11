# Model artifacts and fallback

The [generated manifest reference](generated-config.md) records every immutable
repository revision, remote/local filename, byte count and SHA-256. `stock` and
`uncensored` retain their original artifacts. `stock-dflash2` is an explicit
additional Qwen3.8 NVFP4 v2 artifact containing the DFlash2 companion and supporting
both MTP and DFlash2. Its local filename is distinct even though its upstream
remote filename matches the older stock artifact.

The downloader resumes into a profile-specific staging directory, verifies size
and SHA-256, then places the result at the selected filename. Existing artifacts
are verified and preserved. `prepare-model` downloads without activating;
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
Returning only the source pin without its matching manifest/CLI contract is not
a supported rollback. Repository Git commits preserve the entire old contract.

Uncensored is optional and retains its publisher-defined behavior. Neither
standard refusals nor reduced refusals restrict filesystem/process authority.
