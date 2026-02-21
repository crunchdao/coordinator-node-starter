FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN addgroup --gid 1001 --system appgroup && \
    adduser --system --uid 1001 --ingroup appgroup appuser

WORKDIR /app

# Coordinator engine (from PyPI)
# Bump this to force Docker to re-pull the latest package version
ARG COORDINATOR_NODE_VERSION=0.1.6
RUN pip install --no-cache-dir "coordinator-node>=${COORDINATOR_NODE_VERSION}"

# Challenge package (regular install, not editable)
COPY --chown=appuser:appgroup challenge ./challenge
RUN pip install --no-cache-dir ./challenge

# Runtime definitions (operator customization)
COPY --chown=appuser:appgroup node/runtime_definitions ./runtime_definitions

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD curl -sf http://localhost:8000/healthz || exit 1

CMD ["python", "-m", "coordinator_node"]
