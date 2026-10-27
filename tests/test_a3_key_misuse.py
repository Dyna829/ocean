"""A3 — reusing an Idempotency-Key with a different payload is a 409."""

from __future__ import annotations

import asyncio

from tests.support import EAST, api, snapshot_counts


def test_key_reuse_with_different_payload(env):
    async def scenario() -> None:
        async with api(env.app) as client:
            key = "a3-key"
            first = await client.post(
                "/api/certificates/bulk-issue",
                headers={**EAST, "Idempotency-Key": key},
                json={"courseId": "course_east_fire"},
            )
            assert first.status_code == 200
            before = snapshot_counts(env.db)

            conflict = await client.post(
                "/api/certificates/bulk-issue",
                headers={**EAST, "Idempotency-Key": key},
                json={"courseId": "course_east_safety"},
            )
            assert conflict.status_code == 409
            assert conflict.json()["code"] == "idempotency_key_reuse"
            assert snapshot_counts(env.db) == before, "a 409 must not execute a second operation"

            # The stored result for the original payload is untouched.
            replay = await client.post(
                "/api/certificates/bulk-issue",
                headers={**EAST, "Idempotency-Key": key},
                json={"courseId": "course_east_fire"},
            )
            assert replay.status_code == 200
            assert replay.json() == first.json()
            assert replay.headers["Idempotency-Replayed"] == "true"

            # A missing key is a 400, not an accidental non-idempotent write.
            missing = await client.post(
                "/api/certificates/bulk-issue",
                headers=EAST,
                json={"courseId": "course_east_fire"},
            )
            assert missing.status_code == 400
            assert missing.json()["code"] == "idempotency_key_required"

            # Cross-payload reuse is scoped per tenant: the West admin can use the same string.
            west_same_key = await client.post(
                "/api/certificates/bulk-issue",
                headers={"X-Actor-Email": "bob@west.test", "Idempotency-Key": key},
                json={"courseId": "course_west_fire"},
            )
            assert west_same_key.status_code == 200
            assert west_same_key.json()["summary"]["issued"] == 3

    asyncio.run(scenario())
