# AGENTS.md — build guide for AI assistants / AI 助手构建指南

This file is the operating guide for anyone—human or AI—changing this repository. It is
maintained in English and Chinese; keep both languages in sync. Read it before editing,
and update it together with `README.md` and `DESIGN.md` when behaviour changes.
本文件是任何人类或 AI 修改本仓库时的操作指南，以中英双语维护；修改时请同步更新两种语言。
编辑前先读本文件；行为变化时与 `README.md`、`DESIGN.md` 一起更新。

Source requirements: `docs/briefing.pdf`. The repository is a working reference
implementation, not a greenfield scaffold.
原始需求见 `docs/briefing.pdf`；本仓库是可运行的参考实现，不是空脚手架。

## 1. Project / 项目

**EN.** An internal admin console for a multi-tenant training platform. Tenant admins
review course completions, issue certificates in bulk, revoke them with an audit trail, and
export certificate data as CSV. It runs as one Python process with SQLite and a React SPA,
and must stay small, correct, and runnable with one command.

**中文。** 一个面向多租户培训平台的内部管理控制台。租户管理员查看课程完成情况、批量签发证书、
撤销证书并保留审计记录、导出证书 CSV。系统以单 Python 进程 + SQLite + React SPA 运行，
要求小而正确、一条命令即可启动。

**Current verification / 当前验证：** `./verify.sh` → **17 passed** (A1–A7 + reason-hash +
logging) plus `tsc --noEmit`.

## 2. Scope / 范围

### 2.1 In scope / 范围内

**EN**

- Certificate list: search by learner name or serial number, paginate, sort; real loading,
  empty, and error states.
- Bulk issue: pick a course, issue to eligible learners, per-learner
  `issued` / `skipped` / `failed`, duplicate UI submission disabled.
- Detail: serial, course, learner, tenant-local issue date, status; revocation with explicit
  confirmation; audit for issuance and revocation.
- CSV export: learner name, course title, serial number, tenant-local issue date; preserves
  the current search and sort; handles 100,000 rows.
- Demo data, seeded admins/tenants, logging, and the acceptance tests.

**中文**

- 证书列表：按学员姓名或证书编号搜索、分页、排序；真实覆盖加载中、空列表、错误三态。
- 批量签发：选择课程，向符合条件的学习者签发，逐人返回 `issued` / `skipped` / `failed`，
  前端禁止重复提交。
- 证书详情：编号、课程、学员、租户本地签发日期、状态；撤销需二次确认；签发与撤销都写审计。
- CSV 导出：学员姓名、课程名称、证书编号、租户本地签发日期；保留当前搜索与排序；支持 10 万行。
- 演示数据、seed 的 admin/tenant、日志与验收测试。

### 2.2 Out of scope / 范围外

**EN**

- Production authentication, cloud deployment, notifications, unrelated admin features.
- Visual polish that costs core correctness.
- Not required: async/queue-based bulk issue, keyset pagination for the list, automated UI
  tests, rate limiting, CSV formula-injection hardening, audit retention, i18n, mobile,
  tenant-timezone editing.

**中文**

- 生产级鉴权、云部署、通知、与本流程无关的管理功能。
- 以牺牲核心正确性为代价的视觉打磨。
- 非必需：异步/队列化批量签发、列表 keyset 分页、UI 自动化测试、限流、CSV 公式注入防护、
  审计保留策略、国际化、移动端、租户时区编辑。

## 3. Functionality / 功能

### 3.1 Actors, tenants, demo data / 角色、租户、演示数据

| Actor / 角色 | Email | Tenant / 租户 | Timezone / 时区 |
|---|---|---|---|
| Alice Chen | `alice@east.test` | East Campus (`tenant_east`) | `Australia/Sydney` |
| Bob Miller | `bob@west.test` | West Campus (`tenant_west`) | `Australia/Perth` |

- There is **no login UI**. The actor is identified by the `X-Actor-Email` header; the
  server resolves the `admins` row and derives the tenant from it. The console has an
  “Acting as” switcher; the choice is stored in `localStorage`.
  没有登录 UI。操作者由 `X-Actor-Email` 请求头识别；服务端解析 `admins` 行并据此确定租户。
  控制台有“Acting as”切换器，选择结果存于 `localStorage`。
- Both tenants contain **Safety 101** and **Alex Lee**. East has 13 seeded certificates
  (including Hazard Reporting’s 10 for pagination); West has 1. Both include completed,
  incomplete, and already-certified enrollments.
  两个租户都有 **Safety 101** 与 **Alex Lee**。East 预置 13 张证书（含 Hazard Reporting
  的 10 张用于分页）；West 预置 1 张。两边都覆盖 completed、incomplete、已认证三种情况。
- Seed: `python -m app.seed --reset` or `./start.sh --reset`. The 100k dataset is a
  **separate** database (`data/large.db`), never the default quick-start DB.
  演示数据：`python -m app.seed --reset` 或 `./start.sh --reset`。10 万行数据写入
  **独立**数据库（`data/large.db`），绝不改动默认快速启动库。
- `GET /api/me` returns `{actor, tenant}`; `GET /api/courses` returns per-course
  `completed`, `incomplete`, `certified`, `eligible` counts, scoped to the actor’s tenant.
  `GET /api/me` 返回 `{actor, tenant}`；`GET /api/courses` 返回当前租户每门课的
  `completed`、`incomplete`、`certified`、`eligible` 计数。

Boundary: the actor header is a demo affordance and can be spoofed; this is **by design**
(no production auth). The tenant is never accepted from the client.
边界：actor 请求头是演示用途，可被伪造；这是**有意为之**（不做生产鉴权）。租户绝不从客户端接收。

### 3.2 Certificate list / 证书列表

**Endpoint / 接口**

`GET /api/certificates?q=&page=1&pageSize=20&sort=issued_date&dir=desc`

| Param / 参数 | Rules / 规则 |
|---|---|
| `q` | Learner name or serial substring; max 100 chars; `%`, `_`, `\` are escaped literally |
| `page` | Integer ≥ 1 |
| `pageSize` | Integer 1–100 |
| `sort` | `issued_date`, `learner_name`, `course_title`, `serial` |
| `dir` | `asc`, `desc` |

- Response: `items[]`, `page`, `pageSize`, `total`, `totalPages`, `sort`, `dir`, `q`,
  `tenant`. Each item has `id`, `serial`, `courseId`, `courseTitle`, `learnerId`,
  `learnerName`, `status`, `issuedAt` (UTC), `issuedAtLocal`, `issueDateLocal`, `revokedAt`,
  `revokedAtLocal`, `revokedBy`.
  响应包含 `items[]`、`page`、`pageSize`、`total`、`totalPages`、`sort`、`dir`、`q`、`tenant`；
  每项含上述字段。
- Sorting is total: the requested key, then `id`. `learner_name` / `course_title` use
  `COLLATE NOCASE`; `serial` is binary. `issued_date` sorts by `issued_at` (UTC instant),
  which preserves tenant-local date order for a fixed tenant timezone. The date shown in the
  UI and CSV comes from the persisted `issue_date_local`.
  排序是全序：先请求字段，再 `id`。`learner_name` / `course_title` 使用 `COLLATE NOCASE`；
  `serial` 按二进制。`issued_date` 按 `issued_at`（UTC 时刻）排序；在租户时区固定的前提下，
  这与租户本地日期顺序一致。界面与 CSV 中的日期取签发时落库的 `issue_date_local`。
- UI: debounced search, sortable columns, page-size selector, loading/empty/error states;
  actor switch clears the open detail/bulk dialog and refetches the list with the current
  q/sort/page. Search is ASCII case-insensitive via SQLite `LIKE`.
  界面：防抖搜索、可排序表头、页大小选择、加载/空/错误三态；切换 actor 会清除打开的
  详情/批量对话框，并用当前 q/sort/page 重新拉取列表；搜索通过 SQLite `LIKE` 做 ASCII
  大小写不敏感匹配。

**Boundaries / 边界**

- `%`/`_`/`\` are escaped, so they match literally (verified: all return 0 rows).
  `%`/`_`/`\` 会被转义，按字面匹配（已验证：均返回 0 行）。
- Invalid `page`, `pageSize`, `sort`, `dir`, or `q > 100` → 422; a page past the end returns
  200 with empty `items` and the correct `total`.
  非法 `page`、`pageSize`、`sort`、`dir` 或 `q > 100` → 422；页码越界返回 200、空 `items`，
  `total` 仍正确。
- OFFSET pagination: deep pages are fast at 100k but grow with offset; keyset pagination is
  the next step for very large offsets.
  OFFSET 分页：10 万行时深页仍快，但随 offset 增长；超大 offset 的下一步是 keyset 分页。
- Non-ASCII case folding is not supported by SQLite `LIKE` (documented known defect).
  SQLite `LIKE` 不支持非 ASCII 大小写折叠（已记录的已知缺陷）。

### 3.3 Bulk issue / 批量签发

**Endpoint / 接口**

`POST /api/certificates/bulk-issue` with `Idempotency-Key` header and body
`{"courseId": "...", "reason": "optional"}`.

- `courseId` max 100, `reason` max 200; blank/whitespace reason is treated as no reason.
  `courseId` 最长 100，`reason` 最长 200；空白 reason 视为无 reason。
- Eligibility: enrollment `COMPLETED` and no existing certificate for that
  `(tenant, course, learner)`. Incomplete enrollments are skipped with
  `incomplete_enrollment`; existing certificates are skipped with `already_certified`.
  资格：enrollment 为 `COMPLETED`，且该 `(tenant, course, learner)` 尚无证书。
  incomplete 以 `incomplete_enrollment` 跳过；已有证书以 `already_certified` 跳过。
- The response has `operationId`, `courseId`, `courseTitle`, `tenant`,
  `summary {total, issued, skipped, failed}`, and `outcomes[]` with `learnerId`,
  `learnerName`, `status`, `reason`, `message`, plus `certificateId`/`serial` for issued.
  响应含 `operationId`、`courseId`、`courseTitle`、`tenant`、
  `summary {total, issued, skipped, failed}`，以及逐人 `outcomes[]`（`learnerId`、
  `learnerName`、`status`、`reason`、`message`；issued 额外有 `certificateId`/`serial`）。

**Idempotency / 幂等**

- Key is required (400 `idempotency_key_required` if missing/blank; 400
  `idempotency_key_invalid` if > 200 chars).
  必须提供 key（缺失/空白 → 400 `idempotency_key_required`；超过 200 字符 → 400
  `idempotency_key_invalid`）。
- Same key + same request hash (courseId + trimmed reason) replays the stored response
  verbatim; `Idempotency-Replayed: true`. Same key + different payload → 409
  `idempotency_key_reuse`, no writes.
  同一 key + 同一请求哈希（courseId + trim 后的 reason）原样重放已存响应；
  `Idempotency-Replayed: true`。同一 key + 不同 payload → 409 `idempotency_key_reuse`，不写数据。
- The key row, certificates, audits, and stored response commit in one
  `BEGIN IMMEDIATE` transaction. A replay after a crash/timeout sees the committed row.
  key 行、证书、审计与响应存储在同一 `BEGIN IMMEDIATE` 事务中提交；崩溃/超时后的重试
  会看到已提交的行。
- Each eligible learner is issued inside a `SAVEPOINT`. On `IntegrityError`/`OperationalError`
  that learner gets `failed` (`integrity_conflict`) and the others still commit; this is why
  the response can mix `issued` and `failed`.
  每个符合条件的学习者在一个 `SAVEPOINT` 中签发。遇到 `IntegrityError`/`OperationalError`
  时该人记为 `failed`（`integrity_conflict`），其余人继续提交；因此响应可以同时含
  `issued` 与 `failed`。

**UI / 界面**

- Course picker shows eligibility counts. A `crypto.randomUUID()` key is created when the
  dialog opens, when the course changes, and when `New operation` is clicked; a retry after
  a transport error reuses the current key. The submit button is disabled while in flight;
  per-learner outcome table and summary chips.
  课程选择器显示可签发人数。对话框打开、切换课程或点击 `New operation` 时生成新的
  `crypto.randomUUID()` key；传输错误后的重试复用当前 key。请求期间禁用提交；展示逐人
  结果表与汇总。
- Failure surfaces as an error banner/toast; retries reuse the key unless the user starts a
  new operation. 失败以错误条/提示展示；除非用户开始新操作，否则重试复用同一 key。

**Boundaries / 边界**

- 50k eligible learners take about 4 s and produce an ~8.6 MB JSON response; a second bulk
  issue or a revocation waits for the write lock (measured ~3.7 s during a 50k issue).
  5 万符合条件的学习者约 4 秒，响应约 8.6 MB；第二个 bulk issue 或撤销会等待写锁
  （实测 5 万签发期间撤销等待约 3.7 秒）。
- Cross-tenant `courseId` → 404 `course_not_found`, no certificates/audits.
  跨租户 `courseId` → 404 `course_not_found`，不写证书/审计。
- A `409 idempotency_key_in_progress` branch exists for a future async implementation; today
  the key row is only written as `SUCCEEDED` inside the same transaction, so it is
  unreachable by construction.
  为未来的异步实现保留了 `409 idempotency_key_in_progress` 分支；当前 key 行只在同一事务内
  以 `SUCCEEDED` 写入，因此该分支在构造上不可达。

### 3.4 Detail and revocation / 详情与撤销

- `GET /api/certificates/{id}` returns `{certificate, audit}`; the certificate has the same
  fields as a list item plus the audit timeline (`action`, `actor`, `at`, `atLocal`,
  `detail`). Cross-tenant or missing → 404 `certificate_not_found`, indistinguishable.
  `GET /api/certificates/{id}` 返回 `{certificate, audit}`；证书字段同列表项，另含审计时间线
  （`action`、`actor`、`at`、`atLocal`、`detail`）。跨租户或不存在 → 404
  `certificate_not_found`，两者不可区分。
- `POST /api/certificates/{id}/revoke` accepts optional `{"reason": "..."}` (max 200).
  The first call flips `ACTIVE` → `REVOKED` and writes exactly one `REVOKED` audit row; a
  repeat returns the same detail with `alreadyRevoked: true` and writes no second audit.
  `POST /api/certificates/{id}/revoke` 接受可选 `{"reason": "..."}`（最长 200）。
  首次调用把 `ACTIVE` 改为 `REVOKED` 并恰好写一条 `REVOKED` 审计；重复调用返回同一详情，
  `alreadyRevoked: true`，不再写审计。
- The UI requires an explicit confirmation step before revoking and shows the audit timeline.
  界面撤销前要求显式确认，并展示审计时间线。
- `409 revocation_conflict` exists for a concurrent state change (`UPDATE ... WHERE
  status='ACTIVE'` affecting 0 rows); in practice the `BEGIN IMMEDIATE` write lock makes it
  unreachable, but it is kept as a guard.
  `409 revocation_conflict` 用于并发状态变化（`UPDATE ... WHERE status='ACTIVE'` 影响 0 行）；
  实际上 `BEGIN IMMEDIATE` 写锁使其不可达，但保留作为防御。
- Revoked certificates cannot be reissued: the unique
  `(tenant_id, course_id, learner_id)` constraint keeps one credential per learner/course.
  已撤销证书不能重发：唯一约束 `(tenant_id, course_id, learner_id)` 保证每人每课一张证书。

### 3.5 CSV export / CSV 导出

**Endpoint / 接口**

`GET /api/certificates/export.csv?q=&sort=&dir=`

- Columns: `learner_name,course_title,serial_number,issue_date` (CRLF, UTF-8, no BOM).
  列：`learner_name,course_title,serial_number,issue_date`（CRLF、UTF-8、无 BOM）。
- `issue_date` is the persisted `issue_date_local`; search and sort are preserved.
  `issue_date` 取落库的 `issue_date_local`；保留当前搜索与排序。
- Streams in 2,000-row keyset batches, bounded by a `max(seq)` horizon captured at the start;
  the event loop is not blocked. No whole-file buffering.
  以 2,000 行 keyset 分批流式输出，起始时捕获 `max(seq)` 作为 horizon；不阻塞事件循环，
  不整体缓冲。
- `Content-Type: text/csv; charset=utf-8`; `Content-Disposition: attachment;
  filename="certificates-<tenant>-<YYYYMMDD>.csv"`; `Cache-Control: no-store`;
  `X-Content-Type-Options: nosniff`.
  响应头同上。
- Fields containing comma, quote, CR/LF are RFC-4180 quoted; quotes are doubled.
  含逗号、引号、CR/LF 的字段按 RFC 4180 加引号；引号翻倍。

**Boundaries / 边界**

- 100,000 rows in **under 60 s** (measured ~0.24 s) while a list request stays responsive
  (measured ~4 ms); 1M rows measured ~3.62 s, ~70 MB, ~3.5 MB peak memory.
  10 万行 **60 秒内**（实测约 0.24 秒），导出期间列表仍可用（实测约 4 毫秒）；100 万行实测
  约 3.62 秒、约 70 MB、峰值内存约 3.5 MB。
- Ties on the requested sort key are ordered by `id`, so repeated exports are byte-identical
  while the data is unchanged. 0 matching rows produce the header only.
  指定排序键并列时按 `id` 排序，因此数据不变时重复导出逐字节一致；0 匹配行时只输出表头。
- **Not a full MVCC snapshot.** The `max(seq)` horizon hides certificates issued after the
  export starts; a revocation committed between batches can still appear in a later batch.
  **不是完整 MVCC 快照。** `max(seq)` horizon 隐藏导出开始后新签发的证书；但批次之间提交的
  撤销仍可能出现在后续批次。
- Formula prefixes (`=`, `+`, `-`, `@`) are **not** neutralized; this is a known hardening
  gap, not a PDF requirement. 公式前缀（`=`, `+`, `-`, `@`）**未**做中性化；这是已知加固缺口，
  不是 PDF 要求。
- A zero-row export is `200` with only the header; an invalid `sort`/`dir` is `422`.
  0 行导出为 200 + 仅表头；非法 `sort`/`dir` 为 422。

### 3.6 API surface / 接口一览

| Method | Path | Auth / 鉴权 | Purpose / 用途 |
|---|---|---|---|
| `GET` | `/api/health` | no / 否 | Liveness + DB check / 存活与数据库检查 |
| `GET` | `/api/me` | yes | Current actor + tenant / 当前操作者与租户 |
| `GET` | `/api/courses` | yes | Courses with eligibility counts / 课程与资格计数 |
| `GET` | `/api/certificates` | yes | Search, paginate, sort / 搜索、分页、排序 |
| `GET` | `/api/certificates/export.csv` | yes | Streamed CSV / 流式 CSV |
| `GET` | `/api/certificates/{id}` | yes | Detail + audit / 详情与审计 |
| `POST` | `/api/certificates/{id}/revoke` | yes | Idempotent revocation / 幂等撤销 |
| `POST` | `/api/certificates/bulk-issue` | yes | Idempotent bulk issuance / 幂等批量签发 |

`/api/docs` and `/api/openapi.json` are FastAPI’s generated docs, not product endpoints.
`/api/docs` 与 `/api/openapi.json` 是 FastAPI 生成的文档，不是产品接口。

### 3.7 Error contract / 错误契约

The envelope for **defined** API errors is `{code, message, details?}`. `details` is omitted
when empty; `422` includes `details.errors`. Unknown `/api/*` routes fall through to
FastAPI’s default 404 body `{"detail":"Not Found"}` — a known envelope exception, not a PDF
requirement. Unhandled exceptions return `500 {code:"internal_error", message:"Internal
server error"}`.
**已定义** API 错误的 envelope 为 `{code, message, details?}`；`details` 为空时省略；
`422` 含 `details.errors`。未知 `/api/*` 路由落到 FastAPI 默认 404
`{"detail":"Not Found"}`——这是已知的 envelope 例外，不是 PDF 要求。未捕获异常返回
`500 {code:"internal_error", message:"Internal server error"}`。

| Status | Code | When / 触发条件 |
|---|---|---|
| 400 | `idempotency_key_required` | Missing/blank `Idempotency-Key` / 缺失或空白 key |
| 400 | `idempotency_key_invalid` | Key longer than 200 / key 超过 200 |
| 401 | `unauthenticated` | Missing/unknown actor / 缺失或未知 actor |
| 404 | `certificate_not_found` | Missing or cross-tenant certificate / 不存在或跨租户证书 |
| 404 | `course_not_found` | Missing or cross-tenant course / 不存在或跨租户课程 |
| 409 | `idempotency_key_reuse` | Same key, different payload / 同 key 不同 payload |
| 409 | `idempotency_key_in_progress` | Reserved for async; unreachable today / 为异步保留，当前不可达 |
| 409 | `revocation_conflict` | Concurrent state change; guarded, practically unreachable / 并发状态变化；有防御，实际不可达 |
| 422 | `validation_error` | Pydantic validation / 参数校验失败 |
| 500 | `internal_error` | Unhandled exception / 未捕获异常 |

### 3.8 UI states / 界面状态

- List: explicit loading skeleton, empty state, and error banner with retry. The error state
  is also used when `/api/me` fails.
  列表：明确的加载骨架、空状态、带重试的错误条；`/api/me` 失败时也进入错误态。
- Bulk issue: dialog-level pending state, disabled submit, per-learner outcomes, summary
  chips, and toast/banner on failure.
  批量签发：对话框级 pending、禁用提交、逐人结果、汇总标签，失败时 toast/错误条。
- Revocation: explicit confirmation; cancel performs no write.
  撤销：显式确认；取消不写数据。
- Actor switch: stored in `localStorage`, aborts in-flight `/me` and list requests; stale
  responses are ignored via `AbortController`.
  actor 切换：存于 `localStorage`，中止进行中的 `/me` 与列表请求；通过 `AbortController`
  忽略过期响应。
- No client-side router: the console is a single page. Unknown non-API paths return 404
  JSON, not SPA HTML.
  无客户端路由：控制台是单页。未知非 API 路径返回 404 JSON，而非 SPA HTML。

## 4. Architecture / 代码架构

### 4.1 Repository layout / 目录结构

| Path / 路径 | EN | 中文 |
|---|---|---|
| `app/` | FastAPI application | FastAPI 应用 |
| `app/schema.sql` | DDL, indices, constraints | 建表、索引、约束 |
| `app/db.py` | Thread-local SQLite connections, WAL, `BEGIN IMMEDIATE` helper | 线程局部 SQLite 连接、WAL、`BEGIN IMMEDIATE` 辅助 |
| `app/auth.py` | `X-Actor-Email` → actor + tenant | 头部 → 操作者与租户 |
| `app/routers/api.py` | HTTP endpoints, validation, CSV stream | HTTP 接口、校验、CSV 流 |
| `app/services/certificates.py` | Listing, detail, bulk issue, revocation, export queries | 列表、详情、批量签发、撤销、导出查询 |
| `app/seed.py` | Deterministic demo data | 确定性演示数据 |
| `app/bulkdata.py` | 100k fixture generator | 10 万行夹具生成器 |
| `app/logging.py` | Formatters, levels, request-id context | 格式化、级别、request-id 上下文 |
| `app/middleware.py` | One structured request line, 500 handling | 每请求一条结构化日志、500 处理 |
| `app/timeutil.py` | UTC parsing/formatting, tenant-local date/display | UTC 解析/格式化、租户本地日期/展示 |
| `web/src/` | React 19 + TypeScript SPA | React 19 + TypeScript 单页应用 |
| `tests/` | A1–A7 + logging pytest suites | A1–A7 与日志 pytest 套件 |
| `scripts/generate_large.py` | 100k-row database generator | 10 万行数据库生成器 |
| `docs/` | Briefing and screenshots | 需求 PDF 与截图 |
| `ai/` | AI interaction evidence (not runtime code) | AI 交互证据（非运行时代码） |
| `start.sh` | One-command install/build/seed/serve | 一键安装/构建/seed/启动 |
| `verify.sh` | Pytest + TypeScript typecheck | pytest + TypeScript 类型检查 |

### 4.2 Request flow / 请求流程

**EN.** Uvicorn → `app.asgi:app` → `create_app` → `RequestLogMiddleware` → `/api` router →
`get_actor` (header → admin → tenant) → service function → SQLite. Sync endpoints run in
FastAPI’s worker thread pool; `Database` gives each thread its own SQLite connection (WAL,
`busy_timeout=30000`, `foreign_keys=ON`). Writes use `BEGIN IMMEDIATE`. CSV export runs
per-batch queries via `anyio.to_thread.run_sync`, so the event loop stays responsive. The SPA
in `web/dist` is mounted at `/`; API routes are registered first. No CORS; one origin.

**中文。** Uvicorn → `app.asgi:app` → `create_app` → `RequestLogMiddleware` → `/api` 路由 →
`get_actor`（header → admin → tenant）→ service → SQLite。同步接口运行在 FastAPI 工作线程池；
`Database` 为每个线程提供独立 SQLite 连接（WAL、`busy_timeout=30000`、`foreign_keys=ON`）。
写操作使用 `BEGIN IMMEDIATE`。CSV 导出通过 `anyio.to_thread.run_sync` 逐批查询，事件循环不被阻塞。
`web/dist` 的 SPA 挂载在 `/`，API 路由先注册。无 CORS，单源。

### 4.3 Data model / 数据模型

| Table / 表 | Purpose / 用途 | Key constraints / 关键约束 |
|---|---|---|
| `tenants` | Tenant + IANA timezone | `slug` unique / `slug` 唯一 |
| `admins` | One admin per tenant; actor identity | `email` unique / `email` 唯一 |
| `courses` | Tenant courses | `(tenant_id, id)` unique / 唯一 |
| `learners` | Tenant learners | `(tenant_id, id)` unique / 唯一 |
| `enrollments` | Course/learner status (`COMPLETED`/`INCOMPLETE`) | `(course_id, learner_id)` unique; tenant FKs / 唯一；租户外键 |
| `certificates` | Issued credential + name snapshots | `(tenant_id, id)`, `(tenant_id, serial)`, `(tenant_id, seq)`, `(tenant_id, course_id, learner_id)` unique / 唯一 |
| `audit_events` | `ISSUED` / `REVOKED` events | unique `(certificate_id, action)` / 唯一 |
| `idempotency_keys` | Key → hash, status, stored response | PK `(tenant_id, key)` / 主键 |
| `counters` | Per-tenant certificate sequence | PK `(tenant_id, name)` / 主键 |

- `certificates.issue_date_local` is persisted at issuance; `issued_at` is UTC
  `YYYY-MM-DDTHH:MM:SSZ`; `learner_name` / `course_title` are snapshots so a later rename
  does not rewrite history.
  `certificates.issue_date_local` 在签发时落库；`issued_at` 为 UTC
  `YYYY-MM-DDTHH:MM:SSZ`；`learner_name` / `course_title` 是快照，后续改名不会改写历史。
- Indexes support the four sort keys and export keyset: `(tenant_id, learner_name
  COLLATE NOCASE, id)`, `(tenant_id, course_title COLLATE NOCASE, id)`,
  `(tenant_id, issued_at, id)`, `(tenant_id, serial)`, `(tenant_id, status)`.
  索引支撑四种排序与导出 keyset（见上）。

### 4.4 Backend modules / 后端模块

| Module / 模块 | Responsibility / 职责 |
|---|---|
| `app/asgi.py` | ASGI entrypoint (`uvicorn app.asgi:app`) / ASGI 入口 |
| `app/main.py` | App factory, exception handlers, static mount, startup log / 应用工厂、异常处理、静态挂载、启动日志 |
| `app/config.py` | `BASE_DIR`, `WEB_DIST`, `DB_PATH` resolution / 路径解析 |
| `app/db.py` | Thread-local connection, schema init, `write()` transaction / 线程局部连接、建表、写事务 |
| `app/auth.py` | Header normalization (`strip().lower()`), admin/tenant lookup / 头部归一化、admin/租户查询 |
| `app/errors.py` | `ApiError` envelope / 错误 envelope |
| `app/timeutil.py` | `iso_utc`, `parse_utc`, `local_display`, `local_date` / UTC 与本地日期 |
| `app/routers/api.py` | FastAPI routes, Pydantic models, CSV `StreamingResponse` / 路由、模型、CSV 流 |
| `app/services/certificates.py` | Query/write/export logic, `_escape_like`, `_order_by`, `export_batch`, `csv_cell` / 查询/写入/导出逻辑 |
| `app/seed.py` | Deterministic tenants/admins/courses/learners/enrollments/certificates / 演示数据 |
| `app/bulkdata.py` | Insert N certificates for one tenant / 批量插入证书 |

### 4.5 Frontend / 前端

| File / 文件 | Responsibility / 职责 |
|---|---|
| `web/src/App.tsx` | Page state: actor, list, sort, page, detail, bulk dialog, export, toast / 页面状态 |
| `web/src/api.ts` | Fetch wrappers, `X-Actor-Email`, `X-Request-Id`, error parsing / 请求封装、错误解析 |
| `web/src/hooks.ts` | `useDebouncedValue` and shared hooks / 防抖与共享 hook |
| `web/src/log.ts` | Four-level client logger (`debug`/`info`/`warn`/`error`) / 四级前端日志 |
| `web/src/components/Toolbar.tsx` | Search, sort, page size, export, bulk trigger / 搜索、排序、导出、批量入口 |
| `web/src/components/CertificateTable.tsx` | Table, sort indicators, loading/empty/error rendering / 表格与三态 |
| `web/src/components/DetailDrawer.tsx` | Detail + audit + revoke confirmation / 详情、审计、撤销确认 |
| `web/src/components/BulkIssueDialog.tsx` | Course picker, pending state, outcomes / 课程选择、pending、结果 |
| `web/src/components/Pagination.tsx` | Page controls / 分页控件 |
| `web/src/components/Banner.tsx`, `StatusBadge.tsx` | Error/success banner, status badge / 错误/成功条、状态徽标 |
| `web/src/types.ts` | Shared API types / 共享 API 类型 |

Build: `npm run build` = `tsc --noEmit && vite build` → `web/dist`, served by FastAPI.
构建：`npm run build` = `tsc --noEmit && vite build` → `web/dist`，由 FastAPI 托管。

### 4.6 Tests and fixtures / 测试与夹具

- `tests/conftest.py` creates a temp SQLite DB, seeds it, and builds the app; `live_server`
  starts a real Uvicorn thread for streaming/concurrency tests.
  `tests/conftest.py` 创建临时 SQLite 库、写入 seed、构建应用；`live_server` 启动真实 Uvicorn
  线程用于流式/并发测试。
- `tests/support.py` provides `EAST`/`WEST` headers, `api()` ASGI client, count helpers, and
  CSV parsing.
  `tests/support.py` 提供 `EAST`/`WEST` 头、`api()` ASGI 客户端、计数辅助与 CSV 解析。
- A1–A7 live in `tests/test_a1_…` … `tests/test_a7_…`; `tests/test_logging.py` covers levels,
  fields, correlation, and 500 handling. A6 generates 100,000 rows in the test DB.
  A1–A7 位于 `tests/test_a1_…` 至 `tests/test_a7_…`；`tests/test_logging.py` 覆盖级别、字段、
  关联与 500。A6 在测试库生成 10 万行。

## 5. Stack and commands / 技术栈与命令

| Area / 方面 | Decision / 约定 |
|---|---|
| Backend / 后端 | Python 3.11+ · FastAPI · SQLite (WAL) · Uvicorn |
| Frontend / 前端 | React 19 · TypeScript · Vite; built to `web/dist` and served by FastAPI / 构建到 `web/dist`，由 FastAPI 托管 |
| Origin / 同源 | Single process, single origin, no CORS / 单进程单源，不引入 CORS |
| Start / 启动 | `./start.sh` installs deps, builds the SPA, seeds demo data, serves `:8000` / 安装依赖、构建前端、写入演示数据并启动 |
| Verify / 验证 | `./verify.sh` runs pytest (A1–A7 + logging) plus `tsc --noEmit` / 运行 pytest 与前端类型检查 |
| Data / 数据 | SQLite at `DB_PATH` (default `data/app.db`); `app/seed.py` seeds demo data / 默认 `data/app.db`，由 `app/seed.py` 写入演示数据 |
| Large data / 大数据 | `scripts/generate_large.py` writes a separate 100k-row database / 生成独立的 10 万行数据库 |

**Environment / 环境变量**

| Variable / 变量 | Default | Purpose / 用途 |
|---|---|---|
| `PORT` | `8000` | HTTP port / 端口 |
| `DB_PATH` | `data/app.db` | SQLite file / 数据库文件 |
| `PYTHON` | `python3` | Interpreter used to create `.venv` / 创建虚拟环境的解释器 |
| `LOG_LEVEL` | `INFO` | Backend log level / 后端日志级别 |
| `LOG_FORMAT` | `text` | `text` or `json` / 文本或 JSON |
| `LOG_SLOW_REQUEST_MS` | `2000` | Slow-request threshold / 慢请求阈值 |
| `VITE_LOG_LEVEL` | dev `debug`, prod `info` | Frontend console level / 前端控制台级别 |

```bash
./start.sh                 # http://127.0.0.1:8000
./start.sh --reset         # wipe and reseed demo data
PORT=8080 ./start.sh       # different port
DB_PATH=data/large.db ./start.sh
./verify.sh                # pytest + tsc
.venv/bin/python scripts/generate_large.py --tenant east --count 100000
```

Requirements: Python 3.11+, Node 20.19+/npm 10+ (or pnpm; not required). `start.sh` is
bash 3.2 compatible (macOS).
要求：Python 3.11+、Node 20.19+/npm 10+（pnpm 非必需）。`start.sh` 兼容 bash 3.2（macOS）。

## 6. Non-negotiable rules / 不可妥协的规则

### Tenant isolation / 租户隔离

- The tenant comes from the `admins` row resolved by `X-Actor-Email`; no endpoint accepts a
  tenant id from the client.
  租户由 `X-Actor-Email` 解析出的 `admins` 记录决定，任何接口都不接受客户端传入的租户 ID。
- Every tenant-scoped query filters on `tenant_id`; cross-tenant resources return 404,
  indistinguishable from missing ones.
  所有涉及租户的查询都带 `tenant_id`；跨租户资源返回 404，与不存在不可区分。
- Cross-tenant bulk issue/revoke/export must write nothing and reveal nothing.
  跨租户批量签发/撤销/导出不得写数据，也不得泄露存在性。

### Idempotency / 幂等

- `POST /api/certificates/bulk-issue` requires `Idempotency-Key` (max 200); the business
  write and the stored response commit in the same `BEGIN IMMEDIATE` transaction.
  批量签发必须携带 `Idempotency-Key`（最长 200）；业务写入与结果存储必须在同一个
  `BEGIN IMMEDIATE` 事务内提交。
- Same key + same payload replays the stored response verbatim for sequential and concurrent
  callers; same key + different payload returns 409 and writes nothing.
  同一 key 同一 payload 时，顺序与并发调用都原样重放已有结果；同一 key 不同 payload
  返回 409 且不写任何数据。
- The request hash covers `courseId` + trimmed `reason`; a blank reason is no reason.
  请求哈希覆盖 `courseId` + trim 后的 `reason`；空白 reason 视为无 reason。

### Time / 时间

- Store UTC (`YYYY-MM-DDTHH:MM:SSZ`); persist `issue_date_local` at issuance; derive display
  strings from the tenant’s IANA timezone.
  统一存 UTC；签发时落库 `issue_date_local`；展示串按租户 IANA 时区实时推导。
- `issued_date` sorting uses the stored UTC `issued_at`; for a fixed tenant timezone this
  preserves tenant-local date order. The CSV `issue_date` column and `issueDateLocal` use the
  persisted `issue_date_local`. If a tenant’s IANA timezone is edited outside the API, the
  derived display can diverge from the persisted date; there is no API to change it today.
  `issued_date` 排序使用存储的 UTC `issued_at`；在租户时区固定的前提下，这与租户本地日期
  顺序一致。CSV 的 `issue_date` 列与 `issueDateLocal` 使用签发时落库的 `issue_date_local`。
  如果在 API 之外修改租户 IANA 时区，推导出的展示日期可能与落库日期不一致；目前没有修改
  租户时区的 API。
- A5 fixtures: `2026-01-10T13:30:00Z` → East `2026-01-11 00:30`, West `2026-01-10 21:30`.
  A5 夹具：`2026-01-10T13:30:00Z` → East `2026-01-11 00:30`，West `2026-01-10 21:30`。

### Ordering and export / 排序与导出

- Every ordering is total: the requested sort key first, then `id`. `learner_name` /
  `course_title` use `COLLATE NOCASE`; `serial` is binary; `issued_date` uses `issued_at`.
  List and export share the same key definition, and tied rows keep the same relative order
  on repeated exports.
  所有排序都是全序：先按请求字段，再按 `id`。`learner_name` / `course_title` 使用
  `COLLATE NOCASE`；`serial` 按二进制；`issued_date` 使用 `issued_at`。列表与导出共享同一
  排序定义；重复导出时并列项相对顺序不变。
- Export streams in 2,000-row batches and is never buffered whole; 100,000 rows finish in
  under 60 s and the list endpoint stays responsive while an export is running.
  导出以 2,000 行分批流式输出，禁止整体缓冲；10 万行需在 60 秒内完成，且导出期间列表接口
  保持可用。

### Audit and integrity / 审计与完整性

- Exactly one audit event per actual issuance and per revocation; skipped/failed learners
  write no issuance audit. Revocation is idempotent.
  每次实际签发、每次撤销各恰好一条审计；跳过/失败的学习者不写签发审计；撤销幂等。
- Uniqueness is enforced by the database: `(tenant, course, learner)` and
  `(certificate, action)`, with writes in `BEGIN IMMEDIATE`.
  唯一性由数据库保证：`(tenant, course, learner)` 与 `(certificate, action)`，写操作使用
  `BEGIN IMMEDIATE`。
- A learner whose savepoint fails is reported as `failed`; other learners in the same request
  still commit. 某个学习者的 savepoint 失败时记为 `failed`；同一请求中的其他学习者仍提交。

### Errors / 错误

- Defined errors use `{code, message, details?}`; `details` is omitted when empty. See §3.7
  for codes and the unknown-route exception.
  已定义错误使用 `{code, message, details?}`；`details` 为空时省略。代码与未知路由例外见 §3.7。
- Never leak stack traces, SQL, or another tenant’s existence in an error body.
  错误体中不得泄露堆栈、SQL 或另一个租户的存在性。

### Logging / 日志

- Follow §8. No request bodies, headers, credentials, or learner names; IDs are fine.
  遵循 §8。禁止请求体、请求头、凭据或学员姓名；ID 可以。

### Scope / 范围

- Correct core behaviour before visual polish. Do not add production auth, cloud deployment,
  notifications, or unrelated admin features.
  核心正确性优先于视觉打磨。不要加入生产鉴权、云部署、通知或无关管理功能。

## 7. Boundary capabilities and limits / 边界能力与限制

### 7.1 Measured capacity / 实测容量

| Rows / 行数 | Export / 导出 | CSV size / 大小 | List during export / 导出期间列表 | Deep page / 深页 | Search / 搜索 |
|---|---|---|---|---|---|
| 100,000 | 0.24 s | 7.0 MB | 3.9 ms | 6 ms | 17 ms |
| 300,000 | 1.27 s | 21 MB | 10 ms | 15 ms | 43 ms |
| 1,000,000 | 3.62 s | 70 MB | 24 ms | 48 ms | 142 ms |

- 50,000-learner bulk issue: ~4.0 s, ~8.6 MB response; a revocation during it waited ~3.7 s.
  5 万学习者批量签发：约 4.0 秒、响应约 8.6 MB；期间撤销等待约 3.7 秒。
- Streaming memory: ~5 MB peak for 100k, ~3.5 MB for 1M (tracemalloc).
  流式内存：10 万行峰值约 5 MB，100 万行约 3.5 MB（tracemalloc）。
- A6 asserts 100k < 60 s and a successful list request during the export.
  A6 断言 10 万行 < 60 秒，且导出期间列表请求成功。

### 7.2 Known limits / 已知限制

| Limit / 限制 | EN | 中文 | Impact / 影响 |
|---|---|---|---|
| No production auth | `X-Actor-Email` is spoofable; demo affordance only | `X-Actor-Email` 可伪造，仅供演示 | Out of scope; first thing to fix for production / 范围外；生产化首要修复 |
| SQLite single writer | Concurrent bulk issues/revocations serialise on the write lock; `busy_timeout=30s` | 并发批量签发/撤销在写锁上串行；`busy_timeout=30s` | 50k issue blocks writers ~3.7 s; >30 s wait can fail / 5 万签发阻塞写约 3.7 秒；等待超 30 秒可能失败 |
| Export not full MVCC | `max(seq)` horizon hides new rows; a revocation between batches can appear | `max(seq)` horizon 隐藏新行；批次间撤销可能出现在后续批次 | Admin download acceptable; snapshot would fix / 管理下载可接受；快照可修复 |
| ASCII-only search folding | SQLite `LIKE` case-folds ASCII only | SQLite `LIKE` 仅对 ASCII 做大小写折叠 | Non-ASCII names are case-sensitive / 非 ASCII 姓名大小写敏感 |
| OFFSET pagination | Deep pages grow with offset | 深页随 offset 增长 | Fine at 100k; keyset is next / 10 万行可接受；下一步 keyset |
| No reissue | Unique `(tenant, course, learner)` keeps one credential | 唯一约束保证每人每课一张 | Documented product rule / 已记录的产品规则 |
| No automated UI tests | UI verified manually via screenshots | UI 靠截图人工验证 | Playwright is the next investment / 下一步引入 Playwright |
| Client logs console-only | No ingest/sampling/retention | 无上报/采样/保留 | A closed tab loses logs / 关闭标签页即丢日志 |
| Logs stdout only | No file sink/rotation | 仅 stdout，无文件/轮转 | Collector expected in deployment / 部署时由采集器负责 |
| 100k DB gitignored | `data/large.db` (65 MB) not committed | `data/large.db`（65 MB）不入库 | Regenerate with script / 用脚本重建 |
| No body/header size limit | 2 MB body → 422 after read; no 413; header limit is server-level | 2 MB body 读完后 422；无 413；header 限制在 server 层 | Memory/DoS hardening gap, not PDF / 内存/DoS 加固缺口，非 PDF 要求 |
| Unknown `/api/*` 404 | FastAPI default `{"detail":"Not Found"}` | FastAPI 默认 `{"detail":"Not Found"}` | Envelope inconsistency; low risk / envelope 不一致；低风险 |
| CSV formula prefixes | `=`, `+`, `-`, `@` pass through | `=`, `+`, `-`, `@` 原样输出 | Spreadsheet injection hardening gap / 表格注入加固缺口 |
| Tenant timezone edit | Display derives from current TZ; persisted date stays | 展示按当前时区推导，落库日期不变 | They can diverge; no API to edit TZ / 可能不一致；无 API 修改时区 |
| No rate limiting | Unlimited requests | 无请求限流 | Production hardening, out of scope / 生产加固，范围外 |
| No SPA deep links | Unknown non-API paths 404 JSON | 未知非 API 路径 404 JSON | Single-page console; no router / 单页控制台，无路由 |
| Empty `details` omitted | Errors without details have no `details` key | 无 details 的错误不带该键 | Slight envelope inconsistency / envelope 轻微不一致 |
| Async idempotency branch | `idempotency_key_in_progress` unreachable today | `idempotency_key_in_progress` 当前不可达 | Reserved for future async / 为未来异步保留 |
| `revocation_conflict` | Guarded but practically unreachable under write lock | 有防御，但写锁下实际不可达 | Kept as a safety net / 保留为防御 |

### 7.3 Not implemented / 未实现

- Async/queue bulk issuance; keyset pagination; UI automation; rate limiting; request-body
  caps; CSV formula-injection neutralization; audit retention; i18n; mobile; tenant-timezone
  editing; production auth/cloud/notifications.
  异步/队列化批量签发；keyset 分页；UI 自动化；限流；请求体上限；CSV 公式注入中性化；
  审计保留；国际化；移动端；租户时区编辑；生产鉴权/云/通知。

### 7.4 Boundary checks / 边界检查

| Probe / 探测 | Expected / 预期 |
|---|---|
| `?q=%25`, `?q=_`, `?q=%5C` | Literal search; 0 matches for seed data / 按字面搜索；seed 数据 0 条 |
| `?page=0`, `?pageSize=0`, `?pageSize=101`, `?sort=bad`, `?dir=bad` | 422 / 422 |
| `?page=999` | 200, `items=[]`, correct `total` / 200、空 items、total 正确 |
| Cross-tenant detail/revoke/bulk/export | 404 / non-revealing; no writes / 404、不可区分、不写数据 |
| Same key, same payload × 6 concurrent | One operation, one certificate per learner, one audit each, replay / 一个操作、每人一张、每次一条审计、重放 |
| Same key, different course/reason | 409, no writes / 409，不写数据 |
| 0-row export | Header only, 200 / 仅表头，200 |
| 100k export + concurrent list | <60 s, list succeeds, exact rows / <60 秒、列表成功、行数精确 |
| 2 MB `courseId` | 422; no crash; no explicit 413 / 422；不崩；无显式 413 |
| CSV comma/quote/newline/Unicode | Round-trips exactly / 精确往返 |
| `=1+1` learner name | Passes through (known gap) / 原样输出（已知缺口） |
| Revoke twice | One audit, `alreadyRevoked` on repeat / 一条审计，重复 `alreadyRevoked` |

## 8. Logging / 日志

**EN**

- Backend: `app/logging.py` (formatters, level from `LOG_LEVEL`, `LOG_FORMAT=json`,
  `LOG_SLOW_REQUEST_MS`), one structured line per request from `app/middleware.py`. Levels:
  `DEBUG` diagnostics, `INFO` requests/business events, `WARNING` conflicts/rejected auth/
  slow requests, `ERROR` failed work/unhandled exceptions.
- Request fields: `method`, `path`, `status`, `durationMs`, `request_id`, plus `actor` and
  `tenant` when resolved. Business events: `bulk_issue.start/replay/conflict`,
  `certificate.revoked/revoke_replay`, `export.start/done`, `auth.rejected`,
  `request.failed`.
- Frontend: `web/src/log.ts` with `debug`/`info`/`warn`/`error`; default `debug` in dev and
  `info` in production; override with `VITE_LOG_LEVEL` or `setLogLevel()`. API calls send
  `X-Request-Id` (`web-<12 hex>`) so browser and server logs correlate.
- Use `extra={"fields": {...}}` for structured data. Never log request bodies, headers,
  credentials, or learner names (IDs are fine). Admin emails are logged as actor identity.
  100k export emits one `export.done` line, not one per row.

**中文**

- 后端：`app/logging.py`（格式化、`LOG_LEVEL`、`LOG_FORMAT=json`、`LOG_SLOW_REQUEST_MS`），
  每个请求由 `app/middleware.py` 输出一条结构化日志。级别：`DEBUG` 诊断，`INFO` 请求/业务事件，
  `WARNING` 冲突/鉴权失败/慢请求，`ERROR` 失败操作/未捕获异常。
- 请求字段：`method`、`path`、`status`、`durationMs`、`request_id`，解析到 actor 时加
  `actor`/`tenant`。业务事件：`bulk_issue.start/replay/conflict`、
  `certificate.revoked/revoke_replay`、`export.start/done`、`auth.rejected`、
  `request.failed`。
- 前端：`web/src/log.ts`，级别 `debug`/`info`/`warn`/`error`；开发默认 `debug`，生产默认
  `info`；可用 `VITE_LOG_LEVEL` 或 `setLogLevel()` 覆盖。API 调用携带 `X-Request-Id`
  （`web-<12 hex>`），使浏览器与服务端日志可关联。
- 结构化字段用 `extra={"fields": {...}}`。禁止记录请求体、请求头、凭据或学员姓名（ID 可以）；
  admin 邮箱作为操作者身份记录。10 万行导出只输出一条 `export.done`，不逐行记录。

## 9. Verification / 验证

**EN**

- `./verify.sh` must pass before a commit that claims a scenario works; it runs pytest
  (A1–A7 + logging) and `tsc --noEmit`.
- A1–A7 live in `tests/test_a1_…` … `tests/test_a7_…`; manual steps are in `README.md` §5.
- Never weaken or delete a failing test. Fix the behaviour, or record the defect honestly
  under “Known defects” in `README.md`.
- The list UI must visibly cover loading, empty, and error states.
- Before submission, run the boundary probes in §7.4; for claims about 100k/1M, re-run
  `tests/test_a6_export.py` or the generator commands in §5.

**中文**

- 任何声称某场景可用的提交，必须先在 `./verify.sh` 通过；它运行 pytest（A1–A7 与日志）及
  `tsc --noEmit`。
- A1–A7 对应 `tests/test_a1_…` 至 `tests/test_a7_…`，手工复现步骤见 `README.md` 第 5 节。
- 不得削弱或删除失败用例；要么修好行为，要么在 `README.md` 的「已知缺陷」中如实记录。
- 列表界面必须真实覆盖加载中、空列表、错误三种状态。
- 提交前运行 §7.4 的边界探测；涉及 10 万/100 万行的结论，重跑
  `tests/test_a6_export.py` 或 §5 的生成命令。

### A1–A7 mapping / 验收映射

| ID | Requirement / 要求 | Test / 测试 |
|---|---|---|
| A1 | Tenant isolation across list/detail/bulk/export; cross-tenant detail 404 / 跨租户隔离 | `tests/test_a1_tenant_isolation.py` |
| A2 | Same key sequential/concurrent = one operation; one certificate per learner; one audit each / 同 key 顺序/并发一个操作 | `tests/test_a2_idempotency.py` |
| A3 | Same key, different payload → 409; no overwrite / 同 key 不同 payload → 409 | `tests/test_a3_key_misuse.py` |
| A4 | Only eligible learners issued; skip reasons / 仅向符合条件者签发 | `tests/test_a4_learner_outcomes.py` |
| A5 | DST + tenant-local date: East 2026-01-11 00:30, West 2026-01-10 21:30 / DST 与本地日期 | `tests/test_a5_timezone.py` |
| A6 | 100k export <60 s, exact rows/order, stable ties, list during export / 10 万行导出 | `tests/test_a6_export.py` |
| A7 | Revoke once + one audit; repeat no duplicate / 撤销审计 | `tests/test_a7_revocation_audit.py` |

## 10. Engineering practice / 工程约定

- Small commits with one concern each; prefixes `feat:`, `fix:`, `test:`, `docs:`,
  `chore:`, `refactor:`.
  提交要小、单一职责；前缀使用 `feat:`、`fix:`、`test:`、`docs:`、`chore:`、`refactor:`。
- Keep `README.md`, `DESIGN.md`, and this file in sync when behaviour changes.
  行为变化时同步更新 `README.md`、`DESIGN.md` 与本文件。
- Add or update tests when logging behaviour changes (levels, fields, correlation) and when
  a boundary in §7 is fixed.
  日志行为（级别、字段、关联 ID）或 §7 边界修复时，补测试或更新测试。
- Never commit credentials, tokens, or private third-party data.
  禁止提交凭据、令牌或第三方隐私数据。
- Do not commit `.venv/`, `web/node_modules/`, `web/dist/`, `data/`, or caches.
  不要提交 `.venv/`、`web/node_modules/`、`web/dist/`、`data/` 或缓存目录。
- Keep both languages in this file in sync; a change in one language without the other is a
  documentation bug.
  本文件两种语言必须同步；只改一种语言视为文档缺陷。

## 11. Quick reference / 速查

```bash
./start.sh                 # one command: install, build, seed, serve
./verify.sh                # pytest (A1–A7 + logging) + tsc
./start.sh --reset         # wipe and reseed
PORT=8080 ./start.sh
DB_PATH=data/large.db ./start.sh
.venv/bin/python scripts/generate_large.py --tenant east --count 100000
```

- Actors: `alice@east.test` (East/Sydney), `bob@west.test` (West/Perth).
  角色：`alice@east.test`（East/Sydney）、`bob@west.test`（West/Perth）。
- Header: `X-Actor-Email`; bulk issue also needs `Idempotency-Key`.
  请求头：`X-Actor-Email`；批量签发还需 `Idempotency-Key`。
- Limits: 100k export <60 s; 50k bulk ~4 s; SQLite single writer; no production auth.
  限制：10 万行导出 <60 秒；5 万签发约 4 秒；SQLite 单写；无生产鉴权。
