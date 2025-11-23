from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Iterable, Dict, Optional

from sqlmodel import Session, select, delete

from falcon2_backend.entities.model import Model, Player, ModelScore, ModelScoreByParam, ModelScoreSnapshot
from falcon2_backend.entities.prediction import PredictionParams
from falcon2_backend.services.interfaces.model_repository import ModelRepository
from falcon2_backend.infrastructure.db.db_tables import ModelRow, ModelScoreSnapshotRow


class DbModelRepository(ModelRepository):
    """
    SQLModel-backed implementation of ModelRepository.

    It maps the pure domain Model <-> persistence ModelRow.
    """

    def __init__(self, session: Session):
        self._session = session

    def fetch_all(self) -> Dict[str, Model]:
        stmt = select(ModelRow)
        rows = self._session.exec(stmt).all()

        result: Dict[str, Model] = {}

        for row in rows:
            model = self._row_to_domain(row)
            result[row.crunch_identifier] = model

        return result

    def fetch_by_ids(self, ids: list[str]) -> dict[str, Model]:
        stmt = select(ModelRow).where(ModelRow.crunch_identifier.in_(ids))
        rows = self._session.exec(stmt).all()

        result: Dict[str, Model] = {}

        for row in rows:
            model = self._row_to_domain(row)
            result[row.crunch_identifier] = model

        return result

    def fetch(self, model_id: str) -> Model | None:
        row = self._session.get(ModelRow, model_id)
        if not row:
            return None

        return self._row_to_domain(row)

    def save(self, model: Model) -> None:
        """
        Upsert a model row entirely.
        Scores-by-param are stored in JSONB, so no sync required.
        """

        existing = self._session.get(ModelRow, model.crunch_identifier)
        row = self._domain_to_row(model)

        if existing is None:
            # Insert new row
            self._session.add(row)
        else:
            # Update existing
            existing.name = row.name
            existing.deployment_identifier = row.deployment_identifier
            existing.player_crunch_identifier = row.player_crunch_identifier
            existing.player_name = row.player_name
            existing.overall_score_recent = row.overall_score_recent
            existing.overall_score_steady = row.overall_score_steady
            existing.overall_score_anchor = row.overall_score_anchor
            existing.scores_by_param = row.scores_by_param

        self._session.commit()

    def save_all(self, models: Iterable[Model]) -> None:
        for model in models:
            self.save(model)

    def snapshot_model_scores(self, model_score_snapshots: Iterable[ModelScoreSnapshot]):
        """
        Save model score snapshots to the database.
        """
        rows = [self._snapshot_domain_to_row(snapshot) for snapshot in model_score_snapshots]
        self._session.bulk_save_objects(rows)
        self._session.commit()

    def fetch_model_score_snapshots(self, model_ids: list[str], _from: Optional[datetime], to: Optional[datetime]) -> dict[str, list[ModelScoreSnapshot]]:
        """
        Retrieve model score snapshots for specific models within a time range.
        """
        stmt = select(ModelScoreSnapshotRow)

        if model_ids:
            stmt = stmt.where(
                ModelScoreSnapshotRow.model_id.in_(model_ids)
            )

        if _from:
            stmt = stmt.where(ModelScoreSnapshotRow.performed_at >= _from)
        if to:
            stmt = stmt.where(ModelScoreSnapshotRow.performed_at <= to)

        stmt.order_by(ModelScoreSnapshotRow.performed_at.asc())

        rows = self._session.exec(stmt).all()

        snapshots_by_model = {}
        for row in rows:
            snapshot = self._snapshot_row_to_domain(row)
            if snapshot.model_id not in snapshots_by_model:
                snapshots_by_model[snapshot.model_id] = []
            snapshots_by_model[snapshot.model_id].append(snapshot)

        return snapshots_by_model

    def prune_snapshots(self):
        threshold = datetime.now(timezone.utc) - ModelScoreSnapshot.MAX_HISTORY_AGE

        stmt = (
            delete(ModelScoreSnapshotRow)
            .where(ModelScoreSnapshotRow.performed_at < threshold)
        )

        result = self._session.exec(stmt)
        self._session.commit()

        return result.rowcount or 0

    def _row_to_domain(self, row: ModelRow) -> Model:
        """
        Convert ModelRow (SQL) → Model (Domain)
        """

        # --- Player ---
        player = Player(
            crunch_identifier=row.player_crunch_identifier,
            name=row.player_name,
        )

        # --- Base Model ---
        model = Model(
            crunch_identifier=row.crunch_identifier,
            player=player,
            name=row.name,
            deployment_identifier=row.deployment_identifier,
        )

        # --- Overall score ---
        if (
            row.overall_score_recent is not None
            or row.overall_score_steady is not None
            or row.overall_score_anchor is not None
        ):
            model.overall_score = ModelScore(
                recent=row.overall_score_recent,
                steady=row.overall_score_steady,
                anchor=row.overall_score_anchor,
            )

        # --- Scores by param (JSONB list[dict]) ---
        model.scores_by_param = [
            ModelScoreByParam(
                param=PredictionParams(**entry["param"]),
                score=ModelScore(**entry["score"]),
            )
            for entry in row.scores_by_param or []
        ]

        return model

    def _domain_to_row(self, model: Model) -> ModelRow:
        """
        Convert Model (Domain) → ModelRow (SQL)
        """
        scores = [asdict(sbp) for sbp in model.scores_by_param]

        return ModelRow(
            crunch_identifier=model.crunch_identifier,
            name=model.name,
            deployment_identifier=model.deployment_identifier,
            player_crunch_identifier=model.player.crunch_identifier,
            player_name=model.player.name,
            overall_score_recent=model.overall_score.recent if model.overall_score else None,
            overall_score_steady=model.overall_score.steady if model.overall_score else None,
            overall_score_anchor=model.overall_score.anchor if model.overall_score else None,
            scores_by_param=scores,
        )

    def _snapshot_row_to_domain(self, row: ModelScoreSnapshotRow) -> ModelScoreSnapshot:
        return ModelScoreSnapshot(
            overall_score=ModelScore(
                recent=row.overall_score_recent,
                steady=row.overall_score_steady,
                anchor=row.overall_score_anchor,
            ),
            scores_by_param=[
                ModelScoreByParam(
                    param=PredictionParams(**entry["param"]),
                    score=ModelScore(**entry["score"]),
                )
                for entry in row.scores_by_param or []
            ],
            model_id=row.model_id,
            performed_at=row.performed_at,
            id=row.id
        )

    def _snapshot_domain_to_row(self, model_score_snapshot: ModelScoreSnapshot) -> ModelScoreSnapshotRow:
        return ModelScoreSnapshotRow(
            id=model_score_snapshot.id,
            model_id=model_score_snapshot.model_id,
            performed_at=model_score_snapshot.performed_at,
            overall_score_recent=model_score_snapshot.overall_score.recent,
            overall_score_steady=model_score_snapshot.overall_score.steady,
            overall_score_anchor=model_score_snapshot.overall_score.anchor,
            scores_by_param=[asdict(sbp) for sbp in model_score_snapshot.scores_by_param]
        )