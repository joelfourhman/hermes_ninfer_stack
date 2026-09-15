#!/usr/bin/env python3
"""Apply the narrowly scoped NInfer overflow compatibility fix to native Hermes.

Idempotent, backs up each original, and refuses unfamiliar source layouts.
Run check_hermes_context.py with the Hermes interpreter after Hermes updates.
"""
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ninfer


def main():
    source = ninfer.hermes_home() / "hermes-agent" / "agent"
    edits = [
        ("error_classifier.py", '    "slot context", "n_ctx_slot",\n',
         '    "exceeding engine max_context", "prepared prompt exceeds engine max_context",\n'),
        ("model_metadata.py", "    patterns = (\n        r'max_model_len",
         "        r'engine max_context\\s+(\\d{4,})',  # NInfer reports the actual engine window.\n"),
    ]
    pending = []
    for name, anchor, addition in edits:
        path = source / name
        original = path.read_text(encoding="utf-8")
        if addition in original:
            print(f"Already fixed: {name}")
            continue
        if original.count(anchor) != 1:
            raise RuntimeError(f"Unfamiliar Hermes source in {path}; inspect before patching")
        if name == "model_metadata.py":
            updated = original.replace(anchor, "    patterns = (\n" + addition + "        r'max_model_len")
        else:
            updated = original.replace(anchor, anchor + addition)
        compile(updated, str(path), "exec")
        pending.append((path, updated))
    for path, updated in pending:
        backup = path.with_name(path.name + f".ninfer-backup-{time.time_ns()}")
        backup.write_bytes(path.read_bytes())
        ninfer.atomic_write(path, updated)
        print(f"Fixed: {path}; backup: {backup.name}")


if __name__ == "__main__":
    main()
