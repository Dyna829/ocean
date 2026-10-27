interface ToolbarProps {
  q: string;
  onQChange: (value: string) => void;
  pageSize: number;
  onPageSizeChange: (value: number) => void;
  onExport: () => void;
  onIssue: () => void;
  exporting: boolean;
  total: number | null;
  disabled: boolean;
}

export function Toolbar({
  q,
  onQChange,
  pageSize,
  onPageSizeChange,
  onExport,
  onIssue,
  exporting,
  total,
  disabled,
}: ToolbarProps) {
  return (
    <div className="toolbar">
      <div className="search-field">
        <span className="search-icon" aria-hidden="true">
          ⌕
        </span>
        <input
          type="search"
          value={q}
          onChange={(event) => onQChange(event.target.value)}
          placeholder="Search learner name or serial number"
          aria-label="Search learner name or serial number"
          autoComplete="off"
          disabled={disabled}
        />
        {q ? (
          <button type="button" className="search-clear" onClick={() => onQChange("")} aria-label="Clear search">
            ×
          </button>
        ) : null}
      </div>

      <div className="toolbar-right">
        <span className="result-count" aria-live="polite">
          {total === null ? "—" : `${total.toLocaleString()} certificate${total === 1 ? "" : "s"}`}
        </span>
        <label className="page-size">
          <span>Rows</span>
          <select
            value={pageSize}
            onChange={(event) => onPageSizeChange(Number(event.target.value))}
            disabled={disabled}
            aria-label="Rows per page"
          >
            {[10, 20, 50, 100].map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="btn btn-secondary" onClick={onExport} disabled={disabled || exporting}>
          {exporting ? "Exporting…" : "Export CSV"}
        </button>
        <button type="button" className="btn btn-primary" onClick={onIssue} disabled={disabled}>
          Issue certificates
        </button>
      </div>
    </div>
  );
}
