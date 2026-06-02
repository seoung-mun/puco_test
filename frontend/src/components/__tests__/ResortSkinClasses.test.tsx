import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import HomeScreen from '../HomeScreen';
import LoginScreen from '../LoginScreen';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key: string, fallback?: string) => fallback ?? _key,
  }),
}));

vi.mock('@react-oauth/google', () => ({
  GoogleLogin: () => <button type="button">GOOGLE_LOGIN_BUTTON</button>,
}));

describe('resort skin presentation classes', () => {
  it('marks entry screens with shared resort shell and card classes', () => {
    const { rerender } = render(
      <LoginScreen
        onGoogleLogin={vi.fn()}
        onGoogleLoginError={vi.fn()}
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

    expect(screen.getByText('Puerto Rico').closest('.resort-app-shell')).toBeTruthy();
    expect(screen.getByText('GOOGLE_LOGIN_BUTTON').closest('.resort-card')).toBeTruthy();

    rerender(
      <HomeScreen
        onMultiplayer={vi.fn()}
        onLogout={vi.fn()}
        userNickname="tester"
        error={null}
      />,
    );

    expect(screen.getByRole('button', { name: 'home.onlineMultiplayer' }).closest('.resort-card')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'home.onlineMultiplayer' }).classList.contains('resort-btn-primary')).toBe(true);
  });
});
