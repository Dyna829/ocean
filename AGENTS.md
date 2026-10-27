# AGENTS.md — instructions for AI assistants working in this repository

This repository is the submission for the Ocean AI Labs Beijing technical interview
assessment (see `docs/briefing.pdf`). It is built with AI assistance and the assessment
requires that assistance to be traceable.

## Absolute boundaries

1. **Never touch Section 6 / `written-answers.md`.** The candidate writes those three
   answers alone, in their own words. Do not draft, outline, summarise, translate,
   rephrase, proofread, or improve them — not even as a "review". If asked, decline and
   point at the assessment rule.
2. Do not fabricate AI evidence. Sessions, decision logs, and the completeness
   declaration must describe what actually happened.
3. Do not commit credentials, tokens, or private third-party data. Use
   `[REDACTED: reason]` only where required, without changing substance.

## Product scope (keep it thin)

Build an internal, multi-tenant certificate admin console:

- list/search/paginate/sort certificates, tenant-scoped;
- bulk issue certificates to eligible learners, idempotent;
- certificate detail, revocation with confirmation, audit trail;
- CSV export that preserves search and sort, streaming 100,000 rows.

Out of scope: production authentication, cloud deployment, notifications, unrelated
admin features, visual polish over correctness.

## Technical ground rules

- Backend: Python + FastAPI + SQLite (WAL). Frontend: React 19 + Vite + TypeScript,
  built to `web/dist` and served by FastAPI on one origin.
- `X-Actor-Email` identifies the caller. Tenant scope is derived **server-side** from the
  actor record; never trust a tenant id supplied by the client.
- Every query that touches tenant data carries `tenant_id = :tenant_id`. A resource in
  another tenant must be indistinguishable from a missing resource (404).
- Writes run in `BEGIN IMMEDIATE` transactions. Money-like invariants (one certificate
  per learner/course, one audit event per certificate lifecycle action) are enforced by
  database constraints, not only by application checks.
- Timestamps are stored as UTC ISO-8601 strings. Tenant-local calendar dates are stored
  with the certificate (`issue_date_local`) because the assessment sorts and exports on
  them; display strings are derived from the tenant's IANA timezone.
- Sort order is always total: requested key first, then `id` as a deterministic
  tiebreaker. Exports and lists must agree.

## Verification expectations

- `./verify.sh` must pass before any commit that claims a scenario works.
- Acceptance scenarios A1–A7 live in `tests/test_a*.py`; reproduce steps in `README.md`.
- Do not weaken or delete a failing test to make the suite green. Fix the behaviour or
  document the defect in the README "Known defects" section.

## Commit discipline

- Small commits, imperative subject, one concern each.
- Prefix: `feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`.
- Record material AI decisions (accepted / rejected / tradeoff) in `ai/decision-log.md`
  with the session id, verification evidence, and commit sha.

## Evidence

- `ai/sessions/` holds native session exports; `ai/session-index.csv` indexes them.
- Keep this file in git. It is the AI instruction file for the repository.
