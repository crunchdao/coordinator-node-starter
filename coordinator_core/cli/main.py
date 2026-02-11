from __future__ import annotations

import argparse
from pathlib import Path

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

    subparsers.add_parser("doctor", help="Validate workspace wiring (coming in PR2)")
    subparsers.add_parser("dev", help="Run local dev lifecycle (coming in PR3)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        spec_path = Path(args.spec) if args.spec else None
        return run_init(name=args.name, project_root=Path.cwd(), force=args.force, spec_path=spec_path)
    if args.command == "doctor":
        print("coordinator doctor is planned for PR2")
        return 0
    if args.command == "dev":
        print("coordinator dev is planned for PR3")
        return 0

    parser.print_help()
    return 1


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
