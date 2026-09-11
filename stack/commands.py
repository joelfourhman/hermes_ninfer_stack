"""CLI extensions; keep heavyweight work behind explicit subcommands."""

from __future__ import annotations

import argparse

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
    print(
        f"ACTIVE: {replacements['NINFER_SPEC_BACKEND']} with {replacements['NINFER_DRAFT_TOKENS']} draft tokens"
    )


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
    from stack.bench_agent import benchmark, compare

    bench = sub.add_parser(
        "bench-agent", help="run repeatable coding/research/session agent workloads"
    )
    bench.add_argument("workload", choices=("coding", "research", "long-session", "parallel"))
    bench.add_argument("--driver", choices=("bounded-agent", "hermes"), default="bounded-agent")
    bench.add_argument("--runs", type=int, default=3)
    bench.add_argument("--max-turns", type=int, default=24)
    bench.add_argument("--max-tokens", type=int, default=2048)
    bench.add_argument(
        "--context-kib",
        type=int,
        default=64,
        help="fixture text KiB; actual token counts are recorded",
    )
    bench.add_argument("--session-turns", type=int, default=12)
    bench.add_argument("--timeout", type=float, default=600)
    bench.add_argument("--thinking", action="store_true")
    bench.add_argument(
        "--baseline",
        action="store_true",
        help="measure original image with verified baseline revision",
    )
    bench.add_argument(
        "--smoke",
        action="store_true",
        help="offline coding fixture smoke; no performance claims",
    )
    bench.add_argument("--output")
    bench.set_defaults(func=benchmark)
    comparison = sub.add_parser("bench-compare", help="compare compatible agent result JSON files")
    comparison.add_argument("results", nargs="+")
    comparison.set_defaults(func=compare)
    from stack.metrics import observe

    metrics = sub.add_parser(
        "observe", help="snapshot hardware and native NInfer structured counters"
    )
    metrics.add_argument("--lines", type=int, default=300)
    metrics.add_argument("--output")
    metrics.add_argument("--state", help="optional PROJECT_STATE.json for active epoch/milestone")
    metrics.add_argument("--baseline", action="store_true")
    metrics.set_defaults(func=observe)
    from stack.jobs import register_jobs

    register_jobs(sub)
    worker = sub.add_parser(
        "worker-build", help="build an optional disposable-workspace toolchain image"
    )
    worker.set_defaults(
        func=lambda _: _helper().run(
            [
                _helper().docker_executable() or "docker",
                "build",
                "-t",
                "hermes-agent-worker:local",
                str(_helper().ROOT / "worker"),
            ]
        )
    )
