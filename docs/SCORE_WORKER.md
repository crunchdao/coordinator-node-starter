# Score Worker

The Score worker is responsible for turning raw predictions
into scores and leaderboards.

It is CPU intensive and can be delayed in time, so it is
intentionally kept separate from the Predict worker.

---

## Responsibilities

The Score worker:

1. Retrieves stored predictions that are ready for scoring.  
2. Fetches realised market data (prices).
3. Applies your scoring algorithm on each prediction.
4. Aggregates scores per model.
5. Computes rolling statistics:
    - recent score (e.g. last 24h),
    - steady score (e.g. last 72h),
    - anchor score (e.g. last 7 days).
6. Builds and stores the leaderboard.
7. Cleans old predictions.

---

## Example scoring logic (Condor-style)

In Condor, each model returns a **distribution** instead of a single point prediction.

The scoring:

1. For each prediction:
    - find the prices required to compute the realised outcome,
    - compute the realised outcome (e.g., the realised return),
    - evaluate the predicted PDF at that value,
    - convert the PDF density into a score.

2. Aggregate all scores per model over the selected window.
3. Normalize if needed.
4. Store scores for:
   - each prediction,
   - each model,
   - each (asset, horizon, step) parameter set.

You can adapt this to any scoring logic.

---

## Rolling scores

A common pattern is:

- `recent_score`: performance over the last 24 hours.
- `steady_score`: performance over the last 72 hours.
- `anchor_score`: performance over the last 7 days.

The leaderboard can then use the `anchor_score` for ranking,
while still showing the other scores so newcomers see progress quickly.

---

## Snapshotting Scores

After computing the scores, the Score worker creates a **snapshot** of the model scores to ensure historical tracking.
This snapshot allows past performance to be reported to participants through the Report Worker.


## Cleaning old data

Predictions and snapshots can accumulate quickly, especially with distributions.

To avoid unbounded growth:

- delete predictions older than a certain age (e.g. 10 days),
- delete snapshots older than a certain age (e.g. 10 days),
- keep only what is needed for your rolling windows.

This keeps:

- database size under control,
- queries and scoring loops efficient.

---

## Why an independent process?

Because:

- if scoring crashes, Predict continues to run,
- you can restart Score at any time and re-run it,
- you can run Score on a different machine with more CPU and RAM,
- you can pause scoring without stopping game predictions.

This design comes directly from production experience
with real users and heavy traffic.
