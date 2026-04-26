import React from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

/**
 * Numeric pagination control.
 *
 * Renders: « 1 … 4 5 [6] 7 8 … 20 »
 * Always shows: first, last, current ± 1.
 *
 * Props:
 *   - page: current page (1-based)
 *   - totalPages: total number of pages
 *   - onChange: (newPage: number) => void
 */
export default function Pagination({ page, totalPages, onChange }) {
  if (!totalPages || totalPages <= 1) return null;

  const pages = [];
  const push = (v) => pages.push(v);

  push(1);
  if (page - 1 > 2) push("…");
  for (let i = Math.max(2, page - 1); i <= Math.min(totalPages - 1, page + 1); i++) push(i);
  if (page + 1 < totalPages - 1) push("…");
  if (totalPages > 1) push(totalPages);

  // Dedupe (when the ranges overlap on small totals)
  const seen = new Set();
  const finalPages = pages.filter((p) => {
    const k = String(p);
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });

  const goto = (p) => {
    const np = Math.max(1, Math.min(totalPages, p));
    if (np !== page) onChange(np);
  };

  const baseBtn =
    "min-w-[40px] h-10 px-3 inline-flex items-center justify-center rounded-card border text-sm transition-colors";
  const idleBtn =
    "border-[hsl(var(--line))] text-[hsl(var(--ink))] hover:bg-[hsl(var(--surface))] disabled:opacity-40 disabled:hover:bg-transparent";
  const activeBtn =
    "bg-[hsl(var(--ink))] text-[hsl(var(--bg))] border-[hsl(var(--ink))] cursor-default";

  return (
    <nav
      role="navigation"
      aria-label="Pagination"
      className="mt-10 flex flex-wrap items-center justify-center gap-1.5"
      data-testid="pagination"
    >
      <button
        type="button"
        onClick={() => goto(page - 1)}
        disabled={page <= 1}
        aria-label="Previous page"
        className={`${baseBtn} ${idleBtn}`}
        data-testid="pagination-prev"
      >
        <ChevronLeft size={16} />
      </button>

      {finalPages.map((p, i) =>
        p === "…" ? (
          <span
            key={`e-${i}`}
            className="px-2 text-sm text-[hsl(var(--ink-muted))] select-none"
            aria-hidden="true"
          >
            …
          </span>
        ) : (
          <button
            key={p}
            type="button"
            onClick={() => goto(p)}
            aria-current={p === page ? "page" : undefined}
            className={`${baseBtn} ${p === page ? activeBtn : idleBtn}`}
            data-testid={`pagination-page-${p}`}
          >
            {p}
          </button>
        )
      )}

      <button
        type="button"
        onClick={() => goto(page + 1)}
        disabled={page >= totalPages}
        aria-label="Next page"
        className={`${baseBtn} ${idleBtn}`}
        data-testid="pagination-next"
      >
        <ChevronRight size={16} />
      </button>
    </nav>
  );
}
