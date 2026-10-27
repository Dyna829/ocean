# AI interaction completeness declaration

This declaration covers every AI tool used to produce this submission.

## Tools used

| Tool | Version / configuration | Model | Sessions | Native export |
|---|---|---|---|---|
| DeepSeek Harness (DSH) desktop app | `standard` agent preset, approval policy `ask`, file policy `workspace-write` | `deepseek-flash` | 2 (`session-e45b7148-1eaf-41d9-b867-396867dcceda`, `session-1b259789-6a30-4bb2-b86b-5a4c6b690b06`) | `ai/sessions/dsh-session-e45b7148.jsonl`, `ai/sessions/dsh-session-1b259789.jsonl` (+ untouched `.native.jsonl.zstd` for both) |

Two sessions were used: the main build session (12:24–14:07 +08:00) and a short follow-up
review session (13:30–13:32 +08:00) that examined the idempotency implementation and put the
audit reason into the request hash. Both are exported; no other AI tool, agent, or autocomplete
service was used for the planning, implementation, testing, or documentation of this
repository. No inline editor completion was active during either session.

> Candidate: if any AI assistance outside this session was used, add it to the table above
> before submitting.

## What the export contains

The native DSH session log is a JSONL event stream (format version 4, zstd-compressed on
disk). Both forms are included:

- `ai/sessions/dsh-session-e45b7148.native.jsonl.zstd` and
  `ai/sessions/dsh-session-1b259789.native.jsonl.zstd` — the untouched files written by the
  harness.
- `ai/sessions/dsh-session-e45b7148.jsonl` and `ai/sessions/dsh-session-1b259789.jsonl` —
  the same bytes decompressed with `zstd -d` for review.

The stream contains, with epoch-millisecond timestamps and sequence numbers:

- every user prompt and the full assistant responses (`assistant/message`);
- every tool call and its result (`tool/call`, `tool/result`) — file reads/writes, shell
  commands, their stdout/stderr, and exit codes;
- job registration and completion events for background processes
  (`job/registered`, `job/settled`);
- sandbox mode, approval policy, and the model identifier (`deepseek-flash`).

Because tool calls and outputs are part of the native export, no separate "tool action
evidence" file was needed.

## Export limitations

1. DSH stores sessions as zstd-compressed JSONL and does not provide a separate HTML/PDF
   renderer. The decompressed JSONL is the complete native record; the compressed original
   is shipped alongside it so the transformation is auditable.
2. The export is event-oriented, not a terminal scrollback: command output appears inside
   `tool/result` events rather than as a continuous terminal log. This is the native
   format, not a reduction.
3. The main session was re-exported after it closed (1808 events, ending at `turn/end`);
   the follow-up session was already complete. `ai/session-index.csv` records both windows.
4. No credentials, tokens, or third-party personal data were present, so no
   `[REDACTED: ...]` replacements were necessary.
5. Dependency caches (`.venv`, `web/node_modules`) and the generated 100k database are not
   AI interaction evidence and are excluded from git.

## Section 6 — no-AI confirmation

Section 6 (`written-answers.md`) is the only part of the assessment that must be produced
without AI. The candidate wrote it independently and confirmed completion on 2026-10-27; no
AI tool produced or edited its content. The boundary comes from `docs/briefing.pdf` §6, and
the assistant did not read, draft, outline, summarise, translate, rephrase, proofread, or
improve the answers.

- [x] Candidate: confirmed on 2026-10-27 that `written-answers.md` was written alone,
      without AI assistance of any kind.

## Reproducing the evidence

See `ai/README.md`. The exported session can be inspected with:

```bash
jq -c 'select(.type=="tool/call") | {time, tool: .data.name}' \
  ai/sessions/dsh-session-e45b7148.jsonl | head
```
