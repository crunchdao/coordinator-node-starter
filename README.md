# Coordinator Node Starter

Template source for building Crunch coordinator nodes.

This repository provides:

- `coordinator_core/` — canonical contracts (entities, DB tables, interfaces)
- `node_template/` — runnable default workers/services

## Intended workflow

Create two repositories per Crunch:

1. `crunch-<name>` (public)
   - model interface
   - inference schemas/validation
   - scoring callables
   - quickstarters
2. `crunch-node-<name>` (private)
   - copy/adapt `node_template/`
   - deployment/config for your node

## Required definition points (before implementation)

- Define Model Interface
- Define inference input
- Define inference output
- Define scoring function
- Define ModelScore
- Define checkpoint interval

## Run local template stack

```bash
make deploy
```

Useful endpoints:

- Report API: http://localhost:8000
- UI: http://localhost:3000
- Docs: http://localhost:8080

## Documentation

See `docs/` for concise architecture and bootstrap instructions.
