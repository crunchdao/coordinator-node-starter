# Predict Worker

The Predict worker is the **core engine** of your game.
It is the part that talks to all models in real time.

---

## Responsibilities

The Predict worker must:

1. Connect to the Model Orchestrator through the ModelRunner library.
2. Keep its internal list of models **synchronised**.
3. Periodically fetch or receive new market data.
4. Call `tick` on models to send that data.
5. Call `predict` on models to collect predictions.
6. Store predictions in your storage (DB, parquet, files, ...).

It must be:

- fast,
- stable,
- isolated from heavy scoring logic.

---

## Initialisation with ModelRunner

A typical setup looks like:

```python
runner = ModelRunnerClient(
    timeout=50,
    crunch_id="your-crunch-id",
    host="localhost",
    port=9091,
    max_consecutive_failures=10,
    max_consecutive_timeouts=10
)
```

- `timeout`: maximum time in second to wait for all models on a call.
- `crunch_id`: on-chain identity of the coordinator.
- `host` / `port`: location of the orchestrator (local or remote).
- `max_consecutive_failures`: after this many failures, the model is disconnected.
- `max_consecutive_timeouts`: after this many timed out, the model is disconnected.

Then, in your async service:

```python
await runner.init()   # connect to orchestrator and to all models
await runner.sync()   # keep the model list updated in background
```

Once this is done, you are ready to call models.

---

## Sending tick

Example:

```python
await runner.call(
    method="tick",
    arguments=[
        Argument(
            position=1,
            data=Variant(
                type=VariantType.JSON,
                value=encode_data(VariantType.JSON, prices),
            ),
        )
    ],
)
```

Notes:

- `method` is the name of the method in your base class.
- `arguments` is a list of typed arguments.
- The library encodes and decodes everything for you via gRPC.

You can also target only a subset of models if you want
to give more work to the best performers.

---

## Sending predict and receiving results

Example:

```python
results = await runner.call(
    method="predict",
    arguments=[
        Argument(position=1, data=Variant(type=VariantType.STRING, value=encode_data(VariantType.STRING, asset_code))),
        Argument(position=2, data=Variant(type=VariantType.INT, value=encode_data(VariantType.INT, horizon))),
        Argument(position=3, data=Variant(type=VariantType.INT, value=encode_data(VariantType.INT, step))),
    ],
)
```

Each `result` in `results` typically contains:

- model identifier,
- status (`SUCCESS`, `FAILURE`, `TIMEOUT`),
- payload (for Condor, a JSON distribution),
- time the model takes to predict in microseconds

You then:

- transform each result into a `Prediction` entity,
- enqueue or store it via a repository.

---

## Maintaining and Storing Models Joining the Game

To score models, track their performance, and rank them on the leaderboard in Scoring Worker, the Predict Worker stores a local representation of each model participating in the game.

When a model connects, the Predict Worker extracts its metadata from the `ModelRunner` object provided by the ModelRunner client library.  
This metadata includes, for example:

- `model_id` — unique identifier of the model  
- `model_name` — user-defined model name  
- `cruncher_name` — name of the user (cruncher)  
- `cruncher_id` — unique identifier of the cruncher  
- `deployment_id` — identifier of the deployed version of the model  

It is recommended to keep these fields up to date, as crunchers may change their model name or their profile name at any time.  
Keeping this metadata current ensures that the leaderboard and the reporting remain accurate.

> **Note:** `deployment_id` is useful to detect when a cruncher deploys a new version of their model.  
This allows you to trigger any specific behavior you may need, such as resetting metrics or handling version-specific logic.

Internally, the service maintains a list of all known models.  
The `model_id` is used to determine whether a model is new or already registered.

For example, in the Condor game, when a model joins for the first time, the system replays the prices of the previous 30 days and sends them as `tick` events to initialize the model properly.  
You can refer to the game service code for an example of how this initialization is handled.

---

## Storing predictions

Predictions are stored through a dedicated repository layer.
The `PredictionRepository` defines the interface used by the Predict Worker:

```python
class PredictionRepository(ABC):
    @abstractmethod
    def save_all(self, prediction: Iterable[Prediction]):
        ...
```

The actual implementation is:

- DbPredictionRepository — the concrete class responsible for writing predictions to PostgreSQL.

From the Predict Worker, storing the predictions is done through a single call:
```python
await prediction_repository.save_all(prediction)
```

The Predict Worker does not handle database logic directly; all persistence operations are implemented inside `infrastructure/db` and the interfaces `services/interfaces`

---

## Why not score here?

Scoring can be heavy:

- many predictions,
- complex distribution-based metrics,
- rolling windows.

If scoring runs inside the Predict worker:

- you risk blocking the event loop,
- you risk missing ticks and predictions,
- you may need much larger machines.

That is why we always isolate scoring in its own worker.
