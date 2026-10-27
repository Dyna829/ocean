from __future__ import annotations

import functools
import time
from typing import Any

from anyio import to_thread
from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from ..auth import Actor, get_actor
from ..logging import get_logger
from ..timeutil import iso_utc, utc_now
from ..services import certificates as service

router = APIRouter()
log = get_logger("app.export")

CSV_HEADER = "learner_name,course_title,serial_number,issue_date\r\n"


class BulkIssueRequest(BaseModel):
    courseId: str = Field(min_length=1, max_length=100)
    reason: str | None = Field(default=None, max_length=200)


class RevokeRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=200)


@router.get("/health")
def health(request: Request) -> dict[str, Any]:
    request.app.state.db.conn.execute("SELECT 1").fetchone()
    return {"status": "ok", "time": iso_utc(utc_now())}


@router.get("/me")
def me(actor: Actor = Depends(get_actor)) -> dict[str, Any]:
    return {
        "actor": {"id": actor.admin_id, "email": actor.email, "name": actor.name},
        "tenant": actor.tenant,
    }


@router.get("/courses")
def courses(request: Request, actor: Actor = Depends(get_actor)) -> dict[str, Any]:
    return service.list_courses(request.app.state.db, actor)


@router.get("/certificates")
def list_certificates(
    request: Request,
    actor: Actor = Depends(get_actor),
    q: str = Query("", max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    sort: str = Query("issued_date", pattern="^(issued_date|learner_name|course_title|serial)$"),
    direction: str = Query("desc", alias="dir", pattern="^(asc|desc)$"),
) -> dict[str, Any]:
    return service.list_certificates(
        request.app.state.db,
        actor,
        q=q.strip(),
        page=page,
        page_size=page_size,
        sort=sort,
        direction=direction,
    )


async def _csv_stream(
    db: Any, actor: Actor, q: str, sort: str, direction: str
) -> Any:
    horizon = await to_thread.run_sync(functools.partial(service.export_horizon, db, actor))
    started = time.perf_counter()
    rows_sent = 0
    log.info(
        "export.start",
        extra={
            "fields": {
                "actor": actor.email,
                "tenant": actor.tenant_slug,
                "sort": sort,
                "dir": direction,
                "qLen": len(q),
            }
        },
    )

    try:
        yield CSV_HEADER

        last: tuple[str, str] | None = None
        while True:
            rows = await to_thread.run_sync(
                functools.partial(
                    service.export_batch,
                    db,
                    actor,
                    q=q,
                    sort=sort,
                    direction=direction,
                    horizon=horizon,
                    last=last,
                )
            )
            if not rows:
                return

            buffer: list[str] = []
            for row in rows:
                buffer.append(
                    f"{service.csv_cell(row['learner_name'])},"
                    f"{service.csv_cell(row['course_title'])},"
                    f"{service.csv_cell(row['serial'])},"
                    f"{service.csv_cell(row['issue_date_local'])}\r\n"
                )
                last = (row["sort_value"], row["id"])
            rows_sent += len(rows)
            yield "".join(buffer)
    finally:
        log.info(
            "export.done",
            extra={
                "fields": {
                    "actor": actor.email,
                    "tenant": actor.tenant_slug,
                    "rows": rows_sent,
                    "durationMs": round((time.perf_counter() - started) * 1000, 1),
                }
            },
        )


@router.get("/certificates/export.csv")
def export_certificates(
    request: Request,
    actor: Actor = Depends(get_actor),
    q: str = Query("", max_length=100),
    sort: str = Query("issued_date", pattern="^(issued_date|learner_name|course_title|serial)$"),
    direction: str = Query("desc", alias="dir", pattern="^(asc|desc)$"),
) -> StreamingResponse:
    filename = f"certificates-{actor.tenant_slug}-{utc_now().strftime('%Y%m%d')}.csv"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }
    stream = _csv_stream(request.app.state.db, actor, q.strip(), sort, direction)
    return StreamingResponse(stream, media_type="text/csv; charset=utf-8", headers=headers)


@router.get("/certificates/{certificate_id}")
def certificate_detail(
    certificate_id: str, request: Request, actor: Actor = Depends(get_actor)
) -> dict[str, Any]:
    return service.get_certificate(request.app.state.db, actor, certificate_id)


@router.post("/certificates/{certificate_id}/revoke")
def revoke_certificate(
    certificate_id: str,
    request: Request,
    payload: RevokeRequest | None = None,
    actor: Actor = Depends(get_actor),
) -> dict[str, Any]:
    reason = payload.reason if payload else None
    return service.revoke_certificate(request.app.state.db, actor, certificate_id, reason)


@router.post("/certificates/bulk-issue")
def bulk_issue(
    payload: BulkIssueRequest,
    request: Request,
    actor: Actor = Depends(get_actor),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    status_code, body, replayed = service.bulk_issue(
        request.app.state.db, actor, payload.courseId, idempotency_key, payload.reason
    )
    return JSONResponse(
        body,
        status_code=status_code,
        headers={"Idempotency-Replayed": "true" if replayed else "false"},
    )
