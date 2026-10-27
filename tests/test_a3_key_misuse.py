"""A3 — reusing an Idempotency-Key with a different payload is a 409."""

from __future__ import annotations

import asyncio
import json

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


def test_key_reuse_with_different_reason_is_conflict(env):
    """The audit reason is part of the request payload (A3), not a free annotation."""

    async def scenario() -> None:
        async with api(env.app) as client:
            key = "a3-reason-key"
            first = await client.post(
                "/api/certificates/bulk-issue",
                headers={**EAST, "Idempotency-Key": key},
                json={"courseId": "course_east_fire", "reason": "quarterly compliance"},
            )
            assert first.status_code == 200
            before = snapshot_counts(env.db)

            # Same course, different reason: key misuse, exactly like a different course.
            conflict = await client.post(
                "/api/certificates/bulk-issue",
                headers={**EAST, "Idempotency-Key": key},
                json={"courseId": "course_east_fire", "reason": "re-onboarding"},
            )
            assert conflict.status_code == 409
            assert conflict.json()["code"] == "idempotency_key_reuse"
            assert snapshot_counts(env.db) == before, "a 409 must not execute a second operation"

            # The audit trail still carries the reason of the operation that actually ran.
            details = [
                json.loads(row["detail"])
                for row in env.db.conn.execute(
                    "SELECT detail FROM audit_events WHERE action = 'ISSUED'"
                ).fetchall()
            ]
            reasons = {d["reason"] for d in details if d.get("courseId") == "course_east_fire"}
            assert reasons == {"quarterly compliance"}

            replay = await client.post(
                "/api/certificates/bulk-issue",
                headers={**EAST, "Idempotency-Key": key},
                json={"courseId": "course_east_fire", "reason": "quarterly compliance"},
            )
            assert replay.status_code == 200
            assert replay.headers["Idempotency-Replayed"] == "true"
            assert replay.json() == first.json()

    asyncio.run(scenario())


def test_blank_reason_is_the_same_request_as_no_reason(env):
    """Absent, null, "" and "   " all canonicalise to "no reason", so they replay (A2).

    Rows written before `reason` joined the hash also replay: the absent-reason
    serialisation is unchanged, so legacy keys are not poisoned by the upgrade.
    """

    async def scenario() -> None:
        async with api(env.app) as client:
            key = "a3-blank-reason"
            headers = {**EAST, "Idempotency-Key": key}

            first = await client.post(
                "/api/certificates/bulk-issue",
                headers=headers,
                json={"courseId": "course_east_safety"},
            )
            assert first.status_code == 200
            before = snapshot_counts(env.db)

            for payload in (
                {"courseId": "course_east_safety", "reason": None},
                {"courseId": "course_east_safety", "reason": ""},
                {"courseId": "course_east_safety", "reason": "   "},
            ):
                replay = await client.post(
                    "/api/certificates/bulk-issue", headers=headers, json=payload
                )
                assert replay.status_code == 200, payload
                assert replay.headers["Idempotency-Replayed"] == "true"
                assert replay.json() == first.json()

            assert snapshot_counts(env.db) == before

    asyncio.run(scenario())
