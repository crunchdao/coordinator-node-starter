---
name: coordinator-prediction-format
description: Use when changing prediction format - from distributions to point predictions, categories, or custom formats
---

# Customizing Prediction Format

Change what models return: distributions, point predictions, categories, or custom formats.

## Current Format: Distributions

Models return a list of probability distributions over price returns:

```python
# In prediction.py
@dataclass
class Prediction:
    distributions: list[dict] | None  # e.g., [{"mean": 0.01, "std": 0.02}, ...]
```

Each distribution covers one `step` interval within the `horizon`.

## Coordination Required

Changing prediction format requires updates in multiple places:

```
1. Base class (PyPI package)  ← What models implement
         ↓
2. Prediction entity          ← How predictions are stored
         ↓
3. DB schema                  ← How predictions persist
         ↓
4. Predict worker             ← How predictions are parsed
         ↓
5. Score service              ← How predictions are scored
```

**Order matters!** Update in this sequence to avoid breaking running systems.

## Step-by-Step: Point Predictions

### 1. Update Base Class (Your PyPI Package)

This is in your **separate public repository**, not this repo:

```python
# condorgame/tracker.py (your PyPI package)
class TrackerBase:
    def tick(self, data):
        """Receive latest market data."""
        raise NotImplementedError

    def predict(self, asset: str, horizon: int, step: int) -> list[float]:
        """
        Return point predictions for each step.
        
        Returns:
            List of predicted prices, one per step interval.
            Length should be horizon / step.
        """
        raise NotImplementedError
```

Publish new version to PyPI.

### 2. Update Prediction Entity

Edit `condorgame_backend/entities/prediction.py`:

```python
@dataclass
class Prediction:
    id: str
    model_id: str
    params: PredictionParams
    status: PredictionStatus
    exec_time: float
    
    # Changed from distributions: list[dict] | None
    predictions: list[float] | None  # Point predictions
    
    performed_at: datetime
    resolvable_at: datetime
    score: PredictionScore | None = None

    @staticmethod
    def create(model_id: str, asset: str, horizon: int, step: int, 
               model_result: ModelPredictResult, performed_at: datetime):
        return Prediction(
            id=Prediction.generate_id(model_id, performed_at),
            model_id=model_id,
            params=PredictionParams(asset, horizon, step),
            status=PredictionStatus(model_result.status.value),
            exec_time=model_result.exec_time_us,
            predictions=model_result.result,  # Changed field name
            performed_at=performed_at,
            resolvable_at=performed_at + timedelta(seconds=horizon)
        )
```

### 3. Update DB Schema

Edit `condorgame_backend/infrastructure/db/db_tables.py`:

```python
class PredictionRow(SQLModel, table=True):
    __tablename__ = "predictions"
    
    # ... other fields ...
    
    # Changed from distributions
    predictions: Optional[list[float]] = Field(
        default=None,
        sa_column=Column(JSON)
    )
```

**Migration:** You'll need to handle existing data:
```sql
-- Option 1: Rename column (if compatible)
ALTER TABLE predictions RENAME COLUMN distributions TO predictions;

-- Option 2: Add new column, migrate, drop old
ALTER TABLE predictions ADD COLUMN predictions JSON;
-- ... migrate data ...
ALTER TABLE predictions DROP COLUMN distributions;
```

### 4. Update Repository Mapping

Edit `condorgame_backend/infrastructure/db/db_prediction_repository.py`:

Update any code that maps between `Prediction` entity and `PredictionRow`:

```python
def _to_entity(self, row: PredictionRow) -> Prediction:
    return Prediction(
        # ...
        predictions=row.predictions,  # Changed field
        # ...
    )

def _to_row(self, prediction: Prediction) -> PredictionRow:
    return PredictionRow(
        # ...
        predictions=prediction.predictions,  # Changed field
        # ...
    )
```

### 5. Update Score Service

Edit `condorgame_backend/services/score_service.py`:

```python
def score_prediction(self, prediction: Prediction):
    if prediction.status != PredictionStatus.SUCCESS:
        return PredictionScore(None, False, f"Prediction failed: {prediction.status}")
    
    expected_length = prediction.params.horizon // prediction.params.step
    if len(prediction.predictions) != expected_length:
        return PredictionScore(None, False, "Wrong number of predictions")
    
    errors = []
    step = prediction.params.step
    ts = prediction.resolvable_at.timestamp()
    asset = prediction.params.asset
    
    try:
        for predicted_price in prediction.predictions[::-1]:
            actual = self.prices_cache.get_closest_price(asset, ts)
            if actual:
                _, actual_price = actual
                errors.append(abs(predicted_price - actual_price))
            ts -= step
    except Exception as e:
        return PredictionScore(None, False, f"Error: {e}")
    
    if not errors:
        return PredictionScore(None, False, "No actual prices available")
    
    # Negative MAE so higher = better
    return PredictionScore(-float(numpy.mean(errors)), True, None)
```

## Step-by-Step: Category Predictions

For classification tasks (e.g., "up", "down", "flat"):

### 1. Update Base Class

```python
class TrackerBase:
    CATEGORIES = ["up", "down", "flat"]
    
    def predict(self, asset: str, horizon: int, step: int) -> list[str]:
        """Return category for each step: 'up', 'down', or 'flat'."""
        raise NotImplementedError
```

### 2. Update Prediction Entity

```python
@dataclass
class Prediction:
    categories: list[str] | None  # ["up", "down", "flat", ...]
```

### 3. Update Scoring

```python
def score_prediction(self, prediction: Prediction):
    correct = 0
    total = 0
    step = prediction.params.step
    ts = prediction.resolvable_at.timestamp()
    
    for predicted_category in prediction.categories[::-1]:
        current = self.prices_cache.get_closest_price(asset, ts)
        previous = self.prices_cache.get_closest_price(asset, ts - step)
        
        if current and previous:
            actual_return = current[1] / previous[1] - 1
            
            if actual_return > 0.001:
                actual_category = "up"
            elif actual_return < -0.001:
                actual_category = "down"
            else:
                actual_category = "flat"
            
            if predicted_category == actual_category:
                correct += 1
            total += 1
        
        ts -= step
    
    accuracy = correct / total if total > 0 else 0
    return PredictionScore(accuracy, True, None)
```

## Step-by-Step: Complex Custom Format

For multi-field predictions:

### 1. Define Format

```python
@dataclass
class CustomPrediction:
    point_estimate: float
    confidence_low: float
    confidence_high: float
    direction: str  # "up" or "down"
```

### 2. Update Prediction Entity

```python
@dataclass
class Prediction:
    custom_predictions: list[dict] | None  # Serialized CustomPrediction
```

### 3. Scoring with Multiple Components

```python
def score_prediction(self, prediction: Prediction):
    point_errors = []
    calibration_scores = []
    direction_correct = 0
    
    for pred_dict in prediction.custom_predictions[::-1]:
        # Point accuracy
        point_errors.append(abs(pred_dict["point_estimate"] - actual))
        
        # Calibration: was actual within confidence interval?
        in_interval = pred_dict["confidence_low"] <= actual <= pred_dict["confidence_high"]
        calibration_scores.append(1 if in_interval else 0)
        
        # Direction accuracy
        actual_direction = "up" if actual > previous else "down"
        if pred_dict["direction"] == actual_direction:
            direction_correct += 1
    
    # Combine into single score
    score = (
        -numpy.mean(point_errors) * 0.5 +  # Lower error = better
        numpy.mean(calibration_scores) * 0.3 +  # Higher calibration = better
        direction_correct / len(prediction.custom_predictions) * 0.2  # Higher accuracy = better
    )
    
    return PredictionScore(score, True, None)
```

## Validation

Add validation in predict worker to catch malformed predictions early:

```python
# In predict_service.py, _predict() method
def _validate_prediction(self, result, horizon, step):
    expected_length = horizon // step
    
    if not isinstance(result, list):
        return False, "Prediction must be a list"
    
    if len(result) != expected_length:
        return False, f"Expected {expected_length} predictions, got {len(result)}"
    
    # Add format-specific validation
    return True, None
```

## Testing Format Changes

```bash
# Run predict worker with debug logging
make logs SERVICES=predict-worker 2>&1 | grep -i "predict"

# Check stored predictions
docker compose exec postgres psql -U condorgame -d condorgame -c \
  "SELECT id, predictions FROM predictions ORDER BY performed_at DESC LIMIT 5;"
```
