import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import type { LobbyPlayer } from '../types/gameState';

interface BotAgent { type: string; name: string; }

interface Props {
  players: LobbyPlayer[];
  host: string;
  myName: string;
  onStart: () => void;
  onLogout: () => void;
  onAddBot?: (name: string, botType: string) => void;
  onRemoveBot?: (name: string) => void;
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
    fetch('/api/bot-types')
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
    <div style={{ maxWidth: 520, margin: '60px auto', padding: '0 20px' }}>
      {onBack && (
        <button
          onClick={onBack}
          style={{ position: 'absolute', top: 16, left: 16, background: 'none', border: 'none', color: '#aab', cursor: 'pointer', fontSize: 14 }}
        >
          ← {t('lobby.back')}
        </button>
      )}
      <h1 style={{ color: '#f0c040', textAlign: 'center', marginBottom: 24 }}>
        Puerto Rico — {t('lobby.title')}
      </h1>

      {!isHost && !hostConnected && (
        <div style={{ background: '#2a1010', border: '1px solid #f44', borderRadius: 8, padding: 12, marginBottom: 16, color: '#f99', textAlign: 'center' }}>
          {t('lobby.hostDisconnected')}
        </div>
      )}

      <div style={{ background: '#0d1117', border: '1px solid #2a2a5a', borderRadius: 8, padding: '16px 20px', marginBottom: 16 }}>
        <div style={{ color: '#aab', fontSize: 12, marginBottom: 10 }}>
          {t('lobby.players')} ({activePlayers.length}/3)
        </div>
        {players.map((p, idx) => (
          <div key={p.player_id ?? `player-${idx}`} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 0', borderBottom: '1px solid #1a1a3a' }}>
            <span style={{ width: 9, height: 9, borderRadius: '50%', background: (p.is_bot || p.connected) ? '#3d3' : '#c33', flexShrink: 0, display: 'inline-block' }} />
            <span style={{ color: p.name === myName ? '#f0c040' : '#dde', fontWeight: p.name === myName ? 'bold' : 'normal', flex: 1 }}>
              {p.is_bot && <span style={{ marginRight: 4 }}>🤖</span>}
              {p.name}
            </span>
            {p.is_host && <span style={{ color: '#f0c040', fontSize: 12 }}>👑 host</span>}
            {p.is_spectator && <span style={{ color: '#667', fontSize: 12 }}>{t('lobby.spectator')}</span>}
            {isHost && p.is_bot && onRemoveBot && (
              <button
                onClick={() => onRemoveBot(p.name)}
                style={{ background: 'none', border: '1px solid #444', borderRadius: 4, color: '#888', cursor: 'pointer', fontSize: 13, padding: '1px 7px', lineHeight: 1.4 }}
              >×</button>
            )}
          </div>
        ))}
        {players.length === 0 && (
          <div style={{ color: '#445', fontStyle: 'italic', fontSize: 13 }}>{t('lobby.noPlayers')}</div>
        )}

        {/* Add bot form */}
        {canAddBot && (
          <div style={{ marginTop: 12 }}>
            {addingBot ? (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <select
                  value={newBotType}
                  onChange={e => setNewBotType(e.target.value)}
                  style={{ flex: 1, background: '#0a0f1e', border: '1px solid #2a2a5a', borderRadius: 4, color: '#dde', padding: '4px 6px', fontSize: 13 }}
                  autoFocus
                >
                  {botAgents.map(a => (
                    <option key={a.type} value={a.type}>{a.name}</option>
                  ))}
                </select>
                <button
                  onClick={handleConfirmAddBot}
                  disabled={!newBotType}
                  style={{ background: '#1a4a20', border: '1px solid #3a7a40', borderRadius: 4, color: '#7f7', cursor: 'pointer', padding: '4px 10px', fontSize: 13 }}
                >✓</button>
                <button
                  onClick={() => setAddingBot(false)}
                  style={{ background: 'none', border: '1px solid #444', borderRadius: 4, color: '#888', cursor: 'pointer', padding: '4px 10px', fontSize: 13 }}
                >✗</button>
              </div>
            ) : (
              <button
                onClick={() => setAddingBot(true)}
                style={{ background: 'none', border: '1px dashed #2a4a6a', borderRadius: 6, color: '#6af', cursor: 'pointer', fontSize: 13, padding: '6px 12px', width: '100%' }}
              >
                {t('lobby.addBot')}
              </button>
            )}
          </div>
        )}
      </div>

      {error && <p style={{ color: '#f66', textAlign: 'center', marginBottom: 12 }}>{error}</p>}

      {isHost ? (
        <button
          style={{ width: '100%', padding: '13px 0', fontSize: 16, borderRadius: 8, border: 'none', cursor: canStart ? 'pointer' : 'not-allowed', background: canStart ? '#2a5ab0' : '#1a2a40', color: canStart ? '#fff' : '#556' }}
          onClick={onStart}
          disabled={!canStart}
        >
          {canStart ? t('lobby.start') : t('lobby.needMorePlayers', { n: 3 - connectedActive.length })}
        </button>
      ) : (
        <p style={{ textAlign: 'center', color: '#aab' }}>{t('lobby.waitingHost')}</p>
      )}

      <button
        style={{ display: 'block', margin: '18px auto 0', background: 'none', border: 'none', color: '#556', cursor: 'pointer', fontSize: 13 }}
        onClick={onLogout}
      >
        {t('lobby.logout')}
      </button>
    </div>
  );
}
