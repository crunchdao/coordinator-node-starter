from __future__ import annotations

import logging

import uvicorn
from fastapi import FastAPI

app = FastAPI(title="Node Template Report Worker")


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/reports/leaderboard")
def get_leaderboard() -> list[dict]:
    """Compatibility route retained during runtime migration."""
    return []


@app.get("/reports/models")
def get_models() -> list[dict]:
    """Compatibility route retained during runtime migration."""
    return []


if __name__ == "__main__":
    logging.getLogger(__name__).info("node_template report worker bootstrap")
    uvicorn.run(app, host="0.0.0.0", port=8000)
