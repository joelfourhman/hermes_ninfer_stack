# Troubleshooting

Start with the layered verifier:

```bash
./scripts/verify.sh
```

It stops at the first failed boundary. Use that layer and the cases below rather than changing
multiple services at once.

## NInfer submodule is empty

**Symptom**

`docker compose build ninfer` reports that `ninfer/Dockerfile` or source files are missing.

**Likely cause**

The repository was cloned without its pinned submodule.

**Diagnosis**

```bash
git submodule status
git -C ninfer rev-parse HEAD
```

**Fix**

```bash
git submodule update --init --recursive
git -C ninfer rev-parse HEAD
```

The expected revision is `feaf4dd0983fdaeb2ba4c06eec6da350e644fb3a`.

## Setup rejects `.env`

**Symptom**

`scripts/setup.sh` reports invalid or missing secrets, UID/GID, port, or another required value.

**Likely cause**

An existing `.env` is incomplete, has quoted placeholder secrets, or contains a value outside the
accepted range.

**Diagnosis**

```bash
docker compose --env-file .env config --quiet
```

Compare variable names with `.env.example` without posting the secret values.

**Fix**

Correct the existing file, or move it to a private backup and rerun setup. Do not delete an unknown
`.env` until you have preserved any integration secrets it contains.

## GPU is not visible inside Docker

**Symptom**

Verification fails at the GPU layer, or NInfer reports that no CUDA device is available.

**Likely cause**

Docker is using Windows containers, WSL2 GPU integration is unavailable, NVIDIA Container Toolkit
is not configured, the driver is too old, or `NINFER_GPU_DEVICE` names a device Docker cannot see.

**Diagnosis**

```bash
nvidia-smi
docker run --rm --gpus all \
  nvidia/cuda:13.1.2-base-ubuntu24.04 \
  nvidia-smi
```

The second command must identify an RTX 5090.

**Fix**

Use Linux containers and the WSL2 backend where applicable, repair Docker's NVIDIA runtime path,
update the Windows/Linux NVIDIA driver as appropriate, and set `NINFER_GPU_DEVICE` to the visible
single-device ID. Resolve this before rebuilding NInfer.

## NInfer build fails on CUDA architecture checks

**Symptom**

CMake or NVCC reports an unsupported architecture, unknown `sm_120a`, or a CUDA version error.

**Likely cause**

The build is using a pre-Blackwell toolchain, a non-amd64 builder, an overridden CUDA architecture,
or the wrong NInfer revision.

**Diagnosis**

```bash
git -C ninfer rev-parse HEAD
docker compose build --progress=plain ninfer
```

Look for the CUDA base tag and configured architecture in the build output.

**Fix**

Restore the pinned submodule revision, use the upstream CUDA 13.1.2 Dockerfile on a 64-bit Linux
builder, and remove local `CMAKE_CUDA_ARCHITECTURES` overrides. NInfer intentionally targets
`sm_120a`; changing it is not a supported portability fix.

## NInfer image build fails while installing dependencies

**Symptom**

The build fails before compilation during image pull or package installation.

**Likely cause**

Docker lacks network access, registry authentication is broken, package mirrors are unavailable, or
the host has insufficient disk space.

**Diagnosis**

```bash
docker system df
docker pull nvidia/cuda:13.1.2-devel-ubuntu24.04
docker compose build --progress=plain ninfer
```

**Fix**

Restore Docker registry and package-network access, free Docker storage without deleting project
volumes, and retry the unchanged pinned build. Do not install global host CUDA packages as a
substitute for dependencies owned by the image.

## Model file is missing or has the wrong checksum

**Symptom**

Verification fails before container health, or NInfer reports that the artifact cannot be opened.

**Likely cause**

The download is incomplete, `NINFER_MODEL_FILE` does not match the filename, or a different artifact
was placed under `models/`.

**Diagnosis**

```bash
ls -lh models/
./scripts/download-model.sh
```

The expected SHA-256 is
`bb3360522a06e136e0367f5703414d26272b7285c8a6ab6194135c17dbd81b32`.

**Fix**

Remove only the known incomplete file, download the pinned artifact again, and keep
`NINFER_MODEL_FILE=qwen3_8_27b_nvfp4.ninfer`. Do not rename a GGUF or Safetensors file to `.ninfer`.

## Model load fails despite a correct checksum

**Symptom**

NInfer starts, then exits with an artifact-version, registered-identity, binding, or allocation
error.

**Likely cause**

The NInfer submodule is older than the artifact requirement, startup flags do not match the selected
profile, or VRAM allocation failed.

**Diagnosis**

```bash
git -C ninfer rev-parse HEAD
docker compose logs --tail=200 ninfer
```

**Fix**

Restore the pinned NInfer revision and default model variables. For an allocation failure, follow
the out-of-memory case below. Do not migrate or rewrite the pinned version-2 artifact.

## NInfer runs out of memory

**Symptom**

Startup or a long request fails with a CUDA allocation error, or the container repeatedly restarts.

**Likely cause**

The requested concurrency/context exceeds available VRAM, another process is using the GPU, or
vision/speculative allocations were changed from the tested profile.

**Diagnosis**

```bash
nvidia-smi
docker compose logs --tail=200 ninfer
```

Check NInfer's logged automatic KV capacity and other GPU processes.

**Fix**

Stop unrelated GPU workloads and first set `NINFER_MAX_CONCURRENCY=1`. If context must be reduced,
change `NINFER_CONTEXT_LENGTH`, stop Hermes, rerun `scripts/configure-hermes.sh`, recreate NInfer,
and run verification. Do not claim the new profile as benchmarked until it is measured.

## Host port is already in use

**Symptom**

Compose cannot publish NInfer and reports that port 8080 is allocated.

**Likely cause**

Another host process or container owns the selected loopback port.

**Diagnosis**

```bash
docker ps --format 'table {{.Names}}\t{{.Ports}}'
```

On Linux, also use `ss -ltnp | grep ':8080'` if needed.

**Fix**

Set an unused host port, for example `NINFER_HOST_PORT=18080`, then recreate NInfer. Do not change
Hermes's internal URL; it remains `http://ninfer:8080/v1`.

## `GET /v1/models` fails

**Symptom**

The NInfer container is healthy, but the host request times out, returns 401, or does not list the
expected model.

**Likely cause**

The wrong host port or API key is being used, or `NINFER_MODEL_ID` differs from the expected alias.

**Diagnosis**

```bash
set -a
source .env
set +a
curl -fsS \
  -H "Authorization: Bearer $NINFER_API_KEY" \
  "http://127.0.0.1:${NINFER_HOST_PORT}/v1/models" | jq .
```

**Fix**

Use values from the active `.env`, recreate NInfer after configuration changes, and confirm the
response advertises `NINFER_MODEL_ID`. Never paste the bearer secret into an issue or log bundle.

## Direct chat completion fails

**Symptom**

`GET /v1/models` succeeds, but `/v1/chat/completions` times out or returns an error.

**Likely cause**

The model is still warming, request context exceeds the configured ceiling, NInfer encountered a
runtime error, or the request uses the wrong model alias.

**Diagnosis**

```bash
docker compose logs --tail=200 ninfer
./scripts/verify.sh
```

**Fix**

Wait for the NInfer healthcheck, use `NINFER_MODEL_ID`, keep the request within
`NINFER_CONTEXT_LENGTH`, and address the first CUDA or request error in the NInfer log.

## Hermes cannot connect to NInfer

**Symptom**

Direct host inference succeeds, but verification fails at the Hermes network or inference layer.

**Likely cause**

Hermes is configured with `localhost`, internal DNS is unavailable, the API key environment name is
wrong, or Hermes configuration was changed by the setup wizard.

**Diagnosis**

```bash
docker compose exec -T hermes sh -lc '
  getent hosts ninfer
  curl -fsS -H "Authorization: Bearer $NINFER_API_KEY" \
    http://ninfer:8080/v1/models
'
```

**Fix**

Stop Hermes, run `./scripts/configure-hermes.sh`, and start it again. The provider endpoint must be
`http://ninfer:8080/v1`, not a host-loopback URL.

## Container DNS fails

**Symptom**

Hermes reports that host `ninfer` or `sandbox` cannot be resolved.

**Likely cause**

A service was started outside this Compose project, networks are stale, or a local override removed
Hermes from an internal network.

**Diagnosis**

```bash
docker compose ps
docker compose exec -T hermes getent hosts ninfer sandbox
docker network ls --filter label=com.docker.compose.project
```

**Fix**

Remove unsupported network overrides and reconcile the declared project with
`docker compose up -d`. Compose creates its own networks; no external network should be required.

## Hermes and NInfer model IDs do not match

**Symptom**

Hermes receives a model-not-found response while direct NInfer requests using another name work.

**Likely cause**

`NINFER_MODEL_ID` changed without reapplying Hermes configuration.

**Diagnosis**

```bash
set -a
source .env
set +a
curl -fsS \
  -H "Authorization: Bearer $NINFER_API_KEY" \
  "http://127.0.0.1:${NINFER_HOST_PORT}/v1/models" | jq -r '.data[].id'
docker compose run --rm --no-deps hermes hermes config get model
```

**Fix**

Stop the Hermes service and rerun `./scripts/configure-hermes.sh`. Recreate NInfer if its alias also
changed, then run full verification.

## Tool calls are returned but not executed

**Symptom**

The model responds with tool-like JSON or prose, but no terminal command runs in the sandbox.

**Likely cause**

The model emitted malformed/plain-text calls, Hermes rejected the schema, the SSH backend is not
configured, or the sandbox is unhealthy. NInfer parses tool calls but never executes them itself.

**Diagnosis**

```bash
docker compose logs --tail=200 ninfer
docker compose logs --tail=200 hermes
docker compose ps sandbox
./scripts/verify.sh
```

**Fix**

Repair sandbox health first, rerun `scripts/configure-hermes.sh`, and use the verifier's real
filesystem-side-effect check. A model statement that a command ran is not proof of execution.

## Sandbox is unhealthy or SSH fails

**Symptom**

The sandbox healthcheck fails, or Hermes reports SSH authentication/host-key errors.

**Likely cause**

Key-generation did not complete, named key volumes were removed, host-key state changed, or
workspace ownership no longer matches `HERMES_UID`/`HERMES_GID`.

**Diagnosis**

```bash
docker compose ps
docker compose logs --tail=100 sandbox-keygen sandbox
docker compose exec -T hermes \
  ssh -i /ssh/id_ed25519 -p 2222 \
  -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
  agent@sandbox 'uname -r'
```

**Fix**

Reconcile `sandbox-keygen` and `sandbox` with `docker compose up -d`. If volumes were deliberately
deleted and only the old known-host entry remains, remove that one entry:

```bash
docker compose exec hermes \
  ssh-keygen -f /opt/data/home/.ssh/known_hosts -R '[sandbox]:2222'
```

Do not disable host-key checking globally.

## Model file permissions prevent loading

**Symptom**

NInfer reports permission denied for `/models/...` even though the file exists.

**Likely cause**

The host file is not readable through the Docker bind mount, or the Docker Desktop file-sharing path
is unavailable.

**Diagnosis**

```bash
ls -l "models/${NINFER_MODEL_FILE:-qwen3_8_27b_nvfp4.ninfer}"
set -a
source .env
set +a
docker compose run --rm --no-deps -T \
  -e NINFER_MODEL_FILE="$NINFER_MODEL_FILE" --entrypoint sh ninfer \
  -c 'ls -l /models && test -r "/models/$NINFER_MODEL_FILE"'
```

**Fix**

Grant read access to the specific artifact and ensure the repository path is shared with Docker
Desktop. Keep the mount read-only; changing it to writable is not a permissions fix.

## A service is in a restart loop

**Symptom**

`docker compose ps` repeatedly shows `Restarting` or an increasing restart count.

**Likely cause**

The process fails during initialization while `restart: unless-stopped` keeps retrying.

**Diagnosis**

```bash
docker compose ps
docker compose logs --tail=200 <service>
docker inspect --format '{{.RestartCount}} {{.State.Error}}' \
  "$(docker compose ps -q <service>)"
```

**Fix**

Stop the affected service, correct the first startup error, and start it again. Do not remove named
volumes as a generic restart remedy; that deletes sandbox identities and home state.

## Verification responses were preserved

**Symptom**

`verify.sh` exits non-zero and prints a temporary response directory.

**Likely cause**

A later API or tool-call assertion failed, so the verifier retained its diagnostic JSON.

**Diagnosis**

Inspect only the named temporary directory and the corresponding service log. Treat responses as
potentially private because they can contain prompts or model output.

**Fix**

Address the failed layer, rerun verification, and remove the retained temporary directory after it
is no longer needed. Never attach it publicly without reviewing and redacting it.
