# Coordinator Node Starter

This repository contains everything to instantiate a coordinator node 
and model nodes it communicates with locally. W

As an example we will use one of the competition we delevloped interally: Condor Game - is a real-time probabilistic forecasting challenge for BTC, ETH, SOL and XAU.

Within minutes you will have a full environment running that you can then adapt to your purposes. 

This README focuses on running the project locally and in **local mode** - with this we mean that the model nodes are also running on your machine.  

All concepts, architecture details, and advanced usage are documented in the [documentation](#-documentation)

---

## Documentation

Full documentation is available in the `docs` directory (Markdown format)  
and as a [MkDocs site](http://localhost:8080).

- Source files: `./docs`
- Local docs site (served by MkDocs): http://localhost:8080  
  ➜ available after running the stack with `make deploy`.

---

## Run locally

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

### 2. Coordinator Platform UI 

Once the stack is up, you can access the Coordinator Platform UI at:

http://localhost:3000

From this UI you can see:

- The leaderboard,
- The metrics returned by the report-worker.

once you have a good setup locally this platform will also help you to: 

- Register as a coordinator
- Push your Crunch to Testnet and Mainnet

Important: there is a scoring delay, so the leaderboard will only show up delayed.

- The scoring requires time to process sufficient data.
- Scores and metrics may take at least 1 hour to appear in the UI. (The prediction horizon is 1 hour, so scoring starts after the resolution period.)

If you open the UI immediately after starting the stack, it is normal to see no scores yet.