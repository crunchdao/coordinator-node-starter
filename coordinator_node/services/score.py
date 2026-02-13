"""Score service: resolve actuals on inputs → score predictions → leaderboard."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from coordinator_node.entities.prediction import (
    CheckpointStatus, InputStatus, PredictionStatus, ScoreRecord, SnapshotRecord,
)

from coordinator_node.db.repositories import (
    DBInputRepository, DBLeaderboardRepository, DBModelRepository,
    DBPredictionRepository, DBScoreRepository, DBSnapshotRepository,
)
from coordinator_node.contracts import CrunchContract
from coordinator_node.services.feed_reader import FeedReader


class ScoreService:
    def __init__(
        self,
        checkpoint_interval_seconds: int,
        scoring_function: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
        feed_reader: FeedReader | None = None,
        input_repository: DBInputRepository | None = None,
        prediction_repository: DBPredictionRepository | None = None,
        score_repository: DBScoreRepository | None = None,
        snapshot_repository: DBSnapshotRepository | None = None,
        model_repository: DBModelRepository | None = None,
        leaderboard_repository: DBLeaderboardRepository | None = None,
        contract: CrunchContract | None = None,
        **kwargs: Any,
    ):
        self.checkpoint_interval_seconds = checkpoint_interval_seconds
        self.scoring_function = scoring_function
        self.feed_reader = feed_reader
        self.input_repository = input_repository
        self.prediction_repository = prediction_repository
        self.score_repository = score_repository
        self.snapshot_repository = snapshot_repository
        self.model_repository = model_repository
        self.leaderboard_repository = leaderboard_repository
        self.contract = contract or CrunchContract()

        self.logger = logging.getLogger(__name__)
        self.stop_event = asyncio.Event()

    async def run(self) -> None:
        self.logger.info("score service started")
        while not self.stop_event.is_set():
            try:
                self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.logger.exception("score loop error: %s", exc)
                self._rollback_repositories()
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=self.checkpoint_interval_seconds)
            except asyncio.TimeoutError:
                pass

    def run_once(self) -> bool:
        now = datetime.now(timezone.utc)

        # 1. resolve actuals on inputs past their horizon
        self._resolve_inputs(now)

        # 2. score predictions whose input has actuals
        scored = self._score_predictions(now)
        if not scored:
            self.logger.info("No predictions scored this cycle")
            return False

        # 3. write snapshots (per-model period summary)
        self._write_snapshots(scored, now)

        # 4. rebuild leaderboard from snapshots
        self._rebuild_leaderboard()
        return True

    async def shutdown(self) -> None:
        self.stop_event.set()

    # ── 1. resolve actuals on inputs ──

    def _resolve_inputs(self, now: datetime) -> int:
        if self.input_repository is None or self.feed_reader is None:
            return 0

        unresolved = self.input_repository.find(
            status=InputStatus.RECEIVED, resolvable_before=now,
        )
        if not unresolved:
            return 0

        resolved = 0
        for inp in unresolved:
            # Query feed records using the input's scope dimensions + time window
            records = self.feed_reader.fetch_window(
                start=inp.received_at,
                end=inp.resolvable_at,
                source=inp.scope.get("source"),
                subject=inp.scope.get("subject"),
                kind=inp.scope.get("kind"),
                granularity=inp.scope.get("granularity"),
            )

            actuals = self.contract.resolve_ground_truth(records)
            if actuals is None:
                continue

            inp.actuals = actuals
            inp.status = InputStatus.RESOLVED
            self.input_repository.save(inp)
            resolved += 1

        if resolved:
            self.logger.info("Resolved actuals for %d inputs", resolved)
        return resolved

    # ── 2. score predictions ──

    def _score_predictions(self, now: datetime) -> list[ScoreRecord]:
        predictions = self.prediction_repository.find(status=PredictionStatus.PENDING)
        if not predictions:
            return []

        # Build input lookup for actuals
        input_ids = {p.input_id for p in predictions}
        inputs_by_id: dict[str, Any] = {}
        if self.input_repository is not None:
            for inp in self.input_repository.find(status=InputStatus.RESOLVED):
                if inp.id in input_ids:
                    inputs_by_id[inp.id] = inp

        scored: list[ScoreRecord] = []
        for prediction in predictions:
            inp = inputs_by_id.get(prediction.input_id)
            if inp is None or inp.actuals is None:
                continue  # actuals not yet available

            result = self.scoring_function(prediction.inference_output, inp.actuals)
            validated = self.contract.score_type(**result)

            score = ScoreRecord(
                id=f"SCR_{prediction.id}",
                prediction_id=prediction.id,
                result=validated.model_dump(),
                success=True,
                scored_at=now,
            )

            if self.score_repository is not None:
                self.score_repository.save(score)

            prediction.status = PredictionStatus.SCORED
            self.prediction_repository.save(prediction)
            scored.append(score)

        if scored:
            self.logger.info("Scored %d predictions", len(scored))
        return scored

    # ── 3. snapshots ──

    def _write_snapshots(self, scored: list[ScoreRecord], now: datetime) -> None:
        if self.snapshot_repository is None:
            return

        # Group scores by model (need prediction to get model_id)
        pred_map: dict[str, str] = {}  # prediction_id → model_id
        predictions = self.prediction_repository.find(status=PredictionStatus.SCORED)
        for p in predictions:
            pred_map[p.id] = p.model_id

        by_model: dict[str, list[dict[str, Any]]] = {}
        for score in scored:
            model_id = pred_map.get(score.prediction_id)
            if model_id:
                by_model.setdefault(model_id, []).append(score.result)

        for model_id, results in by_model.items():
            summary = self.contract.aggregate_snapshot(results)
            snapshot = SnapshotRecord(
                id=f"SNAP_{model_id}_{now.strftime('%Y%m%d_%H%M%S')}",
                model_id=model_id,
                period_start=min(s.scored_at for s in scored if pred_map.get(s.prediction_id) == model_id),
                period_end=now,
                prediction_count=len(results),
                result_summary=summary,
                created_at=now,
            )
            self.snapshot_repository.save(snapshot)

        self.logger.info("Wrote %d snapshots", len(by_model))

    # ── 4. leaderboard ──

    def _rebuild_leaderboard(self) -> None:
        models = self.model_repository.fetch_all()
        snapshots = self.snapshot_repository.find() if self.snapshot_repository else []

        aggregated = self._aggregate_from_snapshots(snapshots, models)
        ranked = self._rank(aggregated)

        self.leaderboard_repository.save(
            ranked, meta={"generated_by": "coordinator_node.score_service"},
        )

    def _aggregate_from_snapshots(self, snapshots: list[SnapshotRecord], models: dict) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        aggregation = self.contract.aggregation

        # Group snapshots by model
        by_model: dict[str, list[SnapshotRecord]] = {}
        for snap in snapshots:
            by_model.setdefault(snap.model_id, []).append(snap)

        entries: list[dict[str, Any]] = []
        for model_id, model_snapshots in by_model.items():
            metrics: dict[str, float] = {}
            for window_name, window in aggregation.windows.items():
                cutoff = now - timedelta(hours=window.hours)
                window_snaps = [s for s in model_snapshots if self._ensure_utc(s.period_end) >= cutoff]
                if window_snaps:
                    vals = [float(s.result_summary.get(aggregation.ranking_key, 0)) for s in window_snaps]
                    metrics[window_name] = sum(vals) / len(vals)
                else:
                    metrics[window_name] = 0.0

            model = models.get(model_id)
            entry: dict[str, Any] = {
                "model_id": model_id,
                "score": {
                    "metrics": metrics,
                    "ranking": {
                        "key": aggregation.ranking_key,
                        "value": metrics.get(aggregation.ranking_key, 0.0),
                        "direction": aggregation.ranking_direction,
                    },
                },
            }
            if model:
                entry["model_name"] = model.name
                entry["cruncher_name"] = model.player_name
            entries.append(entry)

        return entries

    def _rank(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        key = self.contract.aggregation.ranking_key
        reverse = self.contract.aggregation.ranking_direction == "desc"

        def sort_key(e: dict[str, Any]) -> float:
            score = e.get("score")
            if not isinstance(score, dict):
                return float("-inf")
            try:
                return float((score.get("metrics") or {}).get(key, 0.0))
            except Exception:
                return float("-inf")

        ranked = sorted(entries, key=sort_key, reverse=reverse)
        for idx, entry in enumerate(ranked, start=1):
            entry["rank"] = idx
        return ranked

    _rank_leaderboard = _rank

    @staticmethod
    def _ensure_utc(dt: datetime) -> datetime:
        """Ensure a datetime is timezone-aware (assume UTC if naive)."""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    def _rollback_repositories(self) -> None:
        for name, repo in [("input", self.input_repository),
                           ("prediction", self.prediction_repository),
                           ("score", self.score_repository),
                           ("snapshot", self.snapshot_repository),
                           ("model", self.model_repository),
                           ("leaderboard", self.leaderboard_repository)]:
            rollback = getattr(repo, "rollback", None)
            if callable(rollback):
                try:
                    rollback()
                except Exception as exc:
                    self.logger.warning("Rollback failed for %s: %s", name, exc)
