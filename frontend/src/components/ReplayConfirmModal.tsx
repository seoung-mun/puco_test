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
      className="resort-modal-backdrop"
    >
      <div
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
        className="resort-modal resort-modal--wide"
      >
        <h2 className="resort-modal-title" style={{ marginBottom: 16 }}>
          {t('replay.confirm.title')}
        </h2>
        <div className="resort-modal-copy" style={{ fontSize: 14, marginBottom: 8 }}>
          <strong>{displayLabel}</strong>
        </div>
        {playerNames.length > 0 && (
          <div className="resort-modal-copy" style={{ fontSize: 13, marginBottom: 6 }}>
            {t('replay.column.players')}: {playerNames.join(', ')}
          </div>
        )}
        <div className="resort-modal-copy" style={{ fontSize: 13, marginBottom: 20 }}>
          {t('replay.column.date')}: {playedDate}
        </div>
        <div className="resort-actions">
          <button
            onClick={onCancel}
            className="resort-btn-secondary"
          >
            {t('replay.confirm.cancel')}
          </button>
          <button
            onClick={onConfirm}
            className="resort-btn-primary"
            style={{ width: 'auto', padding: '8px 16px', fontSize: 13 }}
          >
            {t('replay.confirm.watch')}
          </button>
        </div>
      </div>
    </div>
  );
}
