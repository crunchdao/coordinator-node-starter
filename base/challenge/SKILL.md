---
name: starter-challenge-challenge
summary: Agent instructions for implementing challenge logic.
---

# Challenge skill - challenge

## Primary implementation files

- `starter_challenge/tracker.py` — model interface (participants implement this)
- `starter_challenge/scoring.py` — scoring function for local self-eval
- `starter_challenge/examples/` — quickstarter implementations

## Runtime contract (node-private)

- `../node/runtime_definitions/contracts.py` — CrunchContract defining types, scoring, emission

## Development guidance

- Keep participant-facing challenge logic in this package.
- Keep runtime contracts and deployment config in `../node/`.
- The scoring function in `scoring.py` is used for local self-eval.
  The runtime scoring callable is configured in `contracts.py`.

## Validate from node workspace

```bash
cd ../node
make verify-e2e
```
