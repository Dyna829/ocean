"""A5 — one UTC instant, two tenant-local calendar dates (DST-safe)."""

from __future__ import annotations

import asyncio

from tests.support import EAST, WEST, api, csv_rows


def test_tenant_local_dates(env):
    async def scenario() -> None:
        async with api(env.app) as client:
            east = (
                await client.get("/api/certificates", params={"q": "Alex Lee"}, headers=EAST)
            ).json()
            west = (
                await client.get("/api/certificates", params={"q": "Alex Lee"}, headers=WEST)
            ).json()

            east_item = east["items"][0]
            west_item = west["items"][0]

            assert east_item["serial"] == "CERT-EAST-2026-000001"
            assert west_item["serial"] == "CERT-WEST-2026-000001"

            # Same instant, different tenant-local rendering.
            assert east_item["issuedAt"] == west_item["issuedAt"] == "2026-01-10T13:30:00Z"
            assert east_item["issuedAtLocal"] == "2026-01-11 00:30"  # Australia/Sydney, AEDT
            assert east_item["issueDateLocal"] == "2026-01-11"
            assert west_item["issuedAtLocal"] == "2026-01-10 21:30"  # Australia/Perth, AWST
            assert west_item["issueDateLocal"] == "2026-01-10"

            # CSV exports the tenant-local calendar date, not the UTC date.
            east_csv = csv_rows(
                (
                    await client.get(
                        "/api/certificates/export.csv",
                        params={"q": "Alex Lee", "sort": "serial", "dir": "asc"},
                        headers=EAST,
                    )
                ).text
            )
            west_csv = csv_rows(
                (
                    await client.get(
                        "/api/certificates/export.csv",
                        params={"q": "Alex Lee", "sort": "serial", "dir": "asc"},
                        headers=WEST,
                    )
                ).text
            )
            assert east_csv[0]["issue_date"] == "2026-01-11"
            assert west_csv[0]["issue_date"] == "2026-01-10"
            assert east_csv[0]["serial_number"] == "CERT-EAST-2026-000001"

            # Date sorting uses the tenant-local calendar date and is deterministic.
            listing = (
                await client.get(
                    "/api/certificates",
                    params={"sort": "issued_date", "dir": "asc", "pageSize": 100},
                    headers=EAST,
                )
            ).json()
            dates = [item["issueDateLocal"] for item in listing["items"]]
            assert dates == sorted(dates)
            assert listing["items"][0]["serial"] == "CERT-EAST-2026-000001"

            # Ties on the exact same instant are broken by certificate id, not by chance.
            tied = [
                item
                for item in listing["items"]
                if item["issuedAt"] == "2026-01-18T14:25:00Z"
            ]
            assert len(tied) == 2
            assert [item["id"] for item in tied] == sorted(item["id"] for item in tied)

    asyncio.run(scenario())
