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
    player_id: Player
    overall_score: ModelScore | None
    ...
```

### Prediction

```python
class Prediction:
    id: str
    model_id: str
    params: PredictionParams
    status: PredictionStatus
    distribution: dict # model output (for Condor)
    resolvable_at: datetime
    score: PredictionScore | None = None
    ...
```

You can adapt this to your own game.

---

## Why entities?

Entities allow you to:

- attach helper methods (e.g. `ModelScore.calc_overall_score()`),
- avoid duplicating field lists everywhere,
- Easy to persist regardless of the solution (database, JSON, etc.)
- pass structured data across layers (Predict / Score / Report).

This is useful both for readability and for long-term maintenance.

---

## Repositories

We also define repository interfaces, for example:

```python
class ModelRepository(ABC):
    @abstractmethod
    def fetch_all(self) -> dict[str, Model]: ...
    @abstractmethod
    def fetch_by_ids(self, ids: list[str]) -> dict[str, Model]: ...
    @abstractmethod
    def save(self, model: Model): ...
```

```python
class PredictionRepository(ABC):
    @abstractmethod
    async def save(self, prediction: Prediction) -> None: ...
    @abstractmethod
    def fetch_ready_to_score(self) -> list[Prediction]: ...
    @abstractmethod
    def fetch_all_windowed_scores(self) -> list[WindowedScoreRow]: ...
```

The Predict and Score workers only depend on these interfaces.

Concrete implementations can use:

- PostgreSQL,
- another database,
- parquet,
- S3,
- or any combination.

This keeps your domain logic decoupled from infrastructure.
