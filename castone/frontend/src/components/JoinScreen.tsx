import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { ServerInfo } from '../types/gameState';

interface Props {
  backendUrl: string;
  onJoin: (key: string, name: string, role: 'player' | 'spectator') => Promise<string | null>;
}

export default function JoinScreen({ backendUrl, onJoin }: Props) {
  const { t } = useTranslation();
  const [key, setKey] = useState('');
  const [name, setName] = useState('');
  const [role, setRole] = useState<'player' | 'spectator'>('player');
  const [step, setStep] = useState<'key' | 'reconnect' | 'name'>('key');
  const [offlinePlayers, setOfflinePlayers] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleKeyNext() {
    setLoading(true);
    setError(null);
    try {
      const info: ServerInfo = await fetch(`${backendUrl}/api/server-info`).then(r => r.json());
      if (info.lobby_status === 'playing' && info.players) {
        const offline = info.players.filter(p => !p.connected && !p.is_spectator).map(p => p.name);
        if (offline.length > 0) {
          setOfflinePlayers(offline);
          setName(offline[0]);
          setStep('reconnect');
          return;
        }
      }
      setStep('name');
    } catch {
      setError('Cannot reach server');
    } finally {
      setLoading(false);
    }
  }

  async function handleJoin() {
    setLoading(true);
    setError(null);
    const err = await onJoin(key.trim().toUpperCase(), name.trim(), role);
    setLoading(false);
    if (err) setError(err);
  }

  const cardStyle: React.CSSProperties = {
    background: '#0d1117',
    border: '1px solid #2a2a5a',
    borderRadius: 12,
    padding: '32px 40px',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 16,
    minWidth: 320,
  };

  const btnPrimary: React.CSSProperties = {
    background: '#2a5ab0',
    color: '#fff',
    border: 'none',
    borderRadius: 8,
    padding: '12px 32px',
    fontSize: 16,
    cursor: 'pointer',
    width: '100%',
  };

  const btnLink: React.CSSProperties = {
    background: 'none',
    border: 'none',
    color: '#667',
    cursor: 'pointer',
    fontSize: 13,
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', gap: 24 }}>
      <h1 style={{ color: '#f0c040', margin: 0, fontSize: 36 }}>Puerto Rico</h1>
      <div style={cardStyle}>
        {step === 'key' && (
          <>
            <p style={{ color: '#aab', margin: 0 }}>{t('join.enterKey')}</p>
            <input
              value={key}
              onChange={e => setKey(e.target.value.toUpperCase())}
              placeholder="XXXXXX"
              maxLength={6}
              autoFocus
              style={{ padding: '8px 12px', borderRadius: 6, border: '1px solid #444', background: '#1a1a2e', color: '#f0c040', fontSize: 24, textAlign: 'center', letterSpacing: 6, width: 160, fontFamily: 'monospace' }}
              onKeyDown={e => e.key === 'Enter' && key.trim().length === 6 && handleKeyNext()}
            />
            <button style={{ ...btnPrimary, opacity: key.trim().length === 6 && !loading ? 1 : 0.5 }}
              onClick={handleKeyNext}
              disabled={key.trim().length !== 6 || loading}>
              {loading ? '...' : t('join.next')}
            </button>
            {error && <p style={{ color: '#f66', margin: 0, fontSize: 13 }}>{error}</p>}
          </>
        )}

        {step === 'reconnect' && (
          <>
            <p style={{ color: '#aab', margin: 0 }}>{t('join.whoAreYou')}</p>
            <select
              value={name}
              onChange={e => setName(e.target.value)}
              autoFocus
              style={{ padding: '8px 12px', borderRadius: 6, border: '1px solid #444', background: '#1a1a2e', color: '#eee', fontSize: 16, width: '100%' }}
            >
              {offlinePlayers.map(p => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
            {error && <p style={{ color: '#f66', margin: 0, fontSize: 13 }}>{error}</p>}
            <button style={{ ...btnPrimary, opacity: !loading ? 1 : 0.5 }}
              onClick={handleJoin}
              disabled={loading}>
              {loading ? '...' : t('join.enter')}
            </button>
            <button style={btnLink} onClick={() => { setStep('key'); setError(null); }}>{t('join.back')}</button>
          </>
        )}

        {step === 'name' && (
          <>
            <p style={{ color: '#aab', margin: 0 }}>{t('join.enterName')}</p>
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder={t('join.namePlaceholder')}
              autoFocus
              style={{ padding: '8px 12px', borderRadius: 6, border: '1px solid #444', background: '#1a1a2e', color: '#eee', fontSize: 16, width: '100%', boxSizing: 'border-box' }}
              onKeyDown={e => e.key === 'Enter' && name.trim() && handleJoin()}
            />
            <div style={{ display: 'flex', gap: 20 }}>
              {(['player', 'spectator'] as const).map(r => (
                <label key={r} style={{ color: role === r ? '#f0c040' : '#aab', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}>
                  <input type="radio" checked={role === r} onChange={() => setRole(r)} />
                  {t(`join.as_${r}`)}
                </label>
              ))}
            </div>
            {error && <p style={{ color: '#f66', margin: 0, fontSize: 13 }}>{error}</p>}
            <button style={{ ...btnPrimary, opacity: name.trim() && !loading ? 1 : 0.5 }}
              onClick={handleJoin}
              disabled={!name.trim() || loading}>
              {loading ? '...' : t('join.enter')}
            </button>
            <button style={btnLink} onClick={() => { setStep('key'); setError(null); }}>{t('join.back')}</button>
          </>
        )}
      </div>
    </div>
  );
}
