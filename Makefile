# ---------------------------------------------------------
# Condor Backend Deployment Makefile
# ---------------------------------------------------------

# Optional CLI override:
#   make deploy dev SERVICES="predict-worker score-worker"
SERVICES ?=

# List of backend services only (edit here if needed)
BACKEND_SERVICES = \
    init-db \
    predict-worker \
    score-worker \
    report-worker

IS_ALL := $(filter all,$(MAKECMDGOALS))
IS_DEV := $(filter dev,$(MAKECMDGOALS))
IS_PRODUCTION := $(filter production,$(MAKECMDGOALS))

# Compose files
COMPOSE_FILES := -f docker-compose.yml
ifeq ($(IS_PRODUCTION),production)
	COMPOSE_FILES += -f docker-compose-prod.yml --env-file .production.env --profile production
else ifeq ($(IS_DEV),dev)
	COMPOSE_FILES += -f docker-compose-local.yml --env-file .dev.env
else
    # used during dev or local testing
	COMPOSE_FILES += -f docker-compose-local.yml --env-file .local.env
endif

# Decide the list of services
# If SERVICES is provided on the command line, we keep it as-is.
# Otherwise, we fall back to your default logic.
ifeq ($(SERVICES),)
	ifeq ($(IS_ALL),all)
		SERVICES :=
	else ifeq ($(IS_DEV),dev)
        SERVICES_EXCLUDE := $(BACKEND_SERVICES) documentation
		SERVICES := $(filter-out $(SERVICES_EXCLUDE),$(shell docker compose $(COMPOSE_FILES) config --services))
	else ifeq ($(IS_PRODUCTION),production)
		SERVICES := $(BACKEND_SERVICES)
	else
		SERVICES :=
	endif
endif

# ---------------------------------------------------------
# Commands
# ---------------------------------------------------------

## Build + deploy
deploy:
	docker compose $(COMPOSE_FILES) up -d --build $(SERVICES)

## Restart services
restart:
ifneq ($(SERVICES),)
	docker compose $(COMPOSE_FILES) restart $(SERVICES)
else
	docker compose $(COMPOSE_FILES) restart
endif

## Stop services
stop:
ifneq ($(SERVICES),)
	docker compose $(COMPOSE_FILES) stop $(SERVICES)
else
	docker compose $(COMPOSE_FILES) stop
endif

## Logs (follow)
logs:
ifneq ($(SERVICES),)
	docker compose $(COMPOSE_FILES) logs -f $(SERVICES)
else
	docker compose $(COMPOSE_FILES) logs -f
endif

## Stop & remove
down:
ifneq ($(SERVICES),)
	docker compose $(COMPOSE_FILES) down $(SERVICES)
else
	docker compose $(COMPOSE_FILES) down
endif

## Build images
build:
ifneq ($(SERVICES),)
	docker compose $(COMPOSE_FILES) build $(SERVICES)
else
	docker compose $(COMPOSE_FILES) build
endif

## Verify local end-to-end starter workflow
verify-e2e:
	uv run python scripts/verify_e2e.py

# ---------------------------------------------------------
# Tell make "all" is not a target, it's an argument
# ---------------------------------------------------------
.PHONY: deploy restart stop logs down build verify-e2e all dev production

all:
	@true   # do nothing

dev:
	@true   # do nothing

production:
	@true   # do nothing