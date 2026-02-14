---
name: starter-challenge-workspace
summary: Agent runbook for this generated Crunch workspace.
---

# starter-challenge workspace skill

## Fast path (from workspace root)

```bash
cd node
make deploy
make verify-e2e
make logs-capture
```

## Where logs and diagnostics live

- Live service logs: `cd node && make logs`
- Captured runtime logs: `node/runtime-services.jsonl`
- Lifecycle audit: `process-log.jsonl`
- Additional troubleshooting: `node/RUNBOOK.md`

## Where to edit code

- **Challenge behavior** (tracker, scoring, examples):
  `challenge/starter_challenge/`
- **Runtime contract** (types, callables, emission config):
  `node/runtime_definitions/contracts.py`
- **Node config** (.env, deployment, schedules):
  `node/`

## Validation after changes

```bash
cd node
make verify-e2e
```
