import { GoogleLogin } from '@react-oauth/google';
import { useTranslation } from 'react-i18next';

interface Props {
  onGoogleLogin: (credentialResponse: { credential?: string }) => void;
  isLoggedIn: boolean;
  needsNickname: boolean;
  nicknameInput: string;
  onNicknameChange: (value: string) => void;
  onSetNickname: () => void;
  nicknameError: string | null;
  error: string | null;
}

export default function LoginScreen({
  onGoogleLogin,
  isLoggedIn,
  needsNickname,
  nicknameInput,
  onNicknameChange,
  onSetNickname,
  nicknameError,
  error,
}: Props) {
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

  const inputStyle: React.CSSProperties = {
    padding: '8px 12px',
    borderRadius: 6,
    border: '1px solid #444',
    background: '#1a1a2e',
    color: '#eee',
    fontSize: 15,
    boxSizing: 'border-box',
    width: '100%',
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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', gap: 24 }}>
      <h1 style={{ color: '#f0c040', margin: 0, fontSize: 36 }}>Puerto Rico</h1>

      <div style={cardStyle}>
        {!isLoggedIn && (
          <>
            <p style={{ color: '#aab', margin: 0, fontSize: 14 }}>
              {t('login.signInPrompt', 'Google 계정으로 로그인하세요')}
            </p>
            <GoogleLogin
              onSuccess={onGoogleLogin}
              onError={() => {}}
              theme="filled_black"
              size="large"
              shape="rectangular"
              width="280"
            />
          </>
        )}

        {isLoggedIn && needsNickname && (
          <>
            <p style={{ color: '#aab', margin: 0, fontSize: 14 }}>
              {t('login.setNickname', '닉네임을 설정해주세요')}
            </p>
            <input
              value={nicknameInput}
              onChange={e => onNicknameChange(e.target.value)}
              placeholder={t('login.nicknamePlaceholder', '2-20자, 영문/한글/숫자/_/-')}
              style={inputStyle}
              onKeyDown={e => e.key === 'Enter' && nicknameInput.trim() && onSetNickname()}
            />
            <button
              style={{ ...btnPrimary, opacity: nicknameInput.trim() ? 1 : 0.5 }}
              onClick={onSetNickname}
              disabled={!nicknameInput.trim()}
            >
              {t('login.confirm', '확인')}
            </button>
            {nicknameError && (
              <div style={{ color: '#f88', background: '#300', border: '1px solid #f44', borderRadius: 6, padding: '8px 14px', fontSize: 13 }}>
                {nicknameError}
              </div>
            )}
          </>
        )}

        {error && (
          <div style={{ color: '#f88', background: '#300', border: '1px solid #f44', borderRadius: 6, padding: '8px 14px', fontSize: 13 }}>
            {error}
          </div>
        )}
      </div>
    </div>
  );
}
