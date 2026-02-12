# extensions (node-private)

Use this folder for **node-specific callable overrides** selected via env variables.

## Put code here when

- default functionality from the coordinator core packages is not enough
- override should stay private to this node deployment
- you need custom ranking/scope/predict/report behavior

## Common override callables

```python
def build_prediction_scope(config, inference_input):
    ...

def build_predict_call(config, inference_input, scope):
    ...

def rank_leaderboard(entries):
    ...
```

## Wire via env

- `PREDICTION_SCOPE_BUILDER=extensions.scope:build_prediction_scope`
- `PREDICT_CALL_BUILDER=extensions.predict:build_predict_call`
- `LEADERBOARD_RANKER=extensions.ranking:rank_leaderboard`

Match signatures exactly, otherwise runtime validation will fail.
