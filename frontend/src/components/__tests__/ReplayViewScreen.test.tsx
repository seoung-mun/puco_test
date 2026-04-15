import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ReplayViewScreen from '../ReplayViewScreen';
import type { ReplayDetailResponse } from '../../types/replay';

function mockResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function makeDetail(): ReplayDetailResponse {
  return {
    game_id: 'g1',
    display_label: '04_13_Random_PPO_seoungmun_01',
    title: 'bot game',
    players: [
      { actor_id: 'p1', display_name: 'seoungmun', is_bot: false },
    ],
    played_date: '2026-04-13',
    created_at: '2026-04-13T12:00:00Z',
    finished_at: '2026-04-13T12:30:00Z',
    winner_id: 'p1',
    frames: [
      { turn: 0, phase: 'role_selection', actor_id: 'p1', action: { type: 'select_role', role: 'mayor' }, rich_state: null },
      { turn: 1, phase: 'mayor_action', actor_id: 'p1', action: { type: 'pass' }, rich_state: { governor_id: 'p1' } },
      { turn: 2, phase: 'settler_action', actor_id: 'p1', action: { type: 'pass' }, rich_state: null },
    ],
  };
}

describe('ReplayViewScreen', () => {
  beforeEach(() => {
    localStorage.setItem('lang', 'ko');
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches detail and renders initial frame', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse(makeDetail()));
    render(<ReplayViewScreen token="tok" gameId="g1" onBack={() => {}} />);

    await waitFor(() => {
      expect(screen.getByText('04_13_Random_PPO_seoungmun_01')).toBeTruthy();
    });
    expect(screen.getByTestId('replay-frame-info').textContent).toContain('role_selection');
    expect(screen.getByTestId('replay-frame-info').textContent).toContain('select_role');
  });

  it('next advances frame', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse(makeDetail()));
    render(<ReplayViewScreen token="tok" gameId="g1" onBack={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText('04_13_Random_PPO_seoungmun_01')).toBeTruthy();
    });

    const nextBtn = screen.getByRole('button', { name: '다음' });
    await userEvent.click(nextBtn);
    expect(screen.getByTestId('replay-frame-info').textContent).toContain('mayor_action');
  });

  it('shows no-rich message on frame without rich_state', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse(makeDetail()));
    render(<ReplayViewScreen token="tok" gameId="g1" onBack={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText('04_13_Random_PPO_seoungmun_01')).toBeTruthy();
    });
    expect(screen.getByText(/상세 상태 정보가 없습니다/)).toBeTruthy();
  });

  it('onBack invoked from back button', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse(makeDetail()));
    const onBack = vi.fn();
    render(<ReplayViewScreen token="tok" gameId="g1" onBack={onBack} />);
    const buttons = screen.getAllByRole('button');
    await userEvent.click(buttons[0]);
    expect(onBack).toHaveBeenCalled();
  });

  it('shows error on HTTP failure', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse({ detail: 'nope' }, 404));
    render(<ReplayViewScreen token="tok" gameId="g1" onBack={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText(/HTTP 404/)).toBeTruthy();
    });
  });
});
