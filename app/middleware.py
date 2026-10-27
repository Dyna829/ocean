from __future__ import annotations

import re
import secrets
import time

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse

from .logging import REQUEST_ID, get_logger

log = get_logger("app.request")

EXCLUDED_PREFIXES = ("/assets/",)
EXCLUDED_PATHS = ("/favicon.svg",)
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class RequestLogMiddleware:
    """One structured log line per request, plus X-Request-Id on the response.

    It is a raw ASGI middleware on purpose: ``BaseHTTPMiddleware`` adds buffering
    around streaming responses, which would interfere with the CSV export (A6).
    """

    def __init__(self, app, slow_request_ms: int = 2000) -> None:
        self.app = app
        self.slow_request_ms = slow_request_ms

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in EXCLUDED_PATHS or path.startswith(EXCLUDED_PREFIXES):
            await self.app(scope, receive, send)
            return

        incoming_id = Headers(scope=scope).get("x-request-id", "")
        request_id = (
            incoming_id if REQUEST_ID_PATTERN.match(incoming_id) else secrets.token_hex(6)
        )
        token = REQUEST_ID.set(request_id)
        started = time.perf_counter()
        status = 0
        response_started = False

        async def send_with_request_id(message):
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                status = message["status"]
                response_started = True
                headers = MutableHeaders(scope=message)
                headers.append("X-Request-Id", request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            duration_ms = self._elapsed_ms(started)
            log.exception(
                "request.failed",
                extra={"fields": self._fields(scope, status or 500, duration_ms)},
            )
            if response_started:
                raise
            response = JSONResponse(
                {"code": "internal_error", "message": "Internal server error"},
                status_code=500,
                headers={"X-Request-Id": request_id},
            )
            await response(scope, receive, send)
        else:
            duration_ms = self._elapsed_ms(started)
            fields = self._fields(scope, status, duration_ms)
            if duration_ms >= self.slow_request_ms:
                log.warning(
                    "request.slow",
                    extra={"fields": {**fields, "thresholdMs": self.slow_request_ms}},
                )
            else:
                log.info("request", extra={"fields": fields})
        finally:
            REQUEST_ID.reset(token)

    def _fields(self, scope, status: int, duration_ms: float) -> dict:
        state = scope.get("state") or {}
        fields: dict = {
            "method": scope.get("method", ""),
            "path": scope.get("path", ""),
            "status": status,
            "durationMs": duration_ms,
        }
        if state.get("actor_email"):
            fields["actor"] = state["actor_email"]
        if state.get("tenant_slug"):
            fields["tenant"] = state["tenant_slug"]
        return fields

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        return round((time.perf_counter() - started) * 1000, 1)
