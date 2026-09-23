# Generated configuration reference

Generated from `stack/manifest.json`; edit the manifest, then run `python ninfer.py docs`.

NInfer source/image revision: `594930e7b609efa4bcea3ae4f24cd9d66b5f224f`.
CUDA image base: `docker.io/nvidia/cuda:13.1.2-runtime-ubuntu24.04`.

| Profile | Context tokens | Shared KV tokens | Lanes | Device / host cache slots | Host KV MiB | Compression tokens | Turns |
|---|---:|---:|---:|---:|---:|---:|---:|
| `balanced` | 131,072 | 196,608 | 2 | 2 / 8 | 8,192 | 55,000 | 100000 |
| `single-session` | 131,072 | 131,072 | 1 | 1 / 4 | 4,096 | 55,000 | 100000 |
| `max-context` | 240,000 | 240,000 | 2 | 2 / 8 | 8,192 | 100,000 | 100000 |
| `interactive` | 131,072 | 196,608 | 2 | 2 / 8 | 8,192 | 55,000 | 100000 |
| `coding` | 196,608 | 196,608 | 2 | 2 / 8 | 8,192 | 80,000 | 100000 |
| `research` | 240,000 | 240,000 | 2 | 2 / 8 | 8,192 | 100,000 | 100000 |
| `autonomous` | 196,608 | 196,608 | 2 | 2 / 8 | 8,192 | 80,000 | 100000 |
| `low-vram` | 65,536 | 65,536 | 1 | 1 / 2 | 2,048 | 24,000 | 100000 |

## One-command presets

| Preset | Model | Runtime | Decoder | Purpose |
|---|---|---|---|---|
| `default` | `stock` | `balanced` | `mtp3` | Recommended stock model, balanced context and MTP3 fallback |
| `coding` | `stock-dflash2` | `coding` | `dflash2-7` | Conservative DFlash2 coding setup with a 7-token draft window |
| `coding-fast` | `stock-dflash2` | `coding` | `dflash2-11` | DFlash2-11, faster in the latest short coding sample; use on an otherwise idle RTX 5090 |
| `research` | `stock` | `research` | `mtp3` | 240K stock/MTP3 ceiling for repository and document work |
| `autonomous` | `stock` | `autonomous` | `mtp3` | Stock/MTP3 with conservative context headroom for long-running goals |
| `low-vram` | `stock` | `low-vram` | `mtp3` | 64K stock/MTP3 profile with a smaller cache footprint |
| `uncensored` | `uncensored` | `max-context` | `mtp3` | Original user selection: uncensored, 240K and MTP3 |

All profiles use FP8 KV, prefill chunk 1024, preserved thinking and optimized draft heads.
All presets configure Hermes goals for up to 100,000 turns.
Speculation is independent of workload: default MTP3; DFlash2 requires explicit stock-dflash2 selection.
Candidate profiles require target-GPU memory and workload validation. A context ceiling is not a speed guarantee.

## stock

Stock Qwen3.8-27B NVFP4. NInfer NVFP4 (v3 framing, original weight bytes).

- Repository: `neroued/Qwen3.8-27B-nvfp4-NInfer`
- Revision: `204e3d92c30d9d05f3300d2f52e443ad1edf6ddf`
- Remote artifact: `qwen3_8_27b_nvfp4.ninfer`
- Local artifact: `qwen3_8_27b_nvfp4.v3.ninfer`
- Bytes: 21492938224
- SHA-256: `05e5674ee561d443acae167e4e9b3b06cc67ce429c341beacbfacb057391e1ca`
- Speculative capabilities: mtp

Derived reproducibly with the pinned upstream v3 upgrader; original weights retained.
- Published v2 source: `qwen3_8_27b_nvfp4.ninfer`
- Source bytes: 21492695040
- Source SHA-256: `bb3360522a06e136e0367f5703414d26272b7285c8a6ab6194135c17dbd81b32`

## uncensored

Qwen3.8-27B Uncensored. NInfer qwen3_8_27b-v1 groupwise-int (v3 framing, original weight bytes).

- Repository: `DogOnKeyboard/Qwen3.8-27B-Uncensored-NInfer`
- Revision: `1e15b5919b796bcd96621f13572ad92b5555b641`
- Remote artifact: `qwen3_8_27b_uncensored.ninfer`
- Local artifact: `qwen3_8_27b_uncensored.v3.ninfer`
- Bytes: 18210749936
- SHA-256: `c7eeed95e359bdd2da22cc685525047c32a78ca7c0b00798243a3a40b2b768e7`
- Speculative capabilities: mtp

Derived reproducibly with the pinned upstream v3 upgrader; original weights retained.
- Published v2 source: `qwen3_8_27b_uncensored.ninfer`
- Source bytes: 18210531328
- Source SHA-256: `714565ed29db4415322e9bc13a3464dc1fd8fcc911234740a79af67934e49969`

## stock-dflash2

Stock Qwen3.8 NVFP4 with DFlash2 (opt-in). NInfer NVFP4 (v3 framing, original weight bytes).

- Repository: `neroued/Qwen3.8-27B-nvfp4-NInfer`
- Revision: `11dbbbbbc33db198afe2f02c9232c771ff7031be`
- Remote artifact: `qwen3_8_27b_nvfp4.ninfer`
- Local artifact: `qwen3_8_27b_nvfp4_dflash2.v3.ninfer`
- Bytes: 23719759856
- SHA-256: `579c0f33d14513c9f0b58b58fb692c00ec4c8922523120a8b465a29de83361c5`
- Speculative capabilities: mtp, dflash2

Derived reproducibly with the pinned upstream v3 upgrader; original weights retained.
- Published v2 source: `qwen3_8_27b_nvfp4_dflash2.ninfer`
- Source bytes: 23719496192
- Source SHA-256: `552c374c685dce302603b95fbe940fb04243c0cd44c083efc644ad3d980d462c`
