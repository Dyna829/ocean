import type { KeyboardEvent } from "react";
import type { CertificateItem, ListState, SortDir, SortField } from "../types";
import { StatusBadge } from "./StatusBadge";

interface CertificateTableProps {
  state: ListState;
  sort: SortField;
  dir: SortDir;
  q: string;
  onSort: (field: SortField) => void;
  onSelect: (id: string) => void;
  onRetry: () => void;
}

const COLUMNS: Array<{ field: SortField; label: string; className?: string }> = [
  { field: "serial", label: "Serial number", className: "cell-serial" },
  { field: "learner_name", label: "Learner", className: "cell-learner" },
  { field: "course_title", label: "Course", className: "cell-course" },
  { field: "issued_date", label: "Issued (tenant local)", className: "cell-issued" },
];

function SortHeader({
  field,
  label,
  className,
  sort,
  dir,
  onSort,
}: {
  field: SortField;
  label: string;
  className?: string;
  sort: SortField;
  dir: SortDir;
  onSort: (field: SortField) => void;
}) {
  const active = sort === field;
  return (
    <th scope="col" className={className} aria-sort={active ? (dir === "asc" ? "ascending" : "descending") : "none"}>
      <button type="button" className={`sort-button${active ? " is-active" : ""}`} onClick={() => onSort(field)}>
        {label}
        <span className="sort-indicator" aria-hidden="true">
          {active ? (dir === "asc" ? "▲" : "▼") : "↕"}
        </span>
      </button>
    </th>
  );
}

function CertificateRow({ item, onSelect }: { item: CertificateItem; onSelect: (id: string) => void }) {
  const onKeyDown = (event: KeyboardEvent<HTMLTableRowElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(item.id);
    }
  };

  return (
    <tr className="row-clickable" tabIndex={0} onClick={() => onSelect(item.id)} onKeyDown={onKeyDown}>
      <td className="cell-serial mono">{item.serial}</td>
      <td className="cell-learner">{item.learnerName}</td>
      <td className="cell-course">{item.courseTitle}</td>
      <td className="cell-issued mono" title={`UTC ${item.issuedAt}`}>
        {item.issuedAtLocal}
      </td>
      <td>
        <StatusBadge status={item.status} />
      </td>
      <td className="cell-actions">
        <button
          type="button"
          className="link-button"
          onClick={(event) => {
            event.stopPropagation();
            onSelect(item.id);
          }}
        >
          View
        </button>
      </td>
    </tr>
  );
}

function SkeletonRows() {
  return (
    <>
      {Array.from({ length: 6 }, (_, row) => (
        <tr key={row} className="skeleton-row" aria-hidden="true">
          {Array.from({ length: 6 }, (_, cell) => (
            <td key={cell}>
              <span className="skeleton-line" style={{ width: `${45 + ((row * 7 + cell * 11) % 45)}%` }} />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

export function CertificateTable({ state, sort, dir, q, onSort, onSelect, onRetry }: CertificateTableProps) {
  const columnCount = 6;

  return (
    <div className="table-wrap">
      <table className="cert-table">
        <caption className="sr-only">Certificates</caption>
        <thead>
          <tr>
            {COLUMNS.map((column) => (
              <SortHeader
                key={column.field}
                field={column.field}
                label={column.label}
                className={column.className}
                sort={sort}
                dir={dir}
                onSort={onSort}
              />
            ))}
            <th scope="col">Status</th>
            <th scope="col" className="cell-actions">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {state.kind === "loading" ? <SkeletonRows /> : null}

          {state.kind === "error" ? (
            <tr>
              <td colSpan={columnCount}>
                <div className="table-state" role="alert">
                  <p className="table-state-title">Could not load certificates</p>
                  <p className="muted">{state.message}</p>
                  <button type="button" className="btn btn-secondary" onClick={onRetry}>
                    Try again
                  </button>
                </div>
              </td>
            </tr>
          ) : null}

          {state.kind === "ready" && state.data.items.length === 0 ? (
            <tr>
              <td colSpan={columnCount}>
                <div className="table-state">
                  <p className="table-state-title">
                    {q ? `No certificates match “${q}”` : "No certificates yet"}
                  </p>
                  <p className="muted">
                    {q
                      ? "Try a different learner name or serial number."
                      : "Issue certificates from a course to see them here."}
                  </p>
                </div>
              </td>
            </tr>
          ) : null}

          {state.kind === "ready"
            ? state.data.items.map((item) => <CertificateRow key={item.id} item={item} onSelect={onSelect} />)
            : null}
        </tbody>
      </table>
    </div>
  );
}
