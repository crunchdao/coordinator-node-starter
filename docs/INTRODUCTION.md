# Introduction

This documentation is based on a live walkthrough of a real Condor-like game.
The goal is to help you **copy the architecture**, understand the decisions,
and adapt everything to your own use case with as little friction as possible.

We keep the English **simple and direct**, with short sentences and concrete examples.

---

## What this project does

This project shows how to:

- Receive predictions from many user models.
- Run these models through a **model orchestrator**.
- Store and score predictions.
- Expose a leaderboard and metrics to a frontend.
- Do all of this in a **decentralised way**: we do not keep your scores.

You only interact with:

- **Your own services** (Predict / Score / Report workers).
- **The model orchestrator**, which manages participant models for you.

The orchestrator:

- starts and stops models,
- connects to the blockchain to verify identity and signatures,
- guarantees that each model is owned and run by the right cruncher,
- exposes a clean gRPC interface used by a small Python client library.

---

## High-level flow

Very simplified architecture:

```text
Your core / business logic
        │
        ▼
  Predict / Score / Report workers
        │
        ▼
  ModelRunner client library
        │
        ▼
  Model Orchestrator  ←→  Blockchain (identity)
        │
        ▼
   Participant models
```

You never talk to the individual models directly.
You only talk to the **ModelRunner client**, which:

- keeps a live list of running models,
- calls them concurrently,
- enforces timeouts and failure limits,
- normalises arguments and responses.

---

## Why separate Predict, Score, and Report?

From real competition experience, we strongly recommend to split:

1. **Predict worker**
     - critical,
     - must not be blocked by heavy computation,
     - must run smoothly even with many models,
     - losing predictions can break your game.

2. **Score worker**
     - CPU intensive,
     - can be delayed (you can score 5 or 10 minutes later),
     - can be stopped and restarted,
     - safe to re-run if something goes wrong.

3. **Report worker**
     - only exposes HTTP endpoints (FastAPI),
     - does not perform heavy logic,
     - can go down briefly without breaking the game,
     - can be redeployed independently.

This separation makes:

- updates easier (you can redeploy only the Report worker),
- failures less risky (Predict is protected),
- performance tuning more focused (Score can live on a stronger machine).

---

## How to use this documentation

You can read this documentation in order:

1. [**Architecture Overview**](ARCHITECTURE_OVERVIEW.md) – understand the big picture.
2. [**Running Locally**](RUNNING_LOCALLY.md) – run everything with Docker and `make` commands.
3. [**Core Concepts**](CORE_CONCEPTS.md) – interfaces, base class, tick vs predict, timeouts.
4. [**Predict Worker**](PREDICT_WORKER.md) – the main loop that talks to all models.
5. [**Score Worker**](SCORE_WORKER.md) – how scoring is done and why it is isolated.
6. [**Report Worker**](PREDICT_WORKER.md) – how to expose leaderboards and metrics.
7. [**Entities**](ENTITIES.md) – data structures for models, predictions, and scores.
8. [**Build Your Own Challenge**](BUILD_YOUR_OWN_CHALLENGE.md) – create your own public game.
9. [**Deployment**](DEPLOYMENT.md) – from local to production.
10. [**FAQ**](FAQ.md) – common problems and how to fix them.

Each page is self-contained.  
You can also jump directly to the parts that interest you most.
