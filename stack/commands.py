"""CLI extensions; keep heavyweight work behind explicit subcommands."""

from __future__ import annotations

import argparse
import getpass
import os

from stack.config import (
    DEPLOYMENT_PRESETS,
    RUNTIME_PROFILES,
    runtime_env_values,
    spec_values,
    validate_spec,
)


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


def show_presets(_: argparse.Namespace) -> None:
    print("| Preset | Model | Runtime | Decoder | Purpose |")
    print("|---|---|---|---|---|")
    for preset in DEPLOYMENT_PRESETS.values():
        print(
            f"| {preset.key} | {preset.model} | {preset.runtime} | "
            f"{preset.spec} | {preset.description} |"
        )


def use_preset(args: argparse.Namespace) -> None:
    helper = _helper()
    if not helper.ENV_FILE.exists():
        raise ValueError("Run setup before selecting a deployment preset")
    preset = DEPLOYMENT_PRESETS[args.preset]
    model = helper.model_profile(preset.model)
    runtime = helper.runtime_profile(preset.runtime)
    print(f"Applying {preset.key}: model={model.key}, runtime={runtime.key}, decoder={preset.spec}")
    helper.check_setup_prerequisites(model)
    if not helper.prepare_model(argparse.Namespace(model=model.key, yes=args.yes)):
        return

    previous = helper.read_env()
    replacements = {
        "NINFER_MODEL_PROFILE": model.key,
        "NINFER_MODEL_FILE": model.filename,
        "NINFER_MODEL_ID": "qwen-local",
        **runtime_env_values(runtime),
        **spec_values(preset.spec),
    }
    validate_spec(dict(previous, **replacements))
    resolved = helper.native_hermes_command()
    env_backup = helper.replace_env_values(replacements)
    try:
        helper.validate_env()
        helper.start_ninfer(helper.read_env())
        if resolved is not None:
            profile_name = helper.configure_hermes_preset_profile(
                *resolved, preset.key, helper.read_env()
            )
            print(
                f"Hermes profile {profile_name} is active too. "
                "Restart Hermes Desktop to load this preset."
            )
        else:
            print("Hermes was not found; the NInfer preset is active.")
    except (helper.StackError, ValueError, OSError) as selected_error:
        if env_backup is not None:
            helper.atomic_write(helper.ENV_FILE, env_backup.read_text(encoding="utf-8"))
        try:
            helper.start_ninfer(previous)
        except helper.StackError as rollback_error:
            raise helper.StackError(
                "The preset failed and its previous configuration was restored, "
                "but the former service also needs attention. Run 'python ninfer.py logs'."
            ) from rollback_error
        raise helper.StackError(
            f"The {preset.key} preset failed its live test. The previous model, "
            "runtime, decoder and Hermes configuration were restored."
        ) from selected_error
    print(f"ACTIVE: {preset.key} ({model.key} / {runtime.key} / {preset.spec})")


def configure_client(args: argparse.Namespace) -> None:
    """Configure a native Hermes profile on a LAN client without a local NInfer checkout."""
    helper = _helper()
    endpoint = helper.normalize_ninfer_client_endpoint(args.endpoint)
    key = os.environ.get(args.key_env, "").strip()
    if not key:
        key = getpass.getpass("NInfer LAN API key: ").strip()
    if not key:
        raise ValueError(f"Set {args.key_env} or enter the NInfer LAN API key")
    resolved = helper.native_hermes_command()
    if resolved is None:
        raise ValueError("Hermes Desktop is not installed on this computer")

    preset = DEPLOYMENT_PRESETS[args.preset]
    model = helper.model_profile(preset.model)
    runtime = helper.runtime_profile(preset.runtime)
    values = {
        "NINFER_API_KEY": key,
        "NINFER_MODEL_ID": "qwen-local",
        "NINFER_MODEL_PROFILE": model.key,
        "NINFER_MODEL_FILE": model.filename,
        **runtime_env_values(runtime),
        **spec_values(preset.spec),
    }
    helper.require_ninfer_endpoint(endpoint, key, values["NINFER_MODEL_ID"])
    profile_name = helper.configure_hermes_preset_profile(
        *resolved,
        preset.key,
        values,
        endpoint=endpoint,
        api_key=key,
        activate=not args.no_activate,
    )
    state = "configured and activated" if not args.no_activate else "configured"
    print(f"Hermes profile {profile_name} is {state} for {endpoint}.")
    print("Restart Hermes Desktop to load it.")


def docs(args: argparse.Namespace) -> None:
    from stack.documentation import generate

    generate(args.check)
    print("Generated configuration documentation is current.")


def register_commands(sub) -> None:
    use = sub.add_parser(
        "use", help="apply a complete model/runtime/decoder preset with one restart"
    )
    use.add_argument("preset", choices=tuple(DEPLOYMENT_PRESETS))
    use.add_argument(
        "--yes", action="store_true", help="skip confirmation if its model must download"
    )
    use.set_defaults(func=use_preset)
    client = sub.add_parser(
        "configure-client",
        help="create a native Hermes profile for this NInfer host or a trusted LAN host",
    )
    client.add_argument("preset", choices=tuple(DEPLOYMENT_PRESETS))
    client.add_argument(
        "--endpoint",
        required=True,
        help="NInfer URL, for example http://192.168.1.20:8080/v1",
    )
    client.add_argument(
        "--key-env",
        default="NINFER_API_KEY",
        help="environment variable containing the API key; securely prompts when unset",
    )
    client.add_argument(
        "--no-activate",
        action="store_true",
        help="create/update without changing the active profile",
    )
    client.set_defaults(func=configure_client)
    sub.add_parser("presets", help="show one-command deployment presets").set_defaults(
        func=show_presets
    )
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
