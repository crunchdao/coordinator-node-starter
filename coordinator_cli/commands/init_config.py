from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class InitConfig:
    name: str        # e.g. "my-challenge"
    module: str      # e.g. "my_challenge"
    dest: Path       # e.g. /path/to/my-challenge


def is_valid_slug(name: str) -> bool:
    return bool(_SLUG_PATTERN.fullmatch(name or ""))


def resolve_init_config(name: str, output: Path) -> InitConfig:
    if not name:
        raise ValueError("Challenge name required.")
    if not is_valid_slug(name):
        raise ValueError(
            "Invalid challenge name. Use lowercase slug format like 'btc-trader' "
            "(letters, numbers, single dashes)."
        )

    return InitConfig(
        name=name,
        module=name.replace("-", "_"),
        dest=output / name,
    )
