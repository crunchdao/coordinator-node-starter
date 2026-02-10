# Report Worker

Canonical entrypoint:
- `node_template/workers/report_worker.py`

Current API:

- `GET /healthz`
- `GET /reports/models`
- `GET /reports/leaderboard`
- `GET /reports/models/global`
- `GET /reports/models/params`
- `GET /reports/predictions`

Purpose:
- expose coordinator metrics for UI/consumers
- keep read APIs decoupled from scoring/predict loops
