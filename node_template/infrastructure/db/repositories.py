from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from sqlmodel import Session, delete, select

from coordinator_core.entities.model import Model, ModelScore
from coordinator_core.entities.prediction import PredictionRecord, PredictionScore
from coordinator_core.infrastructure.db.db_tables import (
    LeaderboardRow,
    ModelRow,
    PredictionConfigRow,
    PredictionRow,
)
from coordinator_core.schemas import PredictionScopeEnvelope, ScheduledPredictionConfigEnvelope, ScoreEnvelope
from coordinator_core.services.interfaces.leaderboard_repository import LeaderboardRepository
from coordinator_core.services.interfaces.model_repository import ModelRepository
from coordinator_core.services.interfaces.prediction_repository import PredictionRepository


class DBModelRepository(ModelRepository):
    def __init__(self, session: Session):
        self._session = session

    def rollback(self) -> None:
        self._session.rollback()

    def fetch_all(self) -> dict[str, Model]:
        rows = self._session.exec(select(ModelRow)).all()
        return {row.id: self._row_to_domain(row) for row in rows}

    def fetch_by_ids(self, ids: list[str]) -> dict[str, Model]:
        if not ids:
            return {}
        rows = self._session.exec(select(ModelRow).where(ModelRow.id.in_(ids))).all()
        return {row.id: self._row_to_domain(row) for row in rows}

    def fetch(self, model_id: str) -> Model | None:
        row = self._session.get(ModelRow, model_id)
        return self._row_to_domain(row) if row else None

    def save(self, model: Model) -> None:
        existing = self._session.get(ModelRow, model.id)
        row = self._domain_to_row(model)

        if existing is None:
            self._session.add(row)
        else:
            existing.name = row.name
            existing.deployment_identifier = row.deployment_identifier
            existing.player_id = row.player_id
            existing.player_name = row.player_name
            existing.overall_score_jsonb = row.overall_score_jsonb
            existing.scores_by_scope_jsonb = row.scores_by_scope_jsonb
            existing.meta_jsonb = row.meta_jsonb
            existing.updated_at = datetime.now(timezone.utc)

        self._session.commit()

    def save_all(self, models: Iterable[Model]) -> None:
        for model in models:
            self.save(model)

    @staticmethod
    def _row_to_domain(row: ModelRow) -> Model:
        score = DBModelRepository._json_to_score(row.overall_score_jsonb or {})

        return Model(
            id=row.id,
            name=row.name,
            player_id=row.player_id,
            player_name=row.player_name,
            deployment_identifier=row.deployment_identifier,
            overall_score=score,
            scores_by_scope=row.scores_by_scope_jsonb or [],
            meta=row.meta_jsonb or {},
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _domain_to_row(model: Model) -> ModelRow:
        return ModelRow(
            id=model.id,
            name=model.name,
            deployment_identifier=model.deployment_identifier,
            player_id=model.player_id,
            player_name=model.player_name,
            overall_score_jsonb=DBModelRepository._score_to_json(model.overall_score),
            scores_by_scope_jsonb=model.scores_by_scope,
            meta_jsonb=model.meta,
            created_at=model.created_at,
            updated_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _score_to_json(score: ModelScore | None) -> dict[str, Any]:
        if score is None:
            return {}
        envelope = ScoreEnvelope.model_validate(
            {
                "windows": score.windows,
                "rank_key": score.rank_key,
                "payload": score.payload,
            }
        )
        return envelope.model_dump()

    @staticmethod
    def _json_to_score(score_payload: dict[str, Any]) -> ModelScore | None:
        if not score_payload:
            return None

        envelope = ScoreEnvelope.model_validate(score_payload)
        return ModelScore(
            windows=dict(envelope.windows),
            rank_key=envelope.rank_key,
            payload=dict(envelope.payload),
        )


class DBPredictionRepository(PredictionRepository):
    def __init__(self, session: Session):
        self._session = session

    def rollback(self) -> None:
        self._session.rollback()

    def save(self, prediction: PredictionRecord) -> None:
        existing = self._session.get(PredictionRow, prediction.id)
        row = self._domain_to_row(prediction)

        if existing is None:
            self._session.add(row)
        else:
            existing.status = row.status
            existing.exec_time_ms = row.exec_time_ms
            existing.inference_input_jsonb = row.inference_input_jsonb
            existing.inference_output_jsonb = row.inference_output_jsonb
            existing.meta_jsonb = row.meta_jsonb
            existing.scope_key = row.scope_key
            existing.scope_jsonb = row.scope_jsonb
            existing.prediction_config_id = row.prediction_config_id
            existing.score_value = row.score_value
            existing.score_success = row.score_success
            existing.score_failed_reason = row.score_failed_reason
            existing.score_scored_at = row.score_scored_at

        self._session.commit()

    def save_all(self, predictions: Iterable[PredictionRecord]) -> None:
        for prediction in predictions:
            self.save(prediction)

    def fetch_ready_to_score(self) -> list[PredictionRecord]:
        now = datetime.now(timezone.utc)
        rows = self._session.exec(
            select(PredictionRow)
            .where(PredictionRow.score_scored_at.is_(None))
            .where(PredictionRow.resolvable_at <= now)
        ).all()
        return [self._row_to_domain(row) for row in rows]

    def fetch_active_configs(self) -> list[dict]:
        rows = self._session.exec(
            select(PredictionConfigRow)
            .where(PredictionConfigRow.active.is_(True))
            .order_by(PredictionConfigRow.order.asc())
        ).all()

        configs: list[dict[str, Any]] = []
        for row in rows:
            envelope = ScheduledPredictionConfigEnvelope.model_validate(
                {
                    "id": row.id,
                    "scope_key": row.scope_key,
                    "scope_template": row.scope_template_jsonb or {},
                    "schedule": row.schedule_jsonb or {},
                    "active": row.active,
                    "order": row.order,
                    "meta": row.meta_jsonb or {},
                }
            )
            configs.append(envelope.model_dump())

        return configs

    def fetch_scored_predictions(self) -> list[PredictionRecord]:
        rows = self._session.exec(
            select(PredictionRow).where(PredictionRow.score_scored_at.is_not(None))
        ).all()
        return [self._row_to_domain(row) for row in rows]

    def query_scores(
        self,
        model_ids: list[str],
        _from: datetime | None,
        to: datetime | None,
    ) -> dict[str, list[PredictionRecord]]:
        stmt = select(PredictionRow).where(PredictionRow.score_scored_at.is_not(None))

        if model_ids:
            stmt = stmt.where(PredictionRow.model_id.in_(model_ids))
        if _from is not None:
            stmt = stmt.where(PredictionRow.performed_at >= _from)
        if to is not None:
            stmt = stmt.where(PredictionRow.performed_at <= to)

        rows = self._session.exec(stmt.order_by(PredictionRow.performed_at.asc())).all()

        by_model: dict[str, list[PredictionRecord]] = {}
        for row in rows:
            prediction = self._row_to_domain(row)
            by_model.setdefault(prediction.model_id, []).append(prediction)

        return by_model

    @staticmethod
    def _domain_to_row(prediction: PredictionRecord) -> PredictionRow:
        score_value = prediction.score.value if prediction.score else None
        score_success = prediction.score.success if prediction.score else None
        score_failed_reason = prediction.score.failed_reason if prediction.score else None
        score_scored_at = prediction.score.scored_at if prediction.score else None

        scope_envelope = PredictionScopeEnvelope.model_validate(
            {
                "scope_key": prediction.scope_key,
                "scope": prediction.scope,
            }
        )

        return PredictionRow(
            id=prediction.id,
            model_id=prediction.model_id,
            prediction_config_id=prediction.prediction_config_id,
            scope_key=scope_envelope.scope_key,
            scope_jsonb=scope_envelope.scope,
            status=prediction.status,
            exec_time_ms=prediction.exec_time_ms,
            inference_input_jsonb=prediction.inference_input,
            inference_output_jsonb=prediction.inference_output,
            meta_jsonb=prediction.meta,
            performed_at=prediction.performed_at,
            resolvable_at=prediction.resolvable_at or prediction.performed_at,
            score_value=score_value,
            score_success=score_success,
            score_failed_reason=score_failed_reason,
            score_scored_at=score_scored_at,
        )

    @staticmethod
    def _row_to_domain(row: PredictionRow) -> PredictionRecord:
        score = None
        if row.score_scored_at is not None or row.score_success is not None:
            score = PredictionScore(
                value=row.score_value,
                success=bool(row.score_success),
                failed_reason=row.score_failed_reason,
                scored_at=row.score_scored_at or datetime.now(timezone.utc),
            )

        scope_envelope = PredictionScopeEnvelope.model_validate(
            {
                "scope_key": row.scope_key,
                "scope": row.scope_jsonb or {},
            }
        )

        return PredictionRecord(
            id=row.id,
            model_id=row.model_id,
            prediction_config_id=row.prediction_config_id,
            scope_key=scope_envelope.scope_key,
            scope=scope_envelope.scope,
            status=row.status,
            exec_time_ms=row.exec_time_ms,
            inference_input=row.inference_input_jsonb or {},
            inference_output=row.inference_output_jsonb or {},
            meta=row.meta_jsonb or {},
            performed_at=row.performed_at,
            resolvable_at=row.resolvable_at,
            score=score,
        )


class DBLeaderboardRepository(LeaderboardRepository):
    def __init__(self, session: Session):
        self._session = session

    def rollback(self) -> None:
        self._session.rollback()

    def save(self, leaderboard_entries: list[dict[str, Any]], meta: dict[str, Any] | None = None) -> None:
        row = LeaderboardRow(
            id=f"LBR_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S.%f')[:-3]}",
            entries_jsonb=leaderboard_entries,
            meta_jsonb=meta or {},
        )
        self._session.add(row)
        self._session.commit()

    def get_latest(self) -> dict[str, Any] | None:
        row = self._session.exec(
            select(LeaderboardRow).order_by(LeaderboardRow.created_at.desc())
        ).first()
        if row is None:
            return None

        return {
            "id": row.id,
            "created_at": row.created_at,
            "entries": row.entries_jsonb,
            "meta": row.meta_jsonb,
        }

    def clear(self) -> None:
        self._session.exec(delete(LeaderboardRow))
        self._session.commit()
