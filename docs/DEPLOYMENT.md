# Deployment

## Local deploy

```bash
make deploy
```

## Common commands

```bash
make logs
make logs SERVICES="predict-worker score-worker report-worker"
make restart
make down
```

## Required verification after changes

```bash
sleep 5
docker compose -f docker-compose.yml -f docker-compose-local.yml --env-file .local.env \
  logs score-worker predict-worker report-worker --tail 300 2>&1 \
  | grep -i "error\|exception\|traceback\|failed\|validation" | tail -20

docker compose -f docker-compose.yml -f docker-compose-local.yml --env-file .local.env ps
curl -s http://localhost:8000/healthz
```

Do not consider deployment complete if verification fails.
