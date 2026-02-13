import unittest
from datetime import datetime, timezone

from coordinator_node.entities.model import Model
from coordinator_node.entities.prediction import PredictionRecord
from coordinator_node.contracts import CrunchContract
from coordinator_node.services.realtime_predict import RealtimePredictService


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


class FakeFeedReader:
    def __init__(self, payload=None):
        self._payload = payload or {}
        self.source = "pyth"
        self.subject = "BTC"
        self.kind = "tick"
        self.granularity = "1s"

    def get_input(self, now):
        return self._payload

    def get_ground_truth(self, performed_at, resolvable_at, asset=None):
        return None


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

    def save_prediction(self, prediction: PredictionRecord):
        self.saved_predictions.append(prediction)

    def save_predictions(self, predictions):
        self.saved_predictions.extend(list(predictions))

    def save_actuals(self, prediction_id, actuals):
        for p in self.saved_predictions:
            if p.id == prediction_id:
                p.actuals = actuals
                p.status = "RESOLVED"

    def find_predictions(self, *, status=None, resolvable_before=None, **kwargs):
        results = self.saved_predictions
        if status is not None:
            if isinstance(status, list):
                results = [p for p in results if p.status in status]
            else:
                results = [p for p in results if p.status == status]
        return results

    # legacy compat
    def save(self, prediction):
        self.save_prediction(prediction)

    def save_all(self, predictions):
        self.save_predictions(predictions)

    def fetch_active_configs(self):
        return [
            {
                "id": "CFG_1",
                "scope_key": "BTC-60-60",
                "scope_template": {"subject": "BTC", "horizon": 60, "step": 60},
                "schedule": {"prediction_interval_seconds": 60, "resolve_after_seconds": 60},
                "active": True,
                "order": 1,
            }
        ]


class NoConfigPredictionRepository(InMemoryPredictionRepository):
    def fetch_active_configs(self):
        return []


def _make_service(feed_reader=None, prediction_repo=None, runner=None, contract=None):
    return RealtimePredictService(
        checkpoint_interval_seconds=60,
        feed_reader=feed_reader or FakeFeedReader(),
        contract=contract or CrunchContract(),
        model_repository=InMemoryModelRepository(),
        prediction_repository=prediction_repo or InMemoryPredictionRepository(),
        runner=runner or FakeRunner(),
    )


class TestRealtimePredictService(unittest.IsolatedAsyncioTestCase):
    async def test_run_once_generates_prediction_rows(self):
        repo = InMemoryPredictionRepository()
        service = _make_service(prediction_repo=repo)

        await service.run_once(raw_input={"symbol": "BTC", "asof_ts": 123}, now=datetime.now(timezone.utc))

        self.assertIn("m1", service._known_models)
        self.assertGreaterEqual(len(repo.saved_predictions), 1)

        pred = repo.saved_predictions[0]
        self.assertEqual(pred.scope_key, "BTC-60-60")
        self.assertEqual(pred.scope.get("subject"), "BTC")
        self.assertIsNotNone(pred.input_id)
        self.assertIn("value", pred.inference_output)

    async def test_run_once_uses_feed_reader_when_no_raw_input(self):
        repo = InMemoryPredictionRepository()
        service = _make_service(
            feed_reader=FakeFeedReader({"symbol": "ETH", "asof_ts": 999}),
            prediction_repo=repo,
        )

        await service.run_once(now=datetime.now(timezone.utc))

        self.assertGreaterEqual(len(repo.saved_predictions), 1)
        self.assertIsNotNone(repo.saved_predictions[0].input_id)

    async def test_run_once_returns_false_when_no_active_configs(self):
        service = _make_service(prediction_repo=NoConfigPredictionRepository())

        with self.assertLogs("RealtimePredictService", level="INFO") as logs:
            changed = await service.run_once(raw_input={"symbol": "BTC"}, now=datetime.now(timezone.utc))

        self.assertFalse(changed)
        self.assertTrue(any("No active prediction configs" in line for line in logs.output))

    async def test_run_once_marks_failed_on_output_validation_error(self):
        from pydantic import BaseModel, Field

        class StrictOutput(BaseModel):
            value: float = Field(ge=0.0, le=1.0)

        class BadRunner(FakeRunner):
            async def call(self, method, args):
                return {FakeModelRun("m1"): FakePredictionResult(result={"value": "not-a-number"})}

        repo = InMemoryPredictionRepository()
        service = _make_service(
            prediction_repo=repo,
            runner=BadRunner(),
            contract=CrunchContract(output_type=StrictOutput),
        )

        with self.assertLogs("RealtimePredictService", level="ERROR") as logs:
            changed = await service.run_once(raw_input={"symbol": "BTC"}, now=datetime.now(timezone.utc))

        self.assertTrue(changed)
        pred = repo.saved_predictions[0]
        self.assertEqual(pred.status, "FAILED")
        self.assertIn("_validation_error", pred.inference_output)
        self.assertTrue(any("INFERENCE_OUTPUT_VALIDATION_ERROR" in line for line in logs.output))


if __name__ == "__main__":
    unittest.main()
