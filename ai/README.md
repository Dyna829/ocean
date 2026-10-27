# AI session evidence

Five AI sessions produced this submission, on 2026-10-27 (Asia/Singapore, +08:00), across
two tools.

**DeepSeek Harness (DSH)**, model `deepseek-flash` — the build itself:

| File | What it is |
|---|---|
| `dsh-session-e45b7148.native.jsonl.zstd` | main session, untouched log written by DSH |
| `dsh-session-e45b7148.jsonl` | main session, decompressed for review |
| `dsh-session-1b259789.native.jsonl.zstd` | follow-up review session, untouched log |
| `dsh-session-1b259789.jsonl` | follow-up review session, decompressed |
| `dsh-session-d220c9f4.native.jsonl.zstd` | final packaging session, untouched log |
| `dsh-session-d220c9f4.jsonl` | final packaging session, decompressed |

**MiniMax Code**, model `minimax/MiniMax-M3.1-Flash` — an independent review of the finished
submission and the final evidence refresh:

| File | What it is |
|---|---|
| `mavis-session-0440be7b.native.jsonl` | candidate review session (12:57–13:19), native message log |
| `mavis-session-0440be7b.llm-call.json` | the request record for that session: model, system prompt, tool schemas |
| `mavis-session-0440be7b.manifest.json` | session manifest written by the runtime |
| `mavis-session-0440be7b.runtime.log` | the runtime's own activity log (permission decisions, task lifecycle) |
| `mavis-session-06fd271c.native.jsonl` | evidence-refresh session (13:30–, still open at packaging), native message log |
| `mavis-session-06fd271c.llm-call.json` | the request record for that session |
| `mavis-session-06fd271c.manifest.json` | session manifest written by the runtime |
| `mavis-session-06fd271c.runtime.log` | the runtime's own activity log |

| File | What it is |
|---|---|
| `session-index.csv` | one row per session: model, window, export, purpose, commits |
| `decision-log.md` | accepted / corrected / tradeoff decisions with evidence |
| `completeness-declaration.md` | tools used, export limitations, Section 6 boundary |

## How the DSH export was produced

DSH keeps sessions under `~/.dsh/sessions/<workspace>/<session-id>/session.v4.jsonl.zstd`.
The decompressed copy was produced with:

```bash
BASE=~/.dsh/sessions/--Users-dyna-Documents-Job-ocean--
for ID in e45b7148-1eaf-41d9-b867-396867dcceda 1b259789-6a30-4bb2-b86b-5a4c6b690b06 d220c9f4-8fb6-46a0-bb0e-1a92b104b7ac; do
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

## How the MiniMax Code export was produced

MiniMax Code keeps sessions under `~/.minimax/v2/sessions/<YYYY>/<MM>/<DD>/`, one directory
per session, named `<HH-MM-SS-mmm>-session_<base64(session-id)>`:

```bash
BASE=~/.minimax/v2/sessions/2026/10/27
for D in 04-57-34-937-session_bXZzXzA0NDBiZTdiYWQ1MTQyMzRhNzBkYWUwYTQ5ZjgyZmM4 \
         05-30-39-500-session_bXZzXzA2ZmQyNzFjNDNlYzQ1YTg5MTkzOWRlN2ZhZTI0Y2U1; do
  SHORT=$(echo "$D" | sed -E 's/.*session_bXZzXz([A-Za-z0-9]{8}).*/\1/')
  cp "$BASE/$D/messages.jsonl" "ai/sessions/mavis-session-$SHORT.native.jsonl"
  cp "$BASE/$D/llm-call.json"  "ai/sessions/mavis-session-$SHORT.llm-call.json"
  cp "$BASE/$D/manifest.json"  "ai/sessions/mavis-session-$SHORT.manifest.json"
done
```

The runtime's own activity log lives beside the session metadata and is copied as
`mavis-session-<short>.runtime.log`:

```bash
cp ~/.minimax/v2/observability/logs/sessions/mvs_<session-id>/runtime-10-27.log \
   ai/sessions/mavis-session-<short>.runtime.log
```

Unlike DSH, MiniMax Code does not compress the session log, so the `.native.jsonl` file is
already the untouched record and no second "decompressed for review" copy exists. Every copy
was verified with `sha256sum` against its source.

## Reading the DSH log

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

## Reading the MiniMax Code log

The message log is also JSONL, one message per line, with `message_id`, `turn_id`, and a
`message` object holding `role`, `content[]`, `timestamp`, and — for assistant turns —
`model`, `provider`, `responseId`, `usage`, and `stopReason`.

```bash
# user prompts (strip the injected system reminders)
jq -r 'select(.message.role=="user") | .message.content[]? | select(.type=="text") | .text' \
  ai/sessions/mavis-session-0440be7b.native.jsonl

# assistant replies
jq -r 'select(.message.role=="assistant") | .message.content[]? | select(.type=="text") | .text' \
  ai/sessions/mavis-session-0440be7b.native.jsonl

# tool calls with their arguments
jq -c '.message.content[]? | select(.type=="toolCall") | {name, args: .arguments}' \
  ai/sessions/mavis-session-0440be7b.native.jsonl | head

# tool results, and the ones that failed
jq -r 'select(.message.role=="toolResult") | [.message.toolName, .message.isError] | @tsv' \
  ai/sessions/mavis-session-0440be7b.native.jsonl | sort | uniq -c | sort -rn

# the model identifier and the turn window
jq -r 'select(.message.model) | [.message.provider, .message.model] | @tsv' \
  ai/sessions/mavis-session-0440be7b.native.jsonl | sort -u
```

No credentials or private third-party data are present in either tool's export, so no
redactions were applied.
