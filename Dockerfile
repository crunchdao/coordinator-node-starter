FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Needed for Postgres (psycopg2-binary) and git
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
RUN uv sync

# Activate venv
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Copy entrypoint script
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

# Copy the application code
COPY condorgame_backend ./condorgame_backend

# Entrypoint conditionally enables NewRelic if license key is provided
ENTRYPOINT ["./entrypoint.sh"]

# Default command — overridden in docker compose for each worker
CMD ["python", "-m", "condorgame_backend"]