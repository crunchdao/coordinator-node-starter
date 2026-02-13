from __future__ import annotations

import argparse
import re
from pathlib import Path

from coordinator_cli.commands.init_service import run_init


def _slugify_dirname(path: Path) -> str:
    name = path.resolve().name.lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    name = name.strip("-")
    return name or "my-crunch"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coordinator", description="Coordinator workspace CLI")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="Initialize a coordinator folder")
    init_parser.add_argument("name", nargs="?", help="Challenge slug, e.g. btc-trader (default: current directory name)")
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing target workspace if present")
    init_parser.add_argument("--output", default=".", help="Output root directory (default: current directory)")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        name = args.name or _slugify_dirname(Path(args.output))
        return run_init(
            name=name,
            project_root=Path(args.output).resolve(),
            force=args.force,
        )

    parser.print_help()
    return 1


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
