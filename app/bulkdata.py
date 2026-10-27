"""Synthetic certificates for the A6 export benchmark.

Used by ``scripts/generate_large.py`` and by the A6 test fixture. Rows are
deliberately repetitive: 50 distinct learner names and 20 distinct timestamps
so that the requested sort field has many equal values (A6).
"""

from __future__ import annotations

import sqlite3
from typing import Any

from .timeutil import local_date

NAME_POOL = [
    "Bulk Learner 01",
    "Bulk Learner 02",
    "Bulk Learner 03",
    "Bulk Learner 04",
    "Bulk Learner 05",
    "Bulk Learner 06",
    "Bulk Learner 07",
    "Bulk Learner 08",
    "Bulk Learner 09",
    "Bulk Learner 10",
    "Bulk Learner 11",
    "Bulk Learner 12",
    "Bulk Learner 13",
    "Bulk Learner 14",
    "Bulk Learner 15",
    "Bulk Learner 16",
    "Bulk Learner 17",
    "Bulk Learner 18",
    "Bulk Learner 19",
    "Bulk Learner 20",
    "Bulk Learner 21",
    "Bulk Learner 22",
    "Bulk Learner 23",
    "Bulk Learner 24",
    "Bulk Learner 25",
    "Bulk Learner 26",
    "Bulk Learner 27",
    "Bulk Learner 28",
    "Bulk Learner 29",
    "Bulk Learner 30",
    "Bulk Learner 31",
    "Bulk Learner 32",
    "Bulk Learner 33",
    "Bulk Learner 34",
    "Bulk Learner 35",
    "Bulk Learner 36",
    "Bulk Learner 37",
    "Bulk Learner 38",
    "Bulk Learner 39",
    "Bulk Learner 40",
    "Bulk Learner 41",
    "Bulk Learner 42",
    "Bulk Learner 43",
    "Bulk Learner 44",
    "Bulk Learner 45",
    "Bulk Learner 46",
    "Bulk Learner 47",
    "Bulk Learner 48",
    "Bulk Learner 49",
    "Bulk Learner 50",
]

TIMESTAMPS = [
    "2026-04-01T00:15:00Z",
    "2026-04-02T03:30:00Z",
    "2026-04-03T06:45:00Z",
    "2026-04-04T09:00:00Z",
    "2026-04-05T12:15:00Z",
    "2026-04-06T15:30:00Z",
    "2026-04-07T18:45:00Z",
    "2026-04-08T21:00:00Z",
    "2026-04-09T00:30:00Z",
    "2026-04-10T04:00:00Z",
    "2026-04-11T08:00:00Z",
    "2026-04-12T12:00:00Z",
    "2026-04-13T16:00:00Z",
    "2026-04-14T20:00:00Z",
    "2026-04-15T01:00:00Z",
    "2026-04-16T05:00:00Z",
    "2026-04-17T11:00:00Z",
    "2026-04-18T17:00:00Z",
    "2026-04-19T22:00:00Z",
    "2026-04-20T13:00:00Z",
]


def insert_bulk_certificates(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    count: int,
    course_count: int = 100,
    learner_count: int = 1000,
    course_prefix: str = "Bulk Compliance",
) -> dict[str, Any]:
    tenant = conn.execute(
        "SELECT slug, timezone FROM tenants WHERE id = ?", (tenant_id,)
    ).fetchone()
    if tenant is None:
        raise ValueError(f"unknown tenant {tenant_id}")

    capacity = course_count * learner_count
    if count > capacity:
        raise ValueError(
            f"count={count} exceeds course_count*learner_count={capacity}; "
            "increase course_count or learner_count"
        )

    start_seq = conn.execute(
        "SELECT COALESCE(MAX(seq), 0) AS n FROM certificates WHERE tenant_id = ?",
        (tenant_id,),
    ).fetchone()["n"]

    course_rows = [
        (f"course_bulk_{index:03d}", tenant_id, f"{course_prefix} {index + 1:03d}")
        for index in range(course_count)
    ]
    learner_rows = [
        (f"learner_bulk_{index:04d}", tenant_id, NAME_POOL[index % len(NAME_POOL)])
        for index in range(learner_count)
    ]
    conn.executemany("INSERT OR IGNORE INTO courses (id, tenant_id, title) VALUES (?, ?, ?)", course_rows)
    conn.executemany("INSERT OR IGNORE INTO learners (id, tenant_id, name) VALUES (?, ?, ?)", learner_rows)

    course_ids = [course_id for course_id, _, _ in course_rows]
    course_titles = {course_id: title for course_id, _, title in course_rows}
    learner_ids = [learner_id for learner_id, _, _ in learner_rows]
    learner_names = {learner_id: name for learner_id, _, name in learner_rows}
    learner_names_by_index = [learner_names[learner_id] for learner_id in learner_ids]

    issued_at = TIMESTAMPS
    local_dates = [local_date(value, tenant["timezone"]) for value in issued_at]

    batch: list[tuple[Any, ...]] = []
    inserted = 0
    for index in range(count):
        course_index = index % course_count
        learner_index = (index // course_count) % learner_count
        course_id = course_ids[course_index]
        learner_id = learner_ids[learner_index]
        timestamp_index = index % len(issued_at)

        batch.append(
            (
                f"cert_bulk_{index:07d}",
                tenant_id,
                start_seq + index + 1,
                course_id,
                learner_id,
                learner_names_by_index[learner_index],
                course_titles[course_id],
                f"CERT-{tenant['slug'].upper()}-2026-{start_seq + index + 1:06d}",
                "ACTIVE",
                issued_at[timestamp_index],
                local_dates[timestamp_index],
                issued_at[timestamp_index],
            )
        )
        if len(batch) >= 5000:
            _flush(conn, batch)
            inserted += len(batch)
            batch.clear()

    if batch:
        _flush(conn, batch)
        inserted += len(batch)

    conn.execute(
        """
        INSERT INTO counters (tenant_id, name, value)
        VALUES (?, 'certificate_seq', ?)
        ON CONFLICT (tenant_id, name) DO UPDATE SET value = MAX(value, excluded.value)
        """,
        (tenant_id, start_seq + count),
    )

    return {
        "tenant_id": tenant_id,
        "certificates": inserted,
        "courses": course_count,
        "learners": learner_count,
        "start_seq": start_seq,
    }


def _flush(conn: sqlite3.Connection, batch: list[tuple[Any, ...]]) -> None:
    conn.executemany(
        """
        INSERT INTO certificates
               (id, tenant_id, seq, course_id, learner_id, learner_name, course_title,
                serial, status, issued_at, issue_date_local, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        batch,
    )
