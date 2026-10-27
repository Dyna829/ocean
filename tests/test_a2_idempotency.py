"""A2 — retry safety: the same Idempotency-Key is one logical operation."""

from __future__ import annotations

import asyncio

from tests.support import EAST, api, audit_count, snapshot_counts


def test_sequential_and_concurrent_retries(env):
    async def scenario() -> None:
        async with api(env.app) as client:
            key = "a2-fire-safety"
            payload = {"courseId": "course_east_fire"}

            first = await client.post(
                "/api/certificates/bulk-issue",
                headers={**EAST, "Idempotency-Key": key},
                json=payload,
            )
            assert first.status_code == 200
            assert first.headers["Idempotency-Replayed"] == "false"
            body = first.json()
            assert body["summary"] == {"total": 4, "issued": 4, "skipped": 0, "failed": 0}

            after_first = snapshot_counts(env.db)

            # Sequential retry with the same key returns the same logical result.
            second = await client.post(
                "/api/certificates/bulk-issue",
                headers={**EAST, "Idempotency-Key": key},
                json=payload,
            )
            assert second.status_code == 200
            assert second.headers["Idempotency-Replayed"] == "true"
            assert second.json() == body
            assert snapshot_counts(env.db) == after_first

            for outcome in body["outcomes"]:
                if outcome["status"] == "issued":
                    assert audit_count(env.db, outcome["certificateId"], "ISSUED") == 1
                    assert audit_count(env.db, outcome["certificateId"]) == 1

            # Concurrent first execution: six callers, one operation, one write set.
            key_concurrent = "a2-safety-concurrent"
            concurrent_payload = {"courseId": "course_east_safety"}
            responses = await asyncio.gather(
                *[
                    client.post(
                        "/api/certificates/bulk-issue",
                        headers={**EAST, "Idempotency-Key": key_concurrent},
                        json=concurrent_payload,
                    )
                    for _ in range(6)
                ]
            )

            assert {response.status_code for response in responses} == {200}
            bodies = [response.json() for response in responses]
            assert len({entry["operationId"] for entry in bodies}) == 1
            assert all(entry == bodies[0] for entry in bodies)
            assert bodies[0]["summary"]["issued"] == 2

            replayed = [response.headers["Idempotency-Replayed"] for response in responses]
            assert replayed.count("true") == 5
            assert replayed.count("false") == 1

            # 4 + 2 certificates and one audit event per issuance, nothing duplicated.
            assert snapshot_counts(env.db) == (after_first[0] + 2, after_first[1] + 2)

    asyncio.run(scenario())
