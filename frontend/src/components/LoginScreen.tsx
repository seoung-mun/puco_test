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
  const googleClientIdConfigured = Boolean(import.meta.env.VITE_GOOGLE_CLIENT_ID);
  const currentOrigin = typeof window !== 'undefined' ? window.location.origin : '';
  const preferredDevOrigin = 'http://localhost:3000';
  const isLocalOrigin =
    typeof window !== 'undefined' &&
    ['localhost', '127.0.0.1'].includes(window.location.hostname);
  const isPreferredDevOrigin = currentOrigin === preferredDevOrigin;

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

  const hintStyle: React.CSSProperties = {
    color: '#aab',
    margin: 0,
    fontSize: 12,
    lineHeight: 1.5,
    textAlign: 'center',
  };

  const warningStyle: React.CSSProperties = {
    color: '#ffd7a1',
    background: '#3a2400',
    border: '1px solid #b36b00',
    borderRadius: 6,
    padding: '10px 14px',
    fontSize: 13,
    lineHeight: 1.5,
    width: '100%',
    boxSizing: 'border-box',
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
            {googleClientIdConfigured ? (
              <>
                <GoogleLogin
                  onSuccess={onGoogleLogin}
                  onError={() => {}}
                  theme="filled_black"
                  size="large"
                  shape="rectangular"
                  width="280"
                />
                {isLocalOrigin && (
                  <div style={warningStyle}>
                    <strong style={{ display: 'block', marginBottom: 6 }}>
                      {t('login.googleOriginGuideTitle', '개발용 Google 로그인 안내')}
                    </strong>
                    <p style={{ ...hintStyle, color: '#ffe7bf', textAlign: 'left' }}>
                      {t(
                        'login.googleOriginCurrent',
                        '현재 접속 origin: {{origin}}',
                        { origin: currentOrigin },
                      )}
                    </p>
                    {!isPreferredDevOrigin && (
                      <p style={{ ...hintStyle, color: '#ffe7bf', textAlign: 'left' }}>
                        {t(
                          'login.googleOriginPreferred',
                          'dev에서는 {{origin}} 접속을 권장합니다. 127.0.0.1로 열었다면 localhost로 다시 접속하세요.',
                          { origin: preferredDevOrigin },
                        )}
                      </p>
                    )}
                    <p style={{ ...hintStyle, color: '#ffe7bf', textAlign: 'left' }}>
                      {t(
                        'login.googleOriginHint',
                        'Google Cloud Console의 Authorized JavaScript origins에 {{origin}} 을 정확히 추가해야 403 / origin not allowed 오류가 사라집니다.',
                        { origin: isPreferredDevOrigin ? preferredDevOrigin : currentOrigin },
                      )}
                    </p>
                  </div>
                )}
              </>
            ) : (
              <div style={warningStyle}>
                {t(
                  'login.googleConfigMissing',
                  'Google 로그인 설정이 비어 있습니다. VITE_GOOGLE_CLIENT_ID를 설정한 뒤 frontend 이미지를 다시 빌드하세요.',
                )}
              </div>
            )}
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
