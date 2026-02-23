COMPOSE := docker compose -f docker-compose.yml --env-file .local.env

.PHONY: deploy down logs test init-db reset-db migrate migration

deploy:
	$(COMPOSE) build
	$(COMPOSE) up -d postgres
	$(COMPOSE) run --rm init-db
	$(COMPOSE) up -d

init-db:
	$(COMPOSE) run --rm init-db

reset-db:
	$(COMPOSE) run --rm reset-db

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

test:
	PYTHONPATH=base/challenge:base/node uv run python -m pytest tests/ -x -q

test-e2e:
	bash tests/test_e2e_ui_smoke.sh

# Database migrations (Alembic)
migrate:
	$(COMPOSE) run --rm init-db

migration:
	@read -p "Migration message: " msg; \
	$(COMPOSE) run --rm init-db alembic revision --autogenerate -m "$$msg"
