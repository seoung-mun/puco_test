import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

async function loadRoomListScreen() {
  vi.resetModules();
  return (await import('../RoomListScreen')).default;
}

describe('RoomListScreen', () => {
  beforeEach(() => {
    localStorage.setItem('lang', 'ko');
    vi.stubEnv('VITE_BACKEND_ORIGIN', 'https://backend.example');

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url === 'https://backend.example/api/puco/rooms/') {
        return new Response(JSON.stringify([
          {
            id: 'room-1',
            title: 'Open Room',
            status: 'waiting',
            is_private: false,
            current_players: 1,
            max_players: 3,
            player_names: [{ display_name: 'Alice', is_bot: false }],
          },
        ]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url === 'https://backend.example/api/bot-types') {
        return new Response(JSON.stringify([
          { type: 'random', name: 'Random Bot' },
          { type: 'action_value', name: 'Action Value Bot' },
          { type: 'shipping_rush', name: 'Shipping Rush Bot' },
          { type: 'ppo', name: 'PPO Bot' },
          { type: 'hppo', name: 'HPPO Bot' },
        ]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url === 'https://backend.example/api/puco/rooms/room-1/join') {
        return new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      return new Response('Not found', { status: 404 });
    });

    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it('loads room data and bot types through the configured backend origin', async () => {
    const onCreateBotGame = vi.fn().mockResolvedValue(null);
    const user = userEvent.setup();
    const RoomListScreen = await loadRoomListScreen();

    render(
      <RoomListScreen
        token="test-token"
        userNickname="tester"
        onJoinRoom={vi.fn()}
        onCreateRoom={vi.fn().mockResolvedValue(null)}
        onCreateBotGame={onCreateBotGame}
        onLogout={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        'https://backend.example/api/puco/rooms/',
        expect.objectContaining({
          headers: { Authorization: 'Bearer test-token' },
        }),
      );
    });

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith('https://backend.example/api/bot-types');
    });

    await user.click(screen.getByRole('button', { name: /봇전$/ }));

    const botTypeSelects = await screen.findAllByRole('combobox');
    expect(botTypeSelects).toHaveLength(3);
    expect(screen.queryByRole('option', { name: 'HPPO Bot' })).toBeNull();

    await user.selectOptions(botTypeSelects[0], 'ppo');
    await user.selectOptions(botTypeSelects[1], 'random');
    await user.selectOptions(botTypeSelects[2], 'ppo');

    await user.click(screen.getByRole('button', { name: /봇전 시작/ }));

    await waitFor(() => {
      expect(onCreateBotGame).toHaveBeenCalledWith(['ppo', 'random', 'ppo']);
    });
  });

  it('joins a public room through the configured backend origin', async () => {
    const onJoinRoom = vi.fn();
    const user = userEvent.setup();
    const RoomListScreen = await loadRoomListScreen();

    render(
      <RoomListScreen
        token="test-token"
        userNickname="tester"
        onJoinRoom={onJoinRoom}
        onCreateRoom={vi.fn().mockResolvedValue(null)}
        onLogout={vi.fn()}
      />
    );

    await screen.findByText('Open Room');
    await user.click(screen.getByRole('button', { name: '입장하기' }));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        'https://backend.example/api/puco/rooms/room-1/join',
        expect.objectContaining({
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: 'Bearer test-token',
          },
        }),
      );
    });

    expect(onJoinRoom).toHaveBeenCalledWith('room-1');
  });
});
