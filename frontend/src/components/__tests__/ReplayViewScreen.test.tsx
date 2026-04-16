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
    players: [
      { display_name: 'seoungmun', is_bot: false },
    ],
    replay_frames: [
      { frame_index: 0, step: 0, action: 'Select Role: Builder', commentary: 'Phase END_ROUND -> BUILDER', rich_state: { meta: { round: 1 } } as any },
      { frame_index: 1, step: 1, action: 'Pass', commentary: null, rich_state: { meta: { round: 1 } } as any },
      { frame_index: 2, step: 2, action: 'Pass', commentary: null, rich_state: { meta: { round: 2 } } as any },
    ],
    total_frames: 3,
    final_scores: [],
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
    expect(screen.getByTestId('replay-frame-info').textContent).toContain('Select Role: Builder');
  });

  it('next advances frame', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse(makeDetail()));
    render(<ReplayViewScreen token="tok" gameId="g1" onBack={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText('04_13_Random_PPO_seoungmun_01')).toBeTruthy();
    });

    const nextBtn = screen.getByRole('button', { name: '다음' });
    await userEvent.click(nextBtn);
    expect(screen.getByTestId('replay-frame-info').textContent).toContain('Pass');
  });

  it('shows not-found state on 404', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse({ detail: 'not found' }, 404));
    render(<ReplayViewScreen token="tok" gameId="g1" onBack={() => {}} />);
    await waitFor(() => {
      expect(screen.getByTestId('replay-not-found')).toBeTruthy();
    });
  });

  it('onBack invoked from back button', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse(makeDetail()));
    const onBack = vi.fn();
    render(<ReplayViewScreen token="tok" gameId="g1" onBack={onBack} />);
    const buttons = screen.getAllByRole('button');
    await userEvent.click(buttons[0]);
    expect(onBack).toHaveBeenCalled();
  });

  it('shows error on non-404 HTTP failure', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse({}, 500));
    render(<ReplayViewScreen token="tok" gameId="g1" onBack={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText(/HTTP 500/)).toBeTruthy();
    });
  });
});
