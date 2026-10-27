"""A4 — only eligible learners get certificates; everything else is skipped with a reason."""

from __future__ import annotations

import asyncio

from tests.support import EAST, api, table_count


def test_learner_outcomes(env):
    async def scenario() -> None:
        async with api(env.app) as client:
            response = await client.post(
                "/api/certificates/bulk-issue",
                headers={**EAST, "Idempotency-Key": "a4-safety-101"},
                json={"courseId": "course_east_safety"},
            )
            assert response.status_code == 200
            body = response.json()

            assert body["summary"] == {"total": 4, "issued": 2, "skipped": 2, "failed": 0}
            outcomes = {outcome["learnerName"]: outcome for outcome in body["outcomes"]}

            assert outcomes["Alex Lee"]["status"] == "skipped"
            assert outcomes["Alex Lee"]["reason"] == "already_certified"
            assert outcomes["Alex Lee"]["message"] == "Certificate CERT-EAST-2026-000001 already exists"

            assert outcomes["Tom Baker"]["status"] == "skipped"
            assert outcomes["Tom Baker"]["reason"] == "incomplete_enrollment"

            for name in ("Maya Chen", "Priya Nair"):
                assert outcomes[name]["status"] == "issued"
                assert outcomes[name]["serial"].startswith("CERT-EAST-2026-")

            # No certificate for the incomplete learner, exactly one for the certified one.
            assert table_count(env.db, "certificates", "learner_id = 'learner_east_tom'") == 0
            assert table_count(env.db, "certificates", "learner_id = 'learner_east_alex'") == 1

            # The two new certificates each have exactly one issuance audit event.
            for name in ("Maya Chen", "Priya Nair"):
                assert (
                    table_count(
                        env.db,
                        "audit_events",
                        "certificate_id = ? AND action = 'ISSUED'",
                        (outcomes[name]["certificateId"],),
                    )
                    == 1
                )

    asyncio.run(scenario())
