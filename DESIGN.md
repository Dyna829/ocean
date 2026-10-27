# Design — Multi-tenant Certificate Admin Console

Status: **review candidate**. Stack: Python 3 + FastAPI + SQLite (WAL) · React 19 + Vite + TypeScript.
Brief: `docs/briefing.pdf`.

---

## 1. Goal, scope, and constraints

Tenant admins review course completions, issue certificates in bulk, revoke them, inspect
the audit trail, and export certificate data. Correctness of the core workflow outranks
visual polish; the acceptance scenarios A1–A7 in the brief are the definition of done.

| Area | Decision |
|---|---|
| Backend | Python 3.14, FastAPI 0.162, Uvicorn; SQLite 3.51 via stdlib `sqlite3` (WAL) |
| Frontend | React 19, TypeScript, Vite; built to `web/dist`, served by FastAPI on one origin |
| Startup | `./start.sh` creates venv, installs deps, builds the SPA, seeds demo data, starts the server on `:8000` |
| Verification | `./verify.sh` runs the A1–A7 pytest suite plus the 100k-row export check |
| Actor | `X-Actor-Email` request header; tenant is resolved server-side from the admin record |
| Out of scope | Real authentication, cloud deploy, notifications, i18n, email, extra admin CRUD |

Non-goals deliberately rejected: an ORM (the queries that matter are three joins and a
keyset export; hand-written SQL is auditable), background job infrastructure (bulk issue is
synchronous and small; the export streams), and client-side caching/state libraries.

## 2. Architecture

```
browser ──HTTP──▶ FastAPI (uvicorn, single process)
                    ├── /api/*        JSON + CSV
                    ├── /assets/*     built SPA (web/dist)
                    └── /             index.html
                          │
                          └── SQLite  data/app.db   (WAL, busy_timeout=30s)
```

One process, one origin: no CORS, no reverse proxy, no separate frontend server to keep
alive. FastAPI endpoints are **sync `def` functions**, so Starlette runs them in its
AnyIO worker-thread pool; SQLite calls therefore never block the event loop and a slow
export cannot stall the certificate list (A6). Each thread gets its own connection
(thread-local), all connections open WAL with `busy_timeout=30000` and
`foreign_keys=ON`.

Writes use `BEGIN IMMEDIATE`; SQLite serialises writers across connections, which is also
what makes same-key idempotency safe without an in-process lock.

## 3. Data model

Canonical DDL: `app/schema.sql`. Summary:

| Table | Purpose | Key constraints |
|---|---|---|
| `tenants` | tenant + IANA timezone | `slug` unique |
| `admins` | actor per tenant | `email` unique, `tenant_id` FK |
| `courses` | tenant course catalogue | `tenant_id` FK |
| `learners` | tenant learners | `tenant_id` FK |
| `enrollments` | completion state | `unique(course_id, learner_id)`, status `COMPLETED|INCOMPLETE` |
| `certificates` | issued credentials | `unique(tenant_id, serial)`, `unique(tenant_id, seq)`, **`unique(tenant_id, course_id, learner_id)`** |
| `audit_events` | issuance / revocation trail | **`unique(certificate_id, action)`** |
| `idempotency_keys` | replay store for bulk issue | `PK(tenant_id, key)` |
| `counters` | per-tenant serial sequence | `PK(tenant_id, name)` |

Design notes:

* **Certificate rows snapshot `learner_name` and `course_title`.** A certificate is an
  immutable historical record: renaming a learner must not rewrite an issued credential.
  It also lets list sort, search, and export run against one indexed table instead of a
  join + sort over 100k rows (A6 latency budget).
* **`issue_date_local`** (`YYYY-MM-DD`) is persisted at issuance because the brief requires
  list sorting and CSV to use the tenant-local calendar date. Display strings
  (`2026-01-11 00:30`) are derived per request from UTC + `tenants.timezone`, so a DST or
  timezone correction cannot stale the UI.
* **`seq`** is a per-tenant monotonic integer and doubles as the export snapshot horizon.
* **Uniqueness is the real idempotency guard.** Two concurrent bulk requests cannot create
  a second certificate for the same learner/course because the unique index rejects it; the
  application returns `skipped` for that learner instead of an error.
* **`unique(certificate_id, action)` on audit** makes "exactly one issuance/revocation event
  per certificate" a database invariant, not a code convention (A2, A7).
* A revoked certificate keeps its row and its unique tuple: re-issuing the same
  learner/course is `already_certified`. Documented as a product rule; a "reissue" flow is
  out of scope.

Indexes: `(tenant_id, learner_name COLLATE NOCASE, id)`, `(tenant_id, course_title, id)`,
`(tenant_id, issued_at, id)`, `(tenant_id, serial)`, plus `(tenant_id, status)`.

## 4. API contract

All endpoints are tenant-scoped by the actor; unknown or cross-tenant resources return the
same 404 body. Errors: `{"code": "...", "message": "...", "details": {...}}`.

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/me` | actor + tenant (`slug`, `name`, `timezone`) |
| `GET` | `/api/courses` | courses with `eligible`/`certified`/`incomplete` counts for the bulk form |
| `GET` | `/api/certificates` | `q`, `page`, `pageSize` (≤100), `sort` (`issued_date|learner_name|course_title|serial`), `dir` |
| `GET` | `/api/certificates/{id}` | detail + audit timeline; 404 when not in tenant |
| `POST` | `/api/certificates/bulk-issue` | header `Idempotency-Key`, body `{courseId}`; 409 on key/payload mismatch |
| `POST` | `/api/certificates/{id}/revoke` | idempotent; repeat returns `alreadyRevoked: true` with no new audit |
| `GET` | `/api/certificates/export.csv` | same `q`, `sort`, `dir`; streams CSV |
| `GET` | `/api/health` | liveness + DB check |

`GET /api/certificates` response:

```json
{
  "items": [{
    "id": "cert_9f2c…", "serial": "CERT-EAST-2026-000004",
    "courseId": "course_east_safety", "courseTitle": "Safety 101",
    "learnerId": "learner_east_maya", "learnerName": "Maya Chen",
    "status": "ACTIVE",
    "issuedAt": "2026-01-10T13:30:00Z",
    "issuedAtLocal": "2026-01-11 00:30",
    "issueDateLocal": "2026-01-11"
  }],
  "page": 1, "pageSize": 20, "total": 43, "totalPages": 3,
  "sort": "issued_date", "dir": "desc", "q": "",
  "tenant": {"slug": "east", "timezone": "Australia/Sydney"}
}
```

`POST /api/certificates/bulk-issue` response (stored verbatim for replay):

```json
{
  "operationId": "op_1c7d…", "courseId": "course_east_safety", "courseTitle": "Safety 101",
  "summary": {"total": 4, "issued": 2, "skipped": 2, "failed": 0},
  "outcomes": [
    {"learnerId": "learner_east_alex", "learnerName": "Alex Lee", "status": "skipped",
     "reason": "already_certified", "message": "Certificate CERT-EAST-2026-000001 already exists"},
    {"learnerId": "learner_east_tom", "learnerName": "Tom Baker", "status": "skipped",
     "reason": "incomplete_enrollment", "message": "Enrollment is not completed"},
    {"learnerId": "learner_east_maya", "learnerName": "Maya Chen", "status": "issued",
     "certificateId": "cert_9f2c…", "serial": "CERT-EAST-2026-000004"}
  ]
}
```

Replays return the identical body with `Idempotency-Replayed: true`; the same key with a
different body returns `409 {"code": "idempotency_key_reuse"}` and executes nothing (A3).

## 5. Cross-cutting design

### 5.1 Tenant isolation (A1)

`resolve_actor()` looks up `admins` by `X-Actor-Email`; the tenant id comes from that row
only. No endpoint accepts a tenant id. Every statement carries `tenant_id = :tenant`, and
cross-tenant resources produce the same 404 as missing ones (`certificate_not_found`), so a
probe cannot distinguish "exists elsewhere" from "does not exist". Bulk issue resolves the
course inside the actor's tenant before any write, so a cross-tenant course id leaves
certificates and audit untouched — the test asserts both counts.

### 5.2 Idempotency (A2, A3)

```
BEGIN IMMEDIATE
  row = SELECT * FROM idempotency_keys WHERE tenant_id=? AND key=?
  if row and row.request_hash != hash(body):          -> 409, no writes
  if row and row.status == SUCCEEDED:                 -> return row.response_json
  execute bulk issue (per-learner savepoints)
  INSERT key row (SUCCEEDED, response json, operation id)
COMMIT
```

* The whole operation and the key row commit atomically: a crash leaves neither a partial
  batch nor a poisoned key. The row is only ever inserted as `SUCCEEDED`, so the
  `idempotency_key_in_progress` branch is unreachable today; it exists for the async
  variant (README §9) and would then need stale-row recovery, or a crashed job wedges its
  key forever.
* Concurrent identical requests serialise on SQLite's write lock, then read the committed
  row and replay the same bytes. Sequential requests take the same path.
* The request hash is `sha256(endpoint + canonical_json(request))` over `courseId` and,
  when given, `reason`: the audit reason is part of the payload, so the same course with a
  different reason is `409` (A3) rather than a replay that silently drops it. A blank
  reason canonicalises to "no reason", and that absent-reason form is unchanged from the
  pre-`reason` hash, so keys stored before this rule still replay.
* Failure (500) rolls back the transaction, so no key is stored and a retry is a fresh
  attempt — correct for a transient error.

### 5.3 Time and DST (A5)

* `issued_at` is UTC, second precision, `Z` suffix; sorting on it is a total order.
* `issue_date_local` is computed at issuance with `zoneinfo` for the tenant timezone.
* `issued_at_local` is derived on read (`YYYY-MM-DD HH:MM`) — East `2026-01-11 00:30`,
  West `2026-01-10 21:30` for the same `2026-01-10T13:30:00Z` instant.
* Sorting by "issued date" uses `issued_at, id`: within one tenant, local calendar date is a
  monotonic function of the UTC instant, so the order is identical to sorting by the
  displayed date and stays deterministic for ties.
* Seeded A5 fixtures are two certificates with exactly that UTC timestamp (one per tenant).

### 5.4 Export (A6)

* `StreamingResponse` over an async generator; batches of 2,000 rows fetched in a worker
  thread, so each batch holds the event loop only for the `await`.
* Keyset paging is **two index seeks per batch**: first drain the current sort key with
  `key = ? AND id > ?`, then jump to `key > ?`. A single row-value comparison is not pushed
  into the index when the key is a collated expression with many duplicates, which made the
  first implementation scan from the start of the tenant's index on every batch — 61.7 s for
  1M rows. The two-step form is linear (3.6 s for 1M). Each query names its index with
  `INDEXED BY` so the residual search/horizon filter cannot divert the planner into a temp
  sort.
* Order: requested sort key, then `id`, both in the requested direction — a total order, so
  equal sort keys appear in the same relative order on every export. List and export share
  the same ordering rule.
* Snapshot horizon: `max(seq)` captured at export start; rows issued mid-export are not
  appended to the stream.
* CSV columns: `learner_name,course_title,serial_number,issue_date` (RFC 4180 quoting, UTF-8,
  no BOM). `Content-Disposition` filename includes tenant slug and date.
* Search escapes `%`, `_`, `\` and uses `LIKE ... ESCAPE '\'` on learner name or serial.
* 100k rows ≈ 50 batches ≈ a few seconds locally, well inside the 60 s budget; the list
  endpoint stays responsive because all DB work is off-loop and per-batch.

### 5.5 Revocation and audit (A7)

```sql
UPDATE certificates SET status='REVOKED', revoked_at=?, revoked_by=?
 WHERE id=? AND tenant_id=? AND status='ACTIVE'
```

Inside one transaction: if `rowcount == 1`, insert exactly one `REVOKED` audit event
(details include reason and actor). A repeat update matches zero rows, so no second event
and the response is `200` with `alreadyRevoked: true`. The audit unique index makes a
duplicate physically impossible.

### 5.6 Observability

One structured line per HTTP request from a raw ASGI middleware (not `BaseHTTPMiddleware`,
which buffers streaming responses and would distort the export); the line carries method,
path, status, duration, actor, tenant, and the request id that is also returned as
`X-Request-Id`. Business events (`bulk_issue.*`, `certificate.revoked`, `export.*`,
`auth.rejected`) are logged by the services that own them. Levels are standard
(`DEBUG`/`INFO`/`WARNING`/`ERROR`), selectable with `LOG_LEVEL`, with `LOG_FORMAT=json` for
collectors. The SPA logs the same four levels to the console and sends its own
`X-Request-Id`, so one browser action and its server request share an identifier.

## 6. Acceptance matrix

| ID | Behaviour | How it is verified |
|---|---|---|
| A1 | Bob cannot read or act on East data | `tests/test_a1_tenant_isolation.py`: list/detail/export only West; East detail 404; East course bulk issue 404 and certificate/audit counts unchanged |
| A2 | Same key, sequential + concurrent, one logical operation | `tests/test_a2_idempotency.py`: identical bodies, one cert per learner, `count(audit) == count(issued)`, 6 parallel requests |
| A3 | Same key, different payload → 409 | `tests/test_a3_key_misuse.py`: 409, no new certs/audit, first result intact |
| A4 | Only eligible learners get certificates | `tests/test_a4_learner_outcomes.py`: issued/skipped with reasons |
| A5 | Tenant-local dates across DST | `tests/test_a5_timezone.py`: display strings, CSV dates, date sort |
| A6 | 100k export < 60 s, deterministic ties, list during export | `tests/test_a6_export.py` (100k fixture) + `scripts/perf_a6.py` |
| A7 | Revoke twice → one audit event | `tests/test_a7_revocation_audit.py` |

## 7. Demo data (`app/seed.py`)

Tenants `East` (Australia/Sydney) and `West` (Australia/Perth); admins `alice@east.test`,
`bob@west.test`; both tenants contain course **Safety 101** and learner **Alex Lee**.

| Tenant | Course | Learner | Enrollment | Certificate |
|---|---|---|---|---|
| East | Safety 101 | Alex Lee | COMPLETED | ACTIVE `2026-01-10T13:30:00Z` (A5) |
| East | Safety 101 | Maya Chen | COMPLETED | — (eligible) |
| East | Safety 101 | Priya Nair | COMPLETED | — (eligible) |
| East | Safety 101 | Tom Baker | INCOMPLETE | — (skipped) |
| West | Safety 101 | Alex Lee | COMPLETED | ACTIVE `2026-01-10T13:30:00Z` (A5) |
| West | Safety 101 | Sam Rivera | COMPLETED | — (eligible) |
| West | Safety 101 | Dana Kim | INCOMPLETE | — |
| East | Fire Safety | 4 learners | COMPLETED | — (clean bulk-issue / A2 / A3 fixture) |
| East | Data Privacy | 3 learners | mixed | one REVOKED certificate + audit (UI demo) |
| West | Fire Safety | 3 learners | COMPLETED | — |

Numbers are deterministic; the UI paginates at 10/20/50/100 per page.

`scripts/generate_large.py --tenant east --count 100000 --db data/large.db` builds a
separate database (default quick-start data untouched) containing 100k East certificates
with repeated learner names and identical timestamps to exercise equal sort keys, plus a
small West set so isolation is still demonstrable. Run the app against it with
`DB_PATH=data/large.db ./start.sh`.

## 8. UI plan

Single page, no router (one workflow). Header: app name, actor switcher (Alice/East,
Bob/West), tenant timezone badge. Toolbar: debounced search, page-size select, Export CSV.
Table: serial, learner, course, issued (tenant-local), status badge, row action. States:
skeleton rows while loading, explicit empty state, error banner with retry, disabled
controls while a request is in flight. Detail drawer: all fields, audit timeline, revoke
panel with an explicit confirmation step and optional reason. Bulk-issue dialog: course
picker with eligibility counts, one `crypto.randomUUID()` key per dialog session (retry
reuses it), per-learner outcome table grouped by issued/skipped/failed, summary chips and
the operation id.

## 9. AI evidence

* `ai/sessions/` — native DeepSeek Harness JSONL export(s) for this build, including
  prompts, responses, tool calls, commands, and timestamps.
* `ai/session-index.csv` — one row per session.
* `ai/decision-log.md` — accepted suggestion, rejected/corrected suggestion, scope
  tradeoff, each with session id, verification evidence, and commit.
* `ai/completeness-declaration.md` — tools used, export limitations, Section 6 statement.
* `AGENTS.md` — the instruction file used for this repository.

`written-answers.md` (Section 6) is completed by the candidate without AI and is never
touched by these sessions.

## 10. Risks and tradeoffs

| Risk / tradeoff | Mitigation |
|---|---|
| SQLite single-writer serialises bulk issue and revocation | Writes are short; 30 s busy timeout; documented. Pg/MySQL would keep the DDL and swap the driver |
| Synchronous bulk issue with many eligible learners would be slow | Demo scale is tens; a queue is explicitly out of scope. Summary + per-learner outcomes still returned |
| Export holds a read snapshot per batch, not a true MVCC snapshot | Snapshot horizon cuts new rows; revocation during export can flip a row between batches — acceptable for an admin export, documented |
| `LIKE` case folding is ASCII-only in SQLite | Names in scope are ASCII; documented limitation |
| No authentication (per brief) | Actor header is an explicit demo affordance; tenant scoping still enforced server-side |
| Frontend has no automated tests | Backend A1–A7 covered by pytest; UI verified manually against the same scenarios, recorded in README |

## 11. Three-hour execution plan

| Time | Work |
|---|---|
| 0:00–0:10 | This design, schema, acceptance list (done) |
| 0:10–1:55 | Backend core → frontend workflow → A1/A7 → A2/A3 → A5 → A4 → A6 hardening |
| 1:55–2:20 | Run A1–A7 against the real server, fix high-impact defects |
| 2:20–2:35 | README, demo data, startup check, AI export index, completeness declaration |
| 2:35–3:00 | Section 6 written answers (candidate, no AI), package, final commit |
