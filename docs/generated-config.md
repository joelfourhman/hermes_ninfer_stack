# Generated configuration reference

Generated from `stack/manifest.json`; edit the manifest, then run `python ninfer.py docs`.

NInfer source/image revision: `d49296868dcc17bd478ec185f0d3a801bcc0bf56`.
CUDA image base: `docker.io/nvidia/cuda:13.1.2-runtime-ubuntu24.04`.

| Profile | Context tokens | Shared KV tokens | Lanes | Device / host cache slots | Host KV MiB | Compression tokens | Turns |
|---|---:|---:|---:|---:|---:|---:|---:|
| `balanced` | 131,072 | 196,608 | 2 | 2 / 8 | 8,192 | 90,000 | 40 |
| `single-session` | 131,072 | 131,072 | 1 | 1 / 4 | 4,096 | 100,000 | 40 |
| `max-context` | 240,000 | 240,000 | 2 | 2 / 8 | 8,192 | 200,000 | 40 |
| `interactive` | 131,072 | 196,608 | 2 | 2 / 8 | 8,192 | 90,000 | 40 |
| `coding` | 196,608 | 196,608 | 2 | 2 / 8 | 8,192 | 150,000 | 40 |
| `research` | 240,000 | 240,000 | 2 | 2 / 8 | 8,192 | 200,000 | 40 |
| `autonomous` | 196,608 | 196,608 | 2 | 2 / 8 | 8,192 | 150,000 | 24 |
| `low-vram` | 65,536 | 65,536 | 1 | 1 / 2 | 2,048 | 48,000 | 40 |

## One-command presets

| Preset | Model | Runtime | Decoder | Purpose |
|---|---|---|---|---|
| `default` | `stock` | `balanced` | `mtp3` | Recommended stock model, balanced context and MTP3 fallback |
| `coding` | `stock-dflash2` | `coding` | `dflash2-7` | Measured DFlash2 coding setup with the best TTFT |
| `coding-fast` | `stock-dflash2` | `coding` | `dflash2-11` | DFlash2-11; use while the RTX 5090 is otherwise idle |
| `research` | `stock` | `research` | `mtp3` | 240K stock/MTP3 path qualified for growing sessions |
| `low-vram` | `stock` | `low-vram` | `mtp3` | 64K stock/MTP3 profile with a smaller cache footprint |
| `uncensored` | `uncensored` | `max-context` | `mtp3` | Original user selection: uncensored, 240K and MTP3 |

All profiles use FP8 KV, prefill chunk 1024, preserved thinking and optimized draft heads.
All presets configure Hermes goals for up to 100,000 turns.
Speculation is independent of workload: default MTP3; DFlash2 requires explicit stock-dflash2 selection.
Candidate profiles require target-GPU memory and workload validation. A context ceiling is not a speed guarantee.

## stock

Stock Qwen3.8-27B NVFP4. NInfer NVFP4.

- Repository: `neroued/Qwen3.8-27B-nvfp4-NInfer`
- Revision: `204e3d92c30d9d05f3300d2f52e443ad1edf6ddf`
- Remote artifact: `qwen3_8_27b_nvfp4.ninfer`
- Local artifact: `qwen3_8_27b_nvfp4.ninfer`
- Bytes: 21492695040
- SHA-256: `bb3360522a06e136e0367f5703414d26272b7285c8a6ab6194135c17dbd81b32`
- Speculative capabilities: mtp

## uncensored

Qwen3.8-27B Uncensored. NInfer qwen3_8_27b-v1 groupwise-int.

- Repository: `DogOnKeyboard/Qwen3.8-27B-Uncensored-NInfer`
- Revision: `1e15b5919b796bcd96621f13572ad92b5555b641`
- Remote artifact: `qwen3_8_27b_uncensored.ninfer`
- Local artifact: `qwen3_8_27b_uncensored.ninfer`
- Bytes: 18210531328
- SHA-256: `714565ed29db4415322e9bc13a3464dc1fd8fcc911234740a79af67934e49969`
- Speculative capabilities: mtp

## stock-dflash2

Stock Qwen3.8 NVFP4 v2 with DFlash2 (opt-in). NInfer NVFP4.

- Repository: `neroued/Qwen3.8-27B-nvfp4-NInfer`
- Revision: `11dbbbbbc33db198afe2f02c9232c771ff7031be`
- Remote artifact: `qwen3_8_27b_nvfp4.ninfer`
- Local artifact: `qwen3_8_27b_nvfp4_dflash2.ninfer`
- Bytes: 23719496192
- SHA-256: `552c374c685dce302603b95fbe940fb04243c0cd44c083efc644ad3d980d462c`
- Speculative capabilities: mtp, dflash2
