import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import LoginScreen from '../LoginScreen';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key: string, fallback?: string) => fallback ?? _key,
  }),
}));

vi.mock('@react-oauth/google', () => ({
  GoogleLogin: ({ onError }: { onError: () => void }) => (
    <button type="button" onClick={onError}>
      GOOGLE_LOGIN_BUTTON
    </button>
  ),
}));

describe('LoginScreen', () => {
  it('surfaces google widget setup errors through the provided callback', () => {
    const onGoogleLoginError = vi.fn();

    render(
      <LoginScreen
        onGoogleLogin={vi.fn()}
        onGoogleLoginError={onGoogleLoginError}
        googleLoginAvailable
        isLoggedIn={false}
        needsNickname={false}
        nicknameInput=""
        onNicknameChange={vi.fn()}
        onSetNickname={vi.fn()}
        nicknameError={null}
        error={null}
      />,
    );

    fireEvent.click(screen.getByText('GOOGLE_LOGIN_BUTTON'));

    expect(onGoogleLoginError).toHaveBeenCalledTimes(1);
  });

  it('does not render the google widget when the client id is missing', () => {
    render(
      <LoginScreen
        onGoogleLogin={vi.fn()}
        onGoogleLoginError={vi.fn()}
        googleLoginAvailable={false}
        isLoggedIn={false}
        needsNickname={false}
        nicknameInput=""
        onNicknameChange={vi.fn()}
        onSetNickname={vi.fn()}
        nicknameError={null}
        error={null}
      />,
    );

    expect(screen.queryByText('GOOGLE_LOGIN_BUTTON')).toBeNull();
    expect(screen.getByText('Google 로그인 설정이 비어 있어 버튼을 표시할 수 없습니다.')).toBeTruthy();
  });
});
