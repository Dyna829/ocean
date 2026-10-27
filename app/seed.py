"""Deterministic demo data and the 100k-row generator's base fixtures.

Run directly:  python -m app.seed [--db PATH] [--reset]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from typing import Any

from .config import resolve_db_path
from .db import Database
from .timeutil import local_date

# --------------------------------------------------------------------------- fixtures

TENANTS = [
    {"id": "tenant_east", "slug": "east", "name": "East Campus", "timezone": "Australia/Sydney"},
    {"id": "tenant_west", "slug": "west", "name": "West Campus", "timezone": "Australia/Perth"},
]

ADMINS = [
    {"id": "admin_alice", "tenant_id": "tenant_east", "email": "alice@east.test", "name": "Alice Chen"},
    {"id": "admin_bob", "tenant_id": "tenant_west", "email": "bob@west.test", "name": "Bob Miller"},
]

COURSES = [
    {"id": "course_east_safety", "tenant_id": "tenant_east", "title": "Safety 101"},
    {"id": "course_east_fire", "tenant_id": "tenant_east", "title": "Fire Safety"},
    {"id": "course_east_privacy", "tenant_id": "tenant_east", "title": "Data Privacy"},
    {"id": "course_east_hazard", "tenant_id": "tenant_east", "title": "Hazard Reporting"},
    {"id": "course_west_safety", "tenant_id": "tenant_west", "title": "Safety 101"},
    {"id": "course_west_fire", "tenant_id": "tenant_west", "title": "Fire Safety"},
]

LEARNERS = [
    {"id": "learner_east_alex", "tenant_id": "tenant_east", "name": "Alex Lee"},
    {"id": "learner_east_maya", "tenant_id": "tenant_east", "name": "Maya Chen"},
    {"id": "learner_east_priya", "tenant_id": "tenant_east", "name": "Priya Nair"},
    {"id": "learner_east_tom", "tenant_id": "tenant_east", "name": "Tom Baker"},
    {"id": "learner_east_liam", "tenant_id": "tenant_east", "name": "Liam Wong"},
    {"id": "learner_east_noah", "tenant_id": "tenant_east", "name": "Noah Patel"},
    {"id": "learner_east_ava", "tenant_id": "tenant_east", "name": "Ava Rodriguez"},
    {"id": "learner_east_ethan", "tenant_id": "tenant_east", "name": "Ethan Brooks"},
    {"id": "learner_east_sophia", "tenant_id": "tenant_east", "name": "Sophia Turner"},
    {"id": "learner_east_isla", "tenant_id": "tenant_east", "name": "Isla Murphy"},
    {"id": "learner_east_james", "tenant_id": "tenant_east", "name": "James Cole"},
    {"id": "learner_east_hazard_01", "tenant_id": "tenant_east", "name": "Hazel Moore"},
    {"id": "learner_east_hazard_02", "tenant_id": "tenant_east", "name": "Ivan Petrov"},
    {"id": "learner_east_hazard_03", "tenant_id": "tenant_east", "name": "Jade Wilson"},
    {"id": "learner_east_hazard_04", "tenant_id": "tenant_east", "name": "Kai Nakamura"},
    {"id": "learner_east_hazard_05", "tenant_id": "tenant_east", "name": "Lena Fischer"},
    {"id": "learner_east_hazard_06", "tenant_id": "tenant_east", "name": "Marco Rossi"},
    {"id": "learner_east_hazard_07", "tenant_id": "tenant_east", "name": "Nadia Haddad"},
    {"id": "learner_east_hazard_08", "tenant_id": "tenant_east", "name": "Owen Clarke"},
    {"id": "learner_east_hazard_09", "tenant_id": "tenant_east", "name": "Pia Andersen"},
    {"id": "learner_east_hazard_10", "tenant_id": "tenant_east", "name": "Quinn Taylor"},
    {"id": "learner_west_alex", "tenant_id": "tenant_west", "name": "Alex Lee"},
    {"id": "learner_west_sam", "tenant_id": "tenant_west", "name": "Sam Rivera"},
    {"id": "learner_west_dana", "tenant_id": "tenant_west", "name": "Dana Kim"},
    {"id": "learner_west_grace", "tenant_id": "tenant_west", "name": "Grace Liu"},
    {"id": "learner_west_omar", "tenant_id": "tenant_west", "name": "Omar Haddad"},
    {"id": "learner_west_nina", "tenant_id": "tenant_west", "name": "Nina Petrova"},
]

ENROLLMENTS = [
    ("enr_east_safety_alex", "tenant_east", "course_east_safety", "learner_east_alex", "COMPLETED"),
    ("enr_east_safety_maya", "tenant_east", "course_east_safety", "learner_east_maya", "COMPLETED"),
    ("enr_east_safety_priya", "tenant_east", "course_east_safety", "learner_east_priya", "COMPLETED"),
    ("enr_east_safety_tom", "tenant_east", "course_east_safety", "learner_east_tom", "INCOMPLETE"),
    ("enr_east_fire_liam", "tenant_east", "course_east_fire", "learner_east_liam", "COMPLETED"),
    ("enr_east_fire_noah", "tenant_east", "course_east_fire", "learner_east_noah", "COMPLETED"),
    ("enr_east_fire_ava", "tenant_east", "course_east_fire", "learner_east_ava", "COMPLETED"),
    ("enr_east_fire_ethan", "tenant_east", "course_east_fire", "learner_east_ethan", "COMPLETED"),
    ("enr_east_privacy_sophia", "tenant_east", "course_east_privacy", "learner_east_sophia", "COMPLETED"),
    ("enr_east_privacy_isla", "tenant_east", "course_east_privacy", "learner_east_isla", "COMPLETED"),
    ("enr_east_privacy_james", "tenant_east", "course_east_privacy", "learner_east_james", "INCOMPLETE"),
    ("enr_west_safety_alex", "tenant_west", "course_west_safety", "learner_west_alex", "COMPLETED"),
    ("enr_west_safety_sam", "tenant_west", "course_west_safety", "learner_west_sam", "COMPLETED"),
    ("enr_west_safety_dana", "tenant_west", "course_west_safety", "learner_west_dana", "INCOMPLETE"),
    ("enr_west_fire_grace", "tenant_west", "course_west_fire", "learner_west_grace", "COMPLETED"),
    ("enr_west_fire_omar", "tenant_west", "course_west_fire", "learner_west_omar", "COMPLETED"),
    ("enr_west_fire_nina", "tenant_west", "course_west_fire", "learner_west_nina", "COMPLETED"),
]

# Course "Hazard Reporting" gives the list enough rows to paginate (13 East certs),
# including a pair with an identical timestamp to exercise deterministic ties.
HAZARD_CERTIFICATES = [
    ("learner_east_hazard_01", "2026-01-15T02:05:00Z"),
    ("learner_east_hazard_02", "2026-01-16T06:40:00Z"),
    ("learner_east_hazard_03", "2026-01-17T23:10:00Z"),
    ("learner_east_hazard_04", "2026-01-18T14:25:00Z"),
    ("learner_east_hazard_05", "2026-01-18T14:25:00Z"),
    ("learner_east_hazard_06", "2026-01-20T03:55:00Z"),
    ("learner_east_hazard_07", "2026-01-21T19:30:00Z"),
    ("learner_east_hazard_08", "2026-01-22T08:15:00Z"),
    ("learner_east_hazard_09", "2026-01-23T12:45:00Z"),
    ("learner_east_hazard_10", "2026-01-24T05:00:00Z"),
]

CERTIFICATES: list[dict[str, str]] = [
    # A5 fixtures: the same UTC instant renders as a different local date per tenant.
    {
        "tenant_id": "tenant_east",
        "course_id": "course_east_safety",
        "learner_id": "learner_east_alex",
        "issued_at": "2026-01-10T13:30:00Z",
    },
    {
        "tenant_id": "tenant_west",
        "course_id": "course_west_safety",
        "learner_id": "learner_west_alex",
        "issued_at": "2026-01-10T13:30:00Z",
    },
    {
        "tenant_id": "tenant_east",
        "course_id": "course_east_privacy",
        "learner_id": "learner_east_sophia",
        "issued_at": "2026-02-14T09:15:00Z",
    },
    {
        "tenant_id": "tenant_east",
        "course_id": "course_east_privacy",
        "learner_id": "learner_east_isla",
        "issued_at": "2026-02-20T11:00:00Z",
        "revoked_at": "2026-03-01T08:00:00Z",
    },
]

TENANT_BY_ID = {tenant["id"]: tenant for tenant in TENANTS}
LEARNER_BY_ID = {learner["id"]: learner for learner in LEARNERS}
COURSE_BY_ID = {course["id"]: course for course in COURSES}
ADMIN_BY_TENANT = {admin["tenant_id"]: admin for admin in ADMINS}

DEMO_TABLES = (
    "audit_events",
    "idempotency_keys",
    "certificates",
    "enrollments",
    "counters",
    "courses",
    "learners",
    "admins",
    "tenants",
)


def _insert_all(conn: sqlite3.Connection, hazard_certificates: list[tuple[str, str]]) -> dict[str, int]:
    for tenant in TENANTS:
        conn.execute(
            "INSERT INTO tenants (id, slug, name, timezone) VALUES (?, ?, ?, ?)",
            (tenant["id"], tenant["slug"], tenant["name"], tenant["timezone"]),
        )
    for admin in ADMINS:
        conn.execute(
            "INSERT INTO admins (id, tenant_id, email, name) VALUES (?, ?, ?, ?)",
            (admin["id"], admin["tenant_id"], admin["email"], admin["name"]),
        )
    for course in COURSES:
        conn.execute(
            "INSERT INTO courses (id, tenant_id, title) VALUES (?, ?, ?)",
            (course["id"], course["tenant_id"], course["title"]),
        )
    for learner in LEARNERS:
        conn.execute(
            "INSERT INTO learners (id, tenant_id, name) VALUES (?, ?, ?)",
            (learner["id"], learner["tenant_id"], learner["name"]),
        )
    for enrollment in ENROLLMENTS:
        conn.execute(
            "INSERT INTO enrollments (id, tenant_id, course_id, learner_id, status) "
            "VALUES (?, ?, ?, ?, ?)",
            enrollment,
        )

    rows = list(CERTIFICATES) + [
        {
            "tenant_id": "tenant_east",
            "course_id": "course_east_hazard",
            "learner_id": learner_id,
            "issued_at": issued_at,
        }
        for learner_id, issued_at in hazard_certificates
    ]

    sequences: dict[str, int] = {}
    for cert in rows:
        tenant_id = cert["tenant_id"]
        tenant = TENANT_BY_ID[tenant_id]
        course = COURSE_BY_ID[cert["course_id"]]
        learner = LEARNER_BY_ID[cert["learner_id"]]
        issued_at = cert["issued_at"]
        revoked_at = cert.get("revoked_at")
        sequence = sequences.get(tenant_id, 0) + 1
        sequences[tenant_id] = sequence

        serial = f"CERT-{tenant['slug'].upper()}-{issued_at[:4]}-{sequence:06d}"
        learner_key = cert["learner_id"].split("_", 2)[2]
        course_key = course["id"].split("_")[-1]
        certificate_id = f"cert_{tenant['slug']}_{learner_key}_{course_key}"
        admin = ADMIN_BY_TENANT[tenant_id]

        conn.execute(
            """
            INSERT INTO certificates
                   (id, tenant_id, seq, course_id, learner_id, learner_name, course_title,
                    serial, status, issued_at, issue_date_local, revoked_at, revoked_by,
                    created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                certificate_id,
                tenant_id,
                sequence,
                course["id"],
                learner["id"],
                learner["name"],
                course["title"],
                serial,
                "REVOKED" if revoked_at else "ACTIVE",
                issued_at,
                local_date(issued_at, tenant["timezone"]),
                revoked_at,
                admin["id"] if revoked_at else None,
                issued_at,
            ),
        )
        conn.execute(
            """
            INSERT INTO audit_events
                   (id, tenant_id, certificate_id, action, actor_id, actor_email, at, detail)
            VALUES (?, ?, ?, 'ISSUED', ?, ?, ?, ?)
            """,
            (
                f"{certificate_id}_issued",
                tenant_id,
                certificate_id,
                admin["id"],
                admin["email"],
                issued_at,
                json.dumps({"reason": "demo_seed"}),
            ),
        )
        if revoked_at:
            conn.execute(
                """
                INSERT INTO audit_events
                       (id, tenant_id, certificate_id, action, actor_id, actor_email, at, detail)
                VALUES (?, ?, ?, 'REVOKED', ?, ?, ?, ?)
                """,
                (
                    f"{certificate_id}_revoked",
                    tenant_id,
                    certificate_id,
                    admin["id"],
                    admin["email"],
                    revoked_at,
                    json.dumps({"reason": "Seeded as revoked for demo purposes"}),
                ),
            )

    for tenant_id, value in sequences.items():
        conn.execute(
            "INSERT INTO counters (tenant_id, name, value) VALUES (?, 'certificate_seq', ?)",
            (tenant_id, value),
        )

    return {"tenants": len(TENANTS), "certificates": len(rows)}


def seed_demo(db: Database, *, reset: bool = False) -> dict[str, Any]:
    db.init_schema()
    existing = db.conn.execute("SELECT COUNT(*) AS n FROM tenants").fetchone()["n"]
    if existing and not reset:
        return {
            "seeded": False,
            "reason": "database already contains data; use --reset to rebuild",
            "db": str(db.path),
        }

    with db.write() as conn:
        if reset:
            for table in DEMO_TABLES:
                conn.execute(f"DELETE FROM {table}")
        counts = _insert_all(conn, HAZARD_CERTIFICATES)

    return {
        "seeded": True,
        "db": str(db.path),
        "tenants": counts["tenants"],
        "certificates": counts["certificates"],
        "admins": [admin["email"] for admin in ADMINS],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed deterministic demo data")
    parser.add_argument("--db", default=None, help="database path (defaults to DB_PATH or data/app.db)")
    parser.add_argument("--reset", action="store_true", help="wipe demo rows and reseed")
    args = parser.parse_args()

    database = Database(resolve_db_path(args.db))
    print(json.dumps(seed_demo(database, reset=args.reset), indent=2))


if __name__ == "__main__":
    main()
