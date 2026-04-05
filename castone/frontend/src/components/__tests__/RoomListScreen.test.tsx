import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import RoomListScreen from '../RoomListScreen';

describe('RoomListScreen', () => {
  beforeEach(() => {
    localStorage.setItem('lang', 'ko');

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url === '/api/puco/rooms/') {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url === '/api/bot-types') {
        return new Response(JSON.stringify([
          { type: 'random', name: 'Random Bot' },
          { type: 'ppo', name: 'PPO Bot' },
          { type: 'hppo', name: 'HPPO Bot' },
        ]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      return new Response('Not found', { status: 404 });
    });

    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it('submits the selected bot types when creating a bot game', async () => {
    const onCreateBotGame = vi.fn().mockResolvedValue(null);
    const user = userEvent.setup();

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

    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith('/api/bot-types'));

    await user.click(screen.getByRole('button', { name: /봇전$/ }));

    const botTypeSelects = await screen.findAllByRole('combobox');
    expect(botTypeSelects).toHaveLength(3);

    await user.selectOptions(botTypeSelects[0], 'ppo');
    await user.selectOptions(botTypeSelects[1], 'random');
    await user.selectOptions(botTypeSelects[2], 'ppo');

    await user.click(screen.getByRole('button', { name: /봇전 시작/ }));

    await waitFor(() => {
      expect(onCreateBotGame).toHaveBeenCalledWith(['ppo', 'random', 'ppo']);
    });
  });
});
