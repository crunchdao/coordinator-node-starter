# Database Schema (Canonical)

This document reflects the current canonical SQLModel schema in:

- `coordinator_core/infrastructure/db/db_tables.py`

## ER Diagram

```mermaid
erDiagram
    MODELS ||--o{ PREDICTIONS : "model_id -> models.id"
    SCHEDULED_PREDICTION_CONFIGS ||--o{ PREDICTIONS : "prediction_config_id -> scheduled_prediction_configs.id"
    MODELS ||--o{ MODEL_SCORES : "model_id -> models.id"
    CHECKPOINTS ||--o{ EMISSION_CHECKPOINTS : "checkpoint_id -> checkpoints.id"

    MODELS {
        string id PK
        string name
        string deployment_identifier
        string player_id
        string player_name
        jsonb overall_score_jsonb
        jsonb scores_by_scope_jsonb
        jsonb meta_jsonb
        datetime created_at
        datetime updated_at
    }

    SCHEDULED_PREDICTION_CONFIGS {
        string id PK
        string scope_key
        jsonb scope_template_jsonb
        jsonb schedule_jsonb
        bool active
        int order
        jsonb meta_jsonb
    }

    PREDICTIONS {
        string id PK
        string model_id FK
        string prediction_config_id FK
        string scope_key
        jsonb scope_jsonb
        string status
        float exec_time_ms
        jsonb inference_input_jsonb
        jsonb inference_output_jsonb
        jsonb meta_jsonb
        datetime performed_at
        datetime resolvable_at
        float score_value nullable
        bool score_success nullable
        string score_failed_reason nullable
        datetime score_scored_at nullable
    }

    MODEL_SCORES {
        string id PK
        string model_id FK
        jsonb score_payload_jsonb
        datetime computed_at
    }

    LEADERBOARDS {
        string id PK
        datetime created_at
        jsonb entries_jsonb
        jsonb meta_jsonb
    }

    CHECKPOINTS {
        string id PK
        string checkpoint_kind
        int interval_seconds
        datetime last_run_at nullable
        datetime next_run_at nullable
        jsonb meta_jsonb
    }

    EMISSION_CHECKPOINTS {
        string id PK
        string checkpoint_id FK
        datetime emitted_at
        jsonb payload_jsonb
    }
```

## Notes

- Challenge-specific shapes are carried in JSONB (`*_jsonb`) and typed in application code.
- `scope_key` + `scope_jsonb` are generic prediction dimensions.
- `model_scores.score_payload_jsonb` is the canonical per-model score envelope/payload container.
- `leaderboards.entries_jsonb` remains snapshot-oriented and denormalized by design.
