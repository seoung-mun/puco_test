import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';

interface Props {
  open: boolean;
  displayLabel: string;
  playerNames: string[];
  playedDate: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ReplayConfirmModal({
  open,
  displayLabel,
  playerNames,
  playedDate,
  onConfirm,
  onCancel,
}: Props) {
  const { t } = useTranslation();

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onCancel();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div
      data-testid="replay-confirm-backdrop"
      onClick={onCancel}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0, 0, 0, 0.6)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
        style={{
          background: '#0d1117',
          border: '1px solid #2a2a5a',
          borderRadius: 8,
          padding: '24px 28px',
          maxWidth: 400,
          width: '90%',
          color: '#dde',
        }}
      >
        <h2 style={{ color: '#f0c040', marginTop: 0, marginBottom: 16, fontSize: 18 }}>
          {t('replay.confirm.title')}
        </h2>
        <div style={{ fontSize: 14, marginBottom: 8, color: '#aab' }}>
          <strong style={{ color: '#dde' }}>{displayLabel}</strong>
        </div>
        {playerNames.length > 0 && (
          <div style={{ fontSize: 13, marginBottom: 6, color: '#aab' }}>
            {t('replay.column.players')}: {playerNames.join(', ')}
          </div>
        )}
        <div style={{ fontSize: 13, marginBottom: 20, color: '#aab' }}>
          {t('replay.column.date')}: {playedDate}
        </div>
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button
            onClick={onCancel}
            style={{
              background: 'none',
              border: '1px solid #334',
              borderRadius: 6,
              color: '#aab',
              cursor: 'pointer',
              padding: '8px 16px',
              fontSize: 13,
            }}
          >
            {t('replay.confirm.cancel')}
          </button>
          <button
            onClick={onConfirm}
            style={{
              background: '#2a5ab0',
              border: 'none',
              borderRadius: 6,
              color: '#fff',
              cursor: 'pointer',
              padding: '8px 16px',
              fontSize: 13,
              fontWeight: 'bold',
            }}
          >
            {t('replay.confirm.watch')}
          </button>
        </div>
      </div>
    </div>
  );
}
