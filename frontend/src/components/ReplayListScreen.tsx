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
    <div className="resort-page-shell">
      <div className="resort-app-header">
        <div className="resort-header-left">
          <button
            onClick={onBack}
            className="resort-btn-ghost"
          >
            ← {t('replay.back')}
          </button>
          <h1 className="resort-page-title" style={{ fontSize: 22 }}>{t('replay.title')}</h1>
        </div>
        <div className="resort-header-actions">
          {userNickname && <span className="resort-user-pill">{userNickname}</span>}
          <button
            onClick={refresh}
            className="resort-btn-ghost"
          >
            {t('rooms.refresh')}
          </button>
        </div>
      </div>

      <div className="resort-page-content">
        <div className="resort-toolbar" style={{ marginBottom: 20 }}>
          <input
            value={queryInput}
            onChange={(e) => setQueryInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') submitSearch();
            }}
            placeholder={t('replay.search.placeholder')}
            aria-label={t('replay.search.placeholder')}
            className="resort-input"
            style={{ minWidth: 260 }}
          />
          <button
            onClick={submitSearch}
            className="resort-btn-primary"
            style={{ padding: '8px 16px', width: 'auto', fontSize: 13 }}
          >
            {t('replay.search.submit')}
          </button>
          {query && (
            <button
              onClick={handleReset}
              className="resort-btn-secondary"
            >
              {t('replay.search.reset')}
            </button>
          )}
        </div>

        {loading && <p className="resort-muted">{t('replay.loading')}</p>}
        {error && <p className="resort-error">{error}</p>}

        {!loading && data && data.replays.length === 0 && (
          <div className="resort-empty-state">
            <p style={{ fontSize: 16 }}>{t('replay.empty')}</p>
          </div>
        )}

        {!loading && data && data.replays.length > 0 && (
          <table className="replay-table">
            <thead>
              <tr>
                <th>{t('replay.column.label')}</th>
                <th>{t('replay.column.players')}</th>
                <th>{t('replay.column.date')}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.replays.map((r) => (
                <tr key={r.game_id}>
                  <td className="replay-table__primary">{r.display_label}</td>
                  <td className="replay-table__primary">
                    {r.players.map((p) => p.display_name).join(', ')}
                  </td>
                  <td className="replay-table__muted">{r.played_date}</td>
                  <td>
                    <button
                      onClick={() => setPending(r)}
                      className="resort-btn-primary"
                      style={{ padding: '6px 14px', width: 'auto', fontSize: 13 }}
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
