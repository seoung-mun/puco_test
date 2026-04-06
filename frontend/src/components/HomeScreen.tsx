import { useTranslation } from 'react-i18next';

interface Props {
  onMultiplayer: () => void;
  onLogout?: () => void;
  userNickname?: string | null;
  error?: string | null;
}

export default function HomeScreen({ onMultiplayer, onLogout, userNickname, error }: Props) {
  const { t } = useTranslation();

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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', gap: 24 }}>
      <h1 style={{ color: '#f0c040', margin: 0, fontSize: 36 }}>Puerto Rico</h1>

      <div style={cardStyle}>
        <button style={btnPrimary} onClick={onMultiplayer}>
          {t('home.onlineMultiplayer')}
        </button>
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
