# Deployment Overview

This page gives a high-level view of how to move
from local development to production.

---

## Local vs production

Locally, you:

- run everything with Docker Compose,
- use `make deploy` / `make dev-deploy`,
- run a local orchestrator,
- run local benchmark models.

In production, you typically:

- run the orchestrator on a CrunchDAO-provided node,
- run your workers on your own infrastructure,
- expose the Report worker to the internet (or a restricted audience),
- choose a managed database (PostgreSQL, etc.).

The code of your workers can stay almost identical.

---

## Process separation

In production, each worker should be its own service:

- `predict-worker` (critical),
- `score-worker` (heavy),
- `report-worker` (HTTP / API).

This allows you to:

- scale them independently,
- deploy them independently,
- restart them independently.

For example:

- you can redeploy `report-worker` many times per day,
- while leaving `predict-worker` untouched during trading hours.

---

## Updating safely

Guidelines:

- Avoid redeploying Predict during sensitive periods (e.g. market open).
- If you must update Predict, test the new version locally first.
- Score and Report can be restarted with less risk.

Because the orchestrator and models are external services:

- your workers must handle disconnections gracefully,
- your workers must be able to reconnect to the orchestrator,
- your workers must tolerate temporary UI downtime.

---

## Scaling considerations

When you have many models (hundreds or thousands):

- Predict may need more CPU and memory to handle concurrency.
- Score may need more CPU for heavy aggregation.
- Report may need more replicas if the UI is popular.

The clean separation of workers makes it easy to:

- move Score to a bigger machine,
- put Report behind a load balancer,
- keep Predict lean and focused.

Start simple, then scale only when necessary.
