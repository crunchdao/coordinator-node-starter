"""PostgreSQL LISTEN/NOTIFY helpers for cross-worker event signaling."""
from __future__ import annotations

import asyncio
import logging
import select as _select
from typing import Any

import psycopg2
from coordinator.db.session import database_url

logger = logging.getLogger(__name__)

CHANNEL = "new_feed_data"


def notify(connection: Any = None) -> None:
    """Send a NOTIFY on the feed data channel. Uses raw psycopg2 connection."""
    own_conn = connection is None
    if own_conn:
        connection = _raw_connection()
    try:
        connection.autocommit = True
        with connection.cursor() as cur:
            cur.execute(f"NOTIFY {CHANNEL}")
    finally:
        if own_conn:
            connection.close()


async def wait_for_notify(timeout: float = 30.0) -> bool:
    """Block (async) until a NOTIFY arrives or timeout. Returns True if notified."""
    conn = _raw_connection()
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(f"LISTEN {CHANNEL}")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _poll_notify, conn, timeout)
    finally:
        conn.close()


def _poll_notify(conn: Any, timeout: float) -> bool:
    """Synchronous poll — runs in executor thread."""
    if _select.select([conn], [], [], timeout) == ([], [], []):
        return False  # timeout
    conn.poll()
    return bool(conn.notifies)


def _raw_connection():
    """Create a raw psycopg2 connection from the same DB URL."""
    url = database_url()
    # Convert sqlalchemy URL to psycopg2 DSN
    # postgresql+psycopg2://user:pass@host:port/db → postgresql://user:pass@host:port/db
    dsn = url.replace("+psycopg2", "")
    return psycopg2.connect(dsn)
