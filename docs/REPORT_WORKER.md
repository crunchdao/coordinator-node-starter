# Report Worker

The Report worker is a small FastAPI application
that exposes your game results over HTTP.

It is fully decentralised: CrunchDAO does not store your scores.
The UI talks directly to your Report worker.

---

## Responsibilities

The Report worker:

- reads scores and predictions from your storage,
- exposes leaderboards,
- exposes metrics for each model,
- exposes parameter-level metrics if needed,
- formats data for your frontend.

It does **not**:

- perform scoring,
- manage models,
- talk to the orchestrator.

---

## Typical endpoints

Examples (you can adapt names and payloads):

### Leaderboard

```http
GET /report/leaderboard
```

Returns:

- ranked list of models,
- recent / steady / anchor scores,
- basic metadata.

### Global metrics for a model

```http
GET /report/model/{model_id}/global
```

Returns:

- aggregated scores for the model,
- maybe some summary statistics.

### Parameter-level metrics

```http
GET /report/model/{model_id}/params
```

Returns:

- scores per (asset, horizon, step) combination,
- useful to understand where a model is strong or weak.

### Predictions of a model

```http
GET /report/model/{model_id}/predictions
```

Returns:

- raw or filtered predictions for this model,
- typically useful for debugging or research.

---

## Frontend integration

The CrunchDAO hub, or your custom frontend, calls these endpoints.

The UI is configurable:

- which columns to show in the leaderboard,
- how to format numbers,
- how to group or filter models.

You keep control over:

- which metrics you report,
- how often you update them,
- which parts are public or private.

---

## Why a separate worker?

Just like Score, the Report worker is isolated so that:

- UI errors do not impact Predict or Score,
- you can redeploy UI-facing code without touching the core,
- you can scale it separately if many people hit the endpoints.

It is a good practice to keep any HTTP ingress apart from
critical internal services.
