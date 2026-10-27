from __future__ import annotations

import contextlib
import csv
import io
from typing import AsyncIterator

import httpx

EAST = {"X-Actor-Email": "alice@east.test"}
WEST = {"X-Actor-Email": "bob@west.test"}


@contextlib.asynccontextmanager
async def api(app) -> AsyncIterator[httpx.AsyncClient]:
    """In-process ASGI client (fast, no sockets)."""
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://console.test", timeout=30
    ) as client:
        yield client


def table_count(db, table: str, where: str = "", params: tuple = ()) -> int:
    query = f"SELECT COUNT(*) AS n FROM {table}"
    if where:
        query += f" WHERE {where}"
    return int(db.conn.execute(query, params).fetchone()["n"])


def snapshot_counts(db) -> tuple[int, int]:
    return (
        table_count(db, "certificates"),
        table_count(db, "audit_events"),
    )


def audit_count(db, certificate_id: str, action: str | None = None) -> int:
    if action is None:
        return table_count(db, "audit_events", "certificate_id = ?", (certificate_id,))
    return table_count(
        db, "audit_events", "certificate_id = ? AND action = ?", (certificate_id, action)
    )


def csv_rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))
