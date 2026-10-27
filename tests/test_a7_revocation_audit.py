"""A7 — revoking twice changes state once and writes exactly one audit event."""

from __future__ import annotations

import asyncio

from tests.support import EAST, api, audit_count


def test_revocation_is_idempotent_and_audited(env):
    async def scenario() -> None:
        async with api(env.app) as client:
            certificate_id = "cert_east_sophia_privacy"
            assert audit_count(env.db, certificate_id) == 1

            first = await client.post(
                f"/api/certificates/{certificate_id}/revoke",
                headers=EAST,
                json={"reason": "issued in error"},
            )
            assert first.status_code == 200
            first_body = first.json()
            assert first_body["alreadyRevoked"] is False
            assert first_body["certificate"]["status"] == "REVOKED"
            assert first_body["certificate"]["revokedAt"] is not None

            assert audit_count(env.db, certificate_id) == 2
            assert audit_count(env.db, certificate_id, "REVOKED") == 1

            revoked_event = [event for event in first_body["audit"] if event["action"] == "REVOKED"]
            assert len(revoked_event) == 1
            assert revoked_event[0]["actor"]["email"] == "alice@east.test"
            assert revoked_event[0]["detail"]["reason"] == "issued in error"

            # Repeating the request is a no-op with a 200 and the same audit trail.
            second = await client.post(
                f"/api/certificates/{certificate_id}/revoke", headers=EAST, json={}
            )
            assert second.status_code == 200
            second_body = second.json()
            assert second_body["alreadyRevoked"] is True
            assert second_body["certificate"]["status"] == "REVOKED"
            assert len(second_body["audit"]) == 2
            assert audit_count(env.db, certificate_id, "REVOKED") == 1

            # A certificate that was seeded as revoked behaves the same way.
            seeded_revoked = "cert_east_isla_privacy"
            repeat = await client.post(
                f"/api/certificates/{seeded_revoked}/revoke", headers=EAST, json={}
            )
            assert repeat.status_code == 200
            assert repeat.json()["alreadyRevoked"] is True
            assert audit_count(env.db, seeded_revoked, "REVOKED") == 1

    asyncio.run(scenario())
