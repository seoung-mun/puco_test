import { GoogleLogin } from '@react-oauth/google';
import { useTranslation } from 'react-i18next';

interface Props {
  onGoogleLogin: (credentialResponse: { credential?: string }) => void;
  onGoogleLoginError: () => void;
  googleLoginAvailable: boolean;
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
  onGoogleLoginError,
  googleLoginAvailable,
  isLoggedIn,
  needsNickname,
  nicknameInput,
  onNicknameChange,
  onSetNickname,
  nicknameError,
  error,
}: Props) {
  const { t } = useTranslation();

  return (
    <div className="resort-app-shell resort-app-shell--centered">
      <h1 className="resort-brand-title">Puerto Rico</h1>

      <div className="resort-card">
        {!isLoggedIn && (
          <>
            <p className="resort-helper-text">
              {t('login.signInPrompt', 'Google 계정으로 로그인하세요')}
            </p>
            {googleLoginAvailable ? (
              <GoogleLogin
                onSuccess={onGoogleLogin}
                onError={onGoogleLoginError}
                use_fedcm_for_button
                theme="outline"
                size="large"
                shape="rectangular"
                width="280"
              />
            ) : (
              <div className="resort-helper-text" style={{ textAlign: 'center' }}>
                {t('login.googleSetupRequired', 'Google 로그인 설정이 비어 있어 버튼을 표시할 수 없습니다.')}
              </div>
            )}
          </>
        )}

        {isLoggedIn && needsNickname && (
          <>
            <p className="resort-helper-text">
              {t('login.setNickname', '닉네임을 설정해주세요')}
            </p>
            <input
              value={nicknameInput}
              onChange={e => onNicknameChange(e.target.value)}
              placeholder={t('login.nicknamePlaceholder', '2-20자, 영문/한글/숫자/_/-')}
              className="resort-input"
              onKeyDown={e => e.key === 'Enter' && nicknameInput.trim() && onSetNickname()}
            />
            <button
              className="resort-btn-primary"
              style={{ opacity: nicknameInput.trim() ? 1 : 0.5 }}
              onClick={onSetNickname}
              disabled={!nicknameInput.trim()}
            >
              {t('login.confirm', '확인')}
            </button>
            {nicknameError && (
              <div className="resort-error">
                {nicknameError}
              </div>
            )}
          </>
        )}

        {error && (
          <div className="resort-error">
            {error}
          </div>
        )}
      </div>
    </div>
  );
}
