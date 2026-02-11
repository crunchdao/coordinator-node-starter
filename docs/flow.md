# Standard Local Coordinator Flow

This is the recommended deterministic local flow for creating and validating a crunch workspace.

## 1) Create upfront answers file

Use a single answers file for core decisions so setup is reproducible.

Example (`answers.json`):

```json
{
  "name": "btc-vol",
  "crunch_id": "btc-vol",
  "checkpoint_interval_seconds": 60,
  "model_base_classname": "tracker.TrackerBase"
}
```

Supported formats:
- JSON (`.json`)
- YAML (`.yml` / `.yaml`, requires PyYAML)

## 2) Run preflight (halt if required ports are busy)

```bash
coordinator preflight --ports 3000,5432,8000,9091
```

If busy, preflight exits non-zero and prints actionable commands (`lsof ...`).

## 3) Initialize workspace

```bash
coordinator init --answers answers.json --output .
```

Optional:

```bash
coordinator init --answers answers.json --spec spec.json --preset realtime --output .
```

Merge behavior:
- Answers are loaded first
- Spec values override answers

## 4) Validate

```bash
coordinator doctor --spec <workspace>/spec.json
cd <workspace>/crunch-node-<name>
make deploy
make verify-e2e
make logs-capture
```

## Deterministic defaults included by scaffold

- `MODEL_BASE_CLASSNAME` canonicalized to `tracker.TrackerBase`
- Node `pyproject.toml` includes local package mapping under `[tool.uv.sources]`
- `RUNBOOK.md` generated in node workspace
- `process-log.jsonl` generated in workspace root

## Generated troubleshooting references

- `crunch-node-<name>/RUNBOOK.md`
- `<workspace>/process-log.jsonl`
