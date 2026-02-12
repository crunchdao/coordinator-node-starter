from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_TOKEN_PATTERN = re.compile(r"\[\[([a-zA-Z_][a-zA-Z0-9_]*)\]\]")
_TEMPLATES_ROOT = Path(__file__).resolve().parent.parent / "scaffold" / "templates"


def _render_tokens(template: str, values: dict[str, Any]) -> str:
    missing: set[str] = set()

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            missing.add(key)
            return match.group(0)
        return str(values[key])

    rendered = _TOKEN_PATTERN.sub(_replace, template)
    if missing:
        ordered = ", ".join(sorted(missing))
        raise ValueError(f"Missing template key(s): {ordered}")
    return rendered


def _destination_template(rel_template_path: Path) -> str:
    parts = rel_template_path.parts
    if not parts:
        raise ValueError("Invalid template path")

    scope, *tail = parts
    if scope == "workspace":
        dest_parts = tail
    elif scope == "node":
        dest_parts = ["[[node_name]]", *tail]
    elif scope == "challenge":
        dest_parts = ["[[challenge_name]]", *tail]
    else:
        raise ValueError(
            f"Unsupported template scope '{scope}' in {rel_template_path}. "
            "Use workspace/, node/, or challenge/."
        )

    if not dest_parts:
        raise ValueError(f"Template must target a file: {rel_template_path}")

    last = dest_parts[-1]
    if last.endswith(".tmpl"):
        dest_parts[-1] = last[:-len(".tmpl")]

    return "/".join(dest_parts)


def render_pack_templates(template_set: str, values: dict[str, Any]) -> dict[str, str]:
    root = _TEMPLATES_ROOT / template_set
    if not root.exists():
        raise ValueError(f"Template set not found: {template_set}")

    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts:
            continue

        rel = path.relative_to(root)
        is_template = path.suffix == ".tmpl"
        destination_template = _destination_template(rel)
        destination = _render_tokens(destination_template, values)

        raw = path.read_text(encoding="utf-8")
        content = _render_tokens(raw, values) if is_template else raw
        files[destination] = content

    return files
