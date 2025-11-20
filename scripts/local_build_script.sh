#!/bin/bash

# local-build.sh

echo "Starting local build..."

# Run the local Docker Compose setup
ENV_FILE=.local.env docker compose -f docker-compose.yml up --build

echo "Local build completed!"