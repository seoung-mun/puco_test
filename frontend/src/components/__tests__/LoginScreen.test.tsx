import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, defaultValueOrOptions?: string | { defaultValue?: string }, maybeOptions?: Record<string, string>) => {
      const defaultValue =
        typeof defaultValueOrOptions === 'string'
          ? defaultValueOrOptions
          : defaultValueOrOptions?.defaultValue ?? key;
      return defaultValue;
    },
  }),
}));

vi.mock('../GoogleIdentityButton', () => ({
  default: () => <div>GOOGLE_LOGIN_BUTTON</div>,
}));

import LoginScreen from '../LoginScreen';

describe('LoginScreen', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('shows a config warning when the Google client id is missing', () => {
    vi.stubEnv('VITE_GOOGLE_CLIENT_ID', '');

    render(
      <LoginScreen
        onGoogleLogin={vi.fn()}
        isLoggedIn={false}
        needsNickname={false}
        nicknameInput=""
        onNicknameChange={vi.fn()}
        onSetNickname={vi.fn()}
        nicknameError={null}
        error={null}
      />,
    );

    expect(screen.getByText(/Google 로그인 설정이 비어 있습니다/i)).toBeTruthy();
    expect(screen.queryByText('GOOGLE_LOGIN_BUTTON')).toBeNull();
  });

  it('shows the Google login button when configured', () => {
    vi.stubEnv('VITE_GOOGLE_CLIENT_ID', 'test-client-id.apps.googleusercontent.com');

    render(
      <LoginScreen
        onGoogleLogin={vi.fn()}
        isLoggedIn={false}
        needsNickname={false}
        nicknameInput=""
        onNicknameChange={vi.fn()}
        onSetNickname={vi.fn()}
        nicknameError={null}
        error={null}
      />,
    );

    expect(screen.getByText('GOOGLE_LOGIN_BUTTON')).toBeTruthy();
    expect(screen.queryByText(/Authorized JavaScript origins/i)).toBeNull();
    expect(screen.queryByText(/현재 프런트가 쓰는 client ID/i)).toBeNull();
  });
});
