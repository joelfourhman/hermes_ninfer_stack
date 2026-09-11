# Durable Hermes epochs

The controller wraps stock Hermes CLI sessions. It does not implement a second
LLM agent loop. Each foreground invocation runs a bounded number of epochs:
load handoff → resume session → work → independent validation → checkpoint.
The default epoch is at most 24 turns and 600 seconds, with 50 total epochs and
three failed attempts per approach. An identical repeated failure or repeated
nonprogress forces a named re-plan. Completion requires a fresh structured agent
report declaring the goal complete and a zero exit from your validation command.
Choose a command that actually proves the task; `git status` alone is not proof.

PowerShell example:

```powershell
python ninfer.py job init --repo C:/work/project --goal 'Fix the failing tests' --test-command '["python","-m","unittest"]'
python ninfer.py job resume --state C:/work/project/PROJECT_STATE.json --epochs 3 --max-turns 24 --timeout 600
python ninfer.py job checkpoint --state C:/work/project/PROJECT_STATE.json
python ninfer.py job replan --state C:/work/project/PROJECT_STATE.json --approach 'Reduce to the smallest failing fixture'
```

`PROJECT_STATE.json` contains goal, milestone, completed tasks, failed attempts,
findings, repository HEAD, tests, changed files, blocker, next actions, epoch,
session ID and checkpoint time. Atomic fsync/replace writes carry SHA-256
checksums; a cross-process lock prevents simultaneous controllers. Snapshots and
private epoch evidence live under `.ninfer-jobs/JOB/`. The parent checkpoints
before the epoch and after validation; the Hermes hook persists the last durable
handoff before each tool. Hermes filesystem checkpoints are explicitly enabled.
No auto-approval/oneshot bypass is used.

After Hermes/NInfer restart or reboot, rerun `job resume`. Native Hermes session
storage resumes the last session, including rotated compressed-session IDs when
reported by the CLI. If a worker survived the parent, resume refuses to start a
duplicate. Inspect it, wait or stop it before resuming. NInfer's caches rebuild
from the persisted conversation; its in-memory Responses IDs are not checkpoints.

Corruption stops execution. Pick a valid snapshot belonging to this job:

```text
python ninfer.py job recover --state C:/work/project/PROJECT_STATE.json --snapshot C:/work/project/.ninfer-jobs/JOB/checkpoints/SNAPSHOT.json
```

Recovery preserves the unreadable original and refuses known live workers. A
corrupt ledger may no longer contain a trustworthy PID: check remaining Hermes
processes manually before recovery. Checksums detect corruption, not hostile
tampering by a process with the same filesystem permissions. Reports are fully
validated before updating the handoff. Native compression is session-managed;
the controller promises epoch-level recovery, not exact restoration of every
in-flight tool effect or partial model response. Review non-idempotent external
actions after a crash. No scheduled/background service is installed.

## Execution backends

Local is the default and operates in the supplied repository as your OS user.
Container mode uses the native Hermes Docker backend and a disposable clone of
the repository's committed HEAD. Commit wanted inputs first: dirty/untracked
source files are not copied into the clone. Build the optional example toolchain:

```text
docker build -t hermes-agent-worker:local worker
python ninfer.py job init --repo C:/work/project --goal "Fix tests" --test-command '["python","-m","unittest"]' --backend container --image hermes-agent-worker:local --network none
```

Only the clone is mounted to `/workspace`. Network defaults to none; bridge is an
explicit opt-in. The worker has CPU/RAM limits, dropped capabilities, no privilege
escalation and no Docker socket. Install compilers/dependencies into the image
before starting a no-network job. Independent tests run in the same selected
image with an additional PID limit. Timeouts stop local process trees and remove
the specifically named validation container. Native Hermes manages its own tool
containers; inspect Docker for leftovers after a hard host crash.

```text
python ninfer.py job export --state C:/work/project/PROJECT_STATE.json --destination C:/work/export-1 --artifact dist/result.txt
```

Export writes a tracked-file patch, state and explicitly selected local/container
artifact files. It does not apply/merge them into the original repository.

Remote mode maps Hermes terminal/file tools and validation to SSH:

```text
python ninfer.py job init --repo C:/work/controller --goal "Run project validation" --test-command '["python3","-m","unittest"]' --backend remote --host worker --remote-workspace /srv/work/project
```

Provision the remote repository/toolchain and known-host entry yourself. Validation
uses strict host-key checking and quoted Linux commands; Hermes controls its own
SSH transport. SSH credentials use existing agents/config or HERMES_WORKER_SSH_KEY.
Disconnecting SSH does not guarantee remote child termination; inspect the worker
after a timeout. Retrieve remote artifacts with explicit scp. A Linux VM, Proxmox
guest or DGX Spark can serve as this worker; no platform-specific manager is added.
Browser and arbitrary connector isolation are not implemented.

## Optional supervisor

`supervisor.example.json` is disabled. Make a private copy, select an HTTPS
OpenAI-compatible endpoint/model and name the environment variable containing
its credential. Configure the job, then preview the compact packet:

```text
python ninfer.py job supervisor-config --state PROJECT_STATE.json --config supervisor.local.json
python ninfer.py job supervise --state PROJECT_STATE.json --reason stuck
python ninfer.py job supervise --state PROJECT_STATE.json --reason stuck --send
```

Only the final explicit command sends, and only if enabled. Supported reasons are
initial-architecture, major-plan, stuck, failing-tests, design-decision,
milestone-review and final-review.
The allowlisted packet contains the goal/handoff/failures, not the entire chat or
repository. Findings can still contain sensitive project information: review the
preview. A stuck job writes a request packet but does not automatically call a
provider. A returned review is advisory and never executes tools or silently
changes the plan. Credentials stay in environment variables.
