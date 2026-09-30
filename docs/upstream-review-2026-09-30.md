# September 30 NInfer upstream evaluation

**Decision: retain `594930e7b609efa4bcea3ae4f24cd9d66b5f224f`.** The 39 newer
commits through `d44ab58408aa389728cd8b1ee50179527e1f3e0d` contain useful
Qwen kernel work, but the newest commit stalled our long-context research fixture.
Its parent `4201b5d2d0f6afe235f4ed8e70cd753800770eca` improved DFlash2 and
large prefill while slowing both tested MTP3 coding profiles, including the
active uncensored/autonomous server. One global runtime pin serves every preset.

[Upstream comparison](https://github.com/Neroued/ninfer/compare/594930e7b609efa4bcea3ae4f24cd9d66b5f224f...d44ab58408aa389728cd8b1ee50179527e1f3e0d)
includes the reviewed history. It adds FP8/NVFP4 linear and causal-attention
kernels, recurrent-attention paths, a DFlash2 per-chunk prefill fix, and the
`NINFER_CUDA_SYNC` startup setting. The v3 upgrade converter, chat templates,
server option implementation, and authenticated model/context metadata contract
did not change. Both candidate source states built against the existing CUDA
13.1 Docker base and loaded the existing verified v3 artifacts without conversion.

Measurements used this Windows RTX 5090 (32,607 MiB), NVIDIA 617.14, the same
artifact bytes, preset settings and bounded fixture parameters. The server was
warmed by startup validation, each profile ran sequentially, and clocks were
not locked. All completed runs passed fixture acceptance. Wall times include
model output and tool calls; they are three-run medians except where noted.

| Workload | Current pin | Latest `d44ab58` | Parent `4201b5d` |
|---|---:|---:|---:|
| Uncensored/autonomous coding | 4.47 s | 4.69 s | 5.00 s |
| Stock/default coding | 3.71 s | 4.31 s | 3.89 s |
| DFlash2-11 coding | 3.52 s | 3.69 s | 2.88 s |
| Stock/240K research | 24.23 s | stopped after prolonged prefill | 5.13 s (see below) |

The research agent made six model requests on the current pin and two on
`4201b5d`. Its wall time therefore does not isolate engine speed. On the
comparable request with 84,685 fresh prefill tokens, native prefill
throughput was 4,962 versus 7,203 tokens/s, respectively. The parent produced
616 output tokens on that request versus 44 on the current pin. The parent also
passed a separate one-run research check in 18.68 s. The latest commit was
stopped after its first long request stayed in prefill for more than six minutes;
it did not produce a completed research run.

The parent's DFlash2-11 median native decode rate rose from about 192 to 240
tokens/s on the matched coding fixture. Its uncensored/autonomous MTP3 rate fell
from about 200 to 176 tokens/s with similar output lengths; stock/default fell
from about 190 to 175 tokens/s. The new default CUDA sync mode is `spin`. Retesting
the parent on uncensored/autonomous with `NINFER_CUDA_SYNC=blocking` gave a 4.98 s
median and did not recover the old decode rate. Thus the short-request
regression cannot be addressed by selecting the prior synchronization mode.

The local results are under ignored `benchmarks/sep30-*`; startup and comparison
logs are under ignored `out/sep30-*`. These small, fixed-order samples do not
establish a universal speed ranking or explain the exact kernel responsible for
the latest long-prefill slowdown. The final commit changes attention planning
and is strongly implicated by the parent/latest comparison, but no kernel-level
profile was run. Keeping the present pin protects the active model and the
stock default while upstream work continues.

Docker Desktop initially failed on inaccessible stale IPC sockets. With its
backend stopped, the socket-only directories were preserved as
`%LOCALAPPDATA%/Docker/run.before-ninfer-20260930`,
`%LOCALAPPDATA%/Docker/run.before-ninfer-20260930-retry`, and
`%LOCALAPPDATA%/docker-secrets-engine.before-ninfer-20260930`; Docker then
started normally. Engine images, volumes and settings were not reset. The
current pin and original uncensored/autonomous/MTP3 selection were restored.
The installed Hermes version had dropped the previously documented NInfer
context-overflow classifier/parser additions. The idempotent
`scripts/patch_hermes_context.py` restored them with backups; its focused check
passed, followed by all 11 live verification layers. The offline suite passed
75 tests with six live-only skips; lint, generated docs and repository checks
passed. No repository product code or runtime pin was changed in this evaluation.
