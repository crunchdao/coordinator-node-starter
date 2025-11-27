# Architecture Overview

This section explains the global architecture of the game.
It follows the same structure as the drawing used in the talk.

---

## Big picture

```text
                        +-------------------+
                        |   Your business   |
                        |  (trading, API,   |
                        |   analytics...)   |
                        +---------+---------+
                                  │
                                  ▼
                +-----------------+-----------------+
                | Predict / Score / Report workers |
                +-----------+-----------+----------+
                            │           │
                            ▼           │
                    ModelRunner client  │
                            │           │
                            ▼           │
                   +--------+-----------+--------+
                   |      Model Orchestrator     |
                   +--------+-----------+--------+
                            │
              +-------------+-------------+
              │                           │
              ▼                           ▼
        Blockchain                  Participant models
  (identity, signatures)     (code submitted by crunchers)
```

You only own and deploy:

- the three workers (Predict, Score, Report),
- your storage (DB, parquet, files, ...),
- your own core/business service.

The orchestrator and participant models are separate components,
but you can still run them locally for development.

---

## Components

### Model Orchestrator

The orchestrator is responsible for:

- starting and stopping participant models,
- keeping one process per model,
- checking identity and signatures on the blockchain,
- exposing a gRPC API for the ModelRunner client.

It has two modes:

- **Production mode** – used by CrunchDAO on its servers.
- **Local mode** – used by you for development.

In local mode, it can:

- load models from a `submission/` folder,
- install their `requirements.txt`,
- start each model and keep it running.

You do not have to write an orchestrator yourself.
You reuse the one provided by the protocol.

---

### ModelRunner client library

This is a small Python library that you will use inside your Predict worker.

It:

- connects to the orchestrator,
- keeps a live, synchronised list of models,
- calls methods on all models concurrently,
- handles timeouts and failures,
- normalises arguments and results.

You do not handle threads or asyncio details for each model.
You only call one method, and the library fans out to all models for you.

---

### Predict worker

The Predict worker:

- receives or fetches market data (prices, features, ...),
- sends **tick** calls to all models when new data is available,
- sends **predict** calls to ask for predictions,
- collects and stores all predictions.

It must:

- be fast,
- not block the event loop,
- be robust to individual model failures.

---

### Score worker

The Score worker:

- reads stored predictions,
- fetches realised market data,
- applies your scoring algorithm (for Condor: distribution-based scoring),
- computes rolling scores:
  - recent (24h),
  - steady (72h),
  - anchor (7 days),
- updates the leaderboard.

It is CPU intensive, so we keep it isolated from Predict.

---

### Report worker

The Report worker:

- is a small FastAPI application,
- exposes HTTP endpoints:
  - leaderboard,
  - metrics,
  - detailed per-model views,
- is fully **decentralised**: nothing is stored by CrunchDAO,
  the coordinator (you) answers all requests.

The CrunchDAO UI or any custom UI calls this worker directly.

---

### Storage

You are free to choose storage.

In this implementation we use:

- **PostgreSQL** for predictions and scores.

Reasons:

- large volume of predictions (24h distributions),
- complex queries (rolling windows, aggregation),
- cleaning of old data.

For a simpler game, you could start with:

- parquet files,
- plain JSON files,
- another database.

The pattern remains the same.
