"""Logging: levels, request correlation, business events, and error handling."""

from __future__ import annotations

import asyncio
import json
import logging

from app.logging import REQUEST_ID, JsonFormatter, TextFormatter
from app.main import create_app
from tests.support import EAST, api


def test_request_log_carries_request_id_and_tenant(env, caplog):
    caplog.set_level(logging.DEBUG, logger="app")

    async def scenario() -> str:
        async with api(env.app) as client:
            response = await client.get("/api/certificates", params={"pageSize": 2}, headers=EAST)
            assert response.status_code == 200
            return response.headers["X-Request-Id"]

    request_id = asyncio.run(scenario())
    assert request_id

    records = [record for record in caplog.records if record.getMessage() == "request"]
    assert records, "every API request must emit one 'request' log line"
    fields = records[-1].fields
    assert fields["method"] == "GET"
    assert fields["path"] == "/api/certificates"
    assert fields["status"] == 200
    assert fields["actor"] == "alice@east.test"
    assert fields["tenant"] == "east"
    assert fields["durationMs"] >= 0


def test_bulk_issue_logs_operation_summary(env, caplog):
    caplog.set_level(logging.INFO, logger="app")

    async def scenario() -> None:
        async with api(env.app) as client:
            response = await client.post(
                "/api/certificates/bulk-issue",
                headers={**EAST, "Idempotency-Key": "logging-bulk"},
                json={"courseId": "course_east_fire"},
            )
            assert response.status_code == 200

    asyncio.run(scenario())

    events = {
        record.getMessage(): record
        for record in caplog.records
        if record.name == "app.certificates"
    }
    assert events["bulk_issue.start"].fields["courseId"] == "course_east_fire"
    done = events["bulk_issue.done"].fields
    assert done["issued"] == 4
    assert done["skipped"] == 0
    assert done["failed"] == 0
    assert done["operationId"].startswith("op_")
    assert events["bulk_issue.start"].fields["operationId"] == done["operationId"]


def test_idempotency_conflict_is_warning(env, caplog):
    caplog.set_level(logging.INFO, logger="app")

    async def scenario() -> None:
        async with api(env.app) as client:
            headers = {**EAST, "Idempotency-Key": "logging-conflict"}
            first = await client.post(
                "/api/certificates/bulk-issue",
                headers=headers,
                json={"courseId": "course_east_fire"},
            )
            assert first.status_code == 200
            second = await client.post(
                "/api/certificates/bulk-issue",
                headers=headers,
                json={"courseId": "course_east_safety"},
            )
            assert second.status_code == 409

    asyncio.run(scenario())

    conflicts = [
        record for record in caplog.records if record.getMessage() == "bulk_issue.conflict"
    ]
    assert conflicts
    assert conflicts[0].levelno == logging.WARNING


def test_debug_records_are_hidden_at_info_level(env, caplog):
    caplog.set_level(logging.INFO, logger="app")

    async def scenario() -> None:
        async with api(env.app) as client:
            assert (await client.get("/api/certificates", headers=EAST)).status_code == 200

    asyncio.run(scenario())

    debug_records = [
        record
        for record in caplog.records
        if record.name == "app.certificates" and record.levelno < logging.INFO
    ]
    assert debug_records == []


def test_unhandled_error_returns_500_with_request_id(env, caplog):
    @env.app.get("/api/_boom")
    def boom() -> None:
        raise RuntimeError("kaboom")

    caplog.set_level(logging.ERROR, logger="app")

    async def scenario() -> None:
        async with api(env.app) as client:
            response = await client.get("/api/_boom", headers=EAST)
            assert response.status_code == 500
            assert response.json() == {
                "code": "internal_error",
                "message": "Internal server error",
            }
            assert response.headers["X-Request-Id"]

    asyncio.run(scenario())

    failures = [record for record in caplog.records if record.getMessage() == "request.failed"]
    assert failures
    assert failures[0].levelno == logging.ERROR
    assert failures[0].fields["status"] == 500


def test_slow_request_is_warned(env, caplog, monkeypatch):
    monkeypatch.setenv("LOG_SLOW_REQUEST_MS", "0")
    app = create_app(env.db, serve_static=False)
    caplog.set_level(logging.INFO, logger="app")

    async def scenario() -> None:
        async with api(app) as client:
            assert (await client.get("/api/health")).status_code == 200

    asyncio.run(scenario())

    slow = [record for record in caplog.records if record.getMessage() == "request.slow"]
    assert slow
    assert slow[0].levelno == logging.WARNING


def test_client_request_id_is_echoed_when_safe(env):
    async def scenario() -> None:
        async with api(env.app) as client:
            traced = await client.get(
                "/api/health", headers={"X-Request-Id": "web-trace-abc123"}
            )
            assert traced.headers["X-Request-Id"] == "web-trace-abc123"

            rejected = await client.get(
                "/api/health", headers={"X-Request-Id": "bad id!"}
            )
            generated = rejected.headers["X-Request-Id"]
            assert generated != "bad id!"
            assert len(generated) >= 8

    asyncio.run(scenario())


def test_formatters_emit_structured_fields():
    record = logging.LogRecord(
        "app.test", logging.WARNING, __file__, 1, "sample.event", None, None
    )
    record.fields = {"actor": "alice@east.test", "count": 3, "note": "two words"}

    token = REQUEST_ID.set("req-123")
    try:
        text = TextFormatter().format(record)
        payload = json.loads(JsonFormatter().format(record))
    finally:
        REQUEST_ID.reset(token)

    assert "sample.event" in text
    assert "request_id=req-123" in text
    assert 'note="two words"' in text
    assert payload["level"] == "WARNING"
    assert payload["event"] == "sample.event"
    assert payload["request_id"] == "req-123"
    assert payload["count"] == 3
