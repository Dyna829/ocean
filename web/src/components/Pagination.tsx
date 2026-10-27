interface PaginationProps {
  page: number;
  totalPages: number;
  total: number;
  pageSize: number;
  onPage: (page: number) => void;
}

function pageWindow(page: number, totalPages: number): number[] {
  const size = 5;
  let start = Math.max(1, page - 2);
  const end = Math.min(totalPages, start + size - 1);
  start = Math.max(1, end - size + 1);
  const pages: number[] = [];
  for (let index = start; index <= end; index += 1) pages.push(index);
  return pages;
}

export function Pagination({ page, totalPages, total, pageSize, onPage }: PaginationProps) {
  const first = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);

  return (
    <nav className="pagination" aria-label="Certificates pagination">
      <p className="pagination-summary">
        {total === 0 ? "No results" : `${first.toLocaleString()}–${last.toLocaleString()} of ${total.toLocaleString()}`}
      </p>
      <div className="pagination-controls">
        <button type="button" className="page-button" onClick={() => onPage(page - 1)} disabled={page <= 1}>
          ‹ Prev
        </button>
        {pageWindow(page, totalPages).map((value) => (
          <button
            key={value}
            type="button"
            className={`page-button${value === page ? " is-current" : ""}`}
            onClick={() => onPage(value)}
            aria-current={value === page ? "page" : undefined}
          >
            {value}
          </button>
        ))}
        <button
          type="button"
          className="page-button"
          onClick={() => onPage(page + 1)}
          disabled={page >= totalPages}
        >
          Next ›
        </button>
      </div>
    </nav>
  );
}
