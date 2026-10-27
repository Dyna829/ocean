import type { CertificateStatus } from "../types";

export function StatusBadge({ status }: { status: CertificateStatus }) {
  return (
    <span className={`badge badge-${status.toLowerCase()}`}>
      <span className="badge-dot" aria-hidden="true" />
      {status === "ACTIVE" ? "Active" : "Revoked"}
    </span>
  );
}
