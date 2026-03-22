import { useState } from 'react';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';

interface Props {
  gameExists: boolean;
  onContinue: () => void;
  onStartOffline: (numPlayers: number, names: string[], botTypes: string[]) => Promise<void>;
  onMultiplayer: (hostName: string) => void;
  error?: string | null;
}

type View = 'main' | 'offline_choose' | 'offline_setup' | 'multiplayer';

const BOT_NAMES = [
  // Star Wars
  'Vader', 'Yoda', 'Obi-Wan', 'Palpatine', 'Han Solo', 'Mace Windu',
  // Signore degli Anelli
  'Gandalf', 'Saruman', 'Aragorn', 'Legolas', 'Gimli', 'Gollum',
  // Matrix
  'Morpheus', 'Agent Smith', 'Oracle', 'Trinity',
  // Alien
  'Ripley', 'Ash', 'Bishop',
];

let namePool = [...BOT_NAMES];
function pickBotName(): string {
  if (namePool.length === 0) namePool = [...BOT_NAMES];
  const idx = Math.floor(Math.random() * namePool.length);
  return namePool.splice(idx, 1)[0];
}

export default function HomeScreen({ gameExists, onContinue, onStartOffline, onMultiplayer, error }: Props) {
  const { t } = useTranslation();
  const [view, setView] = useState<View>('main');
  const [hostName, setHostName] = useState('');
  const [loading, setLoading] = useState(false);

  // Offline setup state
  const [numPlayers, setNumPlayers] = useState(3);
  const [names, setNames] = useState(['', '', '', '', '']);
  const [botTypes, setBotTypes] = useState(['', 'scoring', 'scoring', 'scoring', 'scoring']);

  // Auto-fill bot names on mount
  useEffect(() => {
    const initial = ['', '', '', '', ''];
    for (let i = 1; i < 5; i++) initial[i] = pickBotName();
    setNames(initial);
  }, []);

  const cardStyle: React.CSSProperties = {
    background: '#0d1117',
    border: '1px solid #2a2a5a',
    borderRadius: 12,
    padding: '32px 40px',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 16,
    minWidth: 340,
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

  const btnSecondary: React.CSSProperties = {
    background: 'transparent',
    color: '#8af',
    border: '1px solid #2a5ab0',
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

  const inputStyle: React.CSSProperties = {
    padding: '8px 12px',
    borderRadius: 6,
    border: '1px solid #444',
    background: '#1a1a2e',
    color: '#eee',
    fontSize: 15,
    boxSizing: 'border-box',
  };

  const selectStyle: React.CSSProperties = {
    ...inputStyle,
    cursor: 'pointer',
  };

  function handleOfflineClick() {
    if (gameExists) {
      setView('offline_choose');
    } else {
      setView('offline_setup');
    }
  }

  async function handleStart() {
    const trimmed = names.slice(0, numPlayers).map(n => n.trim());
    if (trimmed.some(n => n === '')) return;
    setLoading(true);
    try {
      await onStartOffline(numPlayers, trimmed, botTypes.slice(0, numPlayers));
    } finally {
      setLoading(false);
    }
  }

  const canStart = names.slice(0, numPlayers).every(n => n.trim() !== '');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', gap: 24 }}>
      <h1 style={{ color: '#f0c040', margin: 0, fontSize: 36 }}>Puerto Rico</h1>

      <div style={cardStyle}>

        {/* MAIN MENU */}
        {view === 'main' && (
          <>
            <button style={btnPrimary} onClick={handleOfflineClick}>
              {t('home.offline')}
            </button>
            <button style={btnSecondary} onClick={() => setView('multiplayer')}>
              {t('home.onlineMultiplayer')}
            </button>
          </>
        )}

        {/* OFFLINE: CONTINUE OR NEW */}
        {view === 'offline_choose' && (
          <>
            <button style={btnPrimary} onClick={onContinue}>
              {t('home.continueGame')}
            </button>
            <button style={btnSecondary} onClick={() => setView('offline_setup')}>
              {t('home.newGame')}
            </button>
            <button style={btnLink} onClick={() => setView('main')}>{t('home.back')}</button>
          </>
        )}

        {/* OFFLINE SETUP FORM */}
        {view === 'offline_setup' && (
          <>
            <p style={{ color: '#aab', margin: 0, fontWeight: 600, fontSize: 15 }}>{t('home.newGame')}</p>

            {/* Number of players */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, width: '100%' }}>
              <label style={{ color: '#aab', whiteSpace: 'nowrap' }}>{t('newGame.numPlayers')}</label>
              <select
                value={numPlayers}
                onChange={e => {
                  const n = Number(e.target.value);
                  setNumPlayers(n);
                  // Auto-fill names for bot slots that are newly visible
                  const updatedNames = [...names];
                  for (let i = 0; i < n; i++) {
                    if (botTypes[i] && !updatedNames[i].trim()) {
                      updatedNames[i] = pickBotName();
                    }
                  }
                  setNames(updatedNames);
                }}
                style={{ ...selectStyle, flex: 1 }}
              >
                {[2, 3, 4, 5].map(n => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>

            {/* Player rows */}
            {Array.from({ length: numPlayers }, (_, i) => (
              <div key={i} style={{ display: 'flex', gap: 8, width: '100%' }}>
                <input
                  placeholder={t('newGame.playerName', { n: i + 1 })}
                  value={names[i]}
                  onChange={e => { const n = [...names]; n[i] = e.target.value; setNames(n); }}
                  style={{ ...inputStyle, flex: 2 }}
                />
                <select
                  value={botTypes[i]}
                  onChange={e => {
                    const b = [...botTypes]; b[i] = e.target.value; setBotTypes(b);
                    // Auto-fill a name when switching to bot (if field is still empty or default)
                    if (e.target.value && !names[i].trim()) {
                      const n = [...names]; n[i] = pickBotName(); setNames(n);
                    }
                  }}
                  style={{ ...selectStyle, flex: 1 }}
                >
                  <option value="">{t('newGame.human')}</option>
                  <option value="random">🎲 {t('newGame.botRandom')}</option>
                  <option value="scoring">⚙️ {t('newGame.botSmart')}</option>
                  <option value="gemini">🤖 {t('newGame.botGemini')}</option>
                </select>
              </div>
            ))}

            <p style={{ color: '#668', margin: 0, fontSize: 12 }}>{t('newGame.govNote')}</p>

            <button
              style={{ ...btnPrimary, opacity: canStart && !loading ? 1 : 0.5 }}
              onClick={handleStart}
              disabled={!canStart || loading}
            >
              {loading ? t('newGame.starting') : t('newGame.start')}
            </button>
            {error && (
              <div style={{ color: '#f88', background: '#300', border: '1px solid #f44', borderRadius: 6, padding: '8px 14px', fontSize: 13 }}>
                {error}
              </div>
            )}
            <button style={btnLink} onClick={() => setView(gameExists ? 'offline_choose' : 'main')}>
              {t('home.back')}
            </button>
          </>
        )}

        {/* MULTIPLAYER: ENTER HOST NAME */}
        {view === 'multiplayer' && (
          <>
            <p style={{ color: '#aab', margin: 0 }}>{t('home.enterHostName')}</p>
            <input
              value={hostName}
              onChange={e => setHostName(e.target.value)}
              placeholder={t('home.yourName')}
              autoFocus
              style={{ ...inputStyle, width: '100%' }}
              onKeyDown={e => e.key === 'Enter' && hostName.trim() && onMultiplayer(hostName.trim())}
            />
            <button
              style={{ ...btnPrimary, opacity: hostName.trim() ? 1 : 0.5 }}
              onClick={() => hostName.trim() && onMultiplayer(hostName.trim())}
              disabled={!hostName.trim()}
            >
              {t('home.startMultiplayer')}
            </button>
            <button style={btnLink} onClick={() => setView('main')}>{t('home.back')}</button>
          </>
        )}

      </div>
    </div>
  );
}
