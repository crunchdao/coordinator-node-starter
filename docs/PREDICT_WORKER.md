# Predict Worker

The Predict worker is the **core engine** of your game.
It is the part that talks to all models in real time.

---

## Responsibilities

The Predict worker must:

1. Connect to the Model Orchestrator through the ModelRunner library.
2. Keep its internal list of models **synchronised**.
3. Periodically fetch or receive new market data.
4. Call `on_tick` on models to send that data.
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
    timeout=1.0,
    crunch_id="your-crunch-id",
    host="localhost",
    port=5000,
    max_consecutive_failures=3,
)
```

- `timeout`: maximum time to wait for all models on a call.
- `crunch_id`: on-chain identity of the coordinator.
- `host` / `port`: location of the orchestrator (local or remote).
- `max_consecutive_failures`: after this many failures, the model is disconnected.

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
    method="on_tick",
    arguments=[
        ModelArgument(position=0, type="json", value=price_payload)
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
        ModelArgument(position=0, type="string", value=asset),
        ModelArgument(position=1, type="int", value=horizon),
        ModelArgument(position=2, type="int", value=step),
    ],
)
```

Each `result` in `results` typically contains:

- model identifier,
- status (`SUCCESS`, `FAILURE`, `TIMEOUT`),
- payload (for Condor, a JSON distribution),
- optional error information.

You then:

- transform each result into a `Prediction` entity,
- enqueue or store it via a repository.

---

## Storing predictions

We recommend using a dedicated repository interface, for example:

```python
class PredictionRepository(Protocol):
    async def save(self, prediction: Prediction) -> None:
        ...
```

Your Predict worker only calls:

```python
await prediction_repository.save(prediction)
```

The concrete implementation decides:

- whether this goes to PostgreSQL,
- or to parquet,
- or to a message queue.

This keeps the Predict worker clean.

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
