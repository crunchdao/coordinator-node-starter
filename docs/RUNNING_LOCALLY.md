# Running Everything Locally

You can run **the whole game locally**:

- orchestrator,
- worker processes (Predict / Score / Report),
- your development models.

This is the recommended way to understand and test everything.

---

## Prerequisites

- Docker and Docker Compose installed.
- `make` available on your machine.
- Python for your own code.

---

## Main commands

The project provides a few `make` commands to simplify everything.

### Deploy full stack locally

```bash
make deploy
```

This will:

- start PostgreSQL,
- start the model orchestrator,
- start Predict worker,
- start Score worker,
- start Report worker.

You can then inspect logs:

```bash
make logs
```

---

### Dev mode (run workers from your IDE)

```bash
make dev-deploy
```

This command:

- starts the infrastructure (DB, orchestrator, maybe other base services),
- does **not** start all Python workers automatically.

You then:

- run Predict / Score / Report from your IDE or terminal,
- attach a debugger,
- test code live.

This is very helpful when you want to step through the logic.

---

### Other useful commands

```bash
make restart   # restart services
make stop      # stop containers but do not remove volumes
make down      # stop and remove containers
make build     # rebuild Docker images
```

---

## Local models: submissions

The orchestrator can load local models directly from the repository.

There is a folder:

```text
deployment/config/data/submission/
```

Each subfolder inside `submission/` is a model.

Example:

```text
deployment/config/data/submission/
    condor_game_benchmark/
        main.py
        requirements.txt
    benchmark_2/
        main.py
        requirements.txt
```

When the orchestrator starts, it:

1. scans the `submission/` folder,
2. installs `requirements.txt` for each model,
3. starts each model process.

You can print logs inside the model to confirm it is running.

---

## Local model configuration: models.dev.yaml

The orchestrator also reads a configuration file, for example:

```text
deployment/config/models.dev.yaml
```

Here you declare which local models should join the game.

Example:

```yaml
models:
  - id: "alexis_model"
    name: "Alexis"
    path: "submission/condor_game_benchmark"

  - id: "ap_model"
    name: "AP"
    path: "submission/benchmark_2"
```

- `id` is the internal identifier for the model.
- `name` is a human name, used in the leaderboard.
- `path` is the folder under `submission/`.

On startup, the orchestrator reads this file and knows:

- which models to load,
- where to find their code.

---

## Docker Compose view

The workers appear as separate services in `docker-compose.yml`, for example:

```yaml
services:
  predict-worker:
    image: ...
    command: python -m condor.predict_worker

  score-worker:
    image: ...
    command: python -m condor.score_worker

  report-worker:
    image: ...
    command: python -m condor.report_worker
```

When you rename scripts or packages, remember to update the commands here.

Each worker is a separate process, which makes it easy to:

- restart only one,
- scale them independently in production,
- keep Predict safe while changing Score or Report.
