#!/bin/bash

# production-build.sh
get_docker_compose() {
    if docker compose version >/dev/null 2>&1; then
        echo "docker compose"
    elif command -v docker-compose >/dev/null 2>&1; then
        echo "docker-compose"
    else
        echo "❌ Docker Compose not found" >&2
        return 1
    fi
}

DOCKER_COMPOSE=$(get_docker_compose) || exit 1


echo "Starting production build..."

ENV_FILE=.production.env $DOCKER_COMPOSE -f docker-compose.yml  up --build -d

echo "Production build completed and running in detached mode!"