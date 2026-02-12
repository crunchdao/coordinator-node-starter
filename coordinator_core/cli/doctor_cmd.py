from __future__ import annotations

from pathlib import Path

from coordinator_core.cli.init_config import load_spec, resolve_init_config


def run_doctor(name: str | None, spec_path: Path | None, pack_name: str | None = None) -> int:
    if spec_path is None:
        print("coordinator doctor currently validates init specs. Use --spec path/to/spec.json")
        return 1

    try:
        spec = load_spec(spec_path)
        config = resolve_init_config(
            name=name,
            spec=spec,
            require_spec_version=True,
            pack_name=pack_name,
        )
    except ValueError as exc:
        print(f"doctor failed: {exc}")
        return 1

    print("doctor passed: spec is valid")
    print(f"- name: {config.name}")
    print(f"- crunch_id: {config.crunch_id}")
    print(f"- model_base_classname: {config.model_base_classname}")
    print(f"- pack: {config.pack}")
    print(f"- callables: {len(config.callables)}")
    print(f"- scheduled_prediction_configs: {len(config.scheduled_prediction_configs)}")
    return 0
