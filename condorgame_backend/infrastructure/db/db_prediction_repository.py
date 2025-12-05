import logging
from datetime import datetime, timedelta, timezone
from typing import Iterable, Dict, List, Optional

from sqlmodel import Session, select, delete, text

from condorgame_backend.entities.model import ModelScore
from condorgame_backend.entities.prediction import Prediction, PredictionConfig, PredictionParams, PredictionScore, PredictionStatus

from condorgame_backend.infrastructure.db.db_tables import PredictionRow, PredictionConfigRow

from condorgame_backend.services.interfaces.prediction_repository import PredictionRepository, WindowedScoreRow


class DbPredictionRepository(PredictionRepository):

    def __init__(self, session: Session):
        self._session = session

    # ------------------------------------------------------------
    #                  INTERNAL HELPERS
    # ------------------------------------------------------------

    def _row_to_domain(self, row: PredictionRow) -> Prediction:
        prediction = Prediction(
            id=row.id,
            model_id=row.model_id,
            params=PredictionParams(
                asset=row.asset,
                horizon=row.horizon,
                step=row.step
            ),
            status=PredictionStatus(row.status),
            exec_time=row.exec_time,
            distributions=row.distributions,  # JSONB → list[dict]
            performed_at=row.performed_at,
            resolvable_at=row.resolvable_at,
            score=PredictionScore(
                value=row.score_value,
                success=row.score_success,
                failed_reason=row.score_failed_reason,
                scored_at=row.score_scored_at
            ) if row.score_value else None,
        )

        self._attach_meta(prediction, row)

        return prediction

    def fetch_all_windowed_scores(self) -> List[WindowedScoreRow]:

        now = datetime.now(timezone.utc)

        sql = text("""
            SELECT 
                model_id,
                asset,
                horizon,
                step,
                COUNT(*) AS count,
                MIN(resolvable_at) AS first_resolvable_date,
                AVG(score_value) FILTER (
                    WHERE resolvable_at >= NOW() - INTERVAL '1 second' * :recent_seconds
                ) AS mean_recent,
                AVG(score_value) FILTER (
                    WHERE resolvable_at >= NOW() - INTERVAL '1 second' * :steady_seconds
                ) AS mean_steady,
                AVG(score_value) FILTER (
                    WHERE resolvable_at >= NOW() - INTERVAL '1 second' * :anchor_seconds
                ) AS mean_anchor
            FROM predictions
            WHERE resolvable_at >= NOW() - (INTERVAL '1 second' * :min_resolvable_date) and score_scored_at is not null
            GROUP BY model_id, asset, horizon, step;
        """)

        rows = self._session.execute(
            sql,
            params={
                "recent_seconds": ModelScore.WINDOW_RECENT.total_seconds(),
                "steady_seconds": ModelScore.WINDOW_STEADY.total_seconds(),
                "anchor_seconds": ModelScore.WINDOW_ANCHOR.total_seconds(),
                # Used for performance purposes. We don't need to go much later than the rollover WINDOW_ANCHOR.
                # To account for possible overlaps, a 1-day buffer is added for additional security.
                "min_resolvable_date": (ModelScore.WINDOW_ANCHOR + timedelta(days=1)).total_seconds(),  
            }
        )  # type: ignore

        results: List[WindowedScoreRow] = []

        for r in rows:
            first_resolvable = r.first_resolvable_date.replace(tzinfo=timezone.utc)

            results.append(
                WindowedScoreRow(
                    model_id=r.model_id,
                    asset=r.asset,
                    horizon=r.horizon,
                    step=r.step,
                    count=r.count,
                    recent_mean=r.mean_recent if first_resolvable <= (now - ModelScore.WINDOW_RECENT) else None,
                    steady_mean=r.mean_steady if first_resolvable <= (now - ModelScore.WINDOW_STEADY) else None,
                    anchor_mean=r.mean_anchor if first_resolvable <= (now - ModelScore.WINDOW_ANCHOR) else None,
                )
            )

        return results

    def _domain_to_row(self, p: Prediction) -> PredictionRow:
        row = PredictionRow(
            id=p.id,
            model_id=p.model_id,
            asset=p.params.asset,
            horizon=p.params.horizon,
            step=p.params.step,
            status=p.status.value,
            exec_time=p.exec_time,
            distributions=p.distributions,  # list[dict] → JSONB
            performed_at=p.performed_at,
            resolvable_at=p.resolvable_at,
            score_value=p.score.value if p.score else None,
            score_success=p.score.success if p.score else None,
            score_failed_reason=p.score.failed_reason if p.score else None,
            score_scored_at=p.score.scored_at if p.score else None,
        )
        self._attach_meta(p, row)

        return row

    def _attach_meta(self, domain: any, row: any):
        # bypass __slots__ and attach metadata dynamically
        object.__setattr__(domain, "__meta_row__", row)

    # ------------------------------------------------------------
    #                  PUBLIC METHODS — PREDICTIONS
    # ------------------------------------------------------------

    def fetch_by_id(self, prediction_id: str) -> Optional[Prediction]:
        row = self._session.get(PredictionRow, prediction_id)
        if not row:
            return None
        return self._row_to_domain(row)

    def fetch_ready_to_score(self) -> list[Prediction]:
        stmt = (
            select(PredictionRow)
            .where(PredictionRow.resolvable_at.isnot(None))
            .where(PredictionRow.resolvable_at <= datetime.now(timezone.utc))  # Fix comparison operator
            .where(PredictionRow.score_scored_at.is_(None))
        )
        rows = self._session.exec(stmt).all()
        return [self._row_to_domain(row) for row in rows]

    def _save(self, prediction: Prediction, commit=True) -> None:

        if not hasattr(prediction, "__meta_row__"):
            row = self._domain_to_row(prediction)
            self._session.add(row)
            if commit:
                self._session.commit()
            return

        # EXISTING prediction → update without SELECT
        row: PredictionRow = getattr(prediction, "__meta_row__")
        new_row = self._domain_to_row(prediction)

        for field in PredictionRow.model_fields.keys():
            if field != "id":
                setattr(row, field, getattr(new_row, field))
        if commit:
            self._session.commit()

    def save(self, prediction: Prediction) -> None:
        return self._save(prediction, commit=True)

    def save_all(self, predictions: Iterable[Prediction]) -> None:
        for p in predictions:
            self._save(p, commit=False)
        self._session.commit()

    def prune(self):
        threshold = datetime.now(timezone.utc) - timedelta(days=30)

        stmt = (
            delete(PredictionRow)
            .where(PredictionRow.score_scored_at != None)
            .where(PredictionRow.score_scored_at < threshold)
        )

        result = self._session.exec(stmt)
        self._session.commit()

        # result.rowcount is supported by SQLAlchemy Core
        return result.rowcount or 0

    def query_scores(self, model_ids: list[str], _from: Optional[datetime], to: Optional[datetime]) -> dict[str, list[dict]]:
        stmt = (
            select(
                PredictionRow.id,
                PredictionRow.model_id,
                PredictionRow.asset,
                PredictionRow.horizon,
                PredictionRow.step,
                PredictionRow.score_value,
                PredictionRow.score_success,
                PredictionRow.score_failed_reason,
                PredictionRow.score_scored_at,
                PredictionRow.performed_at
            )
            .where(PredictionRow.model_id.in_(model_ids))
            .where(PredictionRow.score_scored_at != None)
            .where(PredictionRow.performed_at >= _from if _from else True)
            .where(PredictionRow.performed_at <= to if to else True)
        )
        rows = self._session.exec(stmt).all()
        predictions_by_model = {}

        for row in rows:
            if row.model_id not in predictions_by_model:
                predictions_by_model[row.model_id] = []
            predictions_by_model[row.model_id].append(row)

        return predictions_by_model

    # ------------------------------------------------------------
    #            PUBLIC METHODS — PREDICTION CONFIGS
    # ------------------------------------------------------------

    def fetch_active_configs(self) -> list[PredictionConfig]:
        stmt = select(PredictionConfigRow).where(PredictionConfigRow.active == True).order_by(PredictionConfigRow.order)
        rows = self._session.exec(stmt).all()

        return [
            PredictionConfig(
                id=row.id,
                prediction_params=PredictionParams(
                    asset=row.asset,
                    horizon=row.horizon,
                    step=row.step
                ),
                prediction_interval=row.prediction_interval,
                active=row.active,
                order=row.order,
            )
            for row in rows
        ]

    def _save_config(self, config: PredictionConfig, commit: bool = True) -> None:

        # NEW CONFIG (no meta row)
        if not hasattr(config, "__meta_config_row__"):
            row = PredictionConfigRow(
                id=config.id,
                asset=config.prediction_params.asset,
                horizon=config.prediction_params.horizon,
                step=config.prediction_params.step,
                prediction_interval=config.prediction_interval,
                active=config.active,
                order=config.order,
            )

            self._attach_meta(config, row)
            self._session.add(row)

            if commit:
                self._session.commit()
            return

        # EXISTING CONFIG — update the SQLModel row
        row: PredictionConfigRow = getattr(config, "__meta_config_row__")

        for field in PredictionConfigRow.model_fields.values():
            if field != "id":
                setattr(row, field, getattr(row, field))

        if commit:
            self._session.commit()

    def save_config(self, config: PredictionConfig) -> None:
        return self._save_config(config, commit=True)

    def save_all_configs(self, configs: Iterable[PredictionConfig]) -> None:
        configs = list(configs)
        if not configs:
            return

        for cfg in configs:
            self._save_config(cfg, commit=False)

        self._session.commit()

    def delete_configs(self):
        self._session.exec(delete(PredictionConfigRow))
        self._session.commit()
