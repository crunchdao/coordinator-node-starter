# Deployment Overview

This page gives a high-level view of how to move
from local development to production.

---

## Local vs production

Locally, you:

- run everything with Docker Compose,
- use `make deploy` / `make dev deploy`,
- run a local orchestrator,
- run local benchmark models.

In production, you typically:

- The orchestrator runs on a CrunchDAO-provided node.
- Your workers run on your own infrastructure.
- The Report worker is exposed to the internet (or a restricted audience).
- A managed database is used (e.g., PostgreSQL).

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

---

## Commands Overview

The `make deploy` command handles building and deploying services with **Docker Compose**. Below are the relevant variations and how they differ:

| Command                      | Services Deployed                                                   | Configuration                                 | Use Case                                |
|------------------------------|---------------------------------------------------------------------|-----------------------------------------------|-----------------------------------------|
| `make deploy`                | All available services                                              | `docker-compose-local.yml` + `.local.env`     | Testing everything localy               |
| `make deploy dev`            | Only infrastructure (database and model-orchestrator)               | `docker-compose-local.yml` + `.dev.env`       | Development-specific configuration      |
| `make deploy production`     | Backend services only (predict-worker, score-worker, report-worker) | `docker-compose-prod.yml` + `.production.env` | Deploying critical production services  |
| `make deploy production all` | All services (no filtering)                                         | `docker-compose-prod.yml` + `.production.env` | Deploy every service in production mode |

### **Key Notes**

- **Environment Files**: `.local.env`, `.dev.env`, `.production.env` must have the correct variables (e.g., database credentials, API keys). Keep `.production.env` secure.
- **Backend Services**: Key services in production (`BACKEND_SERVICES`) include:
    - `predict-worker`
    - `score-worker`
    - `report-worker`

### Other make commands
#### Stopping Services

| Command                    | Mode             | Description                                           |
|----------------------------|------------------|-------------------------------------------------------|
| `make stop`                | local            | Stop all local services                               |
| `make stop dev`            | dev              | Stop infrastructure (database and model-orchestrator) |
| `make stop production`     | production       | Stop production backend services                      |
| `make stop production all` | production (all) | Stop all production services                          |

---

#### Removing Services (`down`)

| Command                    | Mode             | Description                                                        |
|----------------------------|------------------|--------------------------------------------------------------------|
| `make down`                | local            | Stop and remove all local services, networks, and volumes          |
| `make down dev`            | dev              | Stop and remove all infrastructure services, networks, and volumes |
| `make down production`     | production       | Stop and remove production backend services, networks, and volumes |
| `make down production all` | production (all) | Stop and remove all production services, networks, and volumes     |

---

#### Restarting Services

| Command                       | Mode             | Description                         |
|-------------------------------|------------------|-------------------------------------|
| `make restart`                | local            | Restart all local services          |
| `make restart dev`            | dev              | Restart all infrastructure services |
| `make restart production`     | production       | Restart production backend services |
| `make restart production all` | production (all) | Restart all production services     |

---

#### Building Services

| Command                 | Mode       | Description                             |
|-------------------------|------------|-----------------------------------------|
| `make build`            | local      | Build all local service images          |
| `make build production` | production | Build production backend service images |

---

#### Viewing Logs

| Command                    | Mode             | Description                               |
|----------------------------|------------------|-------------------------------------------|
| `make logs`                | local            | Show logs for all local services          |
| `make logs dev`            | dev              | Show logs for all infrastructure services |
| `make logs production`     | production       | Show logs for production backend services |
| `make logs production all` | production (all) | Show logs for all production services     |


### Selecting Specific Services

All commands above can optionally target **only a subset of services** by using the `SERVICES` variable.

If `SERVICES` is **not** set, the default behavior from the tables above is applied.  
If `SERVICES` **is** set, only the listed services are affected.

Examples:

```bash
# Deploy only predict-worker in local mode
make deploy SERVICES=predict-worker

# Show logs for report-worker in production
make logs production SERVICES=report-worker
```
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
