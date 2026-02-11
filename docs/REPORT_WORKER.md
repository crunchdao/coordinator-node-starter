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
- `GET /reports/schema`
- `GET /reports/schema/leaderboard-columns`
- `GET /reports/schema/metrics-widgets`

Purpose:
- expose coordinator metrics for UI/consumers
- keep read APIs decoupled from scoring/predict loops
- expose canonical report schema so frontend can stay in sync

## Schema provider

Report schema is supplied by a callable configured via:

- `REPORT_SCHEMA_PROVIDER=<module>:<callable>`

Default:

- `node_template.extensions.default_callables:default_report_schema`
  - columns/series centered on 3 window metrics: `score_recent`, `score_steady`, `score_anchor`

Example risk-adjusted profile:

- `node_template.extensions.risk_adjusted_callables:risk_adjusted_report_schema`

The schema provider returns:

- `schema_version`
- `leaderboard_columns`
- `metrics_widgets`

## Frontend override model

Recommended frontend flow:

1. load backend canonical schema from `/reports/schema`
2. merge local override files by key (column `property`, widget `endpoint`/`id`)
3. render merged config
4. warn on override keys not present in backend schema
