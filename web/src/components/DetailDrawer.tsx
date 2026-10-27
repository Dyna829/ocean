import { useEffect, useRef, useState } from "react";
import { ApiError, fetchCertificate, messageOf, revokeCertificate } from "../api";
import type { CertificateDetail } from "../types";
import { Banner } from "./Banner";
import { StatusBadge } from "./StatusBadge";

type State =
  | { kind: "loading" }
  | { kind: "ready"; data: CertificateDetail }
  | { kind: "error"; message: string; notFound: boolean };

interface DetailDrawerProps {
  actor: string;
  certificateId: string;
  timezone: string;
  onClose: () => void;
  onChanged: (message: string) => void;
}

export function DetailDrawer({ actor, certificateId, timezone, onClose, onChanged }: DetailDrawerProps) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [reload, setReload] = useState(0);
  const [confirming, setConfirming] = useState(false);
  const [reason, setReason] = useState("");
  const [revoking, setRevoking] = useState(false);
  const [revokeError, setRevokeError] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    setState({ kind: "loading" });
    fetchCertificate(actor, certificateId, controller.signal)
      .then((data) => setState({ kind: "ready", data }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setState({
          kind: "error",
          message: messageOf(error),
          notFound: error instanceof ApiError && error.status === 404,
        });
      });
    return () => controller.abort();
  }, [actor, certificateId, reload]);

  useEffect(() => {
    closeRef.current?.focus();
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  async function submitRevoke() {
    setRevoking(true);
    setRevokeError(null);
    try {
      const data = await revokeCertificate(actor, certificateId, reason.trim() || undefined);
      setState({ kind: "ready", data });
      setConfirming(false);
      onChanged(`Certificate ${data.certificate.serial} revoked`);
    } catch (error) {
      setRevokeError(messageOf(error));
    } finally {
      setRevoking(false);
    }
  }

  return (
    <div
      className="drawer-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <aside className="drawer" role="dialog" aria-modal="true" aria-labelledby="detail-title">
        <header className="drawer-header">
          <div>
            <p className="eyebrow">Certificate detail</p>
            <h2 id="detail-title" className="mono">
              {state.kind === "ready" ? state.data.certificate.serial : "Loading…"}
            </h2>
          </div>
          <button ref={closeRef} type="button" className="icon-button" onClick={onClose} aria-label="Close details">
            ×
          </button>
        </header>

        <div className="drawer-body">
          {state.kind === "loading" ? (
            <div className="drawer-skeleton" aria-label="Loading certificate">
              {Array.from({ length: 6 }, (_, index) => (
                <span key={index} className="skeleton-line" style={{ width: `${70 - index * 4}%` }} />
              ))}
            </div>
          ) : null}

          {state.kind === "error" ? (
            <>
              <Banner kind="error">{state.message}</Banner>
              {!state.notFound ? (
                <button type="button" className="btn btn-secondary" onClick={() => setReload((value) => value + 1)}>
                  Try again
                </button>
              ) : null}
            </>
          ) : null}

          {state.kind === "ready" ? (
            <>
              <dl className="detail-grid">
                <div>
                  <dt>Status</dt>
                  <dd>
                    <StatusBadge status={state.data.certificate.status} />
                  </dd>
                </div>
                <div>
                  <dt>Learner</dt>
                  <dd>{state.data.certificate.learnerName}</dd>
                </div>
                <div>
                  <dt>Course</dt>
                  <dd>{state.data.certificate.courseTitle}</dd>
                </div>
                <div>
                  <dt>Serial number</dt>
                  <dd className="mono">{state.data.certificate.serial}</dd>
                </div>
                <div>
                  <dt>Issued (tenant local)</dt>
                  <dd className="mono">
                    {state.data.certificate.issuedAtLocal}
                    <span className="detail-sub">{timezone}</span>
                  </dd>
                </div>
                <div>
                  <dt>Issued (UTC)</dt>
                  <dd className="mono">{state.data.certificate.issuedAt}</dd>
                </div>
                <div>
                  <dt>Local calendar date</dt>
                  <dd className="mono">{state.data.certificate.issueDateLocal}</dd>
                </div>
                {state.data.certificate.revokedAt ? (
                  <div>
                    <dt>Revoked</dt>
                    <dd className="mono">
                      {state.data.certificate.revokedAtLocal}
                      <span className="detail-sub">{state.data.certificate.revokedAt}</span>
                    </dd>
                  </div>
                ) : null}
              </dl>

              <section className="detail-section">
                <h3>Audit trail</h3>
                {state.data.audit.length === 0 ? (
                  <p className="muted">No audit events recorded.</p>
                ) : (
                  <ol className="timeline">
                    {state.data.audit.map((event) => (
                      <li key={event.id}>
                        <span className={`timeline-dot timeline-${event.action.toLowerCase()}`} aria-hidden="true" />
                        <div>
                          <p className="timeline-title">
                            {event.action === "ISSUED" ? "Issued" : "Revoked"}{" "}
                            <span className="muted">· {event.actor.email}</span>
                          </p>
                          <p className="timeline-time mono">
                            {event.atLocal} <span className="muted">({event.at})</span>
                          </p>
                          {typeof event.detail.reason === "string" ? (
                            <p className="timeline-note">Reason: {event.detail.reason}</p>
                          ) : null}
                        </div>
                      </li>
                    ))}
                  </ol>
                )}
              </section>

              <section className="detail-section revoke-section">
                <h3>Revocation</h3>
                {state.data.certificate.status === "ACTIVE" ? (
                  confirming ? (
                    <div className="confirm-box" role="group" aria-label="Confirm revocation">
                      <p>
                        <strong>Revoke this certificate?</strong> It becomes REVOKED immediately and the
                        action is written to the audit trail.
                      </p>
                      <label className="field">
                        <span>Reason (optional)</span>
                        <textarea
                          value={reason}
                          onChange={(event) => setReason(event.target.value)}
                          maxLength={200}
                          rows={2}
                          placeholder="e.g. issued in error"
                        />
                      </label>
                      {revokeError ? <Banner kind="error">{revokeError}</Banner> : null}
                      <div className="confirm-actions">
                        <button type="button" className="btn btn-ghost" onClick={() => setConfirming(false)} disabled={revoking}>
                          Cancel
                        </button>
                        <button type="button" className="btn btn-danger" onClick={submitRevoke} disabled={revoking}>
                          {revoking ? "Revoking…" : "Confirm revocation"}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button type="button" className="btn btn-danger" onClick={() => setConfirming(true)}>
                      Revoke certificate
                    </button>
                  )
                ) : (
                  <p className="muted">
                    This certificate is revoked. Revocation is idempotent: repeating it will not create a
                    second audit event.
                  </p>
                )}
              </section>
            </>
          ) : null}
        </div>
      </aside>
    </div>
  );
}
