# Entities

`coordinator_core/entities/` defines stable core entities.

Key objects:

- `Model`
- `PredictionRecord`
- `PredictionScore`
- `ModelScore`
- `Checkpoint`
- `EmissionCheckpoint`

Persistence model lives in `coordinator_core/infrastructure/db/db_tables.py`.

Default extension strategy:
- keep protocol columns stable
- store Crunch-specific payloads in JSONB fields
