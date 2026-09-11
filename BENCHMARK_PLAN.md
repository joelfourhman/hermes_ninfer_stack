# RTX 5090 benchmark plan

Judge accepted workload completion time first, then stability, TTFT, cache/context
behavior and decode throughput. Keep all failures. This is not a tokens/sec contest.
Current local observations are in [BENCHMARK_RESULTS.md](BENCHMARK_RESULTS.md).

## Preparation and controls

1. Save work and pause other Hermes/GPU clients. Record OS/driver, GPU, available
   host RAM, Docker configuration and competing load. Benchmarks sample entire
   host/device memory, so other workloads contaminate those measurements.
2. Run `python ninfer.py verify`. Each live benchmark also verifies the image,
   actual CLI arguments and model SHA-256 against configuration.
3. Keep driver, fixture version, thinking, output cap, turns, context bytes and
   session length constant within a comparison. Use at least three repeats and
   identical acceptance tests. Repeat in reverse order to assess drift.
4. Default runs use a startup-warmed, persistent server; later repetitions can
   share prefixes. For cold measurements restart before each sample and label
   that protocol separately. Model hashing/setup is outside workload timing.
5. Inspect per-run success, native acceptance/restore/cache counters and all
   samples. One second of resource sampling can miss short peaks. Do not claim
   multi-hour stability from short fixtures or derive speedups across models.

## Coding matrix (PowerShell or Command Prompt)

Use new output directory names for every invocation. Never overwrite evidence.

```text
python ninfer.py select-model --model stock
python ninfer.py spec mtp3
python ninfer.py profile balanced
python ninfer.py bench-agent coding --runs 3 --max-tokens 2048 --output benchmarks/A-stock-balanced
python ninfer.py profile coding
python ninfer.py bench-agent coding --runs 3 --max-tokens 2048 --output benchmarks/B-stock-coding

python ninfer.py prepare-model --model stock-dflash2
python ninfer.py select-model --model stock-dflash2
python ninfer.py profile coding
python ninfer.py spec mtp3
python ninfer.py bench-agent coding --runs 3 --max-tokens 2048 --output benchmarks/B2-companion-mtp3
python ninfer.py spec dflash2-7
python ninfer.py bench-agent coding --runs 3 --max-tokens 2048 --output benchmarks/C-companion-d7
python ninfer.py spec dflash2-11
python ninfer.py bench-agent coding --runs 3 --max-tokens 2048 --output benchmarks/D-companion-d11
python ninfer.py bench-compare benchmarks/B2-companion-mtp3/results.json benchmarks/C-companion-d7/results.json benchmarks/D-companion-d11/results.json
```

B2/C/D isolates decoder choice on the same file. A/B compares capacities. A versus
the pre-upgrade image is a separate experiment: preserve the old checkout/env
and locally tagged image, use `--baseline`, and keep artifact/profile identical.
If a candidate fails startup/OOM, retain the failure log and restored config;
do not silently reduce capacity and still label it the original candidate.

Repeat B2/C/D with `--driver hermes --timeout 600`. This includes actual Hermes
epoch execution and tests; the bounded driver excludes Desktop orchestration.
Do not rank these two different drivers together.

## Large context and two lanes

```text
python ninfer.py spec mtp3
python ninfer.py select-model --model stock
python ninfer.py profile research
python ninfer.py bench-agent research --context-kib 256 --runs 3 --max-tokens 2048 --output benchmarks/E-research
python ninfer.py bench-agent long-session --context-kib 256 --session-turns 16 --max-turns 60 --max-tokens 1024 --output benchmarks/E-growing
python ninfer.py bench-agent parallel --context-kib 64 --session-turns 6 --max-turns 30 --output benchmarks/E-parallel
```

Repeat research ingestion at64/256/512KiB and record actual prompt usage. These
arguments describe fixture bytes, not token counts. Stop after an out-of-context
failure and report the limit rather than counting it as a fast completion.
Repeat the same fitting fixture under balanced/coding/research to compare
128K/192K/240K ceilings. For native Hermes compression/resume, repeat long-session
with `--driver hermes`; note that its prompt/tool protocol differs from the
bounded summary/reset simulation. Inspect actual cache/host-state paths.

## Validation commands

```powershell
$env:NINFER_LIVE_TESTS = '1'
python -m unittest discover -s tests -p test_api_live.py -v
Remove-Item Env:NINFER_LIVE_TESTS
python ninfer.py observe
```

On Linux use `NINFER_LIVE_TESTS=1 python3 -m unittest discover -s tests -p test_api_live.py -v`.
CPU smoke: `python ninfer.py bench-agent coding --smoke`. Results are marked mock,
cannot support a performance claim and are rejected by the compare command.
