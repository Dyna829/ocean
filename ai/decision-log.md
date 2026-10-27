# Decision log

Material decisions made while building this submission, including the AI suggestions that
were accepted, corrected, and the scope tradeoffs taken. They came from two DeepSeek
Harness sessions, both model `deepseek-flash`: the main build session
(`session-e45b7148-1eaf-41d9-b867-396867dcceda`, 12:24–14:07 +08:00) and a short follow-up
review (`session-1b259789-6a30-4bb2-b86b-5a4c6b690b06`, 13:30–13:32 +08:00). D2–D8 are from
the main session; D1's reason-hash refinement is from the follow-up. Exports are in
`ai/sessions/`.

Time zone for every timestamp below: Asia/Singapore (+08:00), 2026-10-27.

| # | Type | Decision | Session | Commits |
|---|---|---|---|---|
| D1 | accepted | Database-enforced idempotency instead of an in-process lock | `session-e45b7148`, `session-1b259789` | `b94ac80`, `6b05ddb` |
| D2 | accepted | Name snapshots + keyset streaming export | `session-e45b7148` | `b94ac80`, `6b05ddb` |
| D3 | corrected | Async generator iterated synchronously in the A6 test | `session-e45b7148` | `6b05ddb` |
| D4 | corrected | `start.sh` assumed bash 4 empty-array semantics | `session-e45b7148` | `ebb8485` |
| D5 | tradeoff | SQLite single-writer + synchronous bulk issue, no queue | `session-e45b7148` | `b94ac80`, `0f6674e` |
| D6 | tradeoff | Pinned Vite 7 / TypeScript 5.9 instead of the newest majors | `session-e45b7148` | `48c2938` |
| D7 | accepted | Leveled structured logging with a shared request id | `session-e45b7148` | `dfbeee4` |
| D8 | corrected | Export was super-linear at 1M rows; two-step keyset fixed it | `session-e45b7148` | `3db3bda` |

---

## D1 — Accepted: enforce idempotency in the database, not in process memory

**Context.** A2 requires the same `Idempotency-Key` to be one logical operation for
sequential *and* concurrent callers, returning identical outcomes and creating no extra
certificates or audit events. A3 requires a `409` when the key is reused with a different
payload.

**Proposal accepted.** The AI proposed an `idempotency_keys(tenant_id, key, request_hash,
response_json, ...)` row written in the *same* `BEGIN IMMEDIATE` transaction as the
issuance, plus `unique(tenant_id, course_id, learner_id)` on certificates and
`unique(certificate_id, action)` on audit events as the last line of defence
(`app/schema.sql:66`, `app/schema.sql:96`, `app/db.py:60`).

**Why this was accepted.** It removes the need for an in-process lock or queue: SQLite's
write lock serialises the concurrent callers, the loser of the race reads the committed row
and replays it, a crash rolls back both the certificates and the key row, and A3 becomes a
cheap hash comparison before any write. A retry after a `500` re-executes, which is the
correct behaviour for a transient failure.

**Verification.** `pytest tests/test_a2_idempotency.py tests/test_a3_key_misuse.py` — the
A2 test fires six concurrent requests with one key and asserts exactly one
`operationId`, one `Idempotency-Replayed: false`, five `true`, `+2` certificates and `+2`
audit events; A3 asserts `409 idempotency_key_reuse` with certificate and audit counts
unchanged, and that the original result is still replayable. Two further A3 tests cover
the audit `reason` becoming part of the hash (different reason → 409; blank reason replays);
that refinement was made in the follow-up session `session-1b259789-…`, whose export is in
`ai/sessions/`.

## D2 — Accepted: snapshot names on the certificate and stream exports in keyset batches

**Context.** A6 needs 100,000 rows in under 60 s while a certificate list request stays
responsive, and rows with equal sort keys must keep their relative order across exports.

**Proposal accepted.** Persist `learner_name` and `course_title` on each certificate at
issuance, index them together with `id`, and stream the CSV by fetching 2,000-row keyset
pages — `(sort_key, id) > (last_key, last_id)` — inside the worker-thread pool
(`app/services/certificates.py:504`, `app/routers/api.py:69`). Exports are bounded by a
`max(seq)` horizon captured at the start. Every `ORDER BY` ends in `id ASC`, so ties are
deterministic.

**Why this was accepted.** A certificate is an immutable historical record, so snapshotting
the names is also the correct semantic. It removes a join and a sort from every export
batch: with a plain join the 50 batches would each sort 100k rows. Keyset paging also avoids
holding a cursor/read transaction across thread-pool hops, which SQLite connections and WAL
checkpointing do not tolerate well.

**Verification.** Generated 100,000 East certificates with
`scripts/generate_large.py`; export measured **1.0 s** for 7.0 MB (100,013 rows), two
consecutive exports were byte-identical, and a list request issued while the export stream
was open returned in **11 ms**. `tests/test_a6_export.py` automates exactly this, including
the 60 s budget, and passes against a real uvicorn server.

## D3 — Corrected: the first A6 test consumed an async iterator synchronously

**What happened.** The first full run failed with

```
TypeError: 'async_generator' object is not iterable
tests/test_a6_export.py:86: TypeError
```

The test counted the remaining CSV lines with `sum(1 for _ in line_iterator)`, but
`httpx.Response.aiter_lines()` is asynchronous.

**Correction.** Replaced the call with an `async for` loop that increments a counter, then
re-ran the suite: `7 passed in 4.17s`. The fix is in commit `6b05ddb`; the failing output
and the passing re-run are both in the exported session.

This is the only defect the acceptance suite itself surfaced, and it was fixed rather than
worked around (no assertion was weakened).

## D4 — Corrected: `start.sh` assumed bash 4 empty-array expansion

**What happened.** Running the documented one-command start produced

```
==> Initialising demo data at /tmp/oceantest/demo.db
./start.sh: line 45: SEED_ARGS[@]: unbound variable
```

macOS ships bash 3.2, where expanding an empty array under `set -u` aborts the script. The
AI-written script had used `"${SEED_ARGS[@]}"` unconditionally.

**Correction.** Guarded the expansion with `[ "${#SEED_ARGS[@]}" -gt 0 ]`
(`start.sh:45`), which is portable to bash 3.2. Re-ran `./start.sh`: the server came up on
the requested port, `/` returned `200 text/html` with the built SPA, the JS asset returned
`200`, and `/api/certificates` returned the 13 seeded East rows.

This is exactly the class of bug that only appears when the documented command is executed
end-to-end rather than assumed to work.

## D5 — Tradeoff: SQLite + synchronous bulk issue instead of a queue

**Chosen.** A single Python process with SQLite in WAL mode, synchronous bulk issue, and no
background job infrastructure. The workspace setup must be one command with no external
service, and the assessment dataset is tens of learners per course.

**Cost.** Writers serialise: a second bulk issue or a revocation waits for the first write
transaction. With thousands of eligible learners the HTTP request would be long-lived and a
job queue with polling would be the right design. This is documented in `DESIGN.md` §10 and
`README.md` §9 rather than hidden.

**Verification.** The concurrent A2 test (six parallel requests) completes quickly and the
A6 list-during-export check confirms reads are unaffected by the export; the limits are
stated explicitly in the README's known-defects section.

## D6 — Tradeoff: pinned Vite 7 / TypeScript 5.9 rather than the newest majors

**Context.** The registry currently offers Vite 8.3 and TypeScript 7.0. `@vitejs/plugin-react`
6.x declares `vite: ^8.0.0` plus new transform peer dependencies, and TypeScript 7 is a new
major. With a three-hour budget, a broken dev toolchain is an expensive distraction.

**Decision.** Pinned `vite ^7.3.7`, `@vitejs/plugin-react ^5.2.0`, `typescript ~5.9.3`
(`web/package.json`), and committed the lockfile so `npm ci` is reproducible.

**Verification.** `npm run build` runs `tsc --noEmit && vite build`; it passes both in
`./verify.sh` and in `./start.sh`. The version investigation is visible in the session's
`npm view` tool output.

---

## D7 — Accepted: leveled structured logging with a shared request id

**Context.** Up to this point the API had one `log.warning` call and Uvicorn's default access
log. There was no logging configuration at all, so `app.*` warnings fell through to
`logging.lastResort` and printed without timestamp, level, or logger name; nothing tied a
request to the business events it produced, and the browser had no structured logging.

**Proposal accepted.** Four levels (`DEBUG`/`INFO`/`WARNING`/`ERROR`) on both tiers:

- `app/logging.py` configures one stdout handler with a text or JSON formatter, level from
  `LOG_LEVEL`, and a `request_id` context variable.
- `app/middleware.py` logs exactly one line per request (method, path, status, duration,
  actor, tenant, request_id) and returns `X-Request-Id`; it is raw ASGI rather than
  `BaseHTTPMiddleware` so the streaming CSV export is not buffered.
- Services log their own events: `bulk_issue.start/done/replay/conflict`,
  `certificate.revoked/revoke_replay`, `export.start/done`, `auth.rejected`, plus
  `request.failed` with the traceback.
- `web/src/log.ts` mirrors the levels, logs API calls and UI actions, and sends a generated
  `X-Request-Id` so a console line and the server line share one identifier.

**Why this shape.** The requests that matter for this product are already small and explicit;
a middleware plus a handful of business events gives correlation without a logging framework,
and the level switch maps directly onto what an interviewer or operator would ask for: what
happened (INFO), why it was slow (WARNING), and what broke (ERROR + traceback).

**Verification.**

- `./verify.sh` passes: 7 acceptance scenarios plus the logging tests covering the
  request line fields, `bulk_issue` summary, 409 as `WARNING`, DEBUG suppression at INFO,
  unhandled 500 with `X-Request-Id`, slow-request warning, client id echo/rejection, and the
  text/JSON formatters.
- A replay logs only `bulk_issue.replay` with the stored operation id; `start` is emitted
  only when the request executes, so grepping an operation id never lands on an attempt that
  never ran.
- Manual: text output shows `request_id`, `operationId`, `issued=4`, `durationMs`;
  `LOG_FORMAT=json` emits one JSON object per line; a browser-generated
  `request_id=web-ef5464810e9a` appears on both the console `api.response` entry and the
  server `app.request` line; `setLogLevel("debug")` reveals `api.request`/`api.response`
  while the production default (`info`) hides them.

**Cost.** One INFO line per request (accepted: it replaces Uvicorn's access log, which
`start.sh` now disables). Client logs stay in the browser console — no shipping endpoint —
which is recorded under known defects in `README.md` §10.

---

## D8 — Corrected: the export was super-linear at 1M rows

**What the boundary test showed.** 100,000 rows exported in 0.97 s, 300,000 in 6.09 s, and
1,000,000 in **61.7 s** — roughly 6x and 63x for 3x and 10x the data. The 60 s budget in A6
applies to 100k rows, so acceptance was never at risk, but the curve showed the export would
not survive a larger tenant.

**Root cause.** Two compounding effects:

1. The snapshot condition `c.seq <= ?` made the planner choose the `(tenant_id, seq)` index
   and then build a temp B-tree to satisfy `ORDER BY learner_name, id` for every batch —
   a full sort of the tenant's rows per 2,000-row page.
2. Even with the right index, SQLite does not push a row-value comparison
   `(learner_name COLLATE NOCASE, id) > (?, ?)` into an index seek when the key has many
   duplicates, so each batch restarted at the beginning of the tenant's index.

**Fix.** `export_batch` now does two index seeks per page behind an explicit `INDEXED BY`
hint: first drain the current key with `key = ? AND id > ?`, then jump to `key > ?`. The
tiebreaker direction now follows the requested direction, which makes the order a pure
index order for both ASC and DESC.

**Verification.** 100k **0.24 s**, 300k **1.27 s**, 1M **3.62 s**; a list request during the
1M export returns in 24 ms; `tracemalloc` peak is ~3.5 MB for a 70 MB CSV. The A6 test caught
the intermediate version of this change that ordered a batch by `id` instead of by key and
silently skipped 36,100 rows — it asserts the exact row count, so the bug never reached a
commit.

**Cost.** The queries are now tied to index names in `app/schema.sql`; adding or renaming an
index means updating `SORT_INDEXES`. Documented in `DESIGN.md` §5.4.
