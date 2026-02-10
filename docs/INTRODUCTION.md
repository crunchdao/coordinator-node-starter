# Introduction

This documentation is based on a live walkthrough of a real Condor-like game.
The goal is to help you **copy the architecture**, understand the decisions,
and adapt it to your own use case with as little friction as possible.

We keep the English **simple and direct**, with short sentences and concrete examples.

---

## What this project does

This project shows how to:

- Receive predictions from many user models.
- Run these models through a **model orchestrator**.
- Store and score predictions.
- Expose a leaderboard and metrics to a frontend.
- Do all of this in a **decentralized way**: we do not keep your scores.

You only interact with:

- **Your own services** (Predict / Score / Report workers).
- **The model orchestrator**, which manages participant models for you.

The orchestrator:

- starts and stops models,
- connects to the blockchain to verify identity and signatures,
- guarantees that each model is owned and run by the right cruncher,
- exposes a clean gRPC interface used by a small Python client library.

---

## Architecture at a glance

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
                +-----------+----------------------+
                            │
                            ▼
                    ModelRunner client
                            │
                            ▼
                   +--------+--------------------+
                   |      Model Orchestrator     |
                   +--------+-----------+--------+
                            │
              +-------------+-------------+
              │                           │
              ▼                           ▼
        Blockchain                  Participant models
  (identity, signatures)     (code submitted by crunchers)
```

You never talk to individual models directly.
You talk to the **ModelRunner client**, which:

- keeps a live list of running models,
- calls them concurrently,
- enforces timeouts and failure limits,
- normalizes arguments and responses.

---

## What you own and deploy

You own and deploy:

- your three workers on the Coordinator Node (Predict, Score, Report),
- your storage (PostgreSQL, parquet, files, or another database),
- your own core/business service.

The orchestrator and participant models are separate components,
but you can still run them locally for development.

---

## Main components

### Model Orchestrator

Responsible for:

- starting and stopping participant models,
- keeping one process per model,
- checking identity and signatures on-chain,
- exposing a gRPC API for the ModelRunner client.

Modes:

- **Production mode** – used by Crunch Protocol for the Model Cloud.
- **Local mode** – used by you during local development.

### ModelRunner client library

Used inside your Predict worker. It:

- connects to the orchestrator,
- keeps a synchronized list of models,
- calls methods on all models concurrently,
- handles timeouts and failures,
- normalizes arguments and results.

### Predict worker

- Receives/fetches market data.
- Sends `tick` calls to models when new data arrives.
- Sends `predict` calls and stores predictions.

This is the critical real-time component.

### Score worker

- Reads stored predictions.
- Fetches realized/out-of-sample data.
- Applies your scoring algorithm and updates leaderboard data.

This is CPU-heavy and intentionally isolated from Predict.

### Report worker

- Small FastAPI app.
- Exposes leaderboard and metrics endpoints.
- Used by the Coordinator Platform and local UI (`http://localhost:3000`).

---

## Why separate Predict, Score, and Report?

From real competition experience, we strongly recommend this split:

1. **Predict worker**
     - critical,
     - must not be blocked by heavy computation,
     - must run smoothly even with many models,
     - losing predictions can break your game.

2. **Score worker**
     - CPU intensive,
     - can be delayed (score 5–10 minutes later if needed),
     - can be stopped and restarted,
     - safe to re-run if something goes wrong.

3. **Report worker**
     - serves HTTP endpoints,
     - should stay lightweight,
     - can be redeployed independently.

This separation makes updates safer, failures less risky, and scaling easier.

---

## How to use this documentation

You can read this documentation in order:

1. [**Introduction**](INTRODUCTION.md) – architecture and deployment model in one page.
2. [**Running Locally**](RUNNING_LOCALLY.md) – run everything with Docker and `make` commands.
3. [**Core Concepts**](CORE_CONCEPTS.md) – interfaces, base class, tick vs predict, timeouts.
4. [**Predict Worker**](PREDICT_WORKER.md) – the main loop that talks to all models.
5. [**Score Worker**](SCORE_WORKER.md) – how scoring is done and why it is isolated.
6. [**Report Worker**](REPORT_WORKER.md) – how to expose leaderboards and metrics.
7. [**Entities**](ENTITIES.md) – data structures for models, predictions, and scores.
8. [**Build Your Own Challenge**](BUILD_YOUR_OWN_CHALLENGE.md) – create your own public game.
9. [**Deployment**](DEPLOYMENT.md) – from local to production.
10. [**FAQ**](FAQ.md) – common problems and how to fix them.

Each page is self-contained.
You can jump directly to the parts you need.