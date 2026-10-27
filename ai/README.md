# AI session evidence

Two AI sessions produced the build, both DeepSeek Harness (DSH) with the
`deepseek-flash` model on 2026-10-27 (Asia/Singapore): the main build session
(12:24–14:07) and a short follow-up review of idempotency edge cases (13:30–13:32).

| File | What it is |
|---|---|
| `dsh-session-e45b7148.native.jsonl.zstd` | main session, untouched log written by DSH |
| `dsh-session-e45b7148.jsonl` | main session, decompressed for review |
| `dsh-session-1b259789.native.jsonl.zstd` | follow-up review session, untouched log |
| `dsh-session-1b259789.jsonl` | follow-up review session, decompressed |
| `session-index.csv` | one row per session: model, window, export, purpose, commits |
| `decision-log.md` | accepted / corrected / tradeoff decisions with evidence |
| `completeness-declaration.md` | tools used, export limitations, Section 6 boundary |

## How the export was produced

DSH keeps sessions under `~/.dsh/sessions/<workspace>/<session-id>/session.v4.jsonl.zstd`.
The decompressed copy was produced with:

```bash
BASE=~/.dsh/sessions/--Users-dyna-Documents-Job-ocean--
for ID in e45b7148-1eaf-41d9-b867-396867dcceda 1b259789-6a30-4bb2-b86b-5a4c6b690b06; do
  SHORT=${ID%%-*}
  zstd -d -c "$BASE/session-$ID/session.v4.jsonl.zstd" > "ai/sessions/dsh-session-$SHORT.jsonl"
  cp "$BASE/session-$ID/session.v4.jsonl.zstd" "ai/sessions/dsh-session-$SHORT.native.jsonl.zstd"
done
```

The log is append-only JSONL: one event per line, with `seq` and epoch-millisecond `time`
fields. Relevant event types:

```bash
jq -r '.type' ai/sessions/dsh-session-e45b7148.jsonl | sort | uniq -c | sort -rn
```

## Reading the log

```bash
# user prompts
jq -c 'select(.type=="user/message") | [.data.content[].text]' ai/sessions/dsh-session-e45b7148.jsonl

# tool calls with their arguments (file edits, shell commands, ...)
jq -c 'select(.type=="tool/call") | {time, tool: .data.name, args: .data.arguments}' \
  ai/sessions/dsh-session-e45b7148.jsonl | head

# tool names and how often they were used
jq -r 'select(.type=="tool/call") | .data.name' \
  ai/sessions/dsh-session-e45b7148.jsonl | sort | uniq -c | sort -rn
```

No credentials or private third-party data are present, so no redactions were applied.
