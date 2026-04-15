import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useReplayPlayer } from '../hooks/useReplayPlayer';
import type { ReplayDetailResponse } from '../types/replay';

interface Props {
  token: string;
  gameId: string;
  onBack: () => void;
}

export default function ReplayViewScreen({ token, gameId, onBack }: Props) {
  const { t } = useTranslation();
  const [detail, setDetail] = useState<ReplayDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetch(`/api/puco/replays/${gameId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return (await res.json()) as ReplayDetailResponse;
      })
      .then((body) => {
        if (!cancelled) setDetail(body);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, gameId]);

  const frames = detail?.frames ?? [];
  const player = useReplayPlayer({ frames });
  const { currentFrame, totalFrames, isPlaying, speed, frame, toggle, next, prev, seek, setSpeed } = player;

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
          <h1 style={{ color: '#f0c040', margin: 0, fontSize: 20 }}>
            {detail?.display_label ?? t('replay.title')}
          </h1>
        </div>
      </div>

      <div style={{ padding: '24px 32px' }}>
        {loading && <p style={{ color: '#667' }}>{t('replay.loading')}</p>}
        {error && <p style={{ color: '#f66' }}>{error}</p>}

        {detail && totalFrames > 0 && (
          <>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: '12px 16px',
                background: '#0d1117',
                border: '1px solid #1a1a3a',
                borderRadius: 8,
                marginBottom: 16,
              }}
            >
              <button
                aria-label={t('replay.player.prev')}
                onClick={prev}
                disabled={currentFrame === 0}
                style={controlBtn(currentFrame === 0)}
              >
                «
              </button>
              <button
                aria-label={isPlaying ? t('replay.player.pause') : t('replay.player.play')}
                onClick={toggle}
                style={controlBtn(false)}
              >
                {isPlaying ? '❚❚' : '▶'}
              </button>
              <button
                aria-label={t('replay.player.next')}
                onClick={next}
                disabled={currentFrame >= totalFrames - 1}
                style={controlBtn(currentFrame >= totalFrames - 1)}
              >
                »
              </button>
              <span style={{ color: '#aab', fontSize: 13, minWidth: 90 }}>
                {t('replay.player.frame', { current: currentFrame + 1, total: totalFrames })}
              </span>
              <input
                type="range"
                min={0}
                max={totalFrames - 1}
                value={currentFrame}
                onChange={(e) => seek(parseInt(e.target.value, 10))}
                aria-label={t('replay.player.frame', { current: currentFrame + 1, total: totalFrames })}
                style={{ flex: 1 }}
              />
              <label style={{ color: '#aab', fontSize: 13 }}>
                {t('replay.player.speed')}:
                <select
                  value={speed}
                  onChange={(e) => setSpeed(parseInt(e.target.value, 10))}
                  style={{
                    marginLeft: 6,
                    background: '#1a1a2e',
                    color: '#eee',
                    border: '1px solid #444',
                    borderRadius: 4,
                    padding: '2px 6px',
                  }}
                >
                  {[1, 2, 4, 8].map((s) => (
                    <option key={s} value={s}>
                      {s}x
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div
              data-testid="replay-frame-info"
              style={{
                background: '#0d1117',
                border: '1px solid #1a1a3a',
                borderRadius: 8,
                padding: 16,
              }}
            >
              <div style={{ marginBottom: 8, color: '#aab', fontSize: 13 }}>
                <strong style={{ color: '#dde' }}>Turn:</strong> {frame?.turn ?? '-'} &nbsp;
                <strong style={{ color: '#dde' }}>Phase:</strong> {frame?.phase ?? '-'} &nbsp;
                <strong style={{ color: '#dde' }}>Actor:</strong> {frame?.actor_id ?? '-'}
              </div>
              <pre
                style={{
                  margin: 0,
                  fontSize: 12,
                  color: '#9bf',
                  background: '#05090f',
                  padding: 10,
                  borderRadius: 6,
                  overflow: 'auto',
                }}
              >
                {JSON.stringify(frame?.action ?? {}, null, 2)}
              </pre>
              {!frame?.rich_state && (
                <p style={{ color: '#778', fontSize: 12, marginTop: 8 }}>
                  {t('replay.player.noRich')}
                </p>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function controlBtn(disabled: boolean): React.CSSProperties {
  return {
    background: disabled ? '#1a1a2e' : '#2a5ab0',
    border: 'none',
    borderRadius: 6,
    color: disabled ? '#556' : '#fff',
    cursor: disabled ? 'not-allowed' : 'pointer',
    padding: '6px 12px',
    fontSize: 14,
    minWidth: 40,
  };
}
