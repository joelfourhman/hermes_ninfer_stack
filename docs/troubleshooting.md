# Troubleshooting

## First-run recovery

If `python ninfer.py setup` stops, read its final message first. The setup is
designed to be rerun safely: it keeps the generated connection key, resumes or
rechecks the model download, and preserves an existing Hermes installation.
You normally do **not** need to delete anything or start over.

- If Docker is not running, open Docker Desktop, wait until it reports that the
  engine is running, and rerun `python ninfer.py setup`.
- If the model download was declined or interrupted, rerun
  `python ninfer.py setup` and approve the download. Partial download data is
  retained for the downloader to resume.
- If Windows restarted or the Command Prompt window was closed after NInfer
  finished, run `python ninfer.py setup` again. Completed work is reused.
- If NInfer works but Hermes installation or onboarding was not completed, run
  `python ninfer.py install-hermes`; it restarts the configured local model if
  needed.
- If Hermes was open while its provider was configured, close and reopen
  Hermes, then start a new chat.

Do not post `.env`, the generated NInfer key, or the contents of Hermes's
secret file when asking for help.

For a more detailed diagnosis, run the layered verifier:

```text
python ninfer.py verify
```

It stops at the first failed boundary. Fix that layer before changing multiple
settings.

`python ninfer.py logs` keeps showing new NInfer output until you press Ctrl+C.
Stopping that view does not stop the model service.

## NInfer source is missing or at the wrong revision

**Symptom:** the build cannot find `ninfer/Dockerfile`, or setup reports an
unexpected source revision.

**Fix:** rerun the same setup command. It initializes or repairs a checkout it
created and verifies the exact reviewed revision automatically:

```text
python ninfer.py setup
```

The expected revision is
`feaf4dd0983fdaeb2ba4c06eec6da350e644fb3a`. Do not replace it with an
unpinned checkout as a troubleshooting shortcut. If setup reports local or
untracked changes, it deliberately leaves them untouched; move your own NInfer
source edits to a separate clone before rerunning setup.

## Setup rejects `.env`

**Symptom:** setup reports a missing key, invalid port, model name, context, KV
capacity, or concurrency.

**Fix:** compare variable names and non-secret values with `.env.example`, then
rerun the idempotent setup validator:

```text
python ninfer.py setup
```

Preserve an existing `.env` before replacing it because it can contain the key
already configured in Hermes. Never post the key in an issue.

## Setup pauses before the model download

This is expected after declining the explicit transfer prompt. No model is
downloaded and later stages do not run. Ensure at least 24 GiB is available,
then rerun:

```text
python ninfer.py setup
```

## GPU is not visible in Docker

**Symptom:** verification cannot see CUDA or NInfer reports no compatible
device.

Run the project verifier, which checks both host and container visibility
without asking you to compose Docker commands:

```text
python ninfer.py verify
```

The container check must identify an RTX 5090. On Windows, switch Docker
Desktop to Linux containers and repair its NVIDIA/WSL2 backend. The user does
not need to open a WSL shell to run the project.

## NInfer build rejects the CUDA architecture

**Symptom:** CMake or NVCC reports an unsupported architecture, unknown
`sm_120a`, or wrong CUDA version.

Restore the pinned source and use the upstream CUDA 13.1.2 build. Remove local
architecture overrides. NInfer intentionally targets `sm_120a`; changing it is
not a supported portability fix.

Rerun `python ninfer.py setup`. It verifies and repairs the reviewed source
revision before rebuilding. If you intentionally changed files under
`ninfer/`, setup stops instead of overwriting them.

## Image build fails before compilation

Registry access, package mirrors, or Docker storage may be unavailable. Open
Docker Desktop's **Troubleshoot** and storage views, confirm it has internet
access and free space, then retry through the Python helper:

```text
python ninfer.py build
```

Restore Docker network access or free safe Docker storage, then retry the pinned
build. Installing global host CUDA packages does not repair dependencies owned
by the image.

## Model file is missing or has the wrong checksum

Run the isolated acquisition check again:

```text
python ninfer.py download-model
```

The expected file is `models/qwen3_8_27b_nvfp4.ninfer`; the expected SHA-256 is
`bb3360522a06e136e0367f5703414d26272b7285c8a6ab6194135c17dbd81b32`.

Delete only a known incomplete or incorrect artifact. Do not rename a GGUF or
Safetensors file to `.ninfer`.

## Model load fails despite a correct checksum

Inspect the first NInfer startup error through the Python control command:

```text
python ninfer.py logs
```

Common causes are a mismatched runtime revision, unsupported startup flags, or
VRAM allocation failure. Restore the reviewed source and defaults before
attempting model conversion or mutation.

## NInfer runs out of memory

Close competing GPU programs in Task Manager, then inspect NInfer's output:

```text
python ninfer.py logs
```

Stop unrelated GPU workloads. If the profile must be reduced, lower
`NINFER_CONTEXT_LENGTH` and `NINFER_KV_CAPACITY` together for concurrency one,
recreate NInfer, and reapply the matching Hermes metadata:

```text
python ninfer.py down
python ninfer.py up
python ninfer.py install-hermes
python ninfer.py verify
```

Treat the changed profile as unbenchmarked until measured.

## Host port is already in use

**Symptom:** Docker reports that port 8080, or the configured alternative, is
already allocated.

Set an unused `NINFER_HOST_PORT` in `.env`, recreate NInfer, and update Hermes:

```text
python ninfer.py down
python ninfer.py up
python ninfer.py install-hermes
```

The native provider must use the new
`http://127.0.0.1:${NINFER_HOST_PORT}/v1` address.

## NInfer is healthy but API checks fail

A 401 normally means the request omitted or used the wrong project key. A model
list that lacks `NINFER_MODEL_ID` normally means the running container was not
recreated after an alias change.

If Docker reports the container as healthy but `127.0.0.1` refuses the
connection, rerun `python ninfer.py up`. The helper recreates the project
network once to repair missing Docker Desktop port forwarding. Releases before
this recovery existed incorrectly used an internal Docker network, which could
not publish its port to the Windows host.

Use `python ninfer.py verify` rather than printing the key or constructing a
diagnostic command that exposes it in command history. For service state and
output, use:

```text
python ninfer.py status
python ninfer.py logs
```

## Direct generation fails

If health and model discovery work but generation fails, the model may still be
warming, the request may exceed `NINFER_CONTEXT_LENGTH`, or NInfer may have hit
a CUDA/runtime error. Wait for health, use the advertised model alias, and
address the first server error rather than changing Hermes.

## Hermes Desktop is not installed

Run:

```text
python ninfer.py install-hermes
```

The helper opens the official Hermes Desktop page. Complete the stock installer
and return to the prompt. This project does not supply an alternative `.exe`.

If the website cannot be opened automatically, visit
`https://hermes-agent.nousresearch.com/desktop` directly.

## Hermes was installed but the helper cannot find it

An already-running terminal does not automatically receive a PATH update from
a Windows installer. The helper checks both `PATH` and the official default
`%LOCALAPPDATA%\hermes\bin\hermes.exe` path.

If detection still fails:

1. Finish Hermes Desktop's first-launch local runtime installation.
2. Close and reopen the terminal.
3. Rerun `python ninfer.py install-hermes`; it performs the stock CLI check for
   you.

Do not copy a random `hermes.exe` into the project.

## Hermes configuration check fails

Update or repair Hermes with its official installer, then rerun the helper. The
helper requires a stock release that supports named `providers:` entries,
`key_env`, and `custom:<name>` selection.

It preserves unrelated Hermes configuration. If Hermes reports malformed YAML,
follow its own backup/recovery guidance before allowing another writer to
change the file.

## Hermes cannot connect but direct NInfer verification passes

The native provider should contain:

```text
provider: custom:ninfer
base URL: http://127.0.0.1:${NINFER_HOST_PORT}/v1
model: NINFER_MODEL_ID
key environment name: NINFER_API_KEY
```

Rerun:

```text
python ninfer.py install-hermes
python ninfer.py verify
```

Do not use the old container hostname `http://ninfer:8080/v1`; stock native
Hermes cannot resolve that Compose-only name.

If Desktop was already open, restart it after repair so its local backend and
new sessions use the current provider.

## Hermes and NInfer model IDs differ

Recreate NInfer after changing `NINFER_MODEL_ID`, then rerun the helper. A
healthy server can still reject Hermes if its selected model alias is stale.

```text
python ninfer.py down
python ninfer.py up
python ninfer.py install-hermes
python ninfer.py verify
```

## Tool calls do not run, or run somewhere unexpected

NInfer returns structured tool-call data but does not execute tools. Stock
Hermes decides whether and where to run them according to its native tool
configuration.

There is no SSH sandbox in the active project. A native terminal or file tool
runs with the current user's permissions. Check Hermes's tool selection and
approvals, and do not use successful model prose as proof that a filesystem
action occurred.

## Native Hermes changed or deleted a user file

This is not a Docker escape: Hermes is intentionally native and same-user. Stop
Hermes, preserve logs, inspect the relevant session/tool history, and restore
from source control or protected backup. Review [Security](security.md) before
reenabling the responsible tool. UAC does not protect ordinary user-writable
files from another process running as that user.

## Model file permission denied

Ensure the specific artifact is readable through Docker Desktop file sharing
and keep the mount read-only. Moving the repository to a Docker-accessible path
may be necessary. Changing the model mount to writable is not a permissions
fix.

## NInfer is in a restart loop

```text
python ninfer.py status
python ninfer.py logs
```

Stop NInfer, correct the first startup error, and start it again. Do not delete
the model or project `.env` as a generic restart remedy.

One early `CUDA Graph preparation consumed ... exceeding the planned
allowance` message followed by a successful restart and `listening on` message
is self-recovered. If that graph error repeats without a later successful
listener, capture the logs and report it as an NInfer compatibility problem.

## Verification retained diagnostic responses

On a later API assertion failure, the verifier may retain a named temporary
directory. Inspect only that directory and the matching NInfer log. Responses
can contain private prompts or model output; redact them before sharing and
remove the temporary copy after diagnosis.
