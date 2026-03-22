import { useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import type { HistoryEntry } from '../types/gameState';

interface Props {
  history: HistoryEntry[];
}

function formatTs(ts: number): string {
  const d = new Date(ts * 1000);
  const h = String(d.getHours()).padStart(2, '0');
  const m = String(d.getMinutes()).padStart(2, '0');
  const s = String(d.getSeconds()).padStart(2, '0');
  return `${h}:${m}:${s}`;
}

export default function HistoryPanel({ history }: Props) {
  const { t } = useTranslation();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [history.length]);

  return (
    <div style={{
      background: '#0d1117',
      border: '1px solid #2a2a5a',
      borderRadius: 8,
      padding: '8px 12px',
      maxHeight: 200,
      overflowY: 'auto',
      fontFamily: 'monospace',
      fontSize: 12,
    }}>
      {history.length === 0 && (
        <div style={{ color: '#555', fontStyle: 'italic' }}>{t('history.empty')}</div>
      )}
      {history.map((e, i) => {
        const isRoundEnd = e.action === 'round_end';
        const params = { ...e.params };
        if (params.role)         params.role         = t(`roles.${params.role}`,         { defaultValue: params.role });
        if (params.good)         params.good         = t(`goods.${params.good}`,         { defaultValue: params.good });
        if (params.plantation)   params.plantation   = t(`plantations.${params.plantation}`, { defaultValue: params.plantation });
        if (params.building)     params.building     = t(`buildings.${params.building}`,  { defaultValue: params.building });
        if (params.ship_capacity === 'wharf') params.ship_capacity = t('buildings.wharf', { defaultValue: '개인부두' });
        const text = t(`history.actions.${e.action}`, { ...params, defaultValue: e.action });
        return (
          <div key={i} style={{
            padding: '2px 0',
            borderBottom: isRoundEnd ? '1px solid #2a2a5a' : undefined,
            color: isRoundEnd ? '#f0c040' : '#c0d0e0',
            fontWeight: isRoundEnd ? 'bold' : undefined,
            marginTop: isRoundEnd ? 4 : undefined,
          }}>
            {!isRoundEnd && (
              <span style={{ color: '#556677', marginRight: 8 }}>{formatTs(e.ts)}</span>
            )}
            {text}
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
