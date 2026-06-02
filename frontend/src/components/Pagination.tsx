interface Props {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

export function buildPageList(page: number, totalPages: number): Array<number | 'ellipsis'> {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }
  const items: Array<number | 'ellipsis'> = [];
  const windowStart = Math.max(2, page - 2);
  const windowEnd = Math.min(totalPages - 1, page + 2);

  items.push(1);
  if (windowStart > 2) items.push('ellipsis');
  for (let i = windowStart; i <= windowEnd; i++) items.push(i);
  if (windowEnd < totalPages - 1) items.push('ellipsis');
  items.push(totalPages);
  return items;
}

export default function Pagination({ page, totalPages, onPageChange }: Props) {
  if (totalPages <= 0) return null;
  const atFirst = page <= 1;
  const atLast = page >= totalPages;
  const items = buildPageList(page, totalPages);

  const btn = (label: string, target: number, disabled: boolean, key: string) => (
    <button
      key={key}
      type="button"
      aria-label={key}
      onClick={() => !disabled && onPageChange(target)}
      disabled={disabled}
      className="pagination__btn"
    >
      {label}
    </button>
  );

  return (
    <div
      data-testid="pagination"
      className="pagination"
    >
      {!atFirst && btn('<<', 1, false, 'first-page')}
      {!atFirst && btn('<', page - 1, false, 'prev-page')}
      {items.map((item, i) =>
        item === 'ellipsis' ? (
          <span key={`ellipsis-${i}`} className="pagination__ellipsis">...</span>
        ) : (
          <button
            key={`page-${item}`}
            type="button"
            aria-label={`page-${item}`}
            aria-current={item === page ? 'page' : undefined}
            onClick={() => onPageChange(item)}
            className={`pagination__btn${item === page ? ' pagination__btn--active' : ''}`}
          >
            {item}
          </button>
        )
      )}
      {!atLast && btn('>', page + 1, false, 'next-page')}
      {!atLast && btn('>>', totalPages, false, 'last-page')}
    </div>
  );
}
