from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Generator

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlmodel import Session

from coordinator_node.contracts import CrunchContract
from coordinator_node.entities.prediction import CheckpointStatus
from coordinator_node.schemas import ReportSchemaEnvelope
from coordinator_node.db import (
    DBCheckpointRepository,
    DBLeaderboardRepository,
    DBFeedRecordRepository,
    DBModelRepository,
    DBPredictionRepository,
    DBSnapshotRepository,
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
                    {"type": "select", "label": "Subject", "property": "subject", "autoSelectFirst": True},
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
                    {"type": "select", "label": "Subject", "property": "subject", "autoSelectFirst": True},
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


def get_snapshot_repository(
    session_db: Annotated[Session, Depends(get_db_session)]
) -> DBSnapshotRepository:
    return DBSnapshotRepository(session_db)


def get_checkpoint_repository(
    session_db: Annotated[Session, Depends(get_db_session)]
) -> DBCheckpointRepository:
    return DBCheckpointRepository(session_db)


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
    prediction_repo: Annotated[DBPredictionRepository, Depends(get_prediction_repository)],
    model_repo: Annotated[DBModelRepository, Depends(get_model_repository)],
    model_ids: Annotated[list[str] | None, Query(alias="projectIds")] = None,
    start: Annotated[datetime | None, Query()] = None,
    end: Annotated[datetime | None, Query()] = None,
) -> list[dict]:
    if not model_ids:
        model_ids = list(model_repo.fetch_all().keys())
    else:
        model_ids = _normalize_project_ids(model_ids)
    if not model_ids:
        return []
    if end is None:
        end = datetime.now(timezone.utc)
    if start is None:
        start = end - timedelta(days=7)
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
    prediction_repo: Annotated[DBPredictionRepository, Depends(get_prediction_repository)],
    model_repo: Annotated[DBModelRepository, Depends(get_model_repository)],
    model_ids: Annotated[list[str] | None, Query(alias="projectIds")] = None,
    start: Annotated[datetime | None, Query()] = None,
    end: Annotated[datetime | None, Query()] = None,
) -> list[dict]:
    if not model_ids:
        model_ids = list(model_repo.fetch_all().keys())
    else:
        model_ids = _normalize_project_ids(model_ids)
    if not model_ids:
        return []
    if end is None:
        end = datetime.now(timezone.utc)
    if start is None:
        start = end - timedelta(days=7)
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
    prediction_repo: Annotated[DBPredictionRepository, Depends(get_prediction_repository)],
    model_repo: Annotated[DBModelRepository, Depends(get_model_repository)],
    model_ids: Annotated[list[str] | None, Query(alias="projectIds")] = None,
    start: Annotated[datetime | None, Query()] = None,
    end: Annotated[datetime | None, Query()] = None,
) -> list[dict]:
    if not model_ids:
        model_ids = list(model_repo.fetch_all().keys())
    else:
        model_ids = _normalize_project_ids(model_ids)
    if not model_ids:
        return []
    if end is None:
        end = datetime.now(timezone.utc)
    if start is None:
        start = end - timedelta(days=7)
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


# ── Snapshots ──


@app.get("/reports/snapshots")
def get_snapshots(
    snapshot_repo: Annotated[DBSnapshotRepository, Depends(get_snapshot_repository)],
    model_id: Annotated[str | None, Query()] = None,
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[dict[str, Any]]:
    snapshots = snapshot_repo.find(model_id=model_id, since=since, until=until, limit=limit)
    return [
        {
            "id": s.id,
            "model_id": s.model_id,
            "period_start": s.period_start,
            "period_end": s.period_end,
            "prediction_count": s.prediction_count,
            "result_summary": s.result_summary,
            "created_at": s.created_at,
        }
        for s in snapshots
    ]


# ── Checkpoints ──


@app.get("/reports/checkpoints")
def get_checkpoints(
    checkpoint_repo: Annotated[DBCheckpointRepository, Depends(get_checkpoint_repository)],
    checkpoint_status: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[dict[str, Any]]:
    checkpoints = checkpoint_repo.find(status=checkpoint_status, limit=limit)
    return [_checkpoint_to_dict(c) for c in checkpoints]


@app.get("/reports/checkpoints/latest")
def get_latest_checkpoint(
    checkpoint_repo: Annotated[DBCheckpointRepository, Depends(get_checkpoint_repository)],
) -> dict[str, Any]:
    checkpoint = checkpoint_repo.get_latest()
    if checkpoint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No checkpoints found")
    return _checkpoint_to_dict(checkpoint)


@app.get("/reports/checkpoints/{checkpoint_id}/payload")
def get_checkpoint_payload(
    checkpoint_id: str,
    checkpoint_repo: Annotated[DBCheckpointRepository, Depends(get_checkpoint_repository)],
) -> dict[str, Any]:
    checkpoints = checkpoint_repo.find()
    checkpoint = next((c for c in checkpoints if c.id == checkpoint_id), None)
    if checkpoint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checkpoint not found")
    return {
        "checkpoint_id": checkpoint.id,
        "period_start": checkpoint.period_start.isoformat(),
        "period_end": checkpoint.period_end.isoformat(),
        "entries": checkpoint.entries,
    }


@app.post("/reports/checkpoints/{checkpoint_id}/confirm")
def confirm_checkpoint(
    checkpoint_id: str,
    body: dict[str, Any],
    checkpoint_repo: Annotated[DBCheckpointRepository, Depends(get_checkpoint_repository)],
) -> dict[str, Any]:
    checkpoints = checkpoint_repo.find()
    checkpoint = next((c for c in checkpoints if c.id == checkpoint_id), None)
    if checkpoint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checkpoint not found")
    if checkpoint.status != CheckpointStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Checkpoint is {checkpoint.status}, expected PENDING",
        )

    tx_hash = body.get("tx_hash")
    if not tx_hash:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="tx_hash required")

    checkpoint.status = CheckpointStatus.SUBMITTED
    checkpoint.tx_hash = tx_hash
    checkpoint.submitted_at = datetime.now(timezone.utc)
    checkpoint_repo.save(checkpoint)

    return _checkpoint_to_dict(checkpoint)


@app.patch("/reports/checkpoints/{checkpoint_id}/status")
def update_checkpoint_status(
    checkpoint_id: str,
    body: dict[str, Any],
    checkpoint_repo: Annotated[DBCheckpointRepository, Depends(get_checkpoint_repository)],
) -> dict[str, Any]:
    checkpoints = checkpoint_repo.find()
    checkpoint = next((c for c in checkpoints if c.id == checkpoint_id), None)
    if checkpoint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checkpoint not found")

    new_status = body.get("status")
    valid_transitions: dict[CheckpointStatus, list[CheckpointStatus]] = {
        CheckpointStatus.PENDING: [CheckpointStatus.SUBMITTED],
        CheckpointStatus.SUBMITTED: [CheckpointStatus.CLAIMABLE],
        CheckpointStatus.CLAIMABLE: [CheckpointStatus.PAID],
    }
    allowed = valid_transitions.get(CheckpointStatus(checkpoint.status), [])
    try:
        new_status = CheckpointStatus(new_status)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status: {new_status}. Valid: {[s.value for s in CheckpointStatus]}",
        )
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot transition from {checkpoint.status} to {new_status}. Allowed: {allowed}",
        )

    checkpoint.status = new_status
    checkpoint_repo.save(checkpoint)

    return _checkpoint_to_dict(checkpoint)


# ── Emissions ──


@app.get("/reports/checkpoints/{checkpoint_id}/emission")
def get_checkpoint_emission(
    checkpoint_id: str,
    checkpoint_repo: Annotated[DBCheckpointRepository, Depends(get_checkpoint_repository)],
) -> dict[str, Any]:
    """Return the EmissionCheckpoint in protocol format for on-chain submission."""
    checkpoints = checkpoint_repo.find()
    checkpoint = next((c for c in checkpoints if c.id == checkpoint_id), None)
    if checkpoint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checkpoint not found")
    if not checkpoint.entries:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No emission data in checkpoint")
    return checkpoint.entries[0]


@app.get("/reports/checkpoints/{checkpoint_id}/emission/cli-format")
def get_checkpoint_emission_cli_format(
    checkpoint_id: str,
    checkpoint_repo: Annotated[DBCheckpointRepository, Depends(get_checkpoint_repository)],
) -> dict[str, Any]:
    """Return emission in coordinator-cli JSON file format.

    Format: {crunch, crunchEmission: {wallet: pct}, computeProvider: {addr: pct}, dataProvider: {addr: pct}}
    where pct values are percentages (0-100).
    """
    checkpoints = checkpoint_repo.find()
    checkpoint = next((c for c in checkpoints if c.id == checkpoint_id), None)
    if checkpoint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checkpoint not found")
    if not checkpoint.entries:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No emission data in checkpoint")

    emission = checkpoint.entries[0]
    frac64_multiplier = 1_000_000_000

    # Build crunchEmission: map cruncher_index → percentage
    # Note: in production, cruncher_index maps to wallet addresses via the on-chain AddressIndexMap.
    # The ranking in checkpoint.meta provides model_id for each index.
    ranking = checkpoint.meta.get("ranking", [])
    crunch_emission: dict[str, float] = {}
    for reward in emission.get("cruncher_rewards", []):
        idx = reward["cruncher_index"]
        pct = reward["reward_pct"] / frac64_multiplier * 100.0
        # Use model_id from ranking as key (operator maps to wallet externally)
        model_id = ranking[idx]["model_id"] if idx < len(ranking) else str(idx)
        crunch_emission[model_id] = round(pct, 6)

    compute_provider: dict[str, float] = {}
    for reward in emission.get("compute_provider_rewards", []):
        pct = reward["reward_pct"] / frac64_multiplier * 100.0
        compute_provider[reward["provider"]] = round(pct, 6)

    data_provider: dict[str, float] = {}
    for reward in emission.get("data_provider_rewards", []):
        pct = reward["reward_pct"] / frac64_multiplier * 100.0
        data_provider[reward["provider"]] = round(pct, 6)

    return {
        "crunch": emission.get("crunch", ""),
        "crunchEmission": crunch_emission,
        "computeProvider": compute_provider,
        "dataProvider": data_provider,
    }


@app.get("/reports/emissions/latest")
def get_latest_emission(
    checkpoint_repo: Annotated[DBCheckpointRepository, Depends(get_checkpoint_repository)],
) -> dict[str, Any]:
    """Return the emission from the most recent checkpoint."""
    checkpoint = checkpoint_repo.get_latest()
    if checkpoint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No checkpoints found")
    if not checkpoint.entries:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No emission data in checkpoint")
    return {
        "checkpoint_id": checkpoint.id,
        "status": checkpoint.status,
        "period_start": checkpoint.period_start,
        "period_end": checkpoint.period_end,
        "emission": checkpoint.entries[0],
    }


def _checkpoint_to_dict(c) -> dict[str, Any]:
    return {
        "id": c.id,
        "period_start": c.period_start,
        "period_end": c.period_end,
        "status": c.status,
        "entries": c.entries,
        "meta": c.meta,
        "created_at": c.created_at,
        "tx_hash": c.tx_hash,
        "submitted_at": c.submitted_at,
    }


if __name__ == "__main__":
    logging.getLogger(__name__).info("coordinator report worker bootstrap")
    uvicorn.run(app, host="0.0.0.0", port=8000)
