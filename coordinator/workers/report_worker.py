from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Generator

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlmodel import Session

from coordinator.contracts import CrunchContract
from coordinator.schemas import ReportSchemaEnvelope
from coordinator.db import (
    DBLeaderboardRepository,
    DBFeedRecordRepository,
    DBModelRepository,
    DBPredictionRepository,
    create_session,
)

app = FastAPI(title="Node Template Report Worker")

CONTRACT = CrunchContract()


def auto_report_schema(contract: CrunchContract) -> dict[str, Any]:
    """Auto-generate report schema from the CrunchContract aggregation config."""
    aggregation = contract.aggregation

    # Leaderboard columns: Model column + one per aggregation window
    columns: list[dict[str, Any]] = [
        {
            "id": 1,
            "type": "MODEL",
            "property": "model_id",
            "format": None,
            "displayName": "Model",
            "tooltip": None,
            "nativeConfiguration": {"type": "model", "statusProperty": "status"},
            "order": 0,
        },
    ]
    for i, (window_name, window) in enumerate(aggregation.windows.items()):
        display = window_name.replace("_", " ").title()
        columns.append({
            "id": i + 2,
            "type": "VALUE",
            "property": window_name,
            "format": "decimal-2",
            "displayName": display,
            "tooltip": f"Rolling score over {window.hours}h",
            "nativeConfiguration": None,
            "order": (i + 1) * 10,
        })

    # Chart series from the same windows
    series = [
        {"name": name, "label": name.replace("_", " ").title()}
        for name in aggregation.windows
    ]

    widgets: list[dict[str, Any]] = [
        {
            "id": 1,
            "type": "CHART",
            "displayName": "Score Metrics",
            "tooltip": None,
            "order": 10,
            "endpointUrl": "/reports/models/global",
            "nativeConfiguration": {
                "type": "line",
                "xAxis": {"name": "performed_at"},
                "yAxis": {"series": series, "format": "decimal-2"},
                "displayEvolution": False,
            },
        },
        {
            "id": 2,
            "type": "CHART",
            "displayName": "Predictions",
            "tooltip": None,
            "order": 30,
            "endpointUrl": "/reports/predictions",
            "nativeConfiguration": {
                "type": "line",
                "xAxis": {"name": "performed_at"},
                "yAxis": {
                    "series": [{"name": "score_value"}],
                    "format": "decimal-2",
                },
                "alertConfig": {
                    "reasonField": "score_failed_reason",
                    "field": "score_success",
                },
                "filterConfig": [
                    {"type": "select", "label": "Asset", "property": "asset", "autoSelectFirst": True},
                    {"type": "select", "label": "Horizon", "property": "horizon", "autoSelectFirst": True},
                ],
                "groupByProperty": "param",
                "displayEvolution": False,
            },
        },
        {
            "id": 3,
            "type": "CHART",
            "displayName": "Rolling score by parameters",
            "tooltip": None,
            "order": 20,
            "endpointUrl": "/reports/models/params",
            "nativeConfiguration": {
                "type": "line",
                "xAxis": {"name": "performed_at"},
                "yAxis": {"series": series, "format": "decimal-2"},
                "filterConfig": [
                    {"type": "select", "label": "Asset", "property": "asset", "autoSelectFirst": True},
                    {"type": "select", "label": "Horizon", "property": "horizon", "autoSelectFirst": True},
                ],
                "groupByProperty": "param",
                "displayEvolution": False,
            },
        },
    ]

    schema = {"schema_version": "1", "leaderboard_columns": columns, "metrics_widgets": widgets}

    # Validate against typed contracts
    validated = ReportSchemaEnvelope.model_validate(schema)
    return validated.model_dump()


def _flatten_metrics(metrics: dict[str, Any]) -> dict[str, float | None]:
    flattened: dict[str, float | None] = {}
    for key, value in metrics.items():
        try:
            flattened[f"score_{key}"] = float(value) if value is not None else None
        except Exception:
            flattened[f"score_{key}"] = None
    return flattened


def _compute_window_metrics(scores: list[tuple[datetime, float]], contract: CrunchContract) -> dict[str, float]:
    """Compute windowed metrics from timestamped scores using contract aggregation."""
    now = datetime.now(timezone.utc)
    metrics: dict[str, float] = {}
    for window_name, window in contract.aggregation.windows.items():
        cutoff = now - timedelta(hours=window.hours)
        window_values = [v for ts, v in scores if ts >= cutoff]
        metrics[window_name] = sum(window_values) / len(window_values) if window_values else 0.0
    return metrics


def _normalize_project_ids(raw_ids: list[str]) -> list[str]:
    normalized: list[str] = []
    for item in raw_ids:
        for part in item.split(","):
            stripped = part.strip()
            if stripped:
                normalized.append(stripped)
    return normalized


REPORT_SCHEMA = auto_report_schema(CONTRACT)


def get_db_session() -> Generator[Session, Any, None]:
    with create_session() as session:
        yield session


def get_model_repository(
    session_db: Annotated[Session, Depends(get_db_session)]
) -> DBModelRepository:
    return DBModelRepository(session_db)


def get_leaderboard_repository(
    session_db: Annotated[Session, Depends(get_db_session)]
) -> DBLeaderboardRepository:
    return DBLeaderboardRepository(session_db)


def get_prediction_repository(
    session_db: Annotated[Session, Depends(get_db_session)]
) -> DBPredictionRepository:
    return DBPredictionRepository(session_db)


def get_feed_record_repository(
    session_db: Annotated[Session, Depends(get_db_session)]
) -> DBFeedRecordRepository:
    return DBFeedRecordRepository(session_db)


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
    model_repo: Annotated[DBModelRepository, Depends(get_model_repository)]
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
    leaderboard_repo: Annotated[DBLeaderboardRepository, Depends(get_leaderboard_repository)]
) -> list[dict]:
    leaderboard = leaderboard_repo.get_latest()
    if leaderboard is None:
        return []

    created_at = leaderboard.get("created_at")
    entries = leaderboard.get("entries", [])

    normalized_entries = []
    for entry in entries:
        score = entry.get("score", {})
        metrics = score.get("metrics", {})

        normalized_entries.append(
            {
                "created_at": created_at,
                "model_id": entry.get("model_id"),
                "score_metrics": metrics,
                "score_ranking": score.get("ranking", {}),
                **_flatten_metrics(metrics),
                "rank": entry.get("rank", 999999),
                "model_name": entry.get("model_name"),
                "cruncher_name": entry.get("cruncher_name"),
            }
        )

    return sorted(normalized_entries, key=lambda item: item.get("rank", 999999))


@app.get("/reports/models/global")
def get_models_global(
    model_ids: Annotated[list[str], Query(..., alias="projectIds")],
    start: Annotated[datetime, Query(...)],
    end: Annotated[datetime, Query(...)],
    prediction_repo: Annotated[DBPredictionRepository, Depends(get_prediction_repository)],
) -> list[dict]:
    model_ids = _normalize_project_ids(model_ids)
    predictions_by_model = prediction_repo.query_scores(model_ids=model_ids, _from=start, to=end)

    rows: list[dict] = []
    for model_id, predictions in predictions_by_model.items():
        timed_scores = [
            (p.performed_at, float(p.score.value))
            for p in predictions
            if p.score and p.score.success and p.score.value is not None
        ]
        if not timed_scores:
            continue

        metrics = _compute_window_metrics(timed_scores, CONTRACT)
        performed_at = max((p.performed_at for p in predictions), default=end)

        rows.append(
            {
                "model_id": model_id,
                "score_metrics": metrics,
                "score_ranking": {
                    "key": CONTRACT.aggregation.ranking_key,
                    "value": metrics.get(CONTRACT.aggregation.ranking_key),
                    "direction": CONTRACT.aggregation.ranking_direction,
                },
                **_flatten_metrics(metrics),
                "performed_at": performed_at,
            }
        )

    return rows


@app.get("/reports/models/params")
def get_models_params(
    model_ids: Annotated[list[str], Query(..., alias="projectIds")],
    start: Annotated[datetime, Query(...)],
    end: Annotated[datetime, Query(...)],
    prediction_repo: Annotated[DBPredictionRepository, Depends(get_prediction_repository)],
) -> list[dict]:
    model_ids = _normalize_project_ids(model_ids)
    predictions_by_model = prediction_repo.query_scores(model_ids=model_ids, _from=start, to=end)

    grouped: dict[tuple[str, str], list] = {}
    for model_id, predictions in predictions_by_model.items():
        for prediction in predictions:
            key = (model_id, prediction.scope_key)
            grouped.setdefault(key, []).append(prediction)

    rows: list[dict] = []
    for (model_id, scope_key), predictions in grouped.items():
        timed_scores = [
            (p.performed_at, float(p.score.value))
            for p in predictions
            if p.score and p.score.success and p.score.value is not None
        ]
        if not timed_scores:
            continue

        metrics = _compute_window_metrics(timed_scores, CONTRACT)
        performed_at = max((p.performed_at for p in predictions), default=end)
        scope = predictions[-1].scope if predictions else {}

        rows.append(
            {
                "model_id": model_id,
                "scope_key": scope_key,
                "scope": scope,
                "score_metrics": metrics,
                "score_ranking": {
                    "key": CONTRACT.aggregation.ranking_key,
                    "value": metrics.get(CONTRACT.aggregation.ranking_key),
                    "direction": CONTRACT.aggregation.ranking_direction,
                },
                **_flatten_metrics(metrics),
                "performed_at": performed_at,
            }
        )

    return rows


@app.get("/reports/predictions")
def get_predictions(
    model_ids: Annotated[list[str], Query(..., alias="projectIds")],
    start: Annotated[datetime, Query(...)],
    end: Annotated[datetime, Query(...)],
    prediction_repo: Annotated[DBPredictionRepository, Depends(get_prediction_repository)],
) -> list[dict]:
    model_ids = _normalize_project_ids(model_ids)
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


@app.get("/reports/feeds")
def get_feeds(
    feed_repo: Annotated[DBFeedRecordRepository, Depends(get_feed_record_repository)],
) -> list[dict[str, Any]]:
    return feed_repo.list_indexed_feeds()


@app.get("/reports/feeds/tail")
def get_feeds_tail(
    feed_repo: Annotated[DBFeedRecordRepository, Depends(get_feed_record_repository)],
    source: Annotated[str | None, Query()] = None,
    subject: Annotated[str | None, Query()] = None,
    kind: Annotated[str | None, Query()] = None,
    granularity: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
) -> list[dict[str, Any]]:
    records = feed_repo.tail_records(
        source=source,
        subject=subject,
        kind=kind,
        granularity=granularity,
        limit=limit,
    )

    rows: list[dict[str, Any]] = []
    for record in records:
        rows.append(
            {
                "source": record.source,
                "subject": record.subject,
                "kind": record.kind,
                "granularity": record.granularity,
                "ts_event": record.ts_event,
                "ts_ingested": record.ts_ingested,
                "values": record.values,
                "meta": record.meta,
            }
        )

    return rows


if __name__ == "__main__":
    logging.getLogger(__name__).info("coordinator report worker bootstrap")
    uvicorn.run(app, host="0.0.0.0", port=8000)
