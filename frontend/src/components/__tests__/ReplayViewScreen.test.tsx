import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { GameState, Player } from '../../types/gameState';
import type { ReplayDetailResponse } from '../../types/replay';

async function loadReplayViewScreen() {
  vi.resetModules();
  vi.doMock('../GameScreen', () => ({
    default: ({ state, replayMode }: { state: { meta: { round: number } }; replayMode?: boolean }) => (
      <div data-testid="game-screen-proxy">
        {replayMode ? 'replay' : 'normal'}:{state.meta.round}:{state.meta.phase}
      </div>
    ),
  }));
  return (await import('../ReplayViewScreen')).default;
}

async function loadReplayViewScreenWithRealGameScreen() {
  vi.resetModules();
  vi.doUnmock('../GameScreen');
  vi.doMock('../MetaPanel', () => ({
    default: ({ meta }: { meta: { round: number; phase: string } }) => (
      <div data-testid="meta-panel">
        {meta.round}:{meta.phase}
      </div>
    ),
  }));
  vi.doMock('../CommonBoardPanel', () => ({
    default: () => <div data-testid="common-board-panel" />,
  }));
  vi.doMock('../PlayerPanel', () => ({
    default: ({ player }: { player: { display_name: string } }) => <div>{player.display_name}</div>,
  }));
  vi.doMock('../SanJuan', () => ({
    default: () => <div data-testid="san-juan-panel" />,
  }));
  vi.doMock('../AdminPanel', () => ({
    default: () => null,
  }));
  vi.doMock('../PlayerAdvantages', () => ({
    default: () => null,
  }));
  vi.doMock('../HistoryPanel', () => ({
    default: () => <div data-testid="history-panel" />,
  }));
  vi.doMock('../EndGamePanel', () => ({
    default: () => null,
  }));
  return (await import('../ReplayViewScreen')).default;
}

function mockResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function makePlayer(name: string, displayNumber: number, isGovernor = false): Player {
  return {
    display_name: name,
    display_number: displayNumber,
    is_governor: isGovernor,
    doubloons: 0,
    vp_chips: 0,
    goods: {
      corn: 0,
      indigo: 0,
      sugar: 0,
      tobacco: 0,
      coffee: 0,
      d_total: 0,
    },
    island: {
      total_spaces: 12,
      d_used_spaces: 0,
      d_empty_spaces: 12,
      d_active_quarries: 0,
      plantations: [],
    },
    city: {
      total_spaces: 12,
      d_used_spaces: 0,
      d_empty_spaces: 12,
      colonists_unplaced: 0,
      d_quarry_discount: 0,
      d_total_empty_colonist_slots: 0,
      buildings: [],
    },
    production: {
      corn: { can_produce: false, amount: 0 },
      indigo: { can_produce: false, amount: 0 },
      sugar: { can_produce: false, amount: 0 },
      tobacco: { can_produce: false, amount: 0 },
      coffee: { can_produce: false, amount: 0 },
      d_total: 0,
    },
    warehouse: {
      has_small_warehouse: false,
      has_large_warehouse: false,
      d_goods_storable: 0,
      protected_goods: [],
    },
    captain_first_load_done: false,
    wharf_used_this_phase: false,
    hacienda_used_this_phase: false,
  };
}

function makeRichState(round: number, phase: GameState['meta']['phase']): GameState {
  return {
    meta: {
      round,
      num_players: 3,
      player_order: ['player_0', 'player_1', 'player_2'],
      governor: 'player_2',
      phase,
      active_role: phase === 'role_selection' ? null : 'builder',
      active_player: 'player_0',
      players_acted_this_phase: [],
      end_game_triggered: false,
      end_game_reason: null,
      vp_supply_remaining: 55,
      captain_consecutive_passes: 0,
    },
    common_board: {
      roles: {
        settler: { doubloons_on_role: 0, taken_by: null },
        mayor: { doubloons_on_role: 0, taken_by: null },
        builder: { doubloons_on_role: 0, taken_by: 'player_1' },
        craftsman: { doubloons_on_role: 0, taken_by: null },
        trader: { doubloons_on_role: 0, taken_by: null },
        captain: { doubloons_on_role: 0, taken_by: null },
        prospector: { doubloons_on_role: 0, taken_by: null },
        prospector_2: { doubloons_on_role: 0, taken_by: null },
      },
      colonists: { ship: 3, supply: 20 },
      trading_house: {
        goods: [],
        d_spaces_used: 0,
        d_spaces_remaining: 4,
        d_is_full: false,
      },
      cargo_ships: [],
      available_plantations: {
        face_up: [],
        draw_pile: { corn: 10, indigo: 10, sugar: 10, tobacco: 10, coffee: 10 },
      },
      available_buildings: {},
      quarry_supply_remaining: 8,
      goods_supply: { corn: 10, indigo: 10, sugar: 10, tobacco: 10, coffee: 10 },
    },
    players: {
      player_0: makePlayer('Alice', 1),
      player_1: makePlayer('Bob', 2),
      player_2: makePlayer('Cara', 3, true),
    },
    decision: {
      type: 'waiting',
      player: 'player_waiting',
      note: 'Builder turn',
    },
    history: [],
    action_mask: Array.from({ length: 200 }, () => 0),
    bot_players: {},
    model_versions: {},
    result_summary: null,
  };
}

function makeDetail(): ReplayDetailResponse {
  return {
    game_id: 'g1',
    display_label: '04_13_Random_PPO_seoungmun_01',
    players: [
      { display_name: 'seoungmun', is_bot: false },
    ],
    replay_frames: [
      { frame_index: 0, step: 0, action: 'Select Role: Builder', commentary: 'Phase END_ROUND -> BUILDER', rich_state: { meta: { round: 1, phase: 'role_selection' } } as any },
      { frame_index: 1, step: 1, action: 'Pass', commentary: null, rich_state: { meta: { round: 1, phase: 'builder_action' } } as any },
      { frame_index: 2, step: 2, action: 'Pass', commentary: null, rich_state: { meta: { round: 2, phase: 'captain_action' } } as any },
    ],
    total_frames: 3,
    final_scores: [],
  };
}

function makeRichDetail(): ReplayDetailResponse {
  return {
    game_id: 'g-rich',
    display_label: 'Richer Replay',
    players: [
      { display_name: 'Alice', is_bot: false },
      { display_name: 'Bob', is_bot: true },
      { display_name: 'Cara', is_bot: true },
    ],
    replay_frames: [
      {
        frame_index: 0,
        step: 0,
        action: 'Builder turn',
        commentary: 'A realistic board snapshot',
        rich_state: makeRichState(1, 'builder_action'),
      },
      {
        frame_index: 1,
        step: 1,
        action: 'Next frame',
        commentary: null,
        rich_state: makeRichState(2, 'builder_action'),
      },
    ],
    total_frames: 2,
    final_scores: [],
  };
}

describe('ReplayViewScreen', () => {
  beforeEach(() => {
    localStorage.setItem('lang', 'ko');
    vi.stubEnv('VITE_BACKEND_ORIGIN', 'https://backend.example');
  });
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it('fetches detail and renders initial frame', async () => {
    const ReplayViewScreen = await loadReplayViewScreen();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse(makeDetail()));
    render(<ReplayViewScreen token="tok" gameId="g1" onBack={() => {}} />);

    await waitFor(() => {
      expect(screen.getByText('04_13_Random_PPO_seoungmun_01')).toBeTruthy();
    });
    expect(fetch).toHaveBeenCalledWith(
      'https://backend.example/api/puco/replays/g1',
      expect.objectContaining({
        headers: { Authorization: 'Bearer tok' },
      }),
    );
    expect(screen.getByTestId('replay-frame-info').textContent).toContain('단계');
    expect(screen.getByTestId('replay-frame-info').textContent).toContain('0');
    expect(screen.getByTestId('replay-frame-info').textContent).toContain('Select Role: Builder');
    expect(screen.getByTestId('replay-frame-info').textContent).toContain('Phase END_ROUND -> BUILDER');
    expect(screen.getByTestId('game-screen-proxy').textContent).toContain('replay:1:role_selection');
    expect(screen.queryByText(/"meta"/)).toBeNull();
  });

  it('next advances frame info and rendered board state', async () => {
    const ReplayViewScreen = await loadReplayViewScreen();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse(makeDetail()));
    render(<ReplayViewScreen token="tok" gameId="g1" onBack={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText('04_13_Random_PPO_seoungmun_01')).toBeTruthy();
    });

    const nextBtn = screen.getByRole('button', { name: '다음' });
    await userEvent.click(nextBtn);
    expect(screen.getByTestId('replay-frame-info').textContent).toContain('Pass');
    expect(screen.getByTestId('replay-frame-info').textContent).toContain('1');
    expect(screen.getByTestId('game-screen-proxy').textContent).toContain('replay:1:builder_action');
  });

  it('shows not-found state on 404', async () => {
    const ReplayViewScreen = await loadReplayViewScreen();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse({ detail: 'not found' }, 404));
    render(<ReplayViewScreen token="tok" gameId="g1" onBack={() => {}} />);
    await waitFor(() => {
      expect(screen.getByTestId('replay-not-found')).toBeTruthy();
    });
  });

  it('onBack invoked from back button', async () => {
    const ReplayViewScreen = await loadReplayViewScreen();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse(makeDetail()));
    const onBack = vi.fn();
    render(<ReplayViewScreen token="tok" gameId="g1" onBack={onBack} />);
    const buttons = screen.getAllByRole('button');
    await userEvent.click(buttons[0]);
    expect(onBack).toHaveBeenCalled();
  });

  it('shows error on non-404 HTTP failure', async () => {
    const ReplayViewScreen = await loadReplayViewScreen();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse({}, 500));
    render(<ReplayViewScreen token="tok" gameId="g1" onBack={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText(/HTTP 500/)).toBeTruthy();
    });
  });

  it('renders a realistic rich replay frame through the real GameScreen', async () => {
    const ReplayViewScreen = await loadReplayViewScreenWithRealGameScreen();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse(makeRichDetail()));
    render(<ReplayViewScreen token="tok" gameId="g-rich" onBack={() => {}} />);

    await waitFor(() => {
      expect(screen.getByText('Richer Replay')).toBeTruthy();
    });

    expect(screen.getByTestId('meta-panel').textContent).toBe('1:builder_action');
    expect(screen.getByText('Alice')).toBeTruthy();
    expect(screen.queryByText('Puerto Rico')).toBeNull();
    expect(screen.queryByText((content) => content.includes('player_waiting'))).toBeNull();
    expect(screen.queryByTestId('playback-speed-btn')).toBeNull();
    expect(screen.queryByTestId('playback-pause-btn')).toBeNull();
    const passBtn = document.querySelector('.pass-btn') as HTMLButtonElement | null;
    expect(passBtn).not.toBeNull();
    expect(passBtn?.disabled).toBe(true);
  });
});
