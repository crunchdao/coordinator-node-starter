from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable


class PredictService:
    def __init__(
        self,
        checkpoint_interval_seconds: int,
        inference_input_builder: Callable[[dict[str, Any]], dict[str, Any]],
    ):
        self.checkpoint_interval_seconds = checkpoint_interval_seconds
        self.inference_input_builder = inference_input_builder
        self.logger = logging.getLogger(__name__)
        self.stop_event = asyncio.Event()

    async def run(self) -> None:
        self.logger.info("node_template predict service started")
        while not self.stop_event.is_set():
            # Placeholder hook: in the next step this will build and send inference payloads.
            self.inference_input_builder({})

            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=self.checkpoint_interval_seconds)
            except asyncio.TimeoutError:
                pass

    async def shutdown(self) -> None:
        self.stop_event.set()
