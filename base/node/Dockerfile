FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Coordinator engine (from PyPI)
# Bump this to force Docker to re-pull the latest package version
ARG COORDINATOR_NODE_VERSION=0.1.2
RUN pip install --no-cache-dir "coordinator-node>=${COORDINATOR_NODE_VERSION}"

# Challenge package
COPY challenge ./challenge
RUN pip install --no-cache-dir -e ./challenge

# Runtime definitions (operator customization)
COPY node/runtime_definitions ./runtime_definitions
