"""A1 — tenant isolation: Bob can only see and act on West data."""

from __future__ import annotations

import asyncio

from tests.support import EAST, WEST, api, csv_rows, snapshot_counts


def test_tenant_isolation(env):
    async def scenario() -> None:
        async with api(env.app) as client:
            east = (await client.get("/api/certificates", params={"pageSize": 100}, headers=EAST)).json()
            west = (await client.get("/api/certificates", params={"pageSize": 100}, headers=WEST)).json()

            assert east["total"] == 13
            assert west["total"] == 1
            assert all(item["serial"].startswith("CERT-EAST") for item in east["items"])
            assert all(item["serial"].startswith("CERT-WEST") for item in west["items"])
            assert east["tenant"]["timezone"] == "Australia/Sydney"
            assert west["tenant"]["timezone"] == "Australia/Perth"

            east_id = east["items"][0]["id"]

            # Detail from the wrong tenant is indistinguishable from "not found".
            detail = await client.get(f"/api/certificates/{east_id}", headers=WEST)
            assert detail.status_code == 404
            assert detail.json()["code"] == "certificate_not_found"

            # Cross-tenant bulk issue is rejected before any write happens.
            before = snapshot_counts(env.db)
            bulk = await client.post(
                "/api/certificates/bulk-issue",
                headers={**WEST, "Idempotency-Key": "west-cross-tenant"},
                json={"courseId": "course_east_fire"},
            )
            assert bulk.status_code == 404
            assert bulk.json()["code"] == "course_not_found"
            assert snapshot_counts(env.db) == before, "cross-tenant bulk issue must not write"

            # Cross-tenant revocation is rejected.
            revoke = await client.post(
                f"/api/certificates/{east_id}/revoke", headers=WEST, json={}
            )
            assert revoke.status_code == 404

            # Export is scoped to the actor's tenant.
            export = await client.get(
                "/api/certificates/export.csv", params={"sort": "serial", "dir": "asc"}, headers=WEST
            )
            rows = csv_rows(export.text)
            assert len(rows) == 1
            assert rows[0]["serial_number"].startswith("CERT-WEST")

            # An unknown or missing actor is unauthenticated, not a tenant guess.
            assert (await client.get("/api/certificates")).status_code == 401
            assert (
                await client.get("/api/certificates", headers={"X-Actor-Email": "nobody@test"})
            ).status_code == 401

    asyncio.run(scenario())
