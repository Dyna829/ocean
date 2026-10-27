"""A6 — 100,000-row export: under 60s, deterministic ties, list stays responsive.

Uses a real uvicorn server so the streaming and concurrency behaviour is measured
over HTTP rather than buffered by an in-process transport.
"""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest

from app.bulkdata import insert_bulk_certificates
from tests.support import EAST

BULK_COUNT = 100_000
EXPORT_HEADER = "learner_name,course_title,serial_number,issue_date"
EAST_BASE_ROWS = 13  # seeded East certificates


@pytest.fixture()
def large_env(env):
    with env.db.write() as conn:
        insert_bulk_certificates(conn, tenant_id="tenant_east", count=BULK_COUNT)
    return env


def test_export_100k(large_env, live_server):
    base_url = live_server

    async def scenario() -> None:
        params = {"sort": "learner_name", "dir": "asc"}
        timeout = httpx.Timeout(120.0)

        async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
            started = time.monotonic()
            first = await client.get("/api/certificates/export.csv", params=params, headers=EAST)
            elapsed = time.monotonic() - started

            assert first.status_code == 200
            assert first.headers["content-type"].startswith("text/csv")
            assert elapsed < 60, f"A6 export took {elapsed:.1f}s (budget 60s)"

            lines = first.text.splitlines()
            assert lines[0] == EXPORT_HEADER
            assert len(lines) == 1 + EAST_BASE_ROWS + BULK_COUNT

            # Rows with equal sort keys keep the same relative order on repeated exports.
            second = await client.get(
                "/api/certificates/export.csv", params=params, headers=EAST
            )
            assert second.text == first.text

            # Search and sort are preserved by the export.
            filtered = await client.get(
                "/api/certificates/export.csv",
                params={"q": "Bulk Learner 07", "sort": "serial", "dir": "desc"},
                headers=EAST,
            )
            filtered_rows = filtered.text.splitlines()[1:]
            assert len(filtered_rows) == BULK_COUNT // 50
            assert all("Bulk Learner 07" in row for row in filtered_rows)
            serials = [row.split(",")[2] for row in filtered_rows]
            assert serials == sorted(serials, reverse=True)

            # The certificate list must succeed while the export stream is still open.
            async with client.stream(
                "GET", "/api/certificates/export.csv", params=params, headers=EAST
            ) as stream:
                assert stream.status_code == 200
                line_iterator = stream.aiter_lines()
                assert await anext(line_iterator) == EXPORT_HEADER

                list_started = time.monotonic()
                listing = await client.get(
                    "/api/certificates", params={"pageSize": 5}, headers=EAST
                )
                list_elapsed = time.monotonic() - list_started

                assert listing.status_code == 200
                assert listing.json()["total"] == EAST_BASE_ROWS + BULK_COUNT
                assert list_elapsed < 5, f"list blocked for {list_elapsed:.1f}s during export"

                consumed = 1
                async for _ in line_iterator:
                    consumed += 1
                assert consumed == 1 + EAST_BASE_ROWS + BULK_COUNT

    asyncio.run(scenario())
