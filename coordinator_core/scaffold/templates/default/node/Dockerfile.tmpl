FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends     libpq5     && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir     densitypdf>=0.1.4     fastapi>=0.121.3     model-runner-client>=0.10.0     numpy>=2.3.4     psycopg2-binary>=2.9.11     requests>=2.32.5     sqlmodel>=0.0.27     uvicorn>=0.38.0

COPY runtime/coordinator_core ./coordinator_core
COPY runtime/coordinator_runtime ./coordinator_runtime
COPY runtime/node_template ./node_template
COPY runtime_definitions ./runtime_definitions

CMD ["python", "-m", "node_template"]
