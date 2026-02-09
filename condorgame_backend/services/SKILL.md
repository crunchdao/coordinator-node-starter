---
name: coordinator-scoring
description: Use when customizing the scoring algorithm - replacing density_pdf scoring with custom metrics or changing rolling window calculations
---

# Customizing Scoring

Replace the density_pdf scoring algorithm with your own, or modify rolling windows and aggregation.

## Current Scoring Flow

```
score_predictions()
    ↓
For each prediction ready to score:
    ↓
score_prediction(prediction)
    → Compare distribution vs actual prices
    → Return PredictionScore(value, success, reason)
    ↓
score_models()
    → Aggregate by rolling windows (24h, 72h, 7d)
    → Calculate overall_score per model
    ↓
compute_leaderboard()
    → Rank models by overall_score
```

## Key Files

| File | What It Does |
|------|--------------|
| `services/score_service.py` | Main scoring logic |
| `entities/prediction.py` | `PredictionScore` dataclass |
| `entities/model.py` | `ModelScore`, rolling windows |
| `infrastructure/db/db_prediction_repository.py` | Window aggregation SQL |

## Step-by-Step: Custom Scoring Algorithm

### 1. Understand Current Scoring

In `score_service.py`, the `score_prediction()` method:

```python
def score_prediction(self, prediction: Prediction):
    # Current: uses density_pdf to score probability distributions
    for density_prediction in prediction.distributions[::-1]:
        current_price = self.prices_cache.get_closest_price(asset, ts)
        previous_price = self.prices_cache.get_closest_price(asset, ts - step)
        
        delta_price = np.log(price_current) - np.log(price_prev)
        pdf_value = density_pdf(density_dict=density_prediction, x=delta_price)
        densities.append(pdf_value)
    
    return PredictionScore(float(numpy.mean(densities)), True, None)
```

### 2. Replace Scoring Logic

Modify `score_prediction()` in `services/score_service.py`:

```python
def score_prediction(self, prediction: Prediction):
    """
    Custom scoring example: Mean Absolute Error for point predictions.
    Assumes prediction.distributions is a list of point predictions.
    """
    if prediction.status != PredictionStatus.SUCCESS:
        return PredictionScore(None, False, f"Prediction failed: {prediction.status}")
    
    errors = []
    step = prediction.params.step
    ts = prediction.resolvable_at.timestamp()
    asset = prediction.params.asset
    
    try:
        # Assuming distributions contains point predictions
        for i, predicted_price in enumerate(prediction.distributions[::-1]):
            actual_price_data = self.prices_cache.get_closest_price(asset, ts)
            
            if not actual_price_data:
                continue
                
            _, actual_price = actual_price_data
            error = abs(predicted_price - actual_price)
            errors.append(error)
            
            ts -= step
            
    except Exception as e:
        return PredictionScore(None, False, f"Scoring error: {e}")
    
    if not errors:
        return PredictionScore(None, False, "No prices available for scoring")
    
    # Lower MAE is better, so negate for ranking (higher = better)
    mae = numpy.mean(errors)
    score = -mae  # Negate so higher score = better
    
    return PredictionScore(float(score), True, None)
```

### 3. Handle Failed Scores

In `score_predictions()`, failed scores get assigned the minimum score:

```python
def score_predictions(self) -> bool:
    # ... scoring loop ...
    
    # Failed predictions get minimum score
    min_score = 0.0
    for prediction in predictions:
        if score.success:
            min_score = min(min_score, score.value)
    
    for prediction in predictions:
        if not prediction.score.success:
            prediction.score.value = min_score
```

Adjust this logic if your scoring has different semantics.

## Step-by-Step: Custom Rolling Windows

### 1. Understand Current Windows

In `entities/model.py`:

```python
@dataclass
class ModelScore:
    recent: Optional[float] = None   # 24h
    steady: Optional[float] = None   # 72h  
    anchor: Optional[float] = None   # 7d

    WINDOW_RECENT: ClassVar[timedelta] = timedelta(days=1)
    WINDOW_STEADY: ClassVar[timedelta] = timedelta(days=3)
    WINDOW_ANCHOR: ClassVar[timedelta] = timedelta(days=7)
```

### 2. Modify Window Durations

Edit `entities/model.py`:

```python
class ModelScore:
    WINDOW_RECENT: ClassVar[timedelta] = timedelta(hours=6)   # Was 1 day
    WINDOW_STEADY: ClassVar[timedelta] = timedelta(days=1)    # Was 3 days
    WINDOW_ANCHOR: ClassVar[timedelta] = timedelta(days=3)    # Was 7 days
```

### 3. Update SQL Aggregation

The actual aggregation happens in `infrastructure/db/db_prediction_repository.py`:

```python
def fetch_all_windowed_scores(self) -> list[WindowedScoreRow]:
    # SQL calculates AVG(score_value) for each window
    # Modify the interval expressions to match your windows
```

Find the SQL query and update intervals:

```sql
-- Before
AVG(CASE WHEN performed_at > NOW() - INTERVAL '1 day' THEN score_value END) as recent_mean

-- After (6 hours)
AVG(CASE WHEN performed_at > NOW() - INTERVAL '6 hours' THEN score_value END) as recent_mean
```

## Step-by-Step: Custom Ranking

### 1. Understand Current Ranking

In `entities/model.py`, ranking is by anchor score:

```python
def get_ranking_value(self):
    return self.anchor
```

In `entities/leaderboard.py`:

```python
sorted_models = sorted(
    models,
    key=lambda model: (
        model.overall_score.anchor if ... else float('-inf'),
        model.overall_score.steady if ... else float('-inf'),
        model.overall_score.recent if ... else float('-inf'),
    ),
    reverse=True  # Descending
)
```

### 2. Custom Ranking Logic

Example: Rank by weighted combination:

```python
# In leaderboard.py
def get_combined_score(model):
    score = model.overall_score
    if not score:
        return float('-inf')
    
    # 50% anchor, 30% steady, 20% recent
    anchor = score.anchor if score.anchor is not None else 0
    steady = score.steady if score.steady is not None else 0
    recent = score.recent if score.recent is not None else 0
    
    return 0.5 * anchor + 0.3 * steady + 0.2 * recent

sorted_models = sorted(models, key=get_combined_score, reverse=True)
```

## Step-by-Step: Custom Overall Score Aggregation

### 1. Understand Current Aggregation

In `entities/model.py`, `calc_overall_score()` averages across all params:

```python
def calc_overall_score(self):
    recent_scores = [param.score.recent for param in self.scores_by_param]
    # Simple average
    self.overall_score = ModelScore(
        recent=sum(recent_scores) / len(recent_scores),
        # ...
    )
```

### 2. Custom Aggregation

Example: Weighted by asset importance:

```python
ASSET_WEIGHTS = {"BTC": 2.0, "ETH": 1.5, "SOL": 1.0}

def calc_overall_score(self):
    if not self.scores_by_param:
        self.overall_score = ModelScore(None, None, None)
        return
    
    weighted_recent = []
    total_weight = 0
    
    for param in self.scores_by_param:
        weight = ASSET_WEIGHTS.get(param.param.asset, 1.0)
        if param.score.recent is not None:
            weighted_recent.append(param.score.recent * weight)
            total_weight += weight
    
    self.overall_score = ModelScore(
        recent=sum(weighted_recent) / total_weight if weighted_recent else None,
        # ... same for steady and anchor
    )
```

## Testing Scoring Changes

```bash
# Score a specific prediction for debugging
python -m condorgame_backend.workers.score_worker --prediction-id PRE_model123_20260209_120000

# Watch score worker logs
make logs SERVICES=score-worker
```

Check for:
- `Scored X predictions, Y failed` - failure rate
- `Minimum score: X` - sanity check score range
- Database: `SELECT score_value FROM predictions WHERE score_scored_at IS NOT NULL`
