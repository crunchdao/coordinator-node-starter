# Entities and Repositories

To keep the code clean and maintainable, we use small
Python classes (entities) and repository interfaces.

This is more structured than passing raw dictionaries everywhere,
and makes it easier to change the implementation later.

---

## Example entities

### Model

```python
class Model:
    id: str
    name: str
    player_id: str  # cruncher identity
    score: "ModelScore | None"
```

### Prediction

```python
class Prediction:
    id: str
    model_id: str
    asset: str
    horizon: int
    step: int
    status: str        # SUCCESS / FAILURE / TIMEOUT
    distribution: dict # model output (for Condor)
    created_at: datetime
```

### PredictionParameters

```python
class PredictionParameters:
    asset: str
    horizon: int
    step: int
```

### ModelScore

```python
class ModelScore:
    recent: float
    steady: float
    anchor: float
```

You can adapt this to your own game.

---

## Why entities?

Entities allow you to:

- attach helper methods (e.g. `ModelScore.is_good()`),
- avoid duplicating field lists everywhere,
- change DB schema in one place,
- pass structured data across layers (Predict / Score / Report).

This is useful both for readability and for long-term maintenance.

---

## Repositories

We also define repository interfaces, for example:

```python
class ModelRepository(Protocol):
    async def find_all(self) -> list[Model]: ...
    async def find_by_id(self, model_id: str) -> Model | None: ...
    async def save(self, model: Model) -> None: ...
```

```python
class PredictionRepository(Protocol):
    async def save(self, prediction: Prediction) -> None: ...
    async def find_for_scoring(self, since: datetime) -> list[Prediction]: ...
    async def delete_older_than(self, cutoff: datetime) -> None: ...
```

The Predict and Score workers only depend on these interfaces.

Concrete implementations can use:

- PostgreSQL,
- another database,
- parquet,
- S3,
- or any combination.

This keeps your domain logic decoupled from infrastructure.
