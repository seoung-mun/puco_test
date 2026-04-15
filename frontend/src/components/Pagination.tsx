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
      style={{
        background: 'none',
        border: '1px solid #2a2a5a',
        color: disabled ? '#445' : '#aab',
        padding: '4px 10px',
        borderRadius: 4,
        cursor: disabled ? 'not-allowed' : 'pointer',
        fontSize: 13,
      }}
    >
      {label}
    </button>
  );

  return (
    <div
      data-testid="pagination"
      style={{ display: 'flex', gap: 4, justifyContent: 'center', alignItems: 'center' }}
    >
      {!atFirst && btn('<<', 1, false, 'first-page')}
      {!atFirst && btn('<', page - 1, false, 'prev-page')}
      {items.map((item, i) =>
        item === 'ellipsis' ? (
          <span key={`ellipsis-${i}`} style={{ color: '#556', padding: '4px 6px' }}>...</span>
        ) : (
          <button
            key={`page-${item}`}
            type="button"
            aria-label={`page-${item}`}
            aria-current={item === page ? 'page' : undefined}
            onClick={() => onPageChange(item)}
            style={{
              background: item === page ? '#2a5ab0' : 'none',
              border: '1px solid #2a2a5a',
              color: item === page ? '#fff' : '#aab',
              padding: '4px 10px',
              borderRadius: 4,
              cursor: 'pointer',
              fontSize: 13,
              fontWeight: item === page ? 'bold' : 'normal',
            }}
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
