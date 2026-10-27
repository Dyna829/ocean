from __future__ import annotations

import json
import logging
import math
import secrets
import sqlite3
from typing import Any, Literal

from ..auth import Actor
from ..db import Database
from ..errors import ApiError
from ..timeutil import iso_utc, local_date, local_display, utc_now

log = logging.getLogger("app.certificates")

SortField = Literal["issued_date", "learner_name", "course_title", "serial"]
Direction = Literal["asc", "desc"]

# Every ORDER BY is total: the requested key followed by the certificate id.
SORT_COLUMNS: dict[str, str] = {
    "issued_date": "c.issued_at",
    "learner_name": "c.learner_name COLLATE NOCASE",
    "course_title": "c.course_title COLLATE NOCASE",
    "serial": "c.serial",
}

# Column of the selected row that holds the requested sort key (export keyset).
SORT_ROW_KEYS: dict[str, str] = {
    "issued_date": "issued_at",
    "learner_name": "learner_name",
    "course_title": "course_title",
    "serial": "serial",
}

CERT_COLUMNS = """
    c.id, c.serial, c.course_id, c.course_title, c.learner_id, c.learner_name,
    c.status, c.issued_at, c.issue_date_local, c.revoked_at, c.revoked_by,
    c.created_at
"""

EXPORT_BATCH_SIZE = 2000


# --------------------------------------------------------------------------- helpers


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _filters(tenant_id: str, q: str) -> tuple[list[str], list[Any]]:
    clauses = ["c.tenant_id = ?"]
    params: list[Any] = [tenant_id]
    if q:
        pattern = f"%{_escape_like(q)}%"
        clauses.append("(c.learner_name LIKE ? ESCAPE '\\' OR c.serial LIKE ? ESCAPE '\\')")
        params.extend([pattern, pattern])
    return clauses, params


def _order_by(sort: str, direction: str) -> str:
    expr = SORT_COLUMNS[sort]
    return f"ORDER BY {expr} {direction.upper()}, c.id ASC"


def _keyset(expr: str, direction: str, last: tuple[str, str] | None) -> tuple[str, list[Any]]:
    """Keyset predicate matching ORDER BY {expr} {dir}, c.id ASC."""
    if last is None:
        return "", []
    operator = ">" if direction == "asc" else "<"
    clause = f"(({expr}) {operator} ? OR (({expr}) = ? AND c.id > ?))"
    return clause, [last[0], last[0], last[1]]


def _item(row: sqlite3.Row, timezone: str) -> dict[str, Any]:
    return {
        "id": row["id"],
        "serial": row["serial"],
        "courseId": row["course_id"],
        "courseTitle": row["course_title"],
        "learnerId": row["learner_id"],
        "learnerName": row["learner_name"],
        "status": row["status"],
        "issuedAt": row["issued_at"],
        "issuedAtLocal": local_display(row["issued_at"], timezone),
        "issueDateLocal": row["issue_date_local"],
        "revokedAt": row["revoked_at"],
        "revokedAtLocal": local_display(row["revoked_at"], timezone) if row["revoked_at"] else None,
        "revokedBy": row["revoked_by"],
    }


def _audit_item(row: sqlite3.Row, timezone: str) -> dict[str, Any]:
    return {
        "id": row["id"],
        "action": row["action"],
        "actor": {"id": row["actor_id"], "email": row["actor_email"]},
        "at": row["at"],
        "atLocal": local_display(row["at"], timezone),
        "detail": json.loads(row["detail"] or "{}"),
    }


# --------------------------------------------------------------------------- reads


def list_certificates(
    db: Database,
    actor: Actor,
    *,
    q: str,
    page: int,
    page_size: int,
    sort: str,
    direction: str,
) -> dict[str, Any]:
    clauses, params = _filters(actor.tenant_id, q)
    where = " AND ".join(clauses)
    conn = db.conn

    total = conn.execute(
        f"SELECT COUNT(*) AS n FROM certificates c WHERE {where}", params
    ).fetchone()["n"]

    offset = (page - 1) * page_size
    rows = conn.execute(
        f"""
        SELECT {CERT_COLUMNS}
          FROM certificates c
         WHERE {where}
         {_order_by(sort, direction)}
         LIMIT ? OFFSET ?
        """,
        [*params, page_size, offset],
    ).fetchall()

    return {
        "items": [_item(row, actor.timezone) for row in rows],
        "page": page,
        "pageSize": page_size,
        "total": total,
        "totalPages": math.ceil(total / page_size) if total else 0,
        "sort": sort,
        "dir": direction,
        "q": q,
        "tenant": actor.tenant,
    }


def _detail(conn: sqlite3.Connection, actor: Actor, certificate_id: str) -> dict[str, Any]:
    row = conn.execute(
        f"SELECT {CERT_COLUMNS} FROM certificates c WHERE c.id = ? AND c.tenant_id = ?",
        (certificate_id, actor.tenant_id),
    ).fetchone()
    if row is None:
        # Same response for "does not exist" and "belongs to another tenant" (A1).
        raise ApiError(404, "certificate_not_found", "Certificate not found")

    audits = conn.execute(
        """
        SELECT id, action, actor_id, actor_email, at, detail
          FROM audit_events
         WHERE tenant_id = ? AND certificate_id = ?
         ORDER BY at ASC, id ASC
        """,
        (actor.tenant_id, certificate_id),
    ).fetchall()

    return {
        "certificate": _item(row, actor.timezone),
        "audit": [_audit_item(a, actor.timezone) for a in audits],
    }


def get_certificate(db: Database, actor: Actor, certificate_id: str) -> dict[str, Any]:
    return _detail(db.conn, actor, certificate_id)


def list_courses(db: Database, actor: Actor) -> dict[str, Any]:
    rows = db.conn.execute(
        """
        SELECT c.id, c.title,
               COALESCE(SUM(CASE WHEN e.status = 'COMPLETED' THEN 1 ELSE 0 END), 0) AS completed,
               COALESCE(SUM(CASE WHEN e.status = 'INCOMPLETE' THEN 1 ELSE 0 END), 0) AS incomplete,
               COALESCE(SUM(CASE WHEN cert.id IS NOT NULL THEN 1 ELSE 0 END), 0) AS certified,
               COALESCE(SUM(CASE WHEN e.status = 'COMPLETED' AND cert.id IS NULL THEN 1 ELSE 0 END), 0) AS eligible
          FROM courses c
          LEFT JOIN enrollments e
                 ON e.course_id = c.id AND e.tenant_id = c.tenant_id
          LEFT JOIN certificates cert
                 ON cert.tenant_id = c.tenant_id
                AND cert.course_id = c.id
                AND cert.learner_id = e.learner_id
         WHERE c.tenant_id = ?
         GROUP BY c.id, c.title
         ORDER BY c.title COLLATE NOCASE, c.id
        """,
        (actor.tenant_id,),
    ).fetchall()

    return {
        "courses": [
            {
                "id": row["id"],
                "title": row["title"],
                "completed": row["completed"],
                "incomplete": row["incomplete"],
                "certified": row["certified"],
                "eligible": row["eligible"],
            }
            for row in rows
        ],
        "tenant": actor.tenant,
    }


# --------------------------------------------------------------------------- writes


def revoke_certificate(
    db: Database, actor: Actor, certificate_id: str, reason: str | None
) -> dict[str, Any]:
    with db.write() as conn:
        row = conn.execute(
            "SELECT status FROM certificates WHERE id = ? AND tenant_id = ?",
            (certificate_id, actor.tenant_id),
        ).fetchone()
        if row is None:
            raise ApiError(404, "certificate_not_found", "Certificate not found")

        if row["status"] == "REVOKED":
            detail = _detail(conn, actor, certificate_id)
            return {**detail, "alreadyRevoked": True}

        now = iso_utc(utc_now())
        cursor = conn.execute(
            """
            UPDATE certificates
               SET status = 'REVOKED', revoked_at = ?, revoked_by = ?
             WHERE id = ? AND tenant_id = ? AND status = 'ACTIVE'
            """,
            (now, actor.admin_id, certificate_id, actor.tenant_id),
        )
        if cursor.rowcount != 1:
            raise ApiError(409, "revocation_conflict", "Certificate state changed concurrently")

        conn.execute(
            """
            INSERT INTO audit_events
                   (id, tenant_id, certificate_id, action, actor_id, actor_email, at, detail)
            VALUES (?, ?, ?, 'REVOKED', ?, ?, ?, ?)
            """,
            (
                f"audit_{secrets.token_hex(8)}",
                actor.tenant_id,
                certificate_id,
                actor.admin_id,
                actor.email,
                now,
                json.dumps({"reason": reason} if reason else {}),
            ),
        )

        detail = _detail(conn, actor, certificate_id)

    return {**detail, "alreadyRevoked": False, "revokedAt": now}


def _request_hash(course_id: str) -> str:
    import hashlib

    payload = json.dumps({"endpoint": "bulk-issue", "courseId": course_id}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _next_sequence(conn: sqlite3.Connection, tenant_id: str) -> int:
    row = conn.execute(
        """
        INSERT INTO counters (tenant_id, name, value)
        VALUES (?, 'certificate_seq', 1)
        ON CONFLICT (tenant_id, name) DO UPDATE SET value = value + 1
        RETURNING value
        """,
        (tenant_id,),
    ).fetchone()
    return int(row["value"])


def bulk_issue(
    db: Database,
    actor: Actor,
    course_id: str,
    idempotency_key: str | None,
    reason: str | None = None,
) -> tuple[int, dict[str, Any], bool]:
    key = (idempotency_key or "").strip()
    if not key:
        raise ApiError(400, "idempotency_key_required", "Idempotency-Key header is required")
    if len(key) > 200:
        raise ApiError(400, "idempotency_key_invalid", "Idempotency-Key is too long")

    request_hash = _request_hash(course_id)
    operation_id = f"op_{secrets.token_hex(8)}"
    now_dt = utc_now()
    now = iso_utc(now_dt)

    with db.write() as conn:
        existing = conn.execute(
            "SELECT request_hash, status, response_json FROM idempotency_keys "
            "WHERE tenant_id = ? AND key = ?",
            (actor.tenant_id, key),
        ).fetchone()

        if existing is not None:
            if existing["request_hash"] != request_hash:
                raise ApiError(
                    409,
                    "idempotency_key_reuse",
                    "Idempotency-Key was already used with a different request payload",
                )
            if existing["status"] == "SUCCEEDED":
                return 200, json.loads(existing["response_json"]), True
            raise ApiError(
                409,
                "idempotency_key_in_progress",
                "An operation with this Idempotency-Key is still in progress",
            )

        course = conn.execute(
            "SELECT id, title FROM courses WHERE id = ? AND tenant_id = ?",
            (course_id, actor.tenant_id),
        ).fetchone()
        if course is None:
            # Cross-tenant course ids are indistinguishable from missing ones (A1).
            raise ApiError(404, "course_not_found", "Course not found")

        enrollments = conn.execute(
            """
            SELECT e.id AS enrollment_id, e.status AS enrollment_status,
                   l.id AS learner_id, l.name AS learner_name,
                   cert.id AS certificate_id, cert.serial AS certificate_serial
              FROM enrollments e
              JOIN learners l
                ON l.id = e.learner_id AND l.tenant_id = e.tenant_id
              LEFT JOIN certificates cert
                ON cert.tenant_id = e.tenant_id
               AND cert.course_id = e.course_id
               AND cert.learner_id = e.learner_id
             WHERE e.tenant_id = ? AND e.course_id = ?
             ORDER BY l.name COLLATE NOCASE, l.id
            """,
            (actor.tenant_id, course_id),
        ).fetchall()

        outcomes: list[dict[str, Any]] = []
        for row in enrollments:
            if row["certificate_id"] is not None:
                outcomes.append(
                    {
                        "learnerId": row["learner_id"],
                        "learnerName": row["learner_name"],
                        "status": "skipped",
                        "reason": "already_certified",
                        "message": f"Certificate {row['certificate_serial']} already exists",
                    }
                )
                continue

            if row["enrollment_status"] != "COMPLETED":
                outcomes.append(
                    {
                        "learnerId": row["learner_id"],
                        "learnerName": row["learner_name"],
                        "status": "skipped",
                        "reason": "incomplete_enrollment",
                        "message": "Enrollment is not completed",
                    }
                )
                continue

            conn.execute("SAVEPOINT issue_learner")
            try:
                sequence = _next_sequence(conn, actor.tenant_id)
                serial = f"CERT-{actor.tenant_slug.upper()}-{now_dt.year}-{sequence:06d}"
                certificate_id = f"cert_{secrets.token_hex(8)}"

                conn.execute(
                    """
                    INSERT INTO certificates
                           (id, tenant_id, seq, course_id, learner_id, learner_name,
                            course_title, serial, status, issued_at, issue_date_local,
                            created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?)
                    """,
                    (
                        certificate_id,
                        actor.tenant_id,
                        sequence,
                        course_id,
                        row["learner_id"],
                        row["learner_name"],
                        course["title"],
                        serial,
                        now,
                        local_date(now, actor.timezone),
                        now,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO audit_events
                           (id, tenant_id, certificate_id, action, actor_id, actor_email, at, detail)
                    VALUES (?, ?, ?, 'ISSUED', ?, ?, ?, ?)
                    """,
                    (
                        f"audit_{secrets.token_hex(8)}",
                        actor.tenant_id,
                        certificate_id,
                        actor.admin_id,
                        actor.email,
                        now,
                        json.dumps(
                            {
                                "reason": reason or "bulk_issue",
                                "operationId": operation_id,
                                "courseId": course_id,
                            }
                        ),
                    ),
                )
                conn.execute("RELEASE issue_learner")
                outcomes.append(
                    {
                        "learnerId": row["learner_id"],
                        "learnerName": row["learner_name"],
                        "status": "issued",
                        "certificateId": certificate_id,
                        "serial": serial,
                    }
                )
            except (sqlite3.IntegrityError, sqlite3.OperationalError) as exc:
                conn.execute("ROLLBACK TO issue_learner")
                conn.execute("RELEASE issue_learner")
                log.warning(
                    "bulk_issue learner failure operation=%s learner=%s error=%s",
                    operation_id,
                    row["learner_id"],
                    exc,
                )
                outcomes.append(
                    {
                        "learnerId": row["learner_id"],
                        "learnerName": row["learner_name"],
                        "status": "failed",
                        "reason": "integrity_conflict",
                        "message": "Certificate could not be issued for this learner",
                    }
                )

        issued = sum(1 for outcome in outcomes if outcome["status"] == "issued")
        skipped = sum(1 for outcome in outcomes if outcome["status"] == "skipped")
        failed = sum(1 for outcome in outcomes if outcome["status"] == "failed")

        response = {
            "operationId": operation_id,
            "courseId": course_id,
            "courseTitle": course["title"],
            "tenant": actor.tenant,
            "summary": {
                "total": len(outcomes),
                "issued": issued,
                "skipped": skipped,
                "failed": failed,
            },
            "outcomes": outcomes,
        }
        response_json = json.dumps(response, ensure_ascii=False)

        conn.execute(
            """
            INSERT INTO idempotency_keys
                   (tenant_id, key, request_hash, status, response_status,
                    response_json, operation_id, created_at, completed_at)
            VALUES (?, ?, ?, 'SUCCEEDED', 200, ?, ?, ?, ?)
            """,
            (actor.tenant_id, key, request_hash, response_json, operation_id, now, now),
        )

    return 200, response, False


# --------------------------------------------------------------------------- export


def export_horizon(db: Database, actor: Actor) -> int:
    row = db.conn.execute(
        "SELECT COALESCE(MAX(seq), 0) AS horizon FROM certificates WHERE tenant_id = ?",
        (actor.tenant_id,),
    ).fetchone()
    return int(row["horizon"])


def export_batch(
    db: Database,
    actor: Actor,
    *,
    q: str,
    sort: str,
    direction: str,
    horizon: int,
    last: tuple[str, str] | None,
    limit: int = EXPORT_BATCH_SIZE,
) -> list[sqlite3.Row]:
    expr = SORT_COLUMNS[sort]
    clauses, params = _filters(actor.tenant_id, q)
    clauses.append("c.seq <= ?")
    params.append(horizon)
    clause, key_params = _keyset(expr, direction, last)
    if clause:
        clauses.append(clause)
        params.extend(key_params)

    rows = db.conn.execute(
        f"""
        SELECT {CERT_COLUMNS}, ({expr}) AS sort_value
          FROM certificates c
         WHERE {' AND '.join(clauses)}
         ORDER BY {expr} {direction.upper()}, c.id ASC
         LIMIT ?
        """,
        [*params, limit],
    ).fetchall()
    return rows


def csv_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    if any(char in text for char in ',"\r\n'):
        text = '"' + text.replace('"', '""') + '"'
    return text


def export_sort_value(row: sqlite3.Row, sort: str) -> str:
    return row["sort_value"] if sort != "issued_date" else row["issued_at"]
