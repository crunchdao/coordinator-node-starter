---
name: coordinator-leaderboard-reports
description: Use when customizing leaderboard ranking, adding report endpoints, or exposing new metrics via the API
---

# Customizing Leaderboard & Reports

Modify ranking logic, add new API endpoints, expose custom metrics.

## Architecture

```
Score Worker                    Report Worker (FastAPI)
     ↓                                ↓
compute_leaderboard()          GET /reports/leaderboard
     ↓                         GET /reports/models
Leaderboard.create()           GET /reports/models/global
     ↓                         GET /reports/models/params
Save to DB                     GET /reports/predictions
```

## Key Files

| File | Purpose |
|------|---------|
| `entities/leaderboard.py` | `Leaderboard.create()` ranking logic |
| `entities/model.py` | `ModelScore`, `calc_overall_score()` |
| `workers/report_worker.py` | FastAPI endpoints |
| `infrastructure/db/db_leaderboard_repository.py` | Leaderboard persistence |

## Step-by-Step: Custom Ranking Logic

### 1. Understand Current Ranking

In `entities/leaderboard.py`:

```python
@staticmethod
def create(models: Iterable[Model]) -> "Leaderboard":
    sorted_models = sorted(
        models,
        key=lambda model: (
            model.overall_score.anchor if model.overall_score and model.overall_score.anchor is not None else float('-inf'),
            model.overall_score.steady if model.overall_score and model.overall_score.steady else float('-inf'),
            model.overall_score.recent if model.overall_score and model.overall_score.recent else float('-inf'),
        ),
        reverse=True  # Descending: higher score = better rank
    )
```

**Current logic:** Sort by anchor first, then steady, then recent (tiebreakers).

### 2. Custom Ranking: Weighted Score

```python
# entities/leaderboard.py

def _get_weighted_score(model: Model) -> float:
    """Combine scores with weights: 50% anchor, 30% steady, 20% recent."""
    if not model.overall_score:
        return float('-inf')
    
    score = model.overall_score
    anchor = score.anchor if score.anchor is not None else 0
    steady = score.steady if score.steady is not None else 0
    recent = score.recent if score.recent is not None else 0
    
    return 0.5 * anchor + 0.3 * steady + 0.2 * recent

@staticmethod
def create(models: Iterable[Model]) -> "Leaderboard":
    sorted_models = sorted(models, key=_get_weighted_score, reverse=True)
    # ... rest unchanged
```

### 3. Custom Ranking: Minimum Games Requirement

```python
MIN_PREDICTIONS_FOR_RANKING = 100

@staticmethod
def create(models: Iterable[Model]) -> "Leaderboard":
    # Filter models with insufficient history
    eligible_models = [m for m in models if m.prediction_count >= MIN_PREDICTIONS_FOR_RANKING]
    
    sorted_models = sorted(eligible_models, key=_get_weighted_score, reverse=True)
    
    # Generate entries with ranks
    entries = [
        LeaderboardEntry(
            rank=index + 1,
            model_id=model.crunch_identifier,
            score=model.overall_score,
            model_name=model.name,
            player_name=model.player.name
        )
        for index, model in enumerate(sorted_models)
    ]
    # ...
```

**Note:** You'll need to add `prediction_count` to the `Model` entity and populate it.

### 4. Custom Ranking: Separate Leaderboards

For multiple leaderboards (e.g., by asset):

```python
# entities/leaderboard.py

@dataclass
class Leaderboard:
    id: str
    entries: list[LeaderboardEntry]
    created_at: datetime
    category: str = "overall"  # Add category field

@staticmethod
def create_by_asset(models: Iterable[Model], asset: str) -> "Leaderboard":
    """Create leaderboard for a specific asset."""
    sorted_models = sorted(
        models,
        key=lambda m: _get_asset_score(m, asset),
        reverse=True
    )
    
    return Leaderboard(
        id=f"LBR_{asset}_{datetime.now()...}",
        entries=[...],
        created_at=datetime.now(timezone.utc),
        category=asset
    )

def _get_asset_score(model: Model, asset: str) -> float:
    for sbp in model.scores_by_param:
        if sbp.param.asset == asset:
            return sbp.score.anchor or float('-inf')
    return float('-inf')
```

## Step-by-Step: Add New API Endpoint

### 1. Define Response Schema

In `workers/report_worker.py`, add Pydantic model:

```python
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class ModelStatsResponse(BaseModel):
    model_id: str
    model_name: str
    total_predictions: int
    successful_predictions: int
    average_score: Optional[float]
    best_asset: Optional[str]
    worst_asset: Optional[str]
```

### 2. Add Repository Method (if needed)

In `infrastructure/db/db_model_repository.py`:

```python
def fetch_model_stats(self, model_id: str) -> dict:
    """Fetch aggregated stats for a model."""
    query = text("""
        SELECT 
            model_id,
            COUNT(*) as total_predictions,
            COUNT(*) FILTER (WHERE score_success = true) as successful_predictions,
            AVG(score_value) FILTER (WHERE score_success = true) as average_score
        FROM predictions
        WHERE model_id = :model_id
        GROUP BY model_id
    """)
    
    result = self.session.execute(query, {"model_id": model_id}).fetchone()
    return dict(result) if result else None
```

### 3. Add Endpoint

In `workers/report_worker.py`:

```python
@app.get("/reports/models/{model_id}/stats", response_model=ModelStatsResponse)
def get_model_stats(
    model_id: str,
    model_repo: Annotated[ModelRepository, Depends(get_model_repository)],
    prediction_repo: Annotated[PredictionRepository, Depends(get_prediction_repository)],
):
    """Get detailed statistics for a specific model."""
    model = model_repo.fetch(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    stats = prediction_repo.fetch_model_stats(model_id)
    
    # Find best/worst asset
    best_asset = None
    worst_asset = None
    if model.scores_by_param:
        sorted_by_score = sorted(
            model.scores_by_param,
            key=lambda x: x.score.anchor or float('-inf'),
            reverse=True
        )
        best_asset = sorted_by_score[0].param.asset
        worst_asset = sorted_by_score[-1].param.asset
    
    return ModelStatsResponse(
        model_id=model.crunch_identifier,
        model_name=model.name,
        total_predictions=stats["total_predictions"],
        successful_predictions=stats["successful_predictions"],
        average_score=stats["average_score"],
        best_asset=best_asset,
        worst_asset=worst_asset,
    )
```

### 4. Test Endpoint

```bash
# Start stack
make deploy

# Test new endpoint
curl http://localhost:8000/reports/models/YOUR_MODEL_ID/stats | jq
```

## Step-by-Step: Add Time-Series Metrics

For metrics that change over time (e.g., model performance history):

### 1. Use Existing Snapshots

`ModelScoreSnapshot` already stores historical scores. Query them:

```python
@app.get("/reports/models/{model_id}/history", response_model=List[ScoreHistoryResponse])
def get_model_history(
    model_id: str,
    start: Annotated[datetime, Query(...)],
    end: Annotated[datetime, Query(...)],
    model_repo: Annotated[ModelRepository, Depends(get_model_repository)],
):
    """Get score history for a model."""
    snapshots = model_repo.fetch_model_score_snapshots(
        model_ids=[model_id],
        _from=start,
        to=end
    )
    
    return [
        ScoreHistoryResponse(
            timestamp=snap.performed_at,
            score_recent=snap.overall_score.recent,
            score_steady=snap.overall_score.steady,
            score_anchor=snap.overall_score.anchor,
        )
        for snap in snapshots.get(model_id, [])
    ]
```

### 2. Add Custom Metrics Table

For metrics not in snapshots, create new table:

```python
# infrastructure/db/db_tables.py

class CustomMetricRow(SQLModel, table=True):
    __tablename__ = "custom_metrics"
    
    id: str = Field(primary_key=True)
    model_id: str = Field(index=True, foreign_key="models.crunch_identifier")
    metric_name: str = Field(index=True)
    metric_value: float
    recorded_at: datetime = Field(index=True)
```

Run `init_db` to create the table.

### 3. Record Metrics in Score Worker

```python
# services/score_service.py

def record_custom_metrics(self):
    """Record custom metrics after scoring."""
    for model in self.models.values():
        # Example: prediction volatility
        volatility = self._calculate_volatility(model)
        
        metric = CustomMetricRow(
            id=f"MTR_{model.crunch_identifier}_{datetime.now()...}",
            model_id=model.crunch_identifier,
            metric_name="prediction_volatility",
            metric_value=volatility,
            recorded_at=datetime.now(timezone.utc)
        )
        self.session.add(metric)
    
    self.session.commit()
```

## Step-by-Step: Modify Existing Endpoints

### Add Fields to Leaderboard Response

```python
# workers/report_worker.py

class LeaderboardEntryResponse(BaseModel):
    # ... existing fields ...
    rank: int
    model_id: str
    score_recent: Optional[float]
    score_steady: Optional[float]
    score_anchor: Optional[float]
    
    # Add new fields
    combined_score: Optional[float]
    rank_change_24h: Optional[int]  # +2 means moved up 2 spots

@app.get("/reports/leaderboard", response_model=List[LeaderboardEntryResponse])
def get_leaderboard(...):
    leaderboard = leaderboard_repo.get_latest()
    previous_leaderboard = leaderboard_repo.get_previous()  # You'll need to implement this
    
    previous_ranks = {e.model_id: e.rank for e in previous_leaderboard.entries} if previous_leaderboard else {}
    
    return [
        LeaderboardEntryResponse(
            # ... existing mappings ...
            combined_score=0.5 * (entry.score.anchor or 0) + 0.3 * (entry.score.steady or 0) + 0.2 * (entry.score.recent or 0),
            rank_change_24h=previous_ranks.get(entry.model_id, entry.rank) - entry.rank,
        )
        for entry in entries_sorted
    ]
```

## Testing Changes

```bash
# View report worker logs
make logs SERVICES=report-worker

# Test endpoints
curl http://localhost:8000/reports/leaderboard | jq
curl http://localhost:8000/reports/models | jq
curl "http://localhost:8000/reports/models/global?projectIds=model1&start=2026-01-01T00:00:00Z&end=2026-02-09T00:00:00Z" | jq

# Check OpenAPI docs
open http://localhost:8000/docs
```

## Common Issues

| Issue | Solution |
|-------|----------|
| 422 Validation Error | Check query parameter format, especially dates |
| Empty leaderboard | Score worker hasn't run yet, wait for predictions to resolve |
| Missing model in response | Model hasn't made predictions or hasn't been scored |
| Stale data | Score worker runs every 15 min, leaderboard updates after scoring |
