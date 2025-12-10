# Condor Game Backend

This repository contains the backend services and workers used to run the Condor Game.

This README focuses on running the project in **local mode**.  
All concepts, architecture details, and advanced usage are documented in the [documentation](#-documentation)

---

## 📚 Documentation

Full documentation is available in the `docs` directory (Markdown format)  
and as a [MkDocs site](http://localhost:8080).

- Source files: `./docs`
- Local docs site (served by MkDocs): http://localhost:8080  
  ➜ available after running the stack with `make deploy`.

---

## 🚀 Run locally (local mode)

The local stack is designed to let you:

- run the backend and workers with Docker,
- generate scores,
- and explore the leaderboard / reports UI.

### 1. Start the local stack

From the root of the repository:

```bash
make deploy
```

To learn more about the available commands, please refer to [Commands Overview](docs/DEPLOYMENT.md#commands-overview).

### 2. 📊 Reports UI (leaderboard & metrics)

Once the stack is up, you can access the reports UI at:

👉 http://localhost:3000

From this UI you can see:

- the leaderboard,
- the metrics returned by the report-worker.

⏳ Important: scoring delay

Scoring is not instant.

- The scoring requires time to process sufficient data.
- Scores and metrics may take at least 1 hour to appear in the UI. (The prediction horizon is 1 hour, so scoring starts after the resolution period.)

If you open the UI immediately after starting the stack, it is normal to see no scores yet.