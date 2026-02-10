from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone

from coordinator_core.entities.model import Model
from coordinator_core.entities.prediction import PredictionRecord
from node_template.services.predict_service import PredictService


class FakeModelRun:
    def __init__(self, model_id: str, model_name: str, deployment_id: str = "dep-1"):
        self.model_id = model_id
        self.model_name = model_name
        self.deployment_id = deployment_id
        self.infos = {"cruncher_id": "player-1", "cruncher_name": "alice"}


class FakePredictionResult:
    def __init__(self, status: str = "SUCCESS", result=None, exec_time_us: float = 10.0):
        self.status = status
        self.result = result if result is not None else {"prediction": 1}
        self.exec_time_us = exec_time_us


class FakeRunner:
    def __init__(self):
        self.tick_model = FakeModelRun("m1", "model-one")

    async def init(self):
        return None

    async def sync(self):
        await asyncio.sleep(3600)

    async def call(self, method: str, args, model_runs=None):
        if method == "tick":
            return {self.tick_model: FakePredictionResult(status="SUCCESS", result={})}
        if method == "predict":
            return {self.tick_model: FakePredictionResult(status="SUCCESS", result={"distribution": []})}
        return {}


class InMemoryModelRepository:
    def __init__(self):
        self.models: dict[str, Model] = {}

    def fetch_all(self):
        return self.models

    def fetch_by_ids(self, ids):
        return {k: v for k, v in self.models.items() if k in ids}

    def fetch(self, model_id):
        return self.models.get(model_id)

    def save(self, model: Model):
        self.models[model.id] = model

    def save_all(self, models):
        for model in models:
            self.save(model)


class InMemoryPredictionRepository:
    def __init__(self):
        self.saved_predictions: list[PredictionRecord] = []

    def save(self, prediction: PredictionRecord):
        self.saved_predictions.append(prediction)

    def save_all(self, predictions):
        self.saved_predictions.extend(list(predictions))

    def fetch_ready_to_score(self):
        return []

    def fetch_active_configs(self):
        return [
            {
                "id": "CFG_1",
                "asset": "BTC",
                "horizon": 60,
                "step": 60,
                "prediction_interval": 60,
                "active": True,
                "order": 1,
            }
        ]


class TestNodeTemplatePredictService(unittest.IsolatedAsyncioTestCase):
    async def test_run_once_generates_prediction_rows(self):
        model_repo = InMemoryModelRepository()
        prediction_repo = InMemoryPredictionRepository()

        service = PredictService(
            checkpoint_interval_seconds=60,
            raw_input_provider=None,
            inference_input_builder=lambda raw_input: {"wrapped": raw_input},
            inference_output_validator=lambda inference_output: {"validated": True, **inference_output},
            model_repository=model_repo,
            prediction_repository=prediction_repo,
            runner=FakeRunner(),
        )

        await service.run_once(raw_input={"x": 1}, now=datetime.now(timezone.utc))

        self.assertIn("m1", model_repo.models)
        self.assertGreaterEqual(len(prediction_repo.saved_predictions), 1)
        self.assertEqual(prediction_repo.saved_predictions[0].asset, "BTC")
        self.assertIn("wrapped", prediction_repo.saved_predictions[0].inference_input)
        self.assertTrue(prediction_repo.saved_predictions[0].inference_output.get("validated"))

    async def test_run_once_uses_raw_input_provider_when_input_not_given(self):
        model_repo = InMemoryModelRepository()
        prediction_repo = InMemoryPredictionRepository()

        service = PredictService(
            checkpoint_interval_seconds=60,
            raw_input_provider=lambda now: {"source": "provider", "ts": now.isoformat()},
            inference_input_builder=lambda raw_input: {"wrapped": raw_input},
            inference_output_validator=None,
            model_repository=model_repo,
            prediction_repository=prediction_repo,
            runner=FakeRunner(),
        )

        now = datetime.now(timezone.utc)
        await service.run_once(now=now)

        self.assertGreaterEqual(len(prediction_repo.saved_predictions), 1)
        wrapped = prediction_repo.saved_predictions[0].inference_input["wrapped"]
        self.assertEqual(wrapped["source"], "provider")
        self.assertEqual(wrapped["ts"], now.isoformat())


if __name__ == "__main__":
    unittest.main()
