# AGENTS.md — build guide for AI assistants / AI 助手构建指南

This file is maintained in English and Chinese. Keep both languages in sync when editing.
本文件以中英双语维护；修改时请同步更新两种语言。

## 1. What we are building / 我们要构建什么

**EN.** An internal admin console for a multi-tenant training platform. Tenant admins
review course completions, issue certificates in bulk, revoke them with an audit trail, and
export certificate data as CSV. It must stay small, correct, and runnable with one command.
Source requirements: `docs/briefing.pdf`.

**中文。** 一个面向多租户培训平台的内部管理控制台。租户管理员查看课程完成情况、批量签发证书、
撤销证书并保留审计记录、导出证书 CSV。系统要小而正确，且一条命令即可运行。原始需求见
`docs/briefing.pdf`。

## 2. Scope / 范围

**EN — in scope**

- Certificate list: search by learner name or serial number, paginate, sort; loading, empty,
  and error states.
- Bulk issue: pick a course, issue to eligible learners, return per-learner
  `issued` / `skipped` / `failed`, and disable duplicate submissions in the UI.
- Detail: serial, course, learner, tenant-local issue date, status; revocation with
  confirmation; audit for issuance and revocation.
- CSV export: learner name, course title, serial number, tenant-local issue date; preserves
  the current search and sort; handles 100,000 rows.

**EN — out of scope**

- Production authentication, cloud deployment, notifications, unrelated admin features.
- Visual polish that costs core correctness.

**中文 —— 范围内**

- 证书列表：按学员姓名或证书编号搜索、分页、排序，并具备加载中、空列表、错误三种状态。
- 批量签发：选择课程，向符合条件的学习者签发，逐人返回 `issued` / `skipped` / `failed`，
  前端禁止重复提交。
- 证书详情：编号、课程、学员、租户本地签发日期、状态；撤销需二次确认；签发与撤销都写入审计。
- CSV 导出：学员姓名、课程名称、证书编号、租户本地签发日期；保留当前搜索与排序；
  支持 10 万行。

**中文 —— 范围外**

- 生产级鉴权、云部署、通知、与本流程无关的管理功能。
- 以牺牲核心正确性为代价的视觉打磨。

## 3. Stack and commands / 技术栈与命令

| Area / 方面 | Decision / 约定 |
|---|---|
| Backend / 后端 | Python 3.11+ · FastAPI · SQLite (WAL) · Uvicorn |
| Frontend / 前端 | React 19 · TypeScript · Vite; built to `web/dist` and served by FastAPI / 构建到 `web/dist`，由 FastAPI 托管 |
| Origin / 同源 | Single process, single origin, no CORS / 单进程单源，不引入 CORS |
| Start / 启动 | `./start.sh` installs deps, builds the SPA, seeds demo data, serves `:8000` / 安装依赖、构建前端、写入演示数据并启动 |
| Verify / 验证 | `./verify.sh` runs the A1–A7 pytest suites plus `tsc --noEmit` / 运行 A1–A7 测试与前端类型检查 |
| Data / 数据 | SQLite at `DB_PATH` (default `data/app.db`); `app/seed.py` seeds demo data / 默认 `data/app.db`，由 `app/seed.py` 写入演示数据 |
| Large data / 大数据 | `scripts/generate_large.py` writes a separate 100k-row database / 生成独立的 10 万行数据库 |

## 4. Non-negotiable rules / 不可妥协的规则

### Tenant isolation / 租户隔离

- The tenant comes from the `admins` row resolved by `X-Actor-Email`; no endpoint accepts a
  tenant id from the client.
  租户由 `X-Actor-Email` 解析出的 `admins` 记录决定，任何接口都不接受客户端传入的租户 ID。
- Every tenant-scoped query filters on `tenant_id`; cross-tenant resources return 404,
  indistinguishable from missing ones.
  所有涉及租户的查询都带 `tenant_id`；跨租户资源返回 404，与不存在不可区分。

### Idempotency / 幂等

- `POST /api/certificates/bulk-issue` requires `Idempotency-Key`; the business write and the
  stored response commit in the same `BEGIN IMMEDIATE` transaction.
  批量签发必须携带 `Idempotency-Key`；业务写入与结果存储必须在同一个 `BEGIN IMMEDIATE`
  事务内提交。
- Same key + same payload replays the stored response verbatim for sequential and concurrent
  callers; same key + different payload returns 409 and writes nothing.
  同一 key 同一 payload 时，顺序与并发调用都原样重放已有结果；同一 key 不同 payload
  返回 409 且不写任何数据。

### Time / 时间

- Store UTC (`YYYY-MM-DDTHH:MM:SSZ`); persist `issue_date_local` at issuance; derive display
  strings from the tenant's IANA timezone.
  统一存 UTC；签发时落库 `issue_date_local`；展示串按租户 IANA 时区实时推导。
- List sorting and CSV export both use the tenant-local calendar date.
  列表排序与 CSV 导出都使用租户本地的日历日期。

### Ordering and export / 排序与导出

- Every ordering is total: requested sort key first, then `id`. List and export agree, and
  tied rows keep the same relative order on repeated exports.
  所有排序都是全序：先按请求字段，再按 `id`；列表与导出一致，重复导出时并列项相对顺序不变。
- Export streams in batches and is never buffered whole; 100,000 rows finish in under 60 s
  and the list endpoint stays responsive while an export is running.
  导出必须分批流式输出，禁止整体缓冲；10 万行需在 60 秒内完成，且导出期间列表接口保持可用。

### Audit and integrity / 审计与完整性

- Exactly one audit event per issuance and per revocation; revocation is idempotent.
  每次签发、每次撤销各产生且仅产生一条审计事件；撤销操作幂等。
- Uniqueness is enforced by the database: `(tenant, course, learner)` and
  `(certificate, action)`, with writes in `BEGIN IMMEDIATE`.
  唯一性由数据库保证：`(tenant, course, learner)` 与 `(certificate, action)`，
  写操作使用 `BEGIN IMMEDIATE`。

### Errors / 错误

- Error body is `{ "code", "message", "details" }`: 401 unknown actor, 404 missing or
  cross-tenant, 409 idempotency conflict, 422 validation, 400 missing idempotency key.
  错误体统一为 `{ "code", "message", "details" }`：401 未知操作者，404 不存在或跨租户，
  409 幂等冲突，422 校验失败，400 缺少幂等 key。

## 5. Verification / 验证

**EN**

- `./verify.sh` must pass before a commit that claims a scenario works.
- A1–A7 live in `tests/test_a1_…` … `tests/test_a7_…`; manual reproduction steps are in
  `README.md` §5.
- Never weaken or delete a failing test. Fix the behaviour, or record the defect honestly
  under "Known defects" in `README.md`.
- The list UI must visibly cover loading, empty, and error states.

**中文**

- 任何声称某场景可用的提交，必须先在 `./verify.sh` 通过。
- A1–A7 对应 `tests/test_a1_…` 至 `tests/test_a7_…`，手工复现步骤见 `README.md` 第 5 节。
- 不得削弱或删除失败用例；要么修好行为，要么在 `README.md` 的「已知缺陷」中如实记录。
- 列表界面必须真实覆盖加载中、空列表、错误三种状态。

## 6. Engineering practice / 工程约定

- Small commits with one concern each; prefixes `feat:`, `fix:`, `test:`, `docs:`,
  `chore:`, `refactor:`.
  提交要小、单一职责；前缀使用 `feat:`、`fix:`、`test:`、`docs:`、`chore:`、`refactor:`。
- Keep `README.md` and `DESIGN.md` in sync when behaviour changes.
  行为变化时同步更新 `README.md` 与 `DESIGN.md`。
- Never commit credentials, tokens, or private third-party data.
  禁止提交凭据、令牌或第三方隐私数据。
- Do not commit `.venv/`, `web/node_modules/`, `web/dist/`, `data/`, or caches.
  不要提交 `.venv/`、`web/node_modules/`、`web/dist/`、`data/` 或缓存目录。
