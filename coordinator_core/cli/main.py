from __future__ import annotations

import argparse
from pathlib import Path

from coordinator_core.cli.doctor_cmd import run_doctor
from coordinator_core.cli.init_cmd import run_init


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coordinator", description="Coordinator workspace CLI")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="Scaffold a thin challenge workspace")
    init_parser.add_argument("name", nargs="?", help="Challenge slug, e.g. btc-trader")
    init_parser.add_argument(
        "--spec",
        help="Path to init spec JSON file. Can define name/callables/schedule/env defaults.",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing target workspace if present",
    )
    init_parser.add_argument(
        "--preset",
        help="Preset name (baseline, realtime, in-sample, out-of-sample). Overrides spec preset.",
    )
    init_parser.add_argument(
        "--list-presets",
        action="store_true",
        help="List available built-in presets and exit.",
    )
    init_parser.add_argument(
        "--output",
        default=".",
        help="Output root directory where <name>/ will be created (default: current directory).",
    )

    doctor_parser = subparsers.add_parser("doctor", help="Validate init spec wiring")
    doctor_parser.add_argument("name", nargs="?", help="Optional challenge slug for cross-check")
    doctor_parser.add_argument("--spec", help="Path to init spec JSON file")
    doctor_parser.add_argument("--preset", help="Optional preset override for spec validation")
    subparsers.add_parser("dev", help="Run local dev lifecycle (coming in PR3)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        spec_path = Path(args.spec) if args.spec else None
        return run_init(
            name=args.name,
            project_root=Path(args.output).resolve(),
            force=args.force,
            spec_path=spec_path,
            preset_name=args.preset,
            list_presets=args.list_presets,
        )
    if args.command == "doctor":
        spec_path = Path(args.spec) if args.spec else None
        return run_doctor(name=args.name, spec_path=spec_path, preset_name=args.preset)
    if args.command == "dev":
        print("coordinator dev is planned for PR3")
        return 0

    parser.print_help()
    return 1


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
