# Running Everything Locally

You can run **the whole game locally**:

- orchestrator,
- worker processes (Predict / Score / Report),
- your development models.
- Reports UI (leaderboard & metrics)

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
- start Reports UI (leaderboard & metrics)

#### Reports UI

Once the local stack is running, you can open the Reports UI:

- URL: [http://localhost:3000](http://localhost:3000)  
- Content:
    - Leaderboard
    - Metrics produced by the Report worker

> ⏱️ **Scoring delay**  
> The scoring requires time to process sufficient data.  
> Expect to wait **at least 1 hour** before scores and metrics appear in the UI.
> 
---

### Dev mode (run workers from your IDE)

```bash
make dev deploy
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

## Local Models

> **Note:** This mode is enabled when you run the system locally through `docker-compose-local.yml

In local or development mode, the orchestrator runs through:
```
deployment/model-orchestrator-local/config/docker-entrypoint.sh
```

This provides flexibility for automation, such as rebuilding runner images or applying custom logic before the orchestrator starts.

For the Condor Game, a notebook example is imported and configured to demonstrate model execution.


### Submissions

The orchestrator can load **local models** directly from the `submissions` directory.

This compose file launches the model orchestrator in **development mode**, loading its configuration from:
```
deployment/model-orchestrator-local/config/orchestrator.dev.yml
```

In this mode, the orchestrator will:

1. Read the list of models defined in `models.dev.yml`  
   (see the [Configuration](#configuration) section below)

2. Scan the `submissions` directory :  
      ```
         deployment/model-orchestrator-local/data/submissions/
      ```
3. For each model configured directory found, it will:  
      - detect file changes  
      - automatically rebuild the Docker image  
      - install dependencies from `requirements.txt`  
      - start the model container and execute `main.py`

This provides a fast feedback loop while developing models locally.

---

### Configuration

Inside `orchestrator.dev.yml`, the orchestrator references a model definition file:
```
models.dev.yml
```

This file lists **all models** that should run in local mode.

To register a new local model, add a new entry inside `models.dev.yml`.

A typical model definition looks like this:

```yaml
- id: my-local-model
  submission_id: my-local-model
  crunch_id: condor
  desired_state: RUNNING
  cruncher_id: cruncher-local-1
```

#### Field description

- **id**  
  Unique identifier for the model inside the orchestrator.  
  This is also the identifier you will receive inside the Predict Worker.

- **submission_id**  
  Name of the folder located in `submissions/`.

- **crunch_id**  
  The name of the game/challenge (for example `"condor"`).  
  Models using the same `crunch_id` belong to the same game.

- **desired_state**  
  Controls whether the orchestrator should start the model.  
  Possible values:  
    - `RUNNING` → the orchestrator launches the model  
    - `STOPPED` → the orchestrator ignores the model

- **cruncher_id**  
  A simulated blockchain identifier representing the cruncher that owns the model.
---

## Choosing Your Game Name

Your game name appears in several locations:

- in `models.dev.yml` (`crunch_id`)
- in the Predict Service during creation instance of `DynamicSubclassModelConcurrentRunner`
- in the orchestrator configuration `orchestrator.dev.yml` (`crunches.id` and `crunches.name`)


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
