# NInfer for stock Hermes Desktop on RTX 5090

## Quick start

Install these once with their normal Windows installers:

- The latest [NVIDIA driver](https://www.nvidia.com/en-us/drivers/) for your RTX
  5090. The CUDA Toolkit is not required.
- [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/)
  using its recommended Linux-container backend.
- [Git for Windows](https://git-scm.com/download/win).
- 64-bit [Python 3.10 or newer](https://www.python.org/downloads/windows/), with
  Python added to `PATH`.

Open a normal, non-administrator Command Prompt and run:

```text
git clone https://github.com/joelfourhman/hermes_ninfer_stack.git hermes-ninfer-stack
cd hermes-ninfer-stack
python ninfer.py setup
```

At the prompts:

1. Press Enter to choose the recommended stock model.
2. Press Enter to approve its model download.
3. Press Enter to install and configure stock Hermes Desktop.
4. Complete the official Hermes installer when its page opens. If Hermes asks
   for a provider, choose **Choose provider later**, finish first launch, and
   return to Command Prompt.
5. Follow the remaining prompts until **SETUP COMPLETE**, then start a new
   Hermes chat.

There is no project username or password, and you do not need a Hugging Face
account. The helper creates the private local connection key and gives it to
Hermes without displaying it.

If the window was closed or the Hermes step did not finish, do not start over.
Reopen Command Prompt in the repository directory and run:

```text
python ninfer.py install-hermes
```

The helper starts Docker Desktop and the configured model service if needed.

Setup is safe to rerun after an interruption. Downloads resume when possible,
and existing model files are preserved. For alternate models, storage needs,
the complete prompt walkthrough, and common first-run problems, see the
[installation guide](docs/installation.md).

## Local agents with measured, recoverable work

Stock Hermes Desktop runs natively on Windows. NInfer runs in a single hardened
Linux GPU container. Hermes talks to its authenticated OpenAI-compatible API.
Optional durable jobs use the installed Hermes CLI in a private job home, bounded
epochs, independent validation and a checksummed handoff. Ordinary Desktop use
continues to work without the job controller.

The recommended starting point remains **stock + balanced + MTP3**. Workload
profiles and DFlash2 are selectable candidates. See the actual
[measurements](BENCHMARK_RESULTS.md) before changing your daily configuration.

## Hardware and provenance

- RTX 5090, 32 GB VRAM; close other GPU-heavy applications.
- Windows is the primary host. Docker Desktop needs Linux containers with GPU
  access. Python 3.10+ and Git are required; a host CUDA Toolkit is unnecessary.
- Allow substantial system RAM for Docker, Hermes and pinned host KV. Profiles
  can reserve 8 GiB of host KV in addition to model staging and other processes.
- Allow model storage plus Docker build space. Selecting the companion artifact
  retains the original files and adds another roughly 22 GiB.

The exact NInfer commit, CUDA base, immutable model revisions, file sizes and
SHA-256 checksums are generated in the [configuration reference](docs/generated-config.md)
from [stack/manifest.json](stack/manifest.json). NInfer is pinned to an audited
upstream master commit; it is not represented as a tagged stable release.
`build`, `verify` and `validate` check source/image/artifact/CLI provenance.
[AUDIT.md](AUDIT.md) records the previous deployment and verified upstream behavior.

## Choose a workload

Use one complete preset for normal switching:

```text
python ninfer.py use default
python ninfer.py use coding
python ninfer.py use coding-fast
python ninfer.py use research
python ninfer.py use autonomous
python ninfer.py use low-vram
python ninfer.py use uncensored
```

Each command selects the model artifact, runtime capacity and decoder together,
then starts the service once and creates or updates the matching native Hermes
profile. The profiles are named `ninfer-default`, `ninfer-coding`,
`ninfer-coding-fast`, `ninfer-research`, `ninfer-autonomous`,
`ninfer-low-vram` and `ninfer-uncensored`. The selected profile becomes Hermes'
sticky active profile, so Desktop sessions and settings stay separate between
workloads. `coding` uses DFlash2-7;
`coding-fast` uses the slightly faster but more aggressive DFlash2-11. A preset
prints its complete mapping before it changes configuration. Run
`python ninfer.py presets` to display the mappings. If its artifact is absent,
the normal large-download confirmation still appears unless you pass `--yes`.
On startup failure, all NInfer and Hermes settings return to their prior values.
Restart Hermes Desktop after `use` so the running app loads the selected profile.

The lower-level controls remain available for experiments:

```text
python ninfer.py profiles
python ninfer.py profile coding
python ninfer.py profile research
python ninfer.py profile autonomous
python ninfer.py profile low-vram
python ninfer.py profile balanced
```

`profile` configures NInfer and the installed Hermes provider together, preserves
existing execution/approval settings, live-tests startup and rolls back on failure.
Every preset configures both Hermes goals and the ordinary agent tool loop for up
to 100,000 turns. Durable `job` epochs keep their separate explicit turn budget.
Restart Desktop after changing context so existing processes reload their settings.
`select-runtime --profile NAME` remains supported.

<!-- BEGIN GENERATED PROFILES -->

| Profile | Context tokens | Shared KV tokens | Lanes | Device / host cache slots | Host KV MiB | Compression tokens | Turns |
|---|---:|---:|---:|---:|---:|---:|---:|
| `balanced` | 131,072 | 196,608 | 2 | 2 / 8 | 8,192 | 90,000 | 100000 |
| `single-session` | 131,072 | 131,072 | 1 | 1 / 4 | 4,096 | 100,000 | 100000 |
| `max-context` | 240,000 | 240,000 | 2 | 2 / 8 | 8,192 | 200,000 | 100000 |
| `interactive` | 131,072 | 196,608 | 2 | 2 / 8 | 8,192 | 90,000 | 100000 |
| `coding` | 196,608 | 196,608 | 2 | 2 / 8 | 8,192 | 150,000 | 100000 |
| `research` | 240,000 | 240,000 | 2 | 2 / 8 | 8,192 | 200,000 | 100000 |
| `autonomous` | 196,608 | 196,608 | 2 | 2 / 8 | 8,192 | 150,000 | 100000 |
| `low-vram` | 65,536 | 65,536 | 1 | 1 / 2 | 2,048 | 48,000 | 100000 |

<!-- END GENERATED PROFILES -->

All profiles use FP8 KV, 1,024-token prefill chunks, preserved thinking and the
optimized draft head. `interactive` mirrors balanced; `coding` retains a larger
working history; `research` allows large documents; `autonomous` uses shorter
job epochs; `low-vram` reduces the cache footprint. Original names remain available.
These are context ceilings, not guaranteed sustained capacity or speed on every
artifact. Companion weights and draft windows have their own memory costs.

“240K” means **240,000 tokens total per request**, including prompt and output.
The shared KV pool is not divided statically by two lanes. Concurrent requests
and retained state compete for capacity; two lanes do not promise two full
240K sessions simultaneously. See [cache behavior](docs/performance.md).

## Choose a model and decoder

```text
python ninfer.py select-model --model stock
python ninfer.py spec mtp3

python ninfer.py prepare-model --model stock-dflash2
python ninfer.py select-model --model stock-dflash2
python ninfer.py spec dflash2-7
python ninfer.py spec dflash2-11
python ninfer.py spec dflash2 --draft-tokens 5
```

DFlash2 requires the explicitly selected companion artifact. The original stock
and optional uncensored artifacts support MTP; they are never silently replaced.
MTP accepts 1–5 draft tokens; DFlash2 accepts 1–15. Selecting an older artifact
while DFlash2 is active prints a notice and restores MTP3. Model and decoder
changes live-test startup and restore the previous configuration on failure.
[Model provenance and fallback](docs/models.md) explains the distinction between
an artifact change and a decoder change.

## Measure complete work

```text
python ninfer.py bench-agent coding --runs 3 --max-tokens 2048
python ninfer.py bench-agent coding --driver hermes --runs 3
python ninfer.py bench-agent research --context-kib 256 --runs 3
python ninfer.py bench-agent long-session --session-turns 12 --max-turns 40
python ninfer.py bench-agent parallel --session-turns 6 --max-turns 30
python ninfer.py bench-compare benchmarks/RUN1/results.json benchmarks/RUN2/results.json
python ninfer.py observe
```

The bounded driver executes real fixture reads, model edits and tests. The
`hermes` driver invokes actual stock Hermes with terminal/file tools in a private
home. Both save JSON, acceptance results, human-readable summaries, native logs
and whole-device/host memory samples. Mock `--smoke` results are explicitly
excluded from performance comparisons. [BENCHMARK_PLAN.md](BENCHMARK_PLAN.md)
gives the controlled matrix, cache protocol and exact RTX 5090 commands.

## Resume autonomous work

```text
python ninfer.py job init --repo C:/work/project --goal "Fix the failing tests" --test-command '["python","-m","unittest"]'
python ninfer.py job resume --state C:/work/project/PROJECT_STATE.json --epochs 3
python ninfer.py job status --state C:/work/project/PROJECT_STATE.json
```

The JSON quoting above works in PowerShell; Command Prompt needs escaped inner
double quotes. Each epoch restores the Hermes session, reads the durable handoff,
makes a bounded increment, runs your validation command and checkpoints. Three
failed attempts require `job replan`; the default total budget is 50 epochs.
The controller runs in the foreground. After a crash or reboot, run `job resume`
again; it does not install a background service. See [durable jobs](docs/jobs.md)
for corruption recovery, compression limits, supervisor and artifact export.

## Security and execution

Desktop and local jobs run with your normal user permissions and manual Hermes
approvals. Model refusal behavior is not an isolation boundary. Container jobs
are opt-in, clone the committed repository into a disposable workspace, expose
one mount and default to no network. SSH jobs target an explicitly provisioned
Linux workspace. These modes isolate supported terminal/file tools; they do not
claim to isolate the native Hermes process or every possible plugin/browser.
See [security](docs/security.md) and [job backends](docs/jobs.md).

Remote supervision is disabled by default. Explicitly configure it, review the
compact packet and invoke `job supervise --send` to make a remote request. No
credentials or full conversation histories belong in Git.

The API binds to loopback by default. `python ninfer.py network --mode lan` is an
explicit opt-in to authenticated private-LAN HTTP, without TLS. Use only a
trusted network. `network --mode local` returns to loopback.

To provision another computer on that LAN, install Hermes Desktop and copy or
clone this repository there. On the NInfer host, select the server preset, enable
LAN mode and display the connection details:

```text
python ninfer.py use autonomous
python ninfer.py network --mode lan
python ninfer.py network
python ninfer.py network --show-key
```

Then run this on each client, substituting the endpoint printed by the host:

```text
python ninfer.py configure-client autonomous --endpoint http://192.168.1.20:8080/v1
```

The command securely prompts for the key, verifies the authenticated endpoint,
and creates and activates `ninfer-autonomous` in that client's Hermes Desktop.
Restart Desktop afterward. The host loads one backend preset at a time, so use
the same preset name on the host and every active client profile. Use
`--no-activate` to prepare a client profile without switching to it.

## Maintain and troubleshoot

```text
python ninfer.py up
python ninfer.py logs
python ninfer.py verify
python ninfer.py validate
python ninfer.py docs --check
python -m unittest discover -s tests -v
```

For OOM/startup failure, inspect logs, close competing GPU work and restore
`profile balanced` or `profile low-vram` with `spec mtp3`. A running Desktop
session keeps its loaded config until restarted. Missing native metrics are
reported as unavailable. NInfer caches and Responses IDs are process-local and
are lost when NInfer restarts; durable Hermes sessions/checkpoints rebuild them.

More detail: [installation](docs/installation.md),
[configuration](docs/configuration.md), [architecture](docs/architecture.md),
[compatibility](docs/compatibility.md), [troubleshooting](docs/troubleshooting.md),
[performance](docs/performance.md), [final report](FINAL_REPORT.md).
