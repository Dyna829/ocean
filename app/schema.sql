-- Certificate Admin Console — schema
-- Applied idempotently at startup. See DESIGN.md §3.

PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS tenants (
    id          TEXT PRIMARY KEY,
    slug        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    timezone    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admins (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL REFERENCES tenants (id),
    email       TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS courses (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL REFERENCES tenants (id),
    title       TEXT NOT NULL,
    UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS learners (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL REFERENCES tenants (id),
    name        TEXT NOT NULL,
    UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS enrollments (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL REFERENCES tenants (id),
    course_id   TEXT NOT NULL,
    learner_id  TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('COMPLETED', 'INCOMPLETE')),
    UNIQUE (course_id, learner_id),
    FOREIGN KEY (tenant_id, course_id) REFERENCES courses (tenant_id, id),
    FOREIGN KEY (tenant_id, learner_id) REFERENCES learners (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS certificates (
    id               TEXT PRIMARY KEY,
    tenant_id        TEXT NOT NULL REFERENCES tenants (id),
    seq              INTEGER NOT NULL,
    course_id        TEXT NOT NULL,
    learner_id       TEXT NOT NULL,
    -- Snapshot of the names at issuance: a certificate is an immutable historical
    -- record and the export sorts/filters on these columns (DESIGN.md §3).
    learner_name     TEXT NOT NULL,
    course_title     TEXT NOT NULL,
    serial           TEXT NOT NULL,
    status           TEXT NOT NULL CHECK (status IN ('ACTIVE', 'REVOKED')),
    issued_at        TEXT NOT NULL,   -- UTC, YYYY-MM-DDTHH:MM:SSZ
    issue_date_local TEXT NOT NULL,   -- tenant-local calendar date, YYYY-MM-DD
    revoked_at       TEXT,
    revoked_by       TEXT,
    created_at       TEXT NOT NULL,
    UNIQUE (tenant_id, id),
    UNIQUE (tenant_id, serial),
    UNIQUE (tenant_id, seq),
    -- At most one certificate per learner per course (DESIGN.md §3, A2/A4).
    UNIQUE (tenant_id, course_id, learner_id),
    FOREIGN KEY (tenant_id, course_id) REFERENCES courses (tenant_id, id),
    FOREIGN KEY (tenant_id, learner_id) REFERENCES learners (tenant_id, id)
);

CREATE INDEX IF NOT EXISTS idx_cert_tenant_learner
    ON certificates (tenant_id, learner_name COLLATE NOCASE, id);
CREATE INDEX IF NOT EXISTS idx_cert_tenant_course
    ON certificates (tenant_id, course_title COLLATE NOCASE, id);
CREATE INDEX IF NOT EXISTS idx_cert_tenant_issued
    ON certificates (tenant_id, issued_at, id);
CREATE INDEX IF NOT EXISTS idx_cert_tenant_serial
    ON certificates (tenant_id, serial);
CREATE INDEX IF NOT EXISTS idx_cert_tenant_status
    ON certificates (tenant_id, status);

CREATE TABLE IF NOT EXISTS audit_events (
    id             TEXT PRIMARY KEY,
    tenant_id      TEXT NOT NULL REFERENCES tenants (id),
    certificate_id TEXT NOT NULL,
    action         TEXT NOT NULL CHECK (action IN ('ISSUED', 'REVOKED')),
    actor_id       TEXT NOT NULL,
    actor_email    TEXT NOT NULL,
    at             TEXT NOT NULL,
    detail         TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (tenant_id, certificate_id) REFERENCES certificates (tenant_id, id)
);

-- One issuance and one revocation event per certificate, enforced by the database
-- rather than by application convention (DESIGN.md §5.5, A2, A7).
CREATE UNIQUE INDEX IF NOT EXISTS ux_audit_certificate_action
    ON audit_events (certificate_id, action);
CREATE INDEX IF NOT EXISTS idx_audit_tenant
    ON audit_events (tenant_id, at);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    tenant_id       TEXT NOT NULL REFERENCES tenants (id),
    key             TEXT NOT NULL,
    request_hash    TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('IN_PROGRESS', 'SUCCEEDED')),
    response_status INTEGER,
    response_json   TEXT,
    operation_id    TEXT,
    created_at      TEXT NOT NULL,
    completed_at    TEXT,
    PRIMARY KEY (tenant_id, key)
);

CREATE TABLE IF NOT EXISTS counters (
    tenant_id TEXT NOT NULL REFERENCES tenants (id),
    name      TEXT NOT NULL,
    value     INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, name)
);
