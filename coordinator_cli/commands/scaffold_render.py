from __future__ import annotations

from typing import Any, Mapping

_DEFAULT_BANNED_TOKENS = (
    "coordinator.extensions.default_callables",
    "starter-benchmarktracker",
)


class _StrictFormatDict(dict[str, Any]):
    def __missing__(self, key: str) -> Any:  # pragma: no cover - simple passthrough
        raise KeyError(key)


def render_template_strict(template: str, values: Mapping[str, Any]) -> str:
    try:
        rendered = template.format_map(_StrictFormatDict(values))
    except KeyError as exc:  # pragma: no cover - behavior tested via ValueError
        missing = str(exc).strip("'")
        raise ValueError(f"Missing template key '{missing}'") from exc
    return rendered


def ensure_no_legacy_references(
    files: Mapping[str, str],
    banned_tokens: tuple[str, ...] = _DEFAULT_BANNED_TOKENS,
) -> None:
    for relative_path, content in files.items():
        for token in banned_tokens:
            if token and token in content:
                raise ValueError(
                    f"Legacy token '{token}' found in rendered file '{relative_path}'. "
                    "Update scaffold rendering/templates to use current runtime contracts."
                )
