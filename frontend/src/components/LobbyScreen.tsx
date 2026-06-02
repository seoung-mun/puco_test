import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import type { LobbyPlayer } from '../types/gameState';
import { buildApiUrl } from '../config';

interface BotAgent { type: string; name: string; }

interface Props {
  players: LobbyPlayer[];
  host: string;
  myName: string;
  onStart: () => void;
  onLogout: () => void;
  onAddBot?: (name: string, botType: string) => void;
  onRemoveBot?: (slotIndex: number) => void;
  error?: string | null;
  onBack?: () => void;
}

export default function LobbyScreen({ players, host, myName, onStart, onLogout, onAddBot, onRemoveBot, error, onBack }: Props) {
  const { t } = useTranslation();
  const isHost = myName === host;
  const activePlayers = players.filter(p => !p.is_spectator);
  const connectedActive = activePlayers.filter(p => p.connected !== false || p.is_bot);
  const canStart = isHost && connectedActive.length >= 3;
  const hostPlayer = players.find(p => p.is_host);
  const hostConnected = hostPlayer?.connected ?? false;

  const [addingBot, setAddingBot] = useState(false);
  const [newBotType, setNewBotType] = useState('');
  const [botAgents, setBotAgents] = useState<BotAgent[]>([]);

  const canAddBot = isHost && activePlayers.length < 3;

  useEffect(() => {
    fetch(buildApiUrl('/api/bot-types'))
      .then(r => r.json())
      .then((data: BotAgent[]) => {
        setBotAgents(data);
        if (data.length > 0) setNewBotType(data[0].type);
      })
      .catch(() => {});
  }, []);

  function autoName(type: string): string {
    const agent = botAgents.find(a => a.type === type);
    const baseName = agent?.name ?? type;
    const usedNames = players.map(p => p.name);
    if (!usedNames.includes(baseName)) return baseName;
    let n = 2;
    while (usedNames.includes(`${baseName} ${n}`)) n++;
    return `${baseName} ${n}`;
  }

  function handleConfirmAddBot() {
    if (onAddBot && newBotType) {
      onAddBot(autoName(newBotType), newBotType);
      setAddingBot(false);
    }
  }

  return (
    <div className="resort-page-shell">
    <div className="lobby-shell">
      <div className="lobby-topbar">
        <div>
          {onBack && (
            <button
              onClick={onBack}
              className="resort-btn-link"
              style={{ fontSize: 14 }}
            >
              ← {t('lobby.back')}
            </button>
          )}
        </div>
        <div className="resort-header-actions">
          {myName && (
            <span className="resort-user-pill">
              {myName}
            </span>
          )}
          <button
            onClick={onLogout}
            className="resort-btn-ghost"
          >
            {t('home.logout', '로그아웃')}
          </button>
        </div>
      </div>
      <h1 className="lobby-title">
        Puerto Rico — {t('lobby.title')}
      </h1>

      {!isHost && !hostConnected && (
        <div className="resort-alert" style={{ marginBottom: 16, textAlign: 'center' }}>
          {t('lobby.hostDisconnected')}
        </div>
      )}

      <div className="lobby-panel">
        <div className="lobby-panel__label">
          {t('lobby.players')} ({activePlayers.length}/3)
        </div>
        {players.map((p, idx) => (
          <div key={p.player_id ?? `player-${idx}`} className="lobby-row">
            <span className={`status-dot ${(p.is_bot || p.connected) ? 'status-dot--online' : 'status-dot--offline'}`} />
            <span className={`lobby-row__name${p.name === myName ? ' lobby-row__name--me' : ''}`}>
              {p.is_bot && <span style={{ marginRight: 4 }}>🤖</span>}
              {p.name}
            </span>
            {p.is_host && <span className="lobby-row__meta">👑 host</span>}
            {p.is_spectator && <span className="lobby-row__spectator">{t('lobby.spectator')}</span>}
            {isHost && p.is_bot && onRemoveBot && (
              <button
                onClick={() => onRemoveBot(idx)}
                className="resort-btn-danger"
              >×</button>
            )}
          </div>
        ))}
        {players.length === 0 && (
          <div className="room-card__empty">{t('lobby.noPlayers')}</div>
        )}

        {/* Add bot form */}
        {canAddBot && (
          <div style={{ marginTop: 12 }}>
            {addingBot ? (
              <div className="lobby-bot-form">
                <select
                  value={newBotType}
                  onChange={e => setNewBotType(e.target.value)}
                  className="resort-select"
                  style={{ flex: 1, padding: '4px 6px', fontSize: 13 }}
                  autoFocus
                >
                  {botAgents.map(a => (
                    <option key={a.type} value={a.type}>{a.name}</option>
                  ))}
                </select>
                <button
                  onClick={handleConfirmAddBot}
                  disabled={!newBotType}
                  className="resort-btn-icon"
                >✓</button>
                <button
                  onClick={() => setAddingBot(false)}
                  className="resort-btn-icon"
                >✗</button>
              </div>
            ) : (
              <button
                onClick={() => setAddingBot(true)}
                className="resort-btn-secondary"
                style={{ borderStyle: 'dashed', width: '100%' }}
              >
                {t('lobby.addBot')}
              </button>
            )}
          </div>
        )}
      </div>

      {error && <p className="resort-error" style={{ textAlign: 'center', marginBottom: 12 }}>{error}</p>}

      {isHost ? (
        <button
          className="resort-btn-primary"
          style={{ width: '100%', padding: '13px 0', fontSize: 16, cursor: canStart ? 'pointer' : 'not-allowed', opacity: canStart ? 1 : 0.55 }}
          onClick={onStart}
          disabled={!canStart}
        >
          {canStart ? t('lobby.start') : t('lobby.needMorePlayers', { n: 3 - connectedActive.length })}
        </button>
      ) : (
        <p className="lobby-waiting">{t('lobby.waitingHost')}</p>
      )}

    </div>
    </div>
  );
}
