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
    <div className="resort-page-shell">
      <div className="resort-app-header">
        <div className="resort-header-left">
          <button
            onClick={onBack}
            className="resort-btn-ghost"
          >
            ← {t('replay.back')}
          </button>
          <h1 className="resort-page-title" style={{ fontSize: 20 }}>
            {detail?.display_label ?? t('replay.title')}
          </h1>
        </div>
      </div>

      <div className="resort-page-content">
        {loading && <p className="resort-muted">{t('replay.loading')}</p>}

        {notFound && (
          <div
            data-testid="replay-not-found"
            className="resort-empty-state"
          >
            <p style={{ fontSize: 16 }}>{t('replay.notFound')}</p>
            <button
              onClick={onBack}
              className="resort-btn-primary"
              style={{ marginTop: 16, padding: '8px 18px', width: 'auto', fontSize: 13 }}
            >
              ← {t('replay.back')}
            </button>
          </div>
        )}

        {error && !notFound && <p className="resort-error">{error}</p>}

        {detail && totalFrames === 0 && !notFound && (
          <div className="resort-empty-state" style={{ marginTop: 60 }}>
            <p style={{ fontSize: 15 }}>{t('replay.noFrames')}</p>
          </div>
        )}

        {detail && totalFrames > 0 && (
          <>
            <div className="replay-control-panel">
              <div className="resort-toolbar" style={{ gap: 10 }}>
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
                <span className="resort-muted" style={{ fontSize: 13, minWidth: 90 }}>
                  {t('replay.player.frame', { current: currentFrame + 1, total: totalFrames })}
                </span>
                <label className="resort-muted" style={{ fontSize: 13 }}>
                  {t('replay.player.speed')}:
                  <select
                    value={speed}
                    onChange={(e) => setSpeed(parseInt(e.target.value, 10))}
                    className="resort-select"
                    style={{ marginLeft: 6, padding: '2px 6px', width: 'auto' }}
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
              className="replay-frame-panel"
            >
              <div className="resort-toolbar" style={{ gap: 16, marginBottom: 8, fontSize: 13 }}>
                <span>
                  <strong>{t('replay.player.step')}:</strong> {frame?.step ?? '-'}
                </span>
                <span>
                  <strong>{t('replay.player.currentAction')}:</strong> {frame?.action ?? '-'}
                </span>
              </div>
              {frame?.commentary && (
                <p style={{ color: 'var(--resort-ocean-deep)', fontSize: 13, margin: '6px 0' }}>
                  <strong>{t('replay.player.commentary')}:</strong> {frame.commentary}
                </p>
              )}
            </div>

            {replayGameScreenProps && (
              <div className="replay-game-frame">
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
    background: disabled ? 'rgba(255,255,255,0.48)' : 'linear-gradient(135deg, var(--resort-ocean) 0%, var(--resort-emerald) 100%)',
    border: disabled ? '1px solid var(--resort-border)' : '1px solid rgba(0, 126, 118, 0.28)',
    borderRadius: 6,
    color: disabled ? 'rgba(94, 118, 111, 0.5)' : '#fff',
    cursor: disabled ? 'not-allowed' : 'pointer',
    padding: '6px 12px',
    fontSize: 14,
    minWidth: 40,
  };
}
