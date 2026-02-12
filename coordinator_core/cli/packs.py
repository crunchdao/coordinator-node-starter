from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

_PACKS_ROOT = Path(__file__).resolve().parent.parent / "scaffold" / "packs"


@dataclass(frozen=True)
class PackDefinition:
    id: str
    description: str
    checkpoint_interval_seconds: int
    callables: dict[str, str]
    scheduled_prediction_configs: list[dict[str, Any]]
    template_set: str = "default"


@lru_cache(maxsize=1)
def _load_packs() -> dict[str, PackDefinition]:
    packs: dict[str, PackDefinition] = {}

    if not _PACKS_ROOT.exists():
        return packs

    for pack_file in sorted(_PACKS_ROOT.glob("*/pack.json")):
        payload = json.loads(pack_file.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid pack file (must be object): {pack_file}")

        pack_id = str(payload.get("id") or "").strip()
        if not pack_id:
            raise ValueError(f"Pack missing id: {pack_file}")
        if pack_id in packs:
            raise ValueError(f"Duplicate pack id '{pack_id}' at {pack_file}")

        callables = payload.get("callables")
        schedule = payload.get("scheduled_prediction_configs")
        if not isinstance(callables, dict) or not callables:
            raise ValueError(f"Pack '{pack_id}' has invalid callables in {pack_file}")
        if not isinstance(schedule, list) or not schedule:
            raise ValueError(f"Pack '{pack_id}' has invalid scheduled_prediction_configs in {pack_file}")

        packs[pack_id] = PackDefinition(
            id=pack_id,
            description=str(payload.get("description") or ""),
            checkpoint_interval_seconds=int(payload.get("checkpoint_interval_seconds", 60)),
            callables={str(k): str(v) for k, v in callables.items()},
            scheduled_prediction_configs=deepcopy(schedule),
            template_set=str(payload.get("template_set") or "default"),
        )

    return packs


def list_pack_names() -> list[str]:
    return sorted(_load_packs().keys())


def list_pack_summaries() -> list[tuple[str, str]]:
    packs = _load_packs()
    return [(name, packs[name].description) for name in list_pack_names()]


def get_pack(name: str) -> dict[str, Any]:
    pack_name = str(name or "").strip()
    if not pack_name:
        raise ValueError("Pack name cannot be empty")

    pack = _load_packs().get(pack_name)
    if pack is None:
        allowed = ", ".join(list_pack_names())
        raise ValueError(f"Unknown pack '{pack_name}'. Allowed packs: {allowed}")

    return {
        "id": pack.id,
        "description": pack.description,
        "checkpoint_interval_seconds": pack.checkpoint_interval_seconds,
        "callables": deepcopy(pack.callables),
        "scheduled_prediction_configs": deepcopy(pack.scheduled_prediction_configs),
        "template_set": pack.template_set,
    }
