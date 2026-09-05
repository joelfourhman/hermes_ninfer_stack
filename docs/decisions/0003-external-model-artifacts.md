# ADR 0003: Keep model artifacts outside Git and images

- Status: Superseded by [ADR 0006](0006-locally-built-uncensored-model.md)
- Date: 2026-08-23

## Context

The tested Qwen3.8-27B NVFP4 `.ninfer` artifact is approximately 20.02 GiB. It has independent
upstream provenance, licensing, versioning, and runtime-compatibility requirements. Including it in
the Git repository would make every clone impractical; including it in the NInfer image would make
source rebuilds transfer and duplicate the same large payload.

Automatic download during image build, setup, or CI would hide a large network and storage action
and would make offline or checksum-aware operation harder to reason about.

## Decision

Keep model artifacts in the ignored host `models/` directory and mount that directory read-only at
`/models` in NInfer. Make model acquisition an explicit user decision: the complete
`python ninfer.py setup` workflow prompts before downloading, while
`python ninfer.py prepare-model` is the intentional standalone recovery command.

For the default release profile, pin the Hugging Face repository revision, expected filename, byte
size, and SHA-256 checksum. Refuse a checksum mismatch. Do not download a model
during CI or Docker build, or during setup without the owner's explicit prompt
response.

Pin the NInfer implementation separately as a Git submodule at
`feaf4dd0983fdaeb2ba4c06eec6da350e644fb3a`. The source pin identifies the runtime; the artifact
checksum identifies the model bytes. Both are required for a reproducible profile.

## Alternatives considered

- **Commit the artifact directly to Git.** Rejected because its size would make normal repository
  operations unsuitable and exceed common hosting limits.
- **Use Git LFS.** Rejected because every interested contributor would still encounter a very large
  transfer, hosting quotas would become part of the build contract, and model acquisition would be
  less explicit.
- **Bake the artifact into the NInfer image.** Rejected because the model and runtime change on
  different cadences, and every image rebuild or distribution would duplicate roughly 20 GiB.
- **Download automatically at container startup.** Rejected because startup would require NInfer
  egress, hide a long mutable operation behind healthchecks, and mix model acquisition with serving.
- **Accept any model file without a pinned profile.** Rejected because NInfer supports explicitly
  registered artifact identities; filename presence alone does not establish compatibility.

## Consequences

- A fresh clone is intentionally not inference-ready until the owner performs the documented model
  download step.
- CI and source builds remain lightweight relative to the model payload.
- NInfer can run without external network access once the verified artifact exists.
- The model mount is immutable from the inference container's perspective.
- Users need sufficient host storage for both the artifact and Docker build layers.
- Selecting a different `NINFER_MODEL_FILE` moves the deployment outside the default verified
  profile and requires a deliberate compatibility and integration test.
