"""CLI extensions; keep heavyweight work behind explicit subcommands."""
from __future__ import annotations

import argparse
import json

from stack.config import RUNTIME_PROFILES, spec_values, validate_spec


def _helper():
    # The executable is __main__; importing it again would split patched/global state.
    import sys
    return sys.modules.get("ninfer") or sys.modules["__main__"]


def change_spec(args: argparse.Namespace) -> None:
    helper = _helper()
    if not helper.ENV_FILE.exists():
        raise ValueError("Run setup before selecting speculative decoding")
    replacements = spec_values(args.mode, args.draft_tokens)
    values = dict(helper.read_env(), **replacements)
    validate_spec(values)  # Capability failure must not mutate the environment.
    backup = helper.replace_env_values(replacements)
    try:
        helper.validate_env()
        helper.start_ninfer(helper.read_env())
    except (helper.StackError, ValueError):
        if backup:
            helper.atomic_write(helper.ENV_FILE, backup.read_text(encoding="utf-8"))
            helper.start_ninfer(helper.read_env())
        raise
    print(f"ACTIVE: {replacements['NINFER_SPEC_BACKEND']} with {replacements['NINFER_DRAFT_TOKENS']} draft tokens")


def show_profiles(_: argparse.Namespace) -> None:
    from stack.documentation import profile_table
    print(profile_table())
    print("\nProfiles are memory/workload candidates; balanced + MTP3 remains the default.")


def docs(args: argparse.Namespace) -> None:
    from stack.documentation import generate
    generate(args.check)
    print("Generated configuration documentation is current.")


def register_commands(sub) -> None:
    profile = sub.add_parser("profile", help="select a workload profile and synchronize Hermes")
    profile.add_argument("profile", choices=tuple(RUNTIME_PROFILES))
    profile.set_defaults(func=lambda args: _helper().select_runtime(args))
    sub.add_parser("profiles", help="show profile capacities").set_defaults(func=show_profiles)
    spec = sub.add_parser("spec", help="safely switch MTP/DFlash2 on a compatible artifact")
    spec.add_argument("mode", help="mtp3, dflash2-7, dflash2-11, mtp or dflash2")
    spec.add_argument("--draft-tokens", type=int)
    spec.set_defaults(func=change_spec)
    doc = sub.add_parser("docs", help="generate/check mechanical configuration documentation")
    doc.add_argument("--check", action="store_true")
    doc.set_defaults(func=docs)
    # Subsequent modules register their own bounded command surface here.
