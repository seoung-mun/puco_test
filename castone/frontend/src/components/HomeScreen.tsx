import { useState } from 'react';
import { useTranslation } from 'react-i18next';

interface Props {
  onMultiplayer: (hostName: string) => void;
  onLogout?: () => void;
  userNickname?: string | null;
  error?: string | null;
}

type View = 'main' | 'multiplayer';

export default function HomeScreen({ onMultiplayer, onLogout, userNickname, error }: Props) {
  const { t } = useTranslation();
  const [view, setView] = useState<View>('main');
  const [hostName, setHostName] = useState('');

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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', gap: 24 }}>
      <h1 style={{ color: '#f0c040', margin: 0, fontSize: 36 }}>Puerto Rico</h1>

      <div style={cardStyle}>

        {/* MAIN MENU */}
        {view === 'main' && (
          <button style={btnPrimary} onClick={() => setView('multiplayer')}>
            {t('home.onlineMultiplayer')}
          </button>
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

      {error && (
        <p style={{ color: '#f66', maxWidth: 400, textAlign: 'center' }}>{error}</p>
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 8 }}>
        {userNickname && (
          <span style={{ color: '#667', fontSize: 13 }}>{userNickname}</span>
        )}
        {onLogout && (
          <button style={btnLink} onClick={onLogout}>{t('home.logout', 'Logout')}</button>
        )}
      </div>
    </div>
  );
}
