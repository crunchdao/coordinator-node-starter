---
name: coordinator-scoring
description: Use when defining or changing scoring callable behavior, ModelScore aggregation, and checkpoint-driven score cadence.
---

# Scoring, ModelScore, and Cadence

> Compatibility note: this skill file remains in `condorgame_backend/services/` for routing, but all implementation targets are in `node_template/` and `coordinator_core/`.

## Goal

Help the user define and implement:
- scoring function
- ModelScore aggregation strategy
- checkpoint interval for scoring cadence

## Canonical places to update

- `node_template/services/score_service.py`
- `node_template/workers/score_worker.py`
- `node_template/config/extensions.py`
- `node_template/config/runtime.py`
- `node_template/extensions/default_callables.py`
- `coordinator_core/infrastructure/db/db_tables.py` (`model_scores`, `score_payload_jsonb`)

## Required decisions to collect

1. scoring contract: `score_prediction(prediction, ground_truth)`
2. score semantics: higher-is-better or lower-is-better (normalize accordingly)
3. ModelScore aggregation contract: `aggregate_model_scores(scored_predictions, models)`
4. leaderboard ranking contract: `rank_leaderboard(entries)`
5. checkpoint interval in seconds (`CHECKPOINT_INTERVAL_SECONDS`)

## Extension contracts

```bash
SCORING_FUNCTION=crunch_<name>.scoring:score_prediction
MODEL_SCORE_AGGREGATOR=crunch_<name>.scoring:aggregate_model_scores
LEADERBOARD_RANKER=crunch_<name>.ranking:rank
CHECKPOINT_INTERVAL_SECONDS=900
```

## Implementation checklist

- [ ] scoring callable handles invalid outputs explicitly
- [ ] failed scores include reason and remain JSON-serializable
- [ ] ModelScore representation documented for crunch implementers
- [ ] ranking behavior deterministic and tested
- [ ] cadence configured and justified for cost/latency tradeoff

## Verification

```bash
make deploy
sleep 5
docker compose -f docker-compose.yml -f docker-compose-local.yml --env-file .local.env \
  logs score-worker --tail 200
```
