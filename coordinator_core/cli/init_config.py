from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from coordinator_core.cli.packs import get_pack

_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

SUPPORTED_SPEC_VERSION = "1"

REQUIRED_CALLABLES = {"SCORING_FUNCTION"}


@dataclass(frozen=True)
class InitConfig:
    name: str
    package_module: str
    node_name: str
    challenge_name: str
    crunch_id: str
    model_base_classname: str
    checkpoint_interval_seconds: int
    pack: str
    template_set: str
    callables: dict[str, str]
    scheduled_prediction_configs: list[dict[str, Any]]
    spec: dict[str, Any]


def is_valid_slug(name: str) -> bool:
    return bool(_SLUG_PATTERN.fullmatch(name or ""))


def load_spec(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"Spec file not found: {path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Spec file is not valid JSON: {path} ({exc})") from exc

    if not isinstance(payload, dict):
        raise ValueError("Spec root must be a JSON object")

    return payload


def load_answers(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"Answers file not found: {path}")

    raw = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()

    if suffix == ".json":
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Answers file is not valid JSON: {path} ({exc})") from exc
    else:
        try:
            import yaml  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise ValueError(
                "YAML answers require PyYAML. Install with `pip install pyyaml` or use JSON answers."
            ) from exc

        try:
            payload = yaml.safe_load(raw)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Answers file is not valid YAML: {path} ({exc})") from exc

    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError("Answers root must be an object")
    return payload


def merge_answers_with_spec(answers: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    merged = dict(answers)
    merged.update(spec)
    return merged


def resolve_init_config(
    name: str | None,
    spec: dict[str, Any],
    require_spec_version: bool = False,
    pack_name: str | None = None,
) -> InitConfig:
    spec_name = spec.get("name")

    if require_spec_version:
        if "spec_version" not in spec:
            raise ValueError(
                f"Spec missing required 'spec_version'. Supported version: '{SUPPORTED_SPEC_VERSION}'."
            )
        if str(spec.get("spec_version")) != SUPPORTED_SPEC_VERSION:
            raise ValueError(
                "Unsupported spec_version "
                f"'{spec.get('spec_version')}'. Supported version: '{SUPPORTED_SPEC_VERSION}'."
            )

    if name and spec_name and name != spec_name:
        raise ValueError(
            f"Name mismatch: CLI name '{name}' does not match spec name '{spec_name}'."
        )

    resolved_name = str(name or spec_name or "")
    if not resolved_name:
        raise ValueError("Challenge name required. Provide <name> or include 'name' in --spec.")

    if not is_valid_slug(resolved_name):
        raise ValueError(
            "Invalid challenge name. Use lowercase slug format like 'btc-trader' "
            "(letters, numbers, single dashes)."
        )

    package_module = f"crunch_{resolved_name.replace('-', '_')}"
    node_name = f"crunch-node-{resolved_name}"
    challenge_name = f"crunch-{resolved_name}"

    selected_pack = str(pack_name or spec.get("pack") or "baseline")
    pack = get_pack(selected_pack)
    normalized_spec = dict(spec)
    normalized_spec["pack"] = selected_pack

    crunch_id = str(spec.get("crunch_id", "starter-challenge"))
    model_base_classname = _normalize_model_base_classname(
        str(spec.get("model_base_classname", "tracker.TrackerBase")),
        package_module=package_module,
    )
    normalized_spec["model_base_classname"] = model_base_classname

    checkpoint_interval_seconds = int(
        spec.get("checkpoint_interval_seconds", pack.get("checkpoint_interval_seconds", 60))
    )
    if checkpoint_interval_seconds <= 0:
        raise ValueError("checkpoint_interval_seconds must be > 0")

    callables = _merge_callables(
        package_module=package_module,
        defaults=pack.get("callables") or {},
        overrides=spec.get("callables") or {},
    )
    scheduled_prediction_configs = _resolve_scheduled_prediction_configs(
        value=spec.get("scheduled_prediction_configs"),
        default_value=pack.get("scheduled_prediction_configs"),
    )

    return InitConfig(
        name=resolved_name,
        package_module=package_module,
        node_name=node_name,
        challenge_name=challenge_name,
        crunch_id=crunch_id,
        model_base_classname=model_base_classname,
        checkpoint_interval_seconds=checkpoint_interval_seconds,
        pack=selected_pack,
        template_set=str(pack.get("template_set") or "default"),
        callables=callables,
        scheduled_prediction_configs=scheduled_prediction_configs,
        spec=normalized_spec,
    )


def _normalize_model_base_classname(value: str, package_module: str) -> str:
    canonical = "tracker.TrackerBase"
    if not value:
        return canonical

    if value in (canonical, f"{package_module}.tracker.TrackerBase"):
        return canonical

    return value


def _merge_callables(
    package_module: str,
    defaults: dict[str, Any],
    overrides: dict[str, Any],
) -> dict[str, str]:
    if not isinstance(defaults, dict) or not defaults:
        raise ValueError("Pack callables must be a non-empty object")
    if not isinstance(overrides, dict):
        raise ValueError("'callables' must be an object of ENV_KEY -> module:callable")

    for key in REQUIRED_CALLABLES:
        if key not in defaults:
            raise ValueError(f"Pack callables missing required key '{key}'")

    rendered: dict[str, str] = {}
    for key, value in defaults.items():
        if key not in REQUIRED_CALLABLES:
            continue
        if not isinstance(value, str):
            raise ValueError(f"Pack callable for '{key}' must be '<module>:<callable>'")
        rendered[key] = value.format(package_module=package_module)

    for key, value in overrides.items():
        if key not in REQUIRED_CALLABLES:
            continue
        if not isinstance(value, str) or ":" not in value:
            raise ValueError(f"Callable override for '{key}' must be '<module>:<callable>'")
        rendered[key] = value

    for key, value in rendered.items():
        _validate_callable_path(key=key, value=value)

    return rendered


def _validate_callable_path(key: str, value: str) -> None:
    module_path, sep, callable_name = value.partition(":")
    if not sep or not module_path or not callable_name:
        raise ValueError(f"Callable override for '{key}' must be '<module>:<callable>'")

    if module_path.startswith("node_template"):
        raise ValueError(
            f"Callable '{key}' uses internal module path '{module_path}'. "
            "Use coordinator_runtime.* or challenge/node-local module paths instead."
        )


def _resolve_scheduled_prediction_configs(value: Any, default_value: Any) -> list[dict[str, Any]]:
    resolved = value if value is not None else default_value

    if not isinstance(resolved, list) or not resolved:
        raise ValueError("'scheduled_prediction_configs' must be a non-empty array")

    for idx, row in enumerate(resolved):
        if not isinstance(row, dict):
            raise ValueError(f"scheduled_prediction_configs[{idx}] must be an object")
        for field in ("scope_key", "scope_template", "schedule"):
            if field not in row:
                raise ValueError(f"scheduled_prediction_configs[{idx}] missing '{field}'")

    return resolved
