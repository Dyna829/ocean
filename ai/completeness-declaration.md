# AI interaction completeness declaration

This declaration covers every AI tool used to produce this submission.

## Tools used

| Tool | Version / configuration | Model | Sessions | Native export |
|---|---|---|---|---|
| DeepSeek Harness (DSH) desktop app | `standard` agent preset, approval policy `ask`, file policy `workspace-write` | `deepseek-flash` | 3 (`session-e45b7148-1eaf-41d9-b867-396867dcceda`, `session-1b259789-6a30-4bb2-b86b-5a4c6b690b06`, `session-d220c9f4-8fb6-46a0-bb0e-1a92b104b7ac`) | `ai/sessions/dsh-session-e45b7148.jsonl`, `ai/sessions/dsh-session-1b259789.jsonl`, `ai/sessions/dsh-session-d220c9f4.jsonl` (+ untouched `.native.jsonl.zstd` for all three) |
| MiniMax Code desktop app (agent `mavis`) | local runtime, `bypassPermissions` mode, workspace `/Users/dyna/Documents/Job/ocean` | `minimax/MiniMax-M3.1-Flash` | 2 (`mvs_0440be7bad514234a70dae0a49f82fc8`, `mvs_06fd271c43ec45a891939de7fae24ce5`) | `ai/sessions/mavis-session-0440be7b.native.jsonl`, `ai/sessions/mavis-session-06fd271c.native.jsonl` (+ `.llm-call.json`, `.manifest.json`, `.runtime.log` for both) |

**Five sessions were used, across the two tools above.**

*DeepSeek Harness (3 sessions)* — the main build session (12:24–14:07 +08:00), a short
follow-up review session (13:30–13:32 +08:00) that examined the idempotency implementation
and put the audit reason into the request hash, and a final packaging session
(14:07–15:05 +08:00) that renamed the candidate's written answers to `written-answers.md`,
refreshed the main export, expanded `AGENTS.md` with functionality, architecture and boundary
limits, reconciled this evidence, and pushed the submission.

*MiniMax Code (2 sessions)* — a candidate review session (12:57–13:19 +08:00) that
re-read `AGENTS.md`, inventoried the A1–A7 suites, built and type-checked the frontend, ran
`./verify.sh`, started the server on `:3300` and smoke-tested the live API with `curl`,
cross-checked the actor switcher and the bulk-issue scope against `docs/briefing.pdf`, and
re-ran the idempotency check under real concurrency; and an evidence-refresh session
(13:30– +08:00) that located the native export format, exported both MiniMax Code sessions
into `ai/sessions/`, and reconciled this declaration, `ai/session-index.csv`,
`ai/README.md`, and `ai/decision-log.md` with the sessions that had not been declared.

All five sessions are exported. The first MiniMax Code session (12:57–13:19) ran
concurrently with the DeepSeek Harness build session and was initially missing from this
declaration; it has now been exported and is disclosed above rather than silently omitted.
No other AI tool, agent, or autocomplete service was used for the planning, implementation,
testing, or documentation of this repository. No inline editor completion was active during
any session.

> Candidate: if any AI assistance outside this session was used, add it to the table above
> before submitting.

## What the export contains

The native DSH session log is a JSONL event stream (format version 4, zstd-compressed on
disk). Both forms are included for all three sessions:

- `ai/sessions/dsh-session-e45b7148.native.jsonl.zstd`,
  `ai/sessions/dsh-session-1b259789.native.jsonl.zstd`, and
  `ai/sessions/dsh-session-d220c9f4.native.jsonl.zstd` — the untouched files written by the
  harness.
- `ai/sessions/dsh-session-e45b7148.jsonl`, `ai/sessions/dsh-session-1b259789.jsonl`, and
  `ai/sessions/dsh-session-d220c9f4.jsonl` — the same bytes decompressed with `zstd -d` for
  review.

The stream contains, with epoch-millisecond timestamps and sequence numbers:

- every user prompt and the full assistant responses (`assistant/message`);
- every tool call and its result (`tool/call`, `tool/result`) — file reads/writes, shell
  commands, their stdout/stderr, and exit codes;
- job registration and completion events for background processes
  (`job/registered`, `job/settled`);
- sandbox mode, approval policy, and the model identifier (`deepseek-flash`).

Because tool calls and outputs are part of the native export, no separate "tool action
evidence" file was needed.

The MiniMax Code native session log is also JSONL, one message per line, and four artefacts
are included per session:

- `ai/sessions/mavis-session-0440be7b.native.jsonl` and
  `ai/sessions/mavis-session-06fd271c.native.jsonl` — the untouched `messages.jsonl` files
  written by the runtime.
- `ai/sessions/mavis-session-0440be7b.llm-call.json` and
  `ai/sessions/mavis-session-06fd271c.llm-call.json` — the request record: model, provider,
  thinking level, system prompt, and the tool schemas the agent was offered.
- `ai/sessions/mavis-session-0440be7b.manifest.json` and
  `ai/sessions/mavis-session-06fd271c.manifest.json` — the runtime's session manifest.
- `ai/sessions/mavis-session-0440be7b.runtime.log` and
  `ai/sessions/mavis-session-06fd271c.runtime.log` — the runtime's own activity log
  (permission decisions, background-task lifecycle), shipped here as the tool-action
  evidence for the second tool.

Each message line carries `message_id`, `turn_id`, and a `message` object with `role`,
`content[]`, and a millisecond `timestamp`; assistant turns additionally carry `model`,
`provider`, `responseId`, `usage`, and `stopReason`. The content parts are `text`,
`thinking`, `toolCall` (with the full arguments), `toolResult` (with `toolName`,
`toolCallId`, `isError`, and the output), and `image`. So the export contains every user
prompt, every full assistant response, every tool call with its arguments, every tool
result including failures, all timestamps, and the model identifier.

## Export limitations

1. DSH stores sessions as zstd-compressed JSONL and does not provide a separate HTML/PDF
   renderer. The decompressed JSONL is the complete native record; the compressed original
   is shipped alongside it so the transformation is auditable.
2. The export is event-oriented, not a terminal scrollback: command output appears inside
   `tool/result` events rather than as a continuous terminal log. This is the native
   format, not a reduction.
3. The main session was re-exported after it closed (1808 events, ending at `turn/end`);
   the follow-up session was already complete. The final packaging session was re-exported at
   the final packaging step (15:05), after the content commits were pushed: its closing
   summary and the evidence-packaging commit that adds this export are outside that snapshot.
   Every prompt, tool call, and tool result up to that point is present.
   `ai/session-index.csv` records all three windows.
4. MiniMax Code has the same two limitations, with one difference: it does not compress the
   session log, so `mavis-session-*.native.jsonl` is already the untouched record and no
   "decompressed for review" twin exists. The evidence-refresh session
   (`mvs_06fd271c…`) was still open when the evidence was packaged, so its export is a
   snapshot taken at the packaging step: its closing summary and the two evidence commits
   that add these files are outside that snapshot. The recorded window ends at
   2026-10-27T14:50:40+08:00, and every prompt, tool call, and tool result up to that point
   is present. `ai/session-index.csv` records all five windows.
5. In the MiniMax Code export, the `user` messages contain the harness-injected
   `<system-reminder>` blocks (session id, tool guidance, project instructions) alongside the
   typed prompt, because the runtime records the assembled turn. This is the native
   representation, not a reduction; `ai/README.md` gives a `jq` one-liner that strips the
   reminders to read the typed prompts.
6. The first MiniMax Code session (`mvs_0440be7b…`, 12:57–13:19 +08:00) was not declared
   when the submission was first packaged — it ran concurrently with the DeepSeek Harness
   build session. It is now exported, indexed, and disclosed in the table above. The gap was
   found by reading the local session store, not by recollection.
7. No credentials, tokens, or third-party personal data were present in either tool's
   export, so no `[REDACTED: ...]` replacements were necessary. The exports were scanned
   for API keys, bearer tokens, JWTs, and non-demo email addresses before being copied into
   the repository; the only addresses present are the seeded `alice@east.test` and
   `bob@west.test` actors.
8. Dependency caches (`.venv`, `web/node_modules`) and the generated 100k database are not
   AI interaction evidence and are excluded from git.

## Section 6 — no-AI confirmation

Section 6 (`written-answers.md`) is the only part of the assessment that must be produced
without AI. The candidate wrote it independently and confirmed completion on 2026-10-27; no
AI tool produced or edited its content. The final packaging session moved the file to the
required path without reading or editing its content. The boundary comes from
`docs/briefing.pdf` §6, and the assistant did not read, draft, outline, summarise, translate,
rephrase, proofread, or improve the answers.

This holds for both tools. The DeepSeek Harness packaging session renamed the file and did
not touch its content. Neither MiniMax Code session could have read it either: the review
session (12:57–13:19 +08:00) ended before the file was created at 14:14, and the
evidence-refresh session only checked that the file exists (`ls -la`) — it never opened it.
The assistant was not asked to help with Section 6 and declined no request, because none was
made.

- [x] Candidate: confirmed on 2026-10-27 that `written-answers.md` was written alone,
      without AI assistance of any kind.

## Reproducing the evidence

See `ai/README.md`. The exported session can be inspected with:

```bash
jq -c 'select(.type=="tool/call") | {time, tool: .data.name}' \
  ai/sessions/dsh-session-e45b7148.jsonl | head
```
