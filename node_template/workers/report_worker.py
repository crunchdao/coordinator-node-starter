from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Annotated, Any, Generator

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlmodel import Session

from coordinator_core.schemas import LeaderboardEntryEnvelope
from coordinator_core.services.interfaces.leaderboard_repository import LeaderboardRepository
from coordinator_core.services.interfaces.model_repository import ModelRepository
from coordinator_core.services.interfaces.prediction_repository import PredictionRepository
from node_template.extensions.callable_resolver import resolve_callable
from node_template.extensions.risk_adjusted_callables import compute_return_metrics, flatten_risk_metrics
from node_template.infrastructure.db import (
    DBLeaderboardRepository,
    DBModelRepository,
    DBPredictionRepository,
    create_session,
)

app = FastAPI(title="Node Template Report Worker")


def get_db_session() -> Generator[Session, Any, None]:
    with create_session() as session:
        yield session


def get_model_repository(
    session_db: Annotated[Session, Depends(get_db_session)]
) -> ModelRepository:
    return DBModelRepository(session_db)


def get_leaderboard_repository(
    session_db: Annotated[Session, Depends(get_db_session)]
) -> LeaderboardRepository:
    return DBLeaderboardRepository(session_db)


def get_prediction_repository(
    session_db: Annotated[Session, Depends(get_db_session)]
) -> PredictionRepository:
    return DBPredictionRepository(session_db)


def resolve_report_schema(provider_path: str | None = None) -> dict[str, Any]:
    configured_path = provider_path or os.getenv(
        "REPORT_SCHEMA_PROVIDER",
        "node_template.extensions.default_callables:default_report_schema",
    )
    provider = resolve_callable(configured_path)
    schema = provider()
    if not isinstance(schema, dict):
        raise ValueError("REPORT_SCHEMA_PROVIDER must return a dictionary")

    leaderboard_columns = schema.get("leaderboard_columns")
    metrics_widgets = schema.get("metrics_widgets")
    if not isinstance(leaderboard_columns, list):
        raise ValueError("Report schema must define list field 'leaderboard_columns'")
    if not isinstance(metrics_widgets, list):
        raise ValueError("Report schema must define list field 'metrics_widgets'")

    return {
        "schema_version": str(schema.get("schema_version", "1")),
        "leaderboard_columns": leaderboard_columns,
        "metrics_widgets": metrics_widgets,
    }


REPORT_SCHEMA = resolve_report_schema()


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/reports/schema")
def get_report_schema() -> dict[str, Any]:
    return REPORT_SCHEMA


@app.get("/reports/schema/leaderboard-columns")
def get_report_schema_leaderboard_columns() -> list[dict[str, Any]]:
    return list(REPORT_SCHEMA.get("leaderboard_columns", []))


@app.get("/reports/schema/metrics-widgets")
def get_report_schema_metrics_widgets() -> list[dict[str, Any]]:
    return list(REPORT_SCHEMA.get("metrics_widgets", []))


@app.get("/reports/models")
def get_models(
    model_repo: Annotated[ModelRepository, Depends(get_model_repository)]
) -> list[dict]:
    models = model_repo.fetch_all()

    return [
        {
            "model_id": model.id,
            "model_name": model.name,
            "cruncher_name": model.player_name,
            "cruncher_id": model.player_id,
            "deployment_id": model.deployment_identifier,
        }
        for model in models.values()
    ]


@app.get("/reports/leaderboard")
def get_leaderboard(
    leaderboard_repo: Annotated[LeaderboardRepository, Depends(get_leaderboard_repository)]
) -> list[dict]:
    leaderboard = leaderboard_repo.get_latest()
    if leaderboard is None:
        return []

    created_at = leaderboard.get("created_at")
    entries = leaderboard.get("entries", [])

    normalized_entries = []
    for entry in entries:
        normalized = LeaderboardEntryEnvelope.model_validate(entry)
        metrics = dict(normalized.score.metrics)

        normalized_entries.append(
            {
                "created_at": created_at,
                "model_id": normalized.model_id,
                "score_metrics": metrics,
                "score_ranking": normalized.score.ranking.model_dump(exclude_none=True),
                "score_payload": dict(normalized.score.payload),
                **flatten_risk_metrics(metrics),
                "rank": normalized.rank if normalized.rank is not None else 999999,
                "model_name": normalized.model_name,
                "cruncher_name": normalized.cruncher_name,
            }
        )

    return sorted(normalized_entries, key=lambda item: item.get("rank", 999999))


@app.get("/reports/models/global")
def get_models_global(
    model_ids: Annotated[list[str], Query(..., alias="projectIds")],
    start: Annotated[datetime, Query(...)],
    end: Annotated[datetime, Query(...)],
    prediction_repo: Annotated[PredictionRepository, Depends(get_prediction_repository)],
) -> list[dict]:
    predictions_by_model = prediction_repo.query_scores(model_ids=model_ids, _from=start, to=end)

    rows: list[dict] = []
    for model_id, predictions in predictions_by_model.items():
        scores = [p.score.value for p in predictions if p.score and p.score.success and p.score.value is not None]
        if not scores:
            continue

        metrics = compute_return_metrics([float(value) for value in scores])
        performed_at = max((p.performed_at for p in predictions), default=end)

        rows.append(
            {
                "model_id": model_id,
                "score_metrics": metrics,
                "score_ranking": {
                    "key": "sharpe_like",
                    "value": metrics.get("sharpe_like"),
                    "direction": "desc",
                    "tie_breakers": ["wealth", "mean_return"],
                },
                **flatten_risk_metrics(metrics),
                "performed_at": performed_at,
            }
        )

    return rows


@app.get("/reports/models/params")
def get_models_params(
    model_ids: Annotated[list[str], Query(..., alias="projectIds")],
    start: Annotated[datetime, Query(...)],
    end: Annotated[datetime, Query(...)],
    prediction_repo: Annotated[PredictionRepository, Depends(get_prediction_repository)],
) -> list[dict]:
    predictions_by_model = prediction_repo.query_scores(model_ids=model_ids, _from=start, to=end)

    grouped: dict[tuple[str, str], list] = {}
    for model_id, predictions in predictions_by_model.items():
        for prediction in predictions:
            key = (model_id, prediction.scope_key)
            grouped.setdefault(key, []).append(prediction)

    rows: list[dict] = []
    for (model_id, scope_key), predictions in grouped.items():
        scores = [p.score.value for p in predictions if p.score and p.score.success and p.score.value is not None]
        if not scores:
            continue

        metrics = compute_return_metrics([float(value) for value in scores])
        performed_at = max((p.performed_at for p in predictions), default=end)
        scope = predictions[-1].scope if predictions else {}

        rows.append(
            {
                "model_id": model_id,
                "scope_key": scope_key,
                "scope": scope,
                "score_metrics": metrics,
                "score_ranking": {
                    "key": "sharpe_like",
                    "value": metrics.get("sharpe_like"),
                    "direction": "desc",
                    "tie_breakers": ["wealth", "mean_return"],
                },
                **flatten_risk_metrics(metrics),
                "performed_at": performed_at,
            }
        )

    return rows


@app.get("/reports/predictions")
def get_predictions(
    model_ids: Annotated[list[str], Query(..., alias="projectIds")],
    start: Annotated[datetime, Query(...)],
    end: Annotated[datetime, Query(...)],
    prediction_repo: Annotated[PredictionRepository, Depends(get_prediction_repository)],
) -> list[dict]:
    if len(model_ids) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Service is available only for one model at a time. Please provide a single model_id.",
        )

    predictions_by_model = prediction_repo.query_scores(model_ids=model_ids, _from=start, to=end)

    rows: list[dict] = []
    for _, predictions in predictions_by_model.items():
        for prediction in predictions:
            score = prediction.score
            rows.append(
                {
                    "model_id": prediction.model_id,
                    "prediction_config_id": prediction.prediction_config_id,
                    "scope_key": prediction.scope_key,
                    "scope": prediction.scope,
                    "score_value": score.value if score else None,
                    "score_failed": (not score.success) if score else True,
                    "score_failed_reason": score.failed_reason if score else "Prediction not scored",
                    "scored_at": score.scored_at if score else None,
                    "performed_at": prediction.performed_at,
                }
            )

    return sorted(rows, key=lambda row: row["performed_at"])


if __name__ == "__main__":
    logging.getLogger(__name__).info("node_template report worker bootstrap")
    uvicorn.run(app, host="0.0.0.0", port=8000)
