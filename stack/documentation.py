"""Generate mechanical documentation and env pins; --check detects drift."""

from __future__ import annotations

from pathlib import Path
from stack.config import MANIFEST, MODEL_PROFILES, RUNTIME_PROFILES, NINFER_COMMIT

ROOT = Path(__file__).resolve().parents[1]


def profile_table() -> str:
    rows = [
        "| Profile | Context tokens | Shared KV tokens | Lanes | Device / host cache slots | Host KV MiB | Compression tokens | Turns |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for p in RUNTIME_PROFILES.values():
        rows.append(
            f"| `{p.key}` | {p.context_length:,} | {p.kv_capacity:,} | {p.max_concurrency} | {p.device_state_slots} / {p.host_state_slots} | {p.host_kv_mib:,} | {p.compression_threshold_tokens:,} | {p.max_turns} |"
        )
    return "\n".join(rows)


def generated_reference() -> str:
    rows = [
        "# Generated configuration reference",
        "",
        "Generated from `stack/manifest.json`; edit the manifest, then run `python ninfer.py docs`.",
        "",
        f"NInfer source/image revision: `{NINFER_COMMIT}`.",
        f"CUDA image base: `{MANIFEST['ninfer']['cuda_base']}`.",
        "",
        profile_table(),
        "",
        "All profiles use FP8 KV, prefill chunk 1024, preserved thinking and optimized draft heads.",
        "Speculation is independent of workload: default MTP3; DFlash2 requires explicit stock-dflash2 selection.",
        "Candidate profiles require target-GPU memory and workload validation. A context ceiling is not a speed guarantee.",
        "",
    ]
    for m in MODEL_PROFILES.values():
        rows += [
            f"## {m.key}",
            "",
            f"{m.label}. {m.quantization}.",
            "",
            f"- Repository: `{m.repository}`",
            f"- Revision: `{m.revision}`",
            f"- Remote artifact: `{m.source_filename}`",
            f"- Local artifact: `{m.filename}`",
            f"- Bytes: {m.expected_bytes}",
            f"- SHA-256: `{m.sha256}`",
            f"- Speculative capabilities: {', '.join(m.capabilities)}",
            "",
        ]
    return "\n".join(rows)


def generate(check: bool = False) -> None:
    readme = ROOT / "README.md"
    content = readme.read_text(encoding="utf-8")
    begin, end = "<!-- BEGIN GENERATED PROFILES -->", "<!-- END GENERATED PROFILES -->"
    if content.count(begin) != 1 or content.count(end) != 1:
        raise ValueError("README must contain exactly one generated profile block")
    before, block = content.split(begin)
    _, after = block.split(end)
    expected_readme = before + begin + "\n\n" + profile_table() + "\n\n" + end + after
    if check and content != expected_readme:
        raise ValueError("README profiles are stale; run python ninfer.py docs")
    if not check:
        readme.write_text(expected_readme, encoding="utf-8", newline="\n")
    target = ROOT / "docs/generated-config.md"
    expected = generated_reference()
    if check:
        if not target.exists() or target.read_text(encoding="utf-8") != expected:
            raise ValueError(
                "Generated configuration documentation is stale; run python ninfer.py docs"
            )
    else:
        target.write_text(expected, encoding="utf-8", newline="\n")
    # This env value is a generated projection, never a second authority.
    env = ROOT / ".env.example"
    text = env.read_text(encoding="utf-8")
    marker = "NINFER_SOURCE_REVISION="
    lines = text.splitlines()
    existing = next((line for line in lines if line.startswith(marker)), None)
    wanted = marker + NINFER_COMMIT
    if check and existing != wanted:
        raise ValueError(".env.example source revision is stale; run python ninfer.py docs")
    if not check:
        if existing:
            text = text.replace(existing, wanted)
        else:
            text += "\n# Generated from stack/manifest.json.\n" + wanted + "\n"
        env.write_text(text, encoding="utf-8", newline="\n")
