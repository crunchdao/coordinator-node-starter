FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Coordinator engine (from PyPI)
RUN pip install --no-cache-dir coordinator-node>=0.1.1

# Challenge package
COPY challenge ./challenge
RUN pip install --no-cache-dir -e ./challenge

# Runtime definitions (operator customization)
COPY node/runtime_definitions ./runtime_definitions
