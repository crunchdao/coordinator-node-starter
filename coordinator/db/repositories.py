from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from sqlmodel import Session, delete, select

from coordinator.entities.model import Model, ModelScore
from coordinator.entities.prediction import InputRecord, PredictionRecord, ScoreRecord
from coordinator.db.tables import (
    InputRow,
    LeaderboardRow,
    ModelRow,
    PredictionConfigRow,
    PredictionRow,
    ScoreRow,
)
from coordinator.schemas import PredictionScopeEnvelope, ScheduledPredictionConfigEnvelope, ScoreEnvelope


class DBModelRepository:
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
                "metrics": dict(score.metrics),
                "ranking": dict(score.ranking),
                "payload": dict(score.payload),
            }
        )
        return envelope.model_dump()

    @staticmethod
    def _json_to_score(score_payload: dict[str, Any]) -> ModelScore | None:
        if not score_payload:
            return None

        envelope = ScoreEnvelope.model_validate(score_payload)
        return ModelScore(
            metrics=dict(envelope.metrics),
            ranking=envelope.ranking.model_dump(exclude_none=True),
            payload=dict(envelope.payload),
        )


class DBInputRepository:
    def __init__(self, session: Session):
        self._session = session

    def save(self, record: InputRecord) -> None:
        row = InputRow(
            id=record.id,
            status=record.status,
            raw_data_jsonb=record.raw_data,
            actuals_jsonb=record.actuals,
            scope_jsonb=record.scope,
            meta_jsonb=record.meta,
            received_at=record.received_at,
            resolvable_at=record.resolvable_at,
        )
        existing = self._session.get(InputRow, row.id)
        if existing is None:
            self._session.add(row)
        else:
            existing.status = row.status
            existing.actuals_jsonb = row.actuals_jsonb
            existing.meta_jsonb = row.meta_jsonb
        self._session.commit()

    def find(
        self, *, status: str | None = None, resolvable_before: datetime | None = None,
        since: datetime | None = None, until: datetime | None = None,
        limit: int | None = None,
    ) -> list[InputRecord]:
        stmt = select(InputRow).order_by(InputRow.received_at.asc())
        if status is not None:
            stmt = stmt.where(InputRow.status == status)
        if resolvable_before is not None:
            stmt = stmt.where(InputRow.resolvable_at <= resolvable_before)
        if since is not None:
            stmt = stmt.where(InputRow.received_at >= since)
        if until is not None:
            stmt = stmt.where(InputRow.received_at <= until)
        if limit is not None:
            stmt = stmt.limit(max(1, int(limit)))
        rows = self._session.exec(stmt).all()
        return [InputRecord(
            id=r.id, status=r.status, raw_data=r.raw_data_jsonb or {},
            actuals=r.actuals_jsonb, scope=r.scope_jsonb or {},
            meta=r.meta_jsonb or {}, received_at=r.received_at,
            resolvable_at=r.resolvable_at,
        ) for r in rows]


class DBPredictionRepository:
    def __init__(self, session: Session):
        self._session = session

    def rollback(self) -> None:
        self._session.rollback()

    def save(self, prediction: PredictionRecord) -> None:
        row = self._domain_to_row(prediction)
        existing = self._session.get(PredictionRow, row.id)
        if existing is None:
            self._session.add(row)
        else:
            existing.status = row.status
            existing.exec_time_ms = row.exec_time_ms
            existing.inference_output_jsonb = row.inference_output_jsonb
            existing.meta_jsonb = row.meta_jsonb
            existing.scope_key = row.scope_key
            existing.scope_jsonb = row.scope_jsonb
        self._session.commit()

    def save_all(self, predictions: Iterable[PredictionRecord]) -> None:
        for prediction in predictions:
            self.save(prediction)

    def find(
        self, *, status: str | list[str] | None = None,
        scope_key: str | None = None, model_id: str | None = None,
        since: datetime | None = None, until: datetime | None = None,
        resolvable_before: datetime | None = None, limit: int | None = None,
    ) -> list[PredictionRecord]:
        stmt = select(PredictionRow)
        if status is not None:
            if isinstance(status, list):
                stmt = stmt.where(PredictionRow.status.in_(status))
            else:
                stmt = stmt.where(PredictionRow.status == status)
        if scope_key is not None:
            stmt = stmt.where(PredictionRow.scope_key == scope_key)
        if model_id is not None:
            stmt = stmt.where(PredictionRow.model_id == model_id)
        if since is not None:
            stmt = stmt.where(PredictionRow.performed_at >= since)
        if until is not None:
            stmt = stmt.where(PredictionRow.performed_at <= until)
        if resolvable_before is not None:
            stmt = stmt.where(PredictionRow.resolvable_at <= resolvable_before)
        if limit is not None:
            stmt = stmt.limit(max(1, int(limit)))
        stmt = stmt.order_by(PredictionRow.performed_at.asc())
        rows = self._session.exec(stmt).all()
        return [self._row_to_domain(row) for row in rows]

    def fetch_active_configs(self) -> list[dict]:
        rows = self._session.exec(
            select(PredictionConfigRow)
            .where(PredictionConfigRow.active.is_(True))
            .order_by(PredictionConfigRow.order.asc())
        ).all()
        configs: list[dict[str, Any]] = []
        for row in rows:
            envelope = ScheduledPredictionConfigEnvelope.model_validate({
                "id": row.id, "scope_key": row.scope_key,
                "scope_template": row.scope_template_jsonb or {},
                "schedule": row.schedule_jsonb or {},
                "active": row.active, "order": row.order,
                "meta": row.meta_jsonb or {},
            })
            configs.append(envelope.model_dump())
        return configs

    @staticmethod
    def _domain_to_row(prediction: PredictionRecord) -> PredictionRow:
        return PredictionRow(
            id=prediction.id,
            input_id=prediction.input_id,
            model_id=prediction.model_id,
            prediction_config_id=prediction.prediction_config_id,
            scope_key=prediction.scope_key,
            scope_jsonb=prediction.scope,
            status=prediction.status,
            exec_time_ms=prediction.exec_time_ms,
            inference_output_jsonb=prediction.inference_output,
            meta_jsonb=prediction.meta,
            performed_at=prediction.performed_at,
            resolvable_at=prediction.resolvable_at or prediction.performed_at,
        )

    @staticmethod
    def _row_to_domain(row: PredictionRow) -> PredictionRecord:
        return PredictionRecord(
            id=row.id,
            input_id=row.input_id,
            model_id=row.model_id,
            prediction_config_id=row.prediction_config_id,
            scope_key=row.scope_key,
            scope=row.scope_jsonb or {},
            status=row.status,
            exec_time_ms=row.exec_time_ms,
            inference_output=row.inference_output_jsonb or {},
            meta=row.meta_jsonb or {},
            performed_at=row.performed_at,
            resolvable_at=row.resolvable_at,
        )


class DBScoreRepository:
    def __init__(self, session: Session):
        self._session = session

    def save(self, record: ScoreRecord) -> None:
        row = ScoreRow(
            id=record.id,
            prediction_id=record.prediction_id,
            value=record.value,
            success=record.success,
            failed_reason=record.failed_reason,
            scored_at=record.scored_at,
        )
        existing = self._session.get(ScoreRow, row.id)
        if existing is None:
            self._session.add(row)
        else:
            existing.value = row.value
            existing.success = row.success
            existing.failed_reason = row.failed_reason
            existing.scored_at = row.scored_at
        self._session.commit()

    def find(
        self, *, prediction_id: str | None = None, model_id: str | None = None,
        since: datetime | None = None, until: datetime | None = None,
        limit: int | None = None,
    ) -> list[ScoreRecord]:
        stmt = select(ScoreRow)
        if prediction_id is not None:
            stmt = stmt.where(ScoreRow.prediction_id == prediction_id)
        if since is not None:
            stmt = stmt.where(ScoreRow.scored_at >= since)
        if until is not None:
            stmt = stmt.where(ScoreRow.scored_at <= until)
        if limit is not None:
            stmt = stmt.limit(max(1, int(limit)))
        stmt = stmt.order_by(ScoreRow.scored_at.asc())
        rows = self._session.exec(stmt).all()
        return [ScoreRecord(
            id=r.id, prediction_id=r.prediction_id, value=r.value,
            success=bool(r.success), failed_reason=r.failed_reason,
            scored_at=r.scored_at,
        ) for r in rows]


class DBLeaderboardRepository:
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
