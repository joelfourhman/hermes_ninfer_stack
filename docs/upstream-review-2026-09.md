# September 2026 upstream review

Selected NInfer `594930e7b609efa4bcea3ae4f24cd9d66b5f224f` (September 23),
advancing from `d49296868dcc17bd478ec185f0d3a801bcc0bf56`. This is an audited
master snapshot, not a tagged stable release. Review used the fetched source and
the complete intervening history of 44 commits. The
[upstream comparison](https://github.com/Neroued/ninfer/compare/d49296868dcc17bd478ec185f0d3a801bcc0bf56...594930e7b609efa4bcea3ae4f24cd9d66b5f224f)
contains the reviewed changes.

Relevant changes:

- `04350ba` / `4cde7ad` / `168fdd8`: v3 artifact loading, component bindings and
  architecture-based execution. This breaks v2 loading; the runtime and models
  must migrate together. The stack upgrades its pinned original sources rather
  than silently substituting a different quantization recipe.
- `98dada0` / `8eaed53`: Jinja chat templates and literal control-token handling.
  Converted artifacts embed the upstream-maintained Qwen3.8 template. Hermes
  retains native tool/reasoning history; no custom prompt wrapper is added.
- `c4ae8a9`: restores accurate SiLU in NVFP4 SwiGLU after `05507ab` introduced an
  approximation. The selected pin includes the corrective commit.
- `594930e`, `9e163ee`, Q4/Q5 linear dispatch work and NVFP4 TMA tuning improve
  specific Qwen execution shapes. These are automatic runtime routes. Upstream
  microbenchmarks are not treated as measured Hermes speedups.
- `4c0fe48`: blocking CUDA synchronization replaces CPU spin waiting.
- `f9c4a04`: new state-cache working-set benchmarks for retained agent histories.
- Native structured request logs advance to schema v21. The stack retains the
  native records, including unknown fields, without rewriting their semantics.

The serving contract already includes authenticated `/v1/models` and
`/v1/models/{id}` with `max_model_len`. The previous stack ignored that capacity
on network setup and hid every artifact behind `qwen-local`. The new integration
discovers the live ID and capacity, clamps compression, and names served models
by artifact profile and context. `connect` refreshes this metadata for each CLI
launch. Saved Desktop clients need a refresh/restart following a server switch.
The API's context metadata is a per-request ceiling; usage is per conversation
request, never one global context count shared by all network users.

Migration is deterministic across Windows/Linux: normalize converter/template
text to LF, derive only the container UUID deterministically, and use upstream's
weight-preserving converter. Both input and output hashes are pinned. All original
files remain available for rollback with the former source/manifest. Local
validation checked every tensor's shape and size, sampled its start/middle/end
bytes, and checked the complete replacement template on all three real artifacts.

Performance policy remains FP8 KV, 1024-token prefill, retained thinking and the
optimized proposal head. MTP3 is the conservative general/long-context choice;
coding uses its explicit DFlash2 companion and a smaller KV allocation. A client
profile cannot create additional server model instances or promise two full-size
contexts within a shared KV pool. See [measurements](../BENCHMARK_RESULTS.md) for
qualification and limitations.

On this Windows host, Docker initially failed on an inaccessible stale IPC
socket. The stopped backend's `AppData/Local/Docker/run` directory was preserved
as `run.before-ninfer-20260923`, allowing Docker to recreate its runtime sockets.
Containers, volumes, images and settings were preserved. The new CUDA image built
successfully using upstream's Dockerfile and the existing CUDA 13.1.2 base.

Final validation passed all 11 live layers, including authenticated discovery,
direct generation and native Hermes generation. Six GPU API tests additionally
covered LAN discovery, tools, reasoning, stale IDs and prefix-cache reuse. All
seven presets passed their bounded fixtures; an actual Hermes coding task and
concurrent two-lane work passed. The offline suite passed 75 tests with six
live-only tests skipped. These checks do not establish multi-hour stability.

The original uncensored/autonomous/MTP3 selection, key and LAN binding are
restored. Local native Hermes is synchronized, and the isolated LAN profile was
refreshed without changing profile activation. Profile setup now handles Hermes
deletion tombstones through its official create command and preserves retained
profile files if creation fails. Repeating startup with a matching source/CUDA
image preserves the resident container and its caches. Restart Hermes Desktop
to load the updated model identity and context settings.
