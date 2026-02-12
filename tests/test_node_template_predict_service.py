import unittest
from datetime import datetime, timezone

from coordinator_core.entities.model import Model
from coordinator_core.entities.prediction import PredictionRecord
from node_template.contracts import CrunchContract, InferenceInput, InferenceOutput
from node_template.services.predict_service import PredictService


class FakeModelRun:
    def __init__(self, model_id, model_name="model-1", deployment_id="dep-1"):
        self.model_id = model_id
        self.model_name = model_name
        self.deployment_id = deployment_id
        self.infos = {"cruncher_id": "p1", "cruncher_name": "alice"}


class FakePredictionResult:
    def __init__(self, result=None, status="SUCCESS", exec_time_us=100):
        self.result = result or {"value": 0.5}
        self.status = status
        self.exec_time_us = exec_time_us


class FakeRunner:
    def __init__(self):
        self._initialized = False

    async def init(self):
        self._initialized = True

    async def sync(self):
        pass

    async def call(self, method, args):
        return {FakeModelRun("m1"): FakePredictionResult()}


class FakeInputService:
    """Returns a fixed payload for get_input."""

    def __init__(self, payload=None):
        self._payload = payload or {}

    def get_input(self, now):
        return self._payload


class InMemoryModelRepository:
    def __init__(self):
        self.models: dict[str, Model] = {}

    def fetch_all(self):
        return self.models

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
                "scope_key": "BTC-60-60",
                "scope_template": {"asset": "BTC", "horizon": 60, "step": 60},
                "schedule": {"prediction_interval_seconds": 60, "resolve_after_seconds": 60},
                "active": True,
                "order": 1,
            }
        ]


class NoConfigPredictionRepository(InMemoryPredictionRepository):
    def fetch_active_configs(self):
        return []


class TestNodeTemplatePredictService(unittest.IsolatedAsyncioTestCase):
    async def test_run_once_generates_prediction_rows(self):
        model_repo = InMemoryModelRepository()
        prediction_repo = InMemoryPredictionRepository()

        service = PredictService(
            checkpoint_interval_seconds=60,
            input_service=FakeInputService(),
            contract=CrunchContract(),
            model_repository=model_repo,
            prediction_repository=prediction_repo,
            runner=FakeRunner(),
        )

        await service.run_once(raw_input={"symbol": "BTC", "asof_ts": 123}, now=datetime.now(timezone.utc))

        self.assertIn("m1", model_repo.models)
        self.assertGreaterEqual(len(prediction_repo.saved_predictions), 1)
        self.assertEqual(prediction_repo.saved_predictions[0].scope_key, "BTC-60-60")
        self.assertEqual(prediction_repo.saved_predictions[0].scope.get("asset"), "BTC")
        self.assertEqual(prediction_repo.saved_predictions[0].inference_input["symbol"], "BTC")
        self.assertIn("value", prediction_repo.saved_predictions[0].inference_output)

    async def test_run_once_uses_input_service_when_input_not_given(self):
        model_repo = InMemoryModelRepository()
        prediction_repo = InMemoryPredictionRepository()

        service = PredictService(
            checkpoint_interval_seconds=60,
            input_service=FakeInputService({"symbol": "ETH", "asof_ts": 999}),
            contract=CrunchContract(),
            model_repository=model_repo,
            prediction_repository=prediction_repo,
            runner=FakeRunner(),
        )

        await service.run_once(now=datetime.now(timezone.utc))

        self.assertGreaterEqual(len(prediction_repo.saved_predictions), 1)
        self.assertEqual(prediction_repo.saved_predictions[0].inference_input["symbol"], "ETH")

    async def test_run_once_logs_when_no_active_configs(self):
        model_repo = InMemoryModelRepository()
        prediction_repo = NoConfigPredictionRepository()

        service = PredictService(
            checkpoint_interval_seconds=60,
            input_service=FakeInputService(),
            contract=CrunchContract(),
            model_repository=model_repo,
            prediction_repository=prediction_repo,
            runner=FakeRunner(),
        )

        with self.assertLogs("node_template.services.predict_service", level="INFO") as logs:
            changed = await service.run_once(raw_input={"symbol": "BTC"}, now=datetime.now(timezone.utc))

        self.assertFalse(changed)
        self.assertEqual(len(prediction_repo.saved_predictions), 0)
        self.assertTrue(any("No active prediction configs" in line for line in logs.output))

    async def test_run_once_logs_output_validation_error(self):
        model_repo = InMemoryModelRepository()
        prediction_repo = InMemoryPredictionRepository()

        from pydantic import BaseModel, Field

        class StrictOutput(BaseModel):
            value: float = Field(ge=0.0, le=1.0)

        contract = CrunchContract(output_type=StrictOutput)

        class BadRunner(FakeRunner):
            async def call(self, method, args):
                return {FakeModelRun("m1"): FakePredictionResult(result={"value": "not-a-number"})}

        service = PredictService(
            checkpoint_interval_seconds=60,
            input_service=FakeInputService(),
            contract=contract,
            model_repository=model_repo,
            prediction_repository=prediction_repo,
            runner=BadRunner(),
        )

        with self.assertLogs("node_template.services.predict_service", level="ERROR") as logs:
            changed = await service.run_once(raw_input={"symbol": "BTC"}, now=datetime.now(timezone.utc))

        self.assertTrue(changed)
        self.assertGreaterEqual(len(prediction_repo.saved_predictions), 1)
        self.assertEqual(prediction_repo.saved_predictions[0].status, "FAILED")
        self.assertIn("_validation_error", prediction_repo.saved_predictions[0].inference_output)
        self.assertTrue(any("INFERENCE_OUTPUT_VALIDATION_ERROR" in line for line in logs.output))


if __name__ == "__main__":
    unittest.main()
