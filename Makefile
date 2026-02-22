COMPOSE := docker compose -f docker-compose.yml --env-file .local.env

.PHONY: deploy down logs test

deploy:
	$(COMPOSE) build
	$(COMPOSE) up -d postgres
	$(COMPOSE) run --rm init-db
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

test:
	uv run python -m pytest tests/ -x -q

# Database migrations (Alembic)
migrate:
	$(COMPOSE) exec coordinator-node alembic upgrade head

db-reset:
	$(COMPOSE) exec coordinator-node python -m coordinator_node.db.init_db --reset

migration:
	@read -p "Migration message: " msg; \
	$(COMPOSE) exec coordinator-node alembic revision --autogenerate -m "$$msg"
