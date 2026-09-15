# Hermes context reliability and overnight operation

## Active selection

The September 14 audit selects the **autonomous runtime**, retaining the existing
uncensored model and MTP3 decoder. Context and shared KV capacity are 196,608
tokens; Hermes compresses at 80,000. Two lanes allow a main request plus occasional
small requests; they share the KV allocation, so both cannot fill a complete
window simultaneously. The lower allocation leaves more GPU headroom than 240K.

To restore this runtime without changing the selected model:

```powershell
python ninfer.py profile autonomous
```

`use autonomous` also selects the stock model. `use coding` selects the DFlash2
companion. DFlash2-7/-11 are measured coding choices, but previous 240K DFlash2
allocations failed GPU reservation; maximum context is not a universal improvement.
All profiles now reserve at least half the context before automatic compaction.
Memory layouts and existing benchmark evidence remain in the manifest and
`BENCHMARK_RESULTS.md`; they do not constitute an overnight endurance qualification.

## Root causes and fixes

1. Hermes classified NInfer's `prepared prompt ... exceeding Engine max_context`
   HTTP 400 as a fatal format error before reaching structured error-code handling.
   The native classifier now recognizes both observed NInfer overflow phrasings,
   entering its existing bounded compression/retry path. The context parser also
   reads `Engine max_context N`, allowing recovery after a profile changes the limit.
2. The former 200K trigger left too little margin in the 240K window. The final
   active trigger is 80K in a 196,608-token window. The same policy is generated
   for native Hermes and isolated durable jobs.
3. Automatic summary routing was implicit. Compression now explicitly uses the
   main local route with a 600-second timeout. A real repeat-compaction test also
   reproduced a summary exhausting the server's 8,192-token output cap in reasoning
   mode. Summary requests now send `enable_thinking: false`; main-agent reasoning
   settings remain unchanged. Lean tail retention preserves four recent messages
   and the latest real user request, with older history summarized.

Configuration follows the [official Hermes compression documentation](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/developer-guide/context-compression-and-caching.md)
and the installed implementation. No user conversations were deleted or rewritten.

## Verification and updates

### Measured results on the final profile

| Check | Result |
|---|---|
| Real Hermes compaction, cycle 1 | 117,801 → 15,944 input tokens; checkpoint recalled |
| Same conversation, cycle 2 | 133,691 → 16,017 input tokens; checkpoint recalled |
| Native Hermes coding task | Passed; independently validated all 3 fixture tests |
| Stack unit suite | 61 passed, 4 live-only skips |
| Live API suite | All 4 passed (run before the final context-cap reduction) |
| Installed Hermes classifier and metadata suite | 281 passed |
| Final stack verification | All 11 layers passed, including real native Hermes generation |
| GPU memory during concurrent validation | 27,920 / 32,607 MiB used; about 4.6 GiB free |

Raw synthetic compaction evidence is in
`out/context-audit-1789432478404458600/results.json`; the coding run is in
`benchmarks/context-reliability-coding/`; final verification is in
`out/context-final-verification.log`. The coding task ran concurrently with long
prefills and took 194.77 seconds, so this is a correctness result, not an isolated
speed benchmark. No full-night endurance test was performed.

### Repeat the checks

```powershell
python ninfer.py verify
& "$env:LOCALAPPDATA/hermes/hermes-agent/venv/Scripts/python.exe" scripts/check_hermes_context.py
# Synthetic history only; uses the local GPU and writes ignored evidence under out/.
& "$env:LOCALAPPDATA/hermes/hermes-agent/venv/Scripts/python.exe" scripts/check_hermes_context.py --live --cycles 2
```

The live test crosses the compression threshold, runs the real Hermes compressor,
checks for summary failure and substantial token reduction, and asks the model to
recover a checkpoint identifier originally supplied near the start of the history.
It repeats in the same conversation. It never loads personal session history.

The two native source edits have adjacent timestamped backups. Hermes updates can
replace them; `verify` now detects the regression. If an update still fails the
compatibility test, the idempotent repair is:

```powershell
python scripts/patch_hermes_context.py
& "$env:LOCALAPPDATA/hermes/hermes-agent/venv/Scripts/python.exe" scripts/check_hermes_context.py
```

The repair refuses unfamiliar source layouts. Restart Hermes after applying it.
Native test-only dependencies pytest 9.1.1 and pytest-asyncio 1.3.0 were installed
at the versions pinned by Hermes to run its isolated regression suites.

## Overnight work

Use bounded milestones and persist decisions, test results and next actions in
the task repository's `PROJECT_STATE.md`. The existing
[long-run rules](../HERMES_LONG_RUN_RULES.md) are suitable instructions for the agent.
For coding work that must resume after a stopped process, use the existing
[durable job controller](jobs.md), which checkpoints between epochs:

```powershell
python ninfer.py job init --repo C:/work/project --goal 'Fix the failing tests and document the result' --test-command '["python","-m","unittest"]'
python ninfer.py job resume --state C:/work/project/PROJECT_STATE.json --epochs 48 --max-turns 24 --timeout 600
```

Substitute the actual repository, goal and a meaningful test command. This is a
bounded run, up to roughly eight hours of agent epochs plus validation overhead;
it may stop sooner on completion, blockers or the job's limits. Keep the terminal
running. Resume the same state file after an interruption. No arbitrary task or
scheduled automation was started by this audit.

Windows AC sleep was already disabled, and NInfer uses `restart: unless-stopped`.
Docker must be running; a deliberately stopped container requires starting again.
Keep the PC on AC power and avoid competing GPU-heavy applications. Existing
approval settings remain in force, so a task needing approval can pause. Context
compression cannot guarantee autonomous task quality or protect against unlimited
single-message input, hardware failure, application updates or power loss.

## Use from another Hermes host alongside its default profile

Keep the other host's existing provider and models in its `default` Hermes profile. Create NInfer
as a separate profile and do not activate it globally:

```text
python ninfer.py configure-client autonomous --endpoint http://HOST_LAN_IP:8080/v1 --no-activate
hermes -p ninfer-autonomous chat
```

Use plain `hermes` or `hermes -p default` for the existing provider. Profile isolation means the
80K NInfer compression cap, local summary route, context length, conversation
database and memory do not apply to the default profile. If Desktop was
previously switched to NInfer, run `hermes profile use default` and restart it.
