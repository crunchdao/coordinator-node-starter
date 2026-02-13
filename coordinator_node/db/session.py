from __future__ import annotations

import os

from sqlmodel import Session, create_engine


def database_url() -> str:
    user = os.getenv("POSTGRES_USER", "starter")
    password = os.getenv("POSTGRES_PASSWORD", "starter")
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "starter")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"


engine = create_engine(database_url())

_migrated = False


def create_session() -> Session:
    global _migrated
    if not _migrated:
        from coordinator_node.db.init_db import auto_migrate
        auto_migrate()
        _migrated = True
    return Session(engine)
