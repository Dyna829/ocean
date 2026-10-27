import { useEffect, useState } from "react";
import { downloadCertificateExport, fetchCertificates, fetchMe, messageOf } from "./api";
import { useDebouncedValue } from "./hooks";
import type { ListState, Me, SortDir, SortField } from "./types";
import { Banner } from "./components/Banner";
import { BulkIssueDialog } from "./components/BulkIssueDialog";
import { CertificateTable } from "./components/CertificateTable";
import { DetailDrawer } from "./components/DetailDrawer";
import { Pagination } from "./components/Pagination";
import { Toolbar } from "./components/Toolbar";

const ACTORS = [
  { email: "alice@east.test", label: "Alice Chen · East" },
  { email: "bob@west.test", label: "Bob Miller · West" },
];

const STORAGE_KEY = "cca.actor";

type Toast = { kind: "success" | "error"; text: string };

export default function App() {
  const [actorEmail, setActorEmail] = useState(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return ACTORS.some((actor) => actor.email === stored) ? (stored as string) : ACTORS[0].email;
  });
  const [me, setMe] = useState<Me | null>(null);
  const [meError, setMeError] = useState<string | null>(null);
  const [meReload, setMeReload] = useState(0);

  const [qInput, setQInput] = useState("");
  const q = useDebouncedValue(qInput);
  const [sort, setSort] = useState<SortField>("issued_date");
  const [dir, setDir] = useState<SortDir>("desc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const [list, setList] = useState<ListState>({ kind: "loading" });
  const [refresh, setRefresh] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [toast, setToast] = useState<Toast | null>(null);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, actorEmail);
  }, [actorEmail]);

  useEffect(() => {
    const controller = new AbortController();
    setMe(null);
    setMeError(null);
    fetchMe(actorEmail, controller.signal)
      .then((data) => setMe(data))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setMeError(messageOf(error));
      });
    return () => controller.abort();
  }, [actorEmail, meReload]);

  useEffect(() => {
    setPage(1);
  }, [q, sort, dir, pageSize]);

  useEffect(() => {
    setSelectedId(null);
    setBulkOpen(false);
    setToast(null);
  }, [actorEmail]);

  useEffect(() => {
    if (!me) return;
    const controller = new AbortController();
    setList({ kind: "loading" });
    fetchCertificates(actorEmail, { q, sort, dir, page, pageSize }, controller.signal)
      .then((data) => setList({ kind: "ready", data }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setList({ kind: "error", message: messageOf(error) });
      });
    return () => controller.abort();
  }, [me, actorEmail, q, sort, dir, page, pageSize, refresh]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 4500);
    return () => window.clearTimeout(timer);
  }, [toast]);

  function handleSort(field: SortField) {
    if (field === sort) {
      setDir((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setSort(field);
    setDir(field === "issued_date" ? "desc" : "asc");
  }

  function handleChanged(message: string) {
    setRefresh((value) => value + 1);
    setToast({ kind: "success", text: message });
  }

  async function handleExport() {
    setExporting(true);
    try {
      await downloadCertificateExport(actorEmail, { q, sort, dir });
      setToast({ kind: "success", text: "CSV export downloaded" });
    } catch (error) {
      setToast({ kind: "error", text: messageOf(error) });
    } finally {
      setExporting(false);
    }
  }

  const effectiveList: ListState = meError ? { kind: "error", message: meError } : list;
  const total = effectiveList.kind === "ready" ? effectiveList.data.total : null;

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            C
          </span>
          <div>
            <h1>Certificate Admin Console</h1>
            <p>Multi-tenant training platform</p>
          </div>
        </div>

        <div className="topbar-actions">
          {me ? (
            <span className="tenant-chip">
              <span className="tenant-dot" aria-hidden="true" />
              <strong>{me.tenant.name}</strong>
              <span className="mono muted">{me.tenant.timezone}</span>
            </span>
          ) : null}
          <label className="actor-picker">
            <span>Acting as</span>
            <select value={actorEmail} onChange={(event) => setActorEmail(event.target.value)}>
              {ACTORS.map((actor) => (
                <option key={actor.email} value={actor.email}>
                  {actor.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </header>

      <main className="content">
        <div className="page-heading">
          <div>
            <h2>Certificates</h2>
            <p className="muted">Review completions, issue credentials, revoke, and export.</p>
          </div>
        </div>

        {meError ? (
          <Banner kind="error" onDismiss={() => setMeError(null)}>
            {meError}
          </Banner>
        ) : null}

        <section className="card" aria-busy={effectiveList.kind === "loading"}>
          <Toolbar
            q={qInput}
            onQChange={setQInput}
            pageSize={pageSize}
            onPageSizeChange={setPageSize}
            onExport={() => void handleExport()}
            onIssue={() => setBulkOpen(true)}
            exporting={exporting}
            total={total}
            disabled={!me}
          />
          <CertificateTable
            state={effectiveList}
            sort={sort}
            dir={dir}
            q={q}
            onSort={handleSort}
            onSelect={setSelectedId}
            onRetry={() => {
              setMeError(null);
              setMeReload((value) => value + 1);
              setRefresh((value) => value + 1);
            }}
          />
          {effectiveList.kind === "ready" ? (
            <Pagination
              page={effectiveList.data.page}
              totalPages={effectiveList.data.totalPages}
              total={effectiveList.data.total}
              pageSize={effectiveList.data.pageSize}
              onPage={setPage}
            />
          ) : null}
        </section>
      </main>

      {selectedId ? (
        <DetailDrawer
          actor={actorEmail}
          certificateId={selectedId}
          timezone={me?.tenant.timezone ?? "UTC"}
          onClose={() => setSelectedId(null)}
          onChanged={handleChanged}
        />
      ) : null}

      {bulkOpen ? (
        <BulkIssueDialog
          actor={actorEmail}
          onClose={() => setBulkOpen(false)}
          onCompleted={handleChanged}
        />
      ) : null}

      {toast ? (
        <div className={`toast toast-${toast.kind}`} role="status">
          {toast.text}
        </div>
      ) : null}
    </div>
  );
}
