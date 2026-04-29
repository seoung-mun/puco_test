import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

async function loadLobbyScreen() {
  vi.resetModules();
  return (await import('../LobbyScreen')).default;
}

describe('LobbyScreen', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_BACKEND_ORIGIN', 'https://backend.example');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify([
      { type: 'random', name: 'Random Bot' },
    ]), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })));
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('shows a logout button inside the lobby header', async () => {
    const LobbyScreen = await loadLobbyScreen();

    render(
      <LobbyScreen
        players={[
          {
            name: 'Alice',
            player_id: 'user-1',
            connected: true,
            is_host: true,
            is_bot: false,
            is_spectator: false,
          },
        ]}
        host="Alice"
        myName="Alice"
        onStart={vi.fn()}
        onLogout={vi.fn()}
      />
    );

    expect(screen.getByRole('button', { name: /로그아웃/i })).toBeTruthy();
  });

  it('loads bot types through the configured backend origin', async () => {
    const LobbyScreen = await loadLobbyScreen();

    render(
      <LobbyScreen
        players={[
          {
            name: 'Alice',
            player_id: 'user-1',
            connected: true,
            is_host: true,
            is_bot: false,
            is_spectator: false,
          },
        ]}
        host="Alice"
        myName="Alice"
        onStart={vi.fn()}
        onLogout={vi.fn()}
        onAddBot={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith('https://backend.example/api/bot-types');
    });
  });
});
