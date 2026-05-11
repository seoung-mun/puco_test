import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { buildApiUrl } from '../config';
import GameScreen from './GameScreen';
import { useReplayPlayer } from '../hooks/useReplayPlayer';
import type { GameState } from '../types/gameState';
import type { ReplayDetailResponse } from '../types/replay';

interface Props {
  token: string;
  gameId: string;
  onBack: () => void;
}

const NOOP = () => {};
const NOOP_ASYNC = async () => {};

function buildReplayGameScreenProps(
  state: GameState,
  onBack: () => void,
): React.ComponentProps<typeof GameScreen> {
  return {
    backend: '',
    state,
    error: null,
    saving: false,
    passing: false,
    buildConfirm: null,
    pendingSettlement: null,
    roundFlash: null,
    discardProtected: [],
    discardSingleExtra: null,
    finalScores: state.result_summary ?? null,
    popups: [],
    isAdmin: false,
    isSpectator: false,
    isMultiplayer: false,
    myName: null,
    lobbyPlayers: [],
    isMyTurn: false,
    isBotTurn: false,
    isBlocked: true,
    interactionLocked: true,
    canPass: false,
    replayMode: true,
    onStateLoaded: NOOP,
    onGoToRoomsPreservingAuth: NOOP,
    onLogoutToLogin: NOOP,
    onExitSpectator: NOOP,
    onDismissError: NOOP,
    onClearPopups: NOOP,
    onConfirmBuild: NOOP,
    onCancelBuildConfirm: NOOP,
    onConfirmSettlement: NOOP,
    onSelectRole: NOOP_ASYNC,
    onSettlePlantation: NOOP,
    onUseHacienda: NOOP_ASYNC,
    onPlaceMayorColonist: NOOP_ASYNC,
    onPassAction: NOOP_ASYNC,
    onSellGood: NOOP_ASYNC,
    onCraftsmanPrivilege: NOOP_ASYNC,
    onLoadShip: NOOP_ASYNC,
    onCaptainPass: NOOP_ASYNC,
    onToggleDiscardProtected: NOOP,
    onSetDiscardSingleExtra: NOOP,
    onDoDiscardGoods: NOOP_ASYNC,
    onRequestBuild: NOOP,
    onReturnToRooms: onBack,
  };
}

export default function ReplayViewScreen({ token, gameId, onBack }: Props) {
  const { t } = useTranslation();
  const [detail, setDetail] = useState<ReplayDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setDetail(null);
    setError(null);
    setNotFound(false);
    fetch(buildApiUrl(`/api/puco/replays/${gameId}`), {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (res) => {
        if (res.status === 404) {
          if (!cancelled) setNotFound(true);
          return null;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return (await res.json()) as ReplayDetailResponse;
      })
      .then((body) => {
        if (!cancelled && body) setDetail(body);
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

  const frames = detail?.replay_frames ?? [];
  const player = useReplayPlayer({ frames });
  const {
    currentFrame,
    totalFrames,
    isPlaying,
    speed,
    frame,
    toggle,
    next,
    prev,
    stepForward,
    seek,
    setSpeed,
  } = player;
  const currentState = frame?.rich_state ?? null;
  const replayGameScreenProps = currentState
    ? buildReplayGameScreenProps(currentState, onBack)
    : null;

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

        {notFound && (
          <div
            data-testid="replay-not-found"
            style={{ textAlign: 'center', marginTop: 80, color: '#445' }}
          >
            <p style={{ fontSize: 16 }}>{t('replay.notFound')}</p>
            <button
              onClick={onBack}
              style={{
                marginTop: 16,
                background: '#2a5ab0',
                border: 'none',
                borderRadius: 6,
                color: '#fff',
                cursor: 'pointer',
                padding: '8px 18px',
                fontSize: 13,
              }}
            >
              ← {t('replay.back')}
            </button>
          </div>
        )}

        {error && !notFound && <p style={{ color: '#f66' }}>{error}</p>}

        {detail && totalFrames === 0 && !notFound && (
          <div style={{ textAlign: 'center', marginTop: 60, color: '#556' }}>
            <p style={{ fontSize: 15 }}>{t('replay.noFrames')}</p>
          </div>
        )}

        {detail && totalFrames > 0 && (
          <>
            <div
              style={{
                display: 'grid',
                gap: 12,
                padding: '12px 16px',
                background: '#0d1117',
                border: '1px solid #1a1a3a',
                borderRadius: 8,
                marginBottom: 16,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <button
                  aria-label={t('replay.player.jumpBack')}
                  onClick={() => seek(currentFrame - 10)}
                  disabled={currentFrame === 0}
                  style={controlBtn(currentFrame === 0)}
                >
                  -10
                </button>
                <button
                  aria-label={t('replay.player.prev')}
                  onClick={prev}
                  disabled={currentFrame === 0}
                  style={controlBtn(currentFrame === 0)}
                >
                  ‹
                </button>
                <button
                  aria-label={isPlaying ? t('replay.player.pause') : t('replay.player.play')}
                  onClick={toggle}
                  disabled={totalFrames <= 1}
                  style={controlBtn(totalFrames <= 1)}
                >
                  {isPlaying ? '❚❚' : '▶'}
                </button>
                <button
                  aria-label={t('replay.player.next')}
                  onClick={next}
                  disabled={currentFrame >= totalFrames - 1}
                  style={controlBtn(currentFrame >= totalFrames - 1)}
                >
                  ›
                </button>
                <button
                  aria-label={t('replay.player.jumpForward')}
                  onClick={() => stepForward(10)}
                  disabled={currentFrame >= totalFrames - 1}
                  style={controlBtn(currentFrame >= totalFrames - 1)}
                >
                  +10
                </button>
                <span style={{ color: '#aab', fontSize: 13, minWidth: 90 }}>
                  {t('replay.player.frame', { current: currentFrame + 1, total: totalFrames })}
                </span>
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
              <input
                type="range"
                min={0}
                max={totalFrames - 1}
                value={currentFrame}
                onChange={(e) => seek(parseInt(e.target.value, 10))}
                aria-label={t('replay.player.frame', { current: currentFrame + 1, total: totalFrames })}
                style={{ width: '100%' }}
              />
            </div>

            <div
              data-testid="replay-frame-info"
              style={{
                background: '#0d1117',
                border: '1px solid #1a1a3a',
                borderRadius: 8,
                padding: 16,
                marginBottom: 16,
              }}
            >
              <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 8, color: '#aab', fontSize: 13 }}>
                <span>
                  <strong style={{ color: '#dde' }}>{t('replay.player.step')}:</strong> {frame?.step ?? '-'}
                </span>
                <span>
                  <strong style={{ color: '#dde' }}>{t('replay.player.currentAction')}:</strong> {frame?.action ?? '-'}
                </span>
              </div>
              {frame?.commentary && (
                <p style={{ color: '#9bf', fontSize: 13, margin: '6px 0' }}>
                  <strong style={{ color: '#dde' }}>{t('replay.player.commentary')}:</strong> {frame.commentary}
                </p>
              )}
            </div>

            {replayGameScreenProps && (
              <div
                style={{
                  border: '1px solid #1a1a3a',
                  borderRadius: 10,
                  overflow: 'hidden',
                }}
              >
                <GameScreen {...replayGameScreenProps} />
              </div>
            )}
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
