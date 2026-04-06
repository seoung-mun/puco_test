import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import LobbyScreen from '../LobbyScreen';

describe('LobbyScreen', () => {
  it('shows a logout button inside the lobby header', () => {
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
});
