import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ReplayListScreen from '../ReplayListScreen';
import type { ReplayListResponse } from '../../types/replay';

function mockResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function makeList(overrides?: Partial<ReplayListResponse>): ReplayListResponse {
  return {
    replays: [
      {
        index: 1,
        game_id: 'g1',
        display_label: '04_13_Random_PPO_seoungmun_01',
        human_player_names: ['seoungmun'],
        players: [
          { display_name: 'seoungmun', is_bot: false },
          { display_name: 'Random', is_bot: true },
        ],
        played_date: '2026-04-13',
        created_at: '2026-04-13T12:00:00Z',
        num_players: 2,
        winner: 'seoungmun',
      },
    ],
    page: 1,
    size: 10,
    total_items: 1,
    total_pages: 1,
    ...overrides,
  };
}

describe('ReplayListScreen', () => {
  beforeEach(() => {
    localStorage.setItem('lang', 'ko');
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders replay rows when data loads', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse(makeList()));
    render(
      <ReplayListScreen
        token="tok"
        onBack={() => {}}
        onOpenReplay={() => {}}
      />
    );
    await waitFor(() => {
      expect(screen.getByText('04_13_Random_PPO_seoungmun_01')).toBeTruthy();
    });
    expect(screen.getByText(/2026-04-13/)).toBeTruthy();
  });

  it('search input triggers fetch with player param', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse(makeList()));
    render(
      <ReplayListScreen token="tok" onBack={() => {}} onOpenReplay={() => {}} />
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const input = screen.getByRole('textbox');
    await userEvent.type(input, 'seoungmun{Enter}');
    await waitFor(() => {
      const urls = fetchMock.mock.calls.map((c) => String(c[0]));
      expect(urls.some((u) => u.includes('player=seoungmun'))).toBe(true);
    });
  });

  it('clicking watch opens confirm modal, confirm calls onOpenReplay', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse(makeList()));
    const onOpen = vi.fn();
    render(
      <ReplayListScreen token="tok" onBack={() => {}} onOpenReplay={onOpen} />
    );
    await waitFor(() => {
      expect(screen.getByText('04_13_Random_PPO_seoungmun_01')).toBeTruthy();
    });
    // Find watch button within the row (first button in table cell)
    const tableWatchButtons = screen.getAllByRole('button').filter((b) =>
      b.textContent?.match(/관전|watch|guarda/i)
    );
    expect(tableWatchButtons.length).toBeGreaterThan(0);
    await userEvent.click(tableWatchButtons[0]);

    const dialog = await screen.findByRole('dialog');
    expect(dialog).toBeTruthy();
    // Confirm button inside dialog is the last button
    const dialogButtons = within(dialog).getAllByRole('button');
    await userEvent.click(dialogButtons[dialogButtons.length - 1]);
    expect(onOpen).toHaveBeenCalledWith('g1');
  });

  it('onBack invoked when back button clicked', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse(makeList({ replays: [] })));
    const onBack = vi.fn();
    render(
      <ReplayListScreen token="tok" onBack={onBack} onOpenReplay={() => {}} />
    );
    const buttons = screen.getAllByRole('button');
    await userEvent.click(buttons[0]);
    expect(onBack).toHaveBeenCalled();
  });

  it('shows empty message when no replays', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse(makeList({ replays: [], total_items: 0, total_pages: 0 })));
    render(
      <ReplayListScreen token="tok" onBack={() => {}} onOpenReplay={() => {}} />
    );
    await waitFor(() => {
      expect(screen.queryByRole('table')).toBeNull();
    });
  });
});
