import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { defaultValue?: string; [k: string]: unknown }) => options?.defaultValue ?? key,
  }),
}));

vi.mock('../i18n', () => ({
  default: {
    language: 'ko',
    changeLanguage: vi.fn(),
  },
}));

const useGameWebSocketMock = vi.fn();
vi.mock('../hooks/useGameWebSocket', () => ({
  useGameWebSocket: (...args: unknown[]) => useGameWebSocketMock(...args),
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

interface GameScreenProbeProps {
  isMyTurn: boolean;
  state: {
    meta: {
      active_player: string;
      phase: string;
    };
    decision: {
      player: string;
    };
  };
}

vi.mock('../components/GameScreen', () => ({
  default: ({ isMyTurn, state }: GameScreenProbeProps) => (
    <div data-testid="turn-probe">
      {`isMyTurn=${String(isMyTurn)};active=${state.meta.active_player};decision=${state.decision.player};phase=${state.meta.phase}`}
    </div>
  ),
}));

import App from '../App';

function makePlayer(displayName: string, displayNumber: number, isGovernor = false) {
  return {
    display_name: displayName,
    display_number: displayNumber,
    is_governor: isGovernor,
    doubloons: 2,
    vp_chips: 0,
    goods: { corn: 0, indigo: 0, sugar: 0, tobacco: 0, coffee: 0, d_total: 0 },
    island: { total_spaces: 12, d_used_spaces: 0, d_empty_spaces: 12, d_active_quarries: 0, plantations: [] },
    city: { total_spaces: 12, d_used_spaces: 0, d_empty_spaces: 12, colonists_unplaced: 0, d_quarry_discount: 0, d_total_empty_colonist_slots: 0, buildings: [] },
    production: {
      corn: { can_produce: false, amount: 0 },
      indigo: { can_produce: false, amount: 0 },
      sugar: { can_produce: false, amount: 0 },
      tobacco: { can_produce: false, amount: 0 },
      coffee: { can_produce: false, amount: 0 },
      d_total: 0,
    },
    warehouse: { has_small_warehouse: false, has_large_warehouse: false, d_goods_storable: 0, protected_goods: [] },
    captain_first_load_done: false,
    wharf_used_this_phase: false,
    hacienda_used_this_phase: false,
  };
}

function makeGameState({
  phase,
  activePlayer,
  decisionPlayer,
}: {
  phase: string;
  activePlayer: string;
  decisionPlayer: string;
}) {
  return {
    meta: {
      game_id: 'room-1',
      round: 3,
      step_count: 12,
      num_players: 3,
      player_order: ['player_0', 'player_1', 'player_2'],
      governor: 'player_2',
      phase,
      phase_id: 4,
      active_role: phase === 'builder_action' ? 'builder' : 'trader',
      active_player: activePlayer,
      state_revision: 9,
      players_acted_this_phase: [],
      end_game_triggered: false,
      end_game_reason: null,
      vp_supply_remaining: 45,
      captain_consecutive_passes: 0,
      bot_thinking: false,
    },
    common_board: {
      roles: {
        settler: { doubloons_on_role: 0, taken_by: null },
        mayor: { doubloons_on_role: 0, taken_by: null },
        builder: { doubloons_on_role: 0, taken_by: phase === 'builder_action' ? 'player_0' : null },
        craftsman: { doubloons_on_role: 0, taken_by: null },
        trader: { doubloons_on_role: 0, taken_by: phase === 'trader_action' ? 'player_0' : null },
        captain: { doubloons_on_role: 0, taken_by: null },
        prospector: { doubloons_on_role: 0, taken_by: null },
        prospector_2: { doubloons_on_role: 0, taken_by: null },
      },
      colonists: { ship: 0, supply: 0 },
      trading_house: { goods: [], d_spaces_used: 0, d_spaces_remaining: 4, d_is_full: false },
      cargo_ships: [],
      available_plantations: { face_up: [], draw_pile: { corn: 0, indigo: 0, sugar: 0, tobacco: 0, coffee: 0 } },
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
      player: decisionPlayer,
      note: 'handoff',
    },
    history: [],
    bot_players: {},
    model_versions: {},
    result_summary: null,
    action_mask: Array.from({ length: 200 }, () => 0),
  };
}

describe('App multiplayer turn source contract', () => {
  let nextState: ReturnType<typeof makeGameState>;
  let deliveredState = false;

  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('access_token', 'saved-token');
    localStorage.setItem('active_game_session', JSON.stringify({
      gameId: 'room-1',
      screen: 'game',
      myPlayerId: 'player_0',
      myName: 'Alice',
      isSpectator: false,
      isMultiplayer: true,
    }));

    useGameWebSocketMock.mockReset();
    deliveredState = false;
    useGameWebSocketMock.mockImplementation(({ onStateUpdate }: { onStateUpdate: (state: typeof nextState, actionMask: number[]) => void }) => {
      if (!deliveredState) {
        deliveredState = true;
        queueMicrotask(() => {
          onStateUpdate(nextState, nextState.action_mask);
        });
      }
      return {
        getLatestRevision: () => nextState.meta.state_revision,
      };
    });

    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith('/api/puco/auth/me')) {
        return new Response(JSON.stringify({
          id: 'user-1',
          nickname: 'Alice',
          needs_nickname: false,
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.endsWith('/api/puco/session/active-game')) {
        return new Response(JSON.stringify({
          has_active_game: true,
          game_id: 'room-1',
          status: 'ACTIVE',
          is_host: false,
          is_player: true,
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      throw new Error(`Unexpected fetch: ${url}`);
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('uses meta.active_player instead of decision.player for saved multiplayer user turn ownership', async () => {
    nextState = makeGameState({
      phase: 'trader_action',
      activePlayer: 'player_1',
      decisionPlayer: 'player_0',
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('turn-probe').textContent).toContain('isMyTurn=false');
    });
    expect(screen.getByTestId('turn-probe').textContent).toContain('active=player_1');
    expect(screen.getByTestId('turn-probe').textContent).toContain('decision=player_0');
  });

  it('keeps builder handoff ownership on meta.active_player when decision.player still points at the current user', async () => {
    nextState = makeGameState({
      phase: 'builder_action',
      activePlayer: 'player_2',
      decisionPlayer: 'player_0',
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('turn-probe').textContent).toContain('isMyTurn=false');
    });
    expect(screen.getByTestId('turn-probe').textContent).toContain('phase=builder_action');
    expect(screen.getByTestId('turn-probe').textContent).toContain('active=player_2');
    expect(screen.getByTestId('turn-probe').textContent).toContain('decision=player_0');
  });

  it('still grants turn ownership when meta.active_player is the saved player and decision.player lags behind', async () => {
    nextState = makeGameState({
      phase: 'trader_action',
      activePlayer: 'player_0',
      decisionPlayer: 'player_2',
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('turn-probe').textContent).toContain('isMyTurn=true');
    });
    expect(screen.getByTestId('turn-probe').textContent).toContain('active=player_0');
    expect(screen.getByTestId('turn-probe').textContent).toContain('decision=player_2');
  });
});
