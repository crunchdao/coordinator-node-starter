COMPOSE := docker compose -f docker-compose.yml --env-file .local.env

.PHONY: deploy down logs test

deploy:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

test:
	uv run python -m pytest tests/ -x -q
