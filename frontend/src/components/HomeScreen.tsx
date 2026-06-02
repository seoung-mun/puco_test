import { useTranslation } from 'react-i18next';

interface Props {
  onMultiplayer: () => void;
  onLogout?: () => void;
  userNickname?: string | null;
  error?: string | null;
}

export default function HomeScreen({ onMultiplayer, onLogout, userNickname, error }: Props) {
  const { t } = useTranslation();

  return (
    <div className="resort-app-shell resort-app-shell--centered">
      <h1 className="resort-brand-title">Puerto Rico</h1>

      <div className="resort-card">
        <button className="resort-btn-primary" onClick={onMultiplayer}>
          {t('home.onlineMultiplayer')}
        </button>
      </div>

      {error && (
        <p className="resort-error" style={{ maxWidth: 400, textAlign: 'center' }}>{error}</p>
      )}

      <div className="resort-entry-footer">
        {userNickname && (
          <span className="resort-muted" style={{ fontSize: 13 }}>{userNickname}</span>
        )}
        {onLogout && (
          <button className="resort-btn-link" onClick={onLogout}>{t('home.logout', 'Logout')}</button>
        )}
      </div>
    </div>
  );
}
