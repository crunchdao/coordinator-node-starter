FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi>=0.121.3 \
    model-runner-client>=0.10.0 \
    psycopg2-binary>=2.9.11 \
    pydantic>=2.0 \
    requests>=2.32.5 \
    sqlmodel>=0.0.27 \
    uvicorn>=0.38.0

# Runtime coordinator package (vendored or installed)
COPY node/runtime/coordinator ./coordinator

# Challenge package
COPY challenge ./challenge
RUN pip install --no-cache-dir -e ./challenge

# Runtime definitions (operator customization)
COPY node/runtime_definitions ./runtime_definitions
