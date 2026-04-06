import { useState } from 'react';
import { useTranslation } from 'react-i18next';

// UUID v4 pattern
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

interface Props {
  backendUrl: string;
  onJoin: (key: string, name: string, role: 'player' | 'spectator') => Promise<string | null>;
}

export default function JoinScreen({ backendUrl: _backendUrl, onJoin }: Props) {
  const { t } = useTranslation();
  const [key, setKey] = useState('');
  const [name, setName] = useState('');
  const [role, setRole] = useState<'player' | 'spectator'>('player');
  const [step, setStep] = useState<'key' | 'name'>('key');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const keyValid = UUID_PATTERN.test(key.trim());

  function handleKeyNext() {
    if (!keyValid) {
      setError(t('join.invalidKey', 'Please enter a valid Game ID (UUID format)'));
      return;
    }
    setError(null);
    setStep('name');
  }

  async function handleJoin() {
    setLoading(true);
    setError(null);
    const err = await onJoin(key.trim(), name.trim(), role);
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
            <p style={{ color: '#aab', margin: 0 }}>{t('join.enterKey', 'Enter Game ID')}</p>
            <input
              value={key}
              onChange={e => setKey(e.target.value.trim())}
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              autoFocus
              style={{ padding: '8px 12px', borderRadius: 6, border: '1px solid #444', background: '#1a1a2e', color: '#f0c040', fontSize: 13, textAlign: 'center', width: '100%', fontFamily: 'monospace', boxSizing: 'border-box' }}
              onKeyDown={e => e.key === 'Enter' && keyValid && handleKeyNext()}
            />
            <button style={{ ...btnPrimary, opacity: keyValid && !loading ? 1 : 0.5 }}
              onClick={handleKeyNext}
              disabled={!keyValid || loading}>
              {loading ? '...' : t('join.next')}
            </button>
            {error && <p style={{ color: '#f66', margin: 0, fontSize: 13 }}>{error}</p>}
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
