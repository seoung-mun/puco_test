import { useState } from 'react';
import { useTranslation } from 'react-i18next';

// UUID v4 pattern
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

interface Props {
  backendUrl: string;
  onJoin: (key: string, name: string, role: 'player' | 'spectator') => Promise<string | null>;
}

export default function JoinScreen({ onJoin }: Props) {
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

  return (
    <div className="resort-app-shell resort-app-shell--centered">
      <h1 className="resort-brand-title">Puerto Rico</h1>
      <div className="resort-card resort-card--compact">
        {step === 'key' && (
          <>
            <p className="resort-helper-text">{t('join.enterKey', 'Enter Game ID')}</p>
            <input
              value={key}
              onChange={e => setKey(e.target.value.trim())}
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              autoFocus
              className="resort-input resort-input--code"
              onKeyDown={e => e.key === 'Enter' && keyValid && handleKeyNext()}
            />
            <button className="resort-btn-primary" style={{ opacity: keyValid && !loading ? 1 : 0.5 }}
              onClick={handleKeyNext}
              disabled={!keyValid || loading}>
              {loading ? '...' : t('join.next')}
            </button>
            {error && <p className="resort-error" style={{ margin: 0 }}>{error}</p>}
          </>
        )}

        {step === 'name' && (
          <>
            <p className="resort-helper-text">{t('join.enterName')}</p>
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder={t('join.namePlaceholder')}
              autoFocus
              className="resort-input"
              onKeyDown={e => e.key === 'Enter' && name.trim() && handleJoin()}
            />
            <div style={{ display: 'flex', gap: 20 }}>
              {(['player', 'spectator'] as const).map(r => (
                <label key={r} className={`resort-radio-row${role === r ? ' resort-radio-row--active' : ''}`}>
                  <input type="radio" checked={role === r} onChange={() => setRole(r)} />
                  {t(`join.as_${r}`)}
                </label>
              ))}
            </div>
            {error && <p className="resort-error" style={{ margin: 0 }}>{error}</p>}
            <button className="resort-btn-primary" style={{ opacity: name.trim() && !loading ? 1 : 0.5 }}
              onClick={handleJoin}
              disabled={!name.trim() || loading}>
              {loading ? '...' : t('join.enter')}
            </button>
            <button className="resort-btn-link" onClick={() => { setStep('key'); setError(null); }}>{t('join.back')}</button>
          </>
        )}
      </div>
    </div>
  );
}
