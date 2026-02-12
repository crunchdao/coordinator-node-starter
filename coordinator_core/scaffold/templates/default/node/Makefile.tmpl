COMPOSE := docker compose -f docker-compose.yml --env-file .local.env

.PHONY: deploy down logs logs-capture verify-e2e check-models starter platform backfill

deploy:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

logs-capture:
	uv run python scripts/capture_runtime_logs.py --output runtime-services.jsonl

check-models:
	uv run python scripts/check_models.py

verify-e2e: check-models
	uv run --with requests python scripts/verify_e2e.py

starter:
	@sed -i.bak 's/^REPORT_UI_APP=.*/REPORT_UI_APP=starter/' .local.env
	@sed -i.bak 's|^REPORT_UI_DOCKERFILE=.*|REPORT_UI_DOCKERFILE=apps/starter/Dockerfile|' .local.env
	@sed -i.bak 's|^NEXT_PUBLIC_API_URL=.*|# NEXT_PUBLIC_API_URL=https://hub.crunchdao.com|' .local.env
	@rm -f .local.env.bak
	@echo "Switched to starter UI"
	$(COMPOSE) up -d --build report-ui

platform:
	@sed -i.bak 's/^REPORT_UI_APP=.*/REPORT_UI_APP=platform/' .local.env
	@sed -i.bak 's|^REPORT_UI_DOCKERFILE=.*|REPORT_UI_DOCKERFILE=apps/platform/Dockerfile|' .local.env
	@sed -i.bak 's|^# *NEXT_PUBLIC_API_URL=|NEXT_PUBLIC_API_URL=|' .local.env
	@rm -f .local.env.bak
	@echo "Switched to platform UI"
	$(COMPOSE) up -d --build report-ui

backfill:
	$(COMPOSE) run --rm -v $$(pwd)/scripts:/app/scripts:ro \
		-e FEED_PROVIDER=$(or $(PROVIDER),pyth) \
		-e FEED_ASSETS=$(or $(ASSET),BTC) \
		-e FEED_KIND=$(or $(KIND),tick) \
		-e FEED_GRANULARITY=$(or $(GRANULARITY),1s) \
		score-worker python scripts/backfill.py \
		--provider $(or $(PROVIDER),pyth) \
		--asset $(or $(ASSET),BTC) \
		--kind $(or $(KIND),tick) \
		--granularity $(or $(GRANULARITY),1s) \
		--from $(FROM) --to $(TO) \
		$(if $(PAGE_SIZE),--page-size $(PAGE_SIZE))
