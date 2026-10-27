from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from .errors import ApiError
from .logging import get_logger

log = get_logger("app.auth")


@dataclass(frozen=True)
class Actor:
    admin_id: str
    email: str
    name: str
    tenant_id: str
    tenant_slug: str
    tenant_name: str
    timezone: str

    @property
    def tenant(self) -> dict[str, str]:
        return {
            "id": self.tenant_id,
            "slug": self.tenant_slug,
            "name": self.tenant_name,
            "timezone": self.timezone,
        }


def get_actor(request: Request) -> Actor:
    """Resolve the acting admin from X-Actor-Email.

    The tenant is derived from the admin row only; no request parameter can
    select a tenant (DESIGN.md §5.1).
    """
    raw = (request.headers.get("x-actor-email") or "").strip().lower()
    if not raw:
        log.warning(
            "auth.rejected",
            extra={"fields": {"reason": "missing_header", "path": request.url.path}},
        )
        raise ApiError(401, "unauthenticated", "X-Actor-Email header is required")

    row = request.app.state.db.conn.execute(
        """
        SELECT a.id AS admin_id, a.email AS email, a.name AS admin_name,
               t.id AS tenant_id, t.slug AS tenant_slug, t.name AS tenant_name,
               t.timezone AS tenant_timezone
          FROM admins a
          JOIN tenants t ON t.id = a.tenant_id
         WHERE lower(a.email) = ?
        """,
        (raw,),
    ).fetchone()

    if row is None:
        log.warning(
            "auth.rejected",
            extra={
                "fields": {
                    "reason": "unknown_actor",
                    "email": raw,
                    "path": request.url.path,
                }
            },
        )
        raise ApiError(401, "unauthenticated", "Unknown actor")

    # Visible to the request-log middleware after the response is produced.
    request.state.actor_email = row["email"]
    request.state.tenant_slug = row["tenant_slug"]

    return Actor(
        admin_id=row["admin_id"],
        email=row["email"],
        name=row["admin_name"],
        tenant_id=row["tenant_id"],
        tenant_slug=row["tenant_slug"],
        tenant_name=row["tenant_name"],
        timezone=row["tenant_timezone"],
    )
