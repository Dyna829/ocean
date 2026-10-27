# AI session evidence

One AI session produced this submission: a DeepSeek Harness (DSH) session using the
`deepseek-flash` model on 2026-10-27, 12:24–13:00 (Asia/Singapore).

| File | What it is |
|---|---|
| `dsh-session-e45b7148.native.jsonl.zstd` | untouched session log written by DSH |
| `dsh-session-e45b7148.jsonl` | same log, decompressed for review |
| `session-index.csv` | one row per session: model, window, export, purpose, commits |
| `decision-log.md` | accepted / corrected / tradeoff decisions with evidence |
| `completeness-declaration.md` | tools used, export limitations, Section 6 boundary |

## How the export was produced

DSH keeps sessions under `~/.dsh/sessions/<workspace>/<session-id>/session.v4.jsonl.zstd`.
The decompressed copy was produced with:

```bash
SESSION=~/.dsh/sessions/--Users-dyna-Documents-Job-ocean--/session-e45b7148-1eaf-41d9-b867-396867dcceda
zstd -d -c "$SESSION/session.v4.jsonl.zstd" > ai/sessions/dsh-session-e45b7148.jsonl
cp "$SESSION/session.v4.jsonl.zstd" ai/sessions/dsh-session-e45b7148.native.jsonl.zstd
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
