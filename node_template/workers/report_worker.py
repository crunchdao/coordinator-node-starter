from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Annotated, Any, Generator

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlmodel import Session

from coordinator_core.schemas import LeaderboardEntryEnvelope, ReportSchemaEnvelope
from coordinator_core.services.interfaces.leaderboard_repository import LeaderboardRepository
from coordinator_core.services.interfaces.market_record_repository import MarketRecordRepository
from coordinator_core.services.interfaces.model_repository import ModelRepository
from coordinator_core.services.interfaces.prediction_repository import PredictionRepository
from node_template.extensions.callable_resolver import resolve_callable
from node_template.extensions.default_callables import (
    default_compute_window_metrics,
    default_flatten_report_metrics,
)
from node_template.infrastructure.db import (
    DBLeaderboardRepository,
    DBMarketRecordRepository,
    DBModelRepository,
    DBPredictionRepository,
    create_session,
)

app = FastAPI(title="Node Template Report Worker")


def _normalize_project_ids(raw_ids: list[str]) -> list[str]:
    """Normalize projectIds: the FE may send comma-separated (e.g. '1,2,3')
    or repeated params (e.g. projectIds=1&projectIds=2).
    This handles both forms."""
    normalized: list[str] = []
    for item in raw_ids:
        for part in item.split(","):
            stripped = part.strip()
            if stripped:
                normalized.append(stripped)
    return normalized


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


def get_market_record_repository(
    session_db: Annotated[Session, Depends(get_db_session)]
) -> MarketRecordRepository:
    return DBMarketRecordRepository(session_db)


def resolve_report_schema(provider_path: str | None = None) -> dict[str, Any]:
    configured_path = provider_path or os.getenv(
        "REPORT_SCHEMA_PROVIDER",
        "node_template.extensions.default_callables:default_report_schema",
    )
    provider = resolve_callable(configured_path)
    schema = provider()
    if not isinstance(schema, dict):
        raise ValueError("REPORT_SCHEMA_PROVIDER must return a dictionary")

    # Validate against typed contracts matching the coordinator-webapp FE types.
    # This catches missing/wrong fields at startup instead of crashing the FE
    # at render time (e.g. missing 'type' → TypeError: Cannot read properties
    # of undefined reading 'toLowerCase').
    try:
        validated = ReportSchemaEnvelope.model_validate(schema)
    except Exception as exc:
        raise ValueError(
            f"REPORT_SCHEMA_PROVIDER returned an invalid schema. "
            f"Each leaderboard column must have: id, type (MODEL|VALUE|USERNAME|CHART), "
            f"property, displayName, order. "
            f"Each metric widget must have: id, type (CHART|IFRAME), displayName, "
            f"endpointUrl, order. "
            f"Validation error: {exc}"
        ) from exc

    return validated.model_dump()


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
                **default_flatten_report_metrics(metrics),
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
    model_ids = _normalize_project_ids(model_ids)
    predictions_by_model = prediction_repo.query_scores(model_ids=model_ids, _from=start, to=end)

    rows: list[dict] = []
    for model_id, predictions in predictions_by_model.items():
        scores = [p.score.value for p in predictions if p.score and p.score.success and p.score.value is not None]
        if not scores:
            continue

        metrics = default_compute_window_metrics([float(value) for value in scores])
        performed_at = max((p.performed_at for p in predictions), default=end)

        rows.append(
            {
                "model_id": model_id,
                "score_metrics": metrics,
                "score_ranking": {
                    "key": "anchor",
                    "value": metrics.get("anchor"),
                    "direction": "desc",
                },
                **default_flatten_report_metrics(metrics),
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
    model_ids = _normalize_project_ids(model_ids)
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

        metrics = default_compute_window_metrics([float(value) for value in scores])
        performed_at = max((p.performed_at for p in predictions), default=end)
        scope = predictions[-1].scope if predictions else {}

        rows.append(
            {
                "model_id": model_id,
                "scope_key": scope_key,
                "scope": scope,
                "score_metrics": metrics,
                "score_ranking": {
                    "key": "anchor",
                    "value": metrics.get("anchor"),
                    "direction": "desc",
                },
                **default_flatten_report_metrics(metrics),
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
    market_repo: Annotated[MarketRecordRepository, Depends(get_market_record_repository)],
) -> list[dict[str, Any]]:
    return market_repo.list_indexed_feeds()


@app.get("/reports/feeds/tail")
def get_feeds_tail(
    market_repo: Annotated[MarketRecordRepository, Depends(get_market_record_repository)],
    provider: Annotated[str | None, Query()] = None,
    asset: Annotated[str | None, Query()] = None,
    kind: Annotated[str | None, Query()] = None,
    granularity: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
) -> list[dict[str, Any]]:
    records = market_repo.tail_records(
        provider=provider,
        asset=asset,
        kind=kind,
        granularity=granularity,
        limit=limit,
    )

    rows: list[dict[str, Any]] = []
    for record in records:
        rows.append(
            {
                "provider": record.provider,
                "asset": record.asset,
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
    logging.getLogger(__name__).info("node_template report worker bootstrap")
    uvicorn.run(app, host="0.0.0.0", port=8000)
