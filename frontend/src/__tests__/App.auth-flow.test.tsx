import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { defaultValue?: string }) => options?.defaultValue ?? key,
  }),
}));

vi.mock('../i18n', () => ({
  default: {
    language: 'ko',
    changeLanguage: vi.fn(),
  },
}));

vi.mock('../hooks/useGameWebSocket', () => ({
  useGameWebSocket: vi.fn(),
}));

vi.mock('../hooks/useGameSSE', () => ({
  useGameSSE: vi.fn(),
}));

vi.mock('../components/LoginScreen', () => ({
  default: () => <div>LOGIN_SCREEN</div>,
}));

vi.mock('../components/HomeScreen', () => ({
  default: () => <div>HOME_SCREEN</div>,
}));

vi.mock('../components/RoomListScreen', () => ({
  default: () => <div>ROOMS_SCREEN</div>,
}));

vi.mock('../components/JoinScreen', () => ({
  default: () => <div>JOIN_SCREEN</div>,
}));

vi.mock('../components/LobbyScreen', () => ({
  default: () => <div>LOBBY_SCREEN</div>,
}));

vi.mock('../components/MetaPanel', () => ({
  default: () => null,
}));

vi.mock('../components/CommonBoardPanel', () => ({
  default: () => null,
}));

vi.mock('../components/PlayerPanel', () => ({
  default: () => null,
}));

vi.mock('../components/SanJuan', () => ({
  default: () => null,
}));

vi.mock('../components/AdminPanel', () => ({
  default: () => null,
}));

vi.mock('../components/PlayerAdvantages', () => ({
  default: () => null,
}));

vi.mock('../components/HistoryPanel', () => ({
  default: () => null,
}));

vi.mock('../components/EndGamePanel', () => ({
  default: () => null,
}));

import App from '../App';

describe('App auth flow', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows the login screen when there is no saved token', async () => {
    render(<App />);

    expect(await screen.findByText('LOGIN_SCREEN')).toBeTruthy();
    expect(screen.queryByText('ROOMS_SCREEN')).toBeNull();
  });

  it('goes straight to the online multiplayer room list when a saved token is valid', async () => {
    localStorage.setItem('access_token', 'saved-token');
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      json: async () => ({
        id: 'user-1',
        nickname: 'Alice',
        needs_nickname: false,
      }),
    } as Response);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('ROOMS_SCREEN')).toBeTruthy();
    });
    expect(screen.queryByText('LOGIN_SCREEN')).toBeNull();
    expect(fetch).toHaveBeenCalledWith(
      '/api/puco/auth/me',
      expect.objectContaining({
        headers: expect.any(Headers),
      }),
    );
  });

  it('clears an invalid saved token and returns to login', async () => {
    localStorage.setItem('access_token', 'stale-token');
    vi.mocked(fetch).mockResolvedValue({
      ok: false,
      json: async () => ({ detail: 'invalid token' }),
    } as Response);

    render(<App />);

    expect(await screen.findByText('LOGIN_SCREEN')).toBeTruthy();
    expect(localStorage.getItem('access_token')).toBeNull();
  });
});
