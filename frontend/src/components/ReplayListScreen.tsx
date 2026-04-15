import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useReplayList } from '../hooks/useReplayList';
import type { ReplayListItem } from '../types/replay';
import Pagination from './Pagination';
import ReplayConfirmModal from './ReplayConfirmModal';

interface Props {
  token: string;
  userNickname?: string | null;
  onBack: () => void;
  onOpenReplay: (gameId: string) => void;
}

export default function ReplayListScreen({ token, userNickname, onBack, onOpenReplay }: Props) {
  const { t } = useTranslation();
  const { data, loading, error, page, query, setPage, search, reset, refresh } = useReplayList({
    authToken: token,
  });
  const [queryInput, setQueryInput] = useState('');
  const [pending, setPending] = useState<ReplayListItem | null>(null);

  function submitSearch() {
    search(queryInput);
  }

  function handleReset() {
    setQueryInput('');
    reset();
  }

  return (
    <div style={{ minHeight: '100vh', background: '#070d18', color: '#dde', fontFamily: 'sans-serif' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '20px 32px',
          borderBottom: '1px solid #1a1a3a',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <button
            onClick={onBack}
            style={{
              background: 'none',
              border: '1px solid #2a2a5a',
              borderRadius: 6,
              color: '#88a',
              cursor: 'pointer',
              padding: '7px 14px',
              fontSize: 13,
            }}
          >
            ← {t('replay.back')}
          </button>
          <h1 style={{ color: '#f0c040', margin: 0, fontSize: 22 }}>{t('replay.title')}</h1>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {userNickname && <span style={{ color: '#88a', fontSize: 13 }}>{userNickname}</span>}
          <button
            onClick={refresh}
            style={{
              background: 'none',
              border: '1px solid #2a2a5a',
              borderRadius: 6,
              color: '#88a',
              cursor: 'pointer',
              padding: '7px 14px',
              fontSize: 13,
            }}
          >
            {t('rooms.refresh')}
          </button>
        </div>
      </div>

      <div style={{ padding: '24px 32px' }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 20 }}>
          <input
            value={queryInput}
            onChange={(e) => setQueryInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') submitSearch();
            }}
            placeholder={t('replay.search.placeholder')}
            aria-label={t('replay.search.placeholder')}
            style={{
              padding: '8px 12px',
              borderRadius: 6,
              border: '1px solid #444',
              background: '#1a1a2e',
              color: '#eee',
              fontSize: 14,
              minWidth: 260,
            }}
          />
          <button
            onClick={submitSearch}
            style={{
              background: '#2a5ab0',
              border: 'none',
              borderRadius: 6,
              color: '#fff',
              cursor: 'pointer',
              padding: '8px 16px',
              fontSize: 13,
            }}
          >
            {t('replay.search.submit')}
          </button>
          {query && (
            <button
              onClick={handleReset}
              style={{
                background: 'none',
                border: '1px solid #2a2a5a',
                borderRadius: 6,
                color: '#aab',
                cursor: 'pointer',
                padding: '8px 16px',
                fontSize: 13,
              }}
            >
              {t('replay.search.reset')}
            </button>
          )}
        </div>

        {loading && <p style={{ color: '#667' }}>{t('replay.loading')}</p>}
        {error && <p style={{ color: '#f66' }}>{error}</p>}

        {!loading && data && data.replays.length === 0 && (
          <div style={{ textAlign: 'center', marginTop: 80, color: '#445' }}>
            <p style={{ fontSize: 16 }}>{t('replay.empty')}</p>
          </div>
        )}

        {!loading && data && data.replays.length > 0 && (
          <table
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontSize: 14,
              background: '#0d1117',
              border: '1px solid #1a1a3a',
              borderRadius: 8,
              overflow: 'hidden',
            }}
          >
            <thead>
              <tr style={{ background: '#111827', color: '#aab', textAlign: 'left' }}>
                <th style={{ padding: '10px 14px' }}>{t('replay.column.label')}</th>
                <th style={{ padding: '10px 14px' }}>{t('replay.column.players')}</th>
                <th style={{ padding: '10px 14px' }}>{t('replay.column.date')}</th>
                <th style={{ padding: '10px 14px' }}></th>
              </tr>
            </thead>
            <tbody>
              {data.replays.map((r) => (
                <tr
                  key={r.game_id}
                  style={{ borderTop: '1px solid #1a1a3a' }}
                >
                  <td style={{ padding: '10px 14px', color: '#dde' }}>{r.display_label}</td>
                  <td style={{ padding: '10px 14px', color: '#ccf' }}>
                    {r.players.map((p) => p.display_name).join(', ')}
                  </td>
                  <td style={{ padding: '10px 14px', color: '#aab' }}>{r.played_date}</td>
                  <td style={{ padding: '10px 14px' }}>
                    <button
                      onClick={() => setPending(r)}
                      style={{
                        background: '#2a5ab0',
                        border: 'none',
                        borderRadius: 6,
                        color: '#fff',
                        cursor: 'pointer',
                        padding: '6px 14px',
                        fontSize: 13,
                      }}
                    >
                      {t('replay.action.watch')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {!loading && data && data.total_pages > 1 && (
          <div style={{ marginTop: 20 }}>
            <Pagination page={page} totalPages={data.total_pages} onPageChange={setPage} />
          </div>
        )}
      </div>

      <ReplayConfirmModal
        open={pending !== null}
        displayLabel={pending?.display_label ?? ''}
        playerNames={pending ? pending.players.map((p) => p.display_name) : []}
        playedDate={pending?.played_date ?? ''}
        onConfirm={() => {
          if (pending) {
            const id = pending.game_id;
            setPending(null);
            onOpenReplay(id);
          }
        }}
        onCancel={() => setPending(null)}
      />
    </div>
  );
}
