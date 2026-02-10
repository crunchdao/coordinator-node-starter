from __future__ import annotations

import argparse
import asyncio
import logging

from node_template.config.extensions import ExtensionSettings
from node_template.extensions.callable_resolver import resolve_callable


def parse_arguments():
    parser = argparse.ArgumentParser(description="Node-template score worker")
    parser.add_argument("--prediction-id", required=False)
    return parser.parse_args()


async def main(prediction_id: str | None = None) -> None:
    logging.getLogger(__name__).info("node_template score worker bootstrap")
    settings = ExtensionSettings.from_env()
    resolve_callable(settings.scoring_function, required_params=("prediction", "ground_truth"))

    if prediction_id is not None:
        logging.getLogger(__name__).info("single prediction scoring not implemented yet")
        return

    # Placeholder: this worker will be connected to node_template ScoreService during migration.
    while True:
        await asyncio.sleep(60)


if __name__ == "__main__":
    args = parse_arguments()
    asyncio.run(main(args.prediction_id))
