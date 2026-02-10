from __future__ import annotations

import asyncio
import logging

from node_template.config.extensions import ExtensionSettings
from node_template.extensions.callable_resolver import resolve_callable


def build_service() -> dict[str, object]:
    settings = ExtensionSettings.from_env()
    inference_input_builder = resolve_callable(
        settings.inference_input_builder,
        required_params=("raw_input",),
    )
    return {
        "settings": settings,
        "inference_input_builder": inference_input_builder,
    }


async def main() -> None:
    logging.getLogger(__name__).info("node_template predict worker bootstrap")
    build_service()

    # Placeholder: this worker will be connected to node_template PredictService during migration.
    while True:
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
