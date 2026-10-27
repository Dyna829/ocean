import { useEffect, useRef, useState } from "react";
import { ApiError, bulkIssue, fetchCourses, messageOf } from "../api";
import type { BulkResponse, Course } from "../types";
import { Banner } from "./Banner";

type CoursesState =
  | { kind: "loading" }
  | { kind: "ready"; courses: Course[] }
  | { kind: "error"; message: string };

type ResultState =
  | { kind: "idle" }
  | { kind: "pending" }
  | { kind: "done"; data: BulkResponse; replayed: boolean }
  | { kind: "error"; message: string; retryable: boolean };

interface BulkIssueDialogProps {
  actor: string;
  onClose: () => void;
  onCompleted: (message: string) => void;
}

export function BulkIssueDialog({ actor, onClose, onCompleted }: BulkIssueDialogProps) {
  const [courses, setCourses] = useState<CoursesState>({ kind: "loading" });
  const [courseId, setCourseId] = useState("");
  const [result, setResult] = useState<ResultState>({ kind: "idle" });
  const [reload, setReload] = useState(0);
  const keyRef = useRef<string>(crypto.randomUUID());
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    setCourses({ kind: "loading" });
    fetchCourses(actor, controller.signal)
      .then((data) => setCourses({ kind: "ready", courses: data.courses }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setCourses({ kind: "error", message: messageOf(error) });
      });
    return () => controller.abort();
  }, [actor, reload]);

  useEffect(() => {
    if (courses.kind !== "ready" || courseId) return;
    const first = courses.courses.find((course) => course.eligible > 0) ?? courses.courses[0];
    if (first) setCourseId(first.id);
  }, [courses, courseId]);

  useEffect(() => {
    closeRef.current?.focus();
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  const selectedCourse =
    courses.kind === "ready" ? courses.courses.find((course) => course.id === courseId) : undefined;
  const pending = result.kind === "pending";

  function selectCourse(nextId: string) {
    // A new course is a new logical operation: new idempotency key.
    keyRef.current = crypto.randomUUID();
    setCourseId(nextId);
    setResult({ kind: "idle" });
  }

  function newOperation() {
    keyRef.current = crypto.randomUUID();
    setResult({ kind: "idle" });
  }

  async function submit() {
    if (!courseId || pending) return;
    setResult({ kind: "pending" });
    try {
      const { data, replayed } = await bulkIssue(actor, courseId, keyRef.current);
      setResult({ kind: "done", data, replayed });
      onCompleted(`Issued ${data.summary.issued} of ${data.summary.total} learner(s) · ${data.courseTitle}`);
    } catch (error) {
      const keyReuse = error instanceof ApiError && error.code === "idempotency_key_reuse";
      setResult({ kind: "error", message: messageOf(error), retryable: !keyReuse });
    }
  }

  return (
    <div
      className="modal-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !pending) onClose();
      }}
    >
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="bulk-title">
        <header className="modal-header">
          <div>
            <p className="eyebrow">Bulk issue</p>
            <h2 id="bulk-title">Issue certificates</h2>
          </div>
          <button ref={closeRef} type="button" className="icon-button" onClick={onClose} aria-label="Close" disabled={pending}>
            ×
          </button>
        </header>

        <div className="modal-body">
          {courses.kind === "loading" ? <p className="muted">Loading courses…</p> : null}

          {courses.kind === "error" ? (
            <>
              <Banner kind="error">{courses.message}</Banner>
              <button type="button" className="btn btn-secondary" onClick={() => setReload((value) => value + 1)}>
                Try again
              </button>
            </>
          ) : null}

          {courses.kind === "ready" && result.kind !== "done" ? (
            <form
              className="bulk-form"
              onSubmit={(event) => {
                event.preventDefault();
                void submit();
              }}
            >
              <label className="field">
                <span>Course</span>
                <select value={courseId} onChange={(event) => selectCourse(event.target.value)} disabled={pending}>
                  {courses.courses.map((course) => (
                    <option key={course.id} value={course.id}>
                      {course.title} — {course.eligible} eligible
                    </option>
                  ))}
                </select>
              </label>

              {selectedCourse ? (
                <div className="stats-grid">
                  <div className="stat">
                    <span className="stat-value">{selectedCourse.eligible}</span>
                    <span className="stat-label">Eligible now</span>
                  </div>
                  <div className="stat">
                    <span className="stat-value">{selectedCourse.certified}</span>
                    <span className="stat-label">Already certified</span>
                  </div>
                  <div className="stat">
                    <span className="stat-value">{selectedCourse.incomplete}</span>
                    <span className="stat-label">Incomplete</span>
                  </div>
                </div>
              ) : null}

              <p className="hint">
                Incomplete learners and learners who already hold a certificate are skipped — the response
                reports every outcome. Reusing an <code>Idempotency-Key</code> replays the stored result
                instead of issuing again.
              </p>

              {result.kind === "error" ? <Banner kind="error">{result.message}</Banner> : null}

              <div className="modal-actions">
                <button type="button" className="btn btn-ghost" onClick={onClose} disabled={pending}>
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={pending || !courseId || (selectedCourse?.eligible ?? 0) === 0}
                >
                  {pending
                    ? "Issuing…"
                    : selectedCourse
                      ? `Issue to ${selectedCourse.eligible} learner${selectedCourse.eligible === 1 ? "" : "s"}`
                      : "Select a course"}
                </button>
              </div>
            </form>
          ) : null}

          {result.kind === "done" ? (
            <div className="bulk-result">
              <div className="summary-chips">
                <span className="chip chip-issued">Issued {result.data.summary.issued}</span>
                <span className="chip chip-skipped">Skipped {result.data.summary.skipped}</span>
                <span className="chip chip-failed">Failed {result.data.summary.failed}</span>
                <span className="chip chip-total">Total {result.data.summary.total}</span>
              </div>
              <p className="muted mono">
                operation {result.data.operationId} · {result.data.courseTitle}
              </p>
              {result.replayed ? (
                <Banner kind="info">
                  Replayed the stored outcome for this Idempotency-Key — no certificate was issued twice.
                </Banner>
              ) : null}

              <div className="outcome-table-wrap">
                <table className="outcome-table">
                  <thead>
                    <tr>
                      <th scope="col">Learner</th>
                      <th scope="col">Outcome</th>
                      <th scope="col">Detail</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.data.outcomes.map((outcome) => (
                      <tr key={outcome.learnerId}>
                        <td>{outcome.learnerName}</td>
                        <td>
                          <span className={`badge badge-outcome-${outcome.status}`}>{outcome.status}</span>
                        </td>
                        <td className="muted">
                          {outcome.status === "issued"
                            ? outcome.serial
                            : (outcome.message ?? outcome.reason ?? "—")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={newOperation}>
                  New operation
                </button>
                <button type="button" className="btn btn-primary" onClick={onClose}>
                  Done
                </button>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
