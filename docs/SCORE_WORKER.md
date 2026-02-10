# Score Worker

Canonical entrypoint:
- `node_template/workers/score_worker.py`

Main service:
- `node_template/services/score_service.py`

Responsibilities:
- fetch ready predictions
- apply configured scoring function
- persist prediction scores
- aggregate ModelScore entries
- apply leaderboard ranker and persist leaderboard
