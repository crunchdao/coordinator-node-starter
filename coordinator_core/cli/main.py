from __future__ import annotations

import argparse
from pathlib import Path

from coordinator_core.cli.demo_cmd import run_demo
from coordinator_core.cli.doctor_cmd import run_doctor
from coordinator_core.cli.init_service import run_init
from coordinator_core.cli.preflight_cmd import parse_ports, run_preflight


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coordinator", description="Coordinator workspace CLI")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="Initialize a coordinator folder")
    init_parser.add_argument("name", nargs="?", help="Challenge slug, e.g. btc-trader (default: current directory name)")
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing target workspace if present",
    )
    init_parser.add_argument(
        "--output",
        default=".",
        help="Output root directory where <name>/ will be created (default: current directory).",
    )

    doctor_parser = subparsers.add_parser("doctor", help="Validate init spec wiring")
    doctor_parser.add_argument("name", nargs="?", help="Optional challenge slug for cross-check")
    doctor_parser.add_argument("--spec", help="Path to init spec JSON file")
    doctor_parser.add_argument("--pack", help="Optional pack override for spec validation")

    preflight_parser = subparsers.add_parser("preflight", help="Check local prerequisites")
    preflight_parser.add_argument(
        "--ports",
        default="3000,5432,8000,9091",
        help="Comma-separated ports that must be free (default: 3000,5432,8000,9091)",
    )

    demo_parser = subparsers.add_parser("demo", help="Render a default btc-up demo workspace")
    demo_parser.add_argument(
        "--output",
        default=".",
        help="Output root directory where btc-up/ will be created (default: current directory).",
    )
    demo_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing btc-up workspace if present",
    )
    demo_parser.add_argument(
        "--webapp-path",
        help="Optional local coordinator-webapp path for report-ui build context",
    )
    demo_parser.add_argument(
        "--start",
        action="store_true",
        help="Start the stack immediately after scaffolding",
    )

    return parser


def _slugify_dirname(path: Path) -> str:
    """Convert a directory name to a valid challenge slug."""
    import re
    name = path.resolve().name.lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    name = name.strip("-")
    return name or "my-crunch"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        name = args.name or _slugify_dirname(Path(args.output))
        return run_init(
            name=name,
            project_root=Path(args.output).resolve(),
            force=args.force,
            spec_path=None,
            answers_path=None,
            pack_name="realtime",
            list_packs=False,
        )
    if args.command == "doctor":
        spec_path = Path(args.spec) if args.spec else None
        return run_doctor(name=args.name, spec_path=spec_path, pack_name=args.pack)
    if args.command == "preflight":
        try:
            ports = parse_ports(args.ports)
        except ValueError as exc:
            print(f"preflight failed: {exc}")
            return 1
        return run_preflight(ports=ports)
    if args.command == "demo":
        webapp_path = Path(args.webapp_path) if args.webapp_path else None
        return run_demo(
            output_root=Path(args.output).resolve(),
            force=args.force,
            webapp_path=webapp_path,
            start=args.start,
        )

    parser.print_help()
    return 1


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
