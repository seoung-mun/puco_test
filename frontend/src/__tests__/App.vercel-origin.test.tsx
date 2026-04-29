import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

vi.mock('../components/GameScreen', () => ({
  default: () => null,
}));

vi.mock('../components/AppScreenGate', () => ({
  default: ({ screen, onJoinRoom, onBackFromLobby }: {
    screen: string;
    onJoinRoom: (roomId: string) => void;
    onBackFromLobby: () => Promise<void>;
  }) => {
    if (screen === 'rooms') {
      return <button onClick={() => onJoinRoom('room-1')}>JOIN_ROOM</button>;
    }
    if (screen === 'lobby') {
      return <button onClick={() => void onBackFromLobby()}>LEAVE_LOBBY</button>;
    }
    return <div>{screen.toUpperCase()}_GATE</div>;
  },
}));

class MockWebSocket {
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  close = vi.fn();
  send = vi.fn();

  constructor(public url: string) {}
}

async function loadApp() {
  vi.resetModules();
  return (await import('../App')).default;
}

describe('App Vercel origin flow', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('access_token', 'saved-token');
    vi.stubEnv('VITE_BACKEND_ORIGIN', 'https://backend.example');
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket);
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url === 'https://backend.example/api/puco/auth/me') {
        return new Response(JSON.stringify({
          id: 'user-1',
          nickname: 'Alice',
          needs_nickname: false,
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url === 'https://backend.example/api/puco/rooms/room-1/leave') {
        return new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      return new Response('Not found', { status: 404 });
    }));
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it('leaves the lobby through the configured backend origin', async () => {
    const App = await loadApp();
    const user = userEvent.setup();

    render(<App />);

    await screen.findByRole('button', { name: 'JOIN_ROOM' });
    await user.click(screen.getByRole('button', { name: 'JOIN_ROOM' }));
    await screen.findByRole('button', { name: 'LEAVE_LOBBY' });
    await user.click(screen.getByRole('button', { name: 'LEAVE_LOBBY' }));

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        'https://backend.example/api/puco/rooms/room-1/leave',
        expect.objectContaining({
          method: 'POST',
          headers: { Authorization: 'Bearer saved-token' },
        }),
      );
    });

    await screen.findByRole('button', { name: 'JOIN_ROOM' });
  });
});
