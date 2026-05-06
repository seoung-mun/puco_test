import { render, screen, waitFor } from '@testing-library/react';
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

vi.mock('../components/GameScreen', () => ({
  default: () => <div>GAME_SCREEN</div>,
}));

vi.mock('../components/MetaPanel', () => ({ default: () => null }));
vi.mock('../components/CommonBoardPanel', () => ({ default: () => null }));
vi.mock('../components/PlayerPanel', () => ({ default: () => null }));
vi.mock('../components/SanJuan', () => ({ default: () => null }));
vi.mock('../components/AdminPanel', () => ({ default: () => null }));
vi.mock('../components/PlayerAdvantages', () => ({ default: () => null }));
vi.mock('../components/HistoryPanel', () => ({ default: () => null }));
vi.mock('../components/EndGamePanel', () => ({ default: () => null }));

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  send = vi.fn();
  close = vi.fn();

  constructor(public url: string) {
    MockWebSocket.instances.push(this);
    queueMicrotask(() => this.onopen?.());
  }
}

function makeGameState(gameId: string) {
  return {
    meta: {
      game_id: gameId,
      round: 1,
      num_players: 3,
      player_order: ['player-1', 'player-2', 'player-3'],
      governor: 'player-1',
      phase: 'role_selection',
      active_role: null,
      active_player: 'player-1',
      state_revision: 1,
      players_acted_this_phase: [],
      end_game_triggered: false,
      end_game_reason: null,
      vp_supply_remaining: 40,
      captain_consecutive_passes: 0,
    },
    common_board: {
      roles: {
        settler: { doubloons_on_role: 0, taken_by: null },
        mayor: { doubloons_on_role: 0, taken_by: null },
        builder: { doubloons_on_role: 0, taken_by: null },
        craftsman: { doubloons_on_role: 0, taken_by: null },
        trader: { doubloons_on_role: 0, taken_by: null },
        captain: { doubloons_on_role: 0, taken_by: null },
      },
      colonists: { ship: 0, supply: 0 },
      trading_house: { goods: [], d_spaces_used: 0, d_spaces_remaining: 12, d_is_full: false },
      cargo_ships: [],
      available_plantations: { face_up: [], draw_pile: { corn: 0, indigo: 0, sugar: 0, tobacco: 0, coffee: 0 } },
      available_buildings: {},
      quarry_supply_remaining: 8,
      goods_supply: { corn: 0, indigo: 0, sugar: 0, tobacco: 0, coffee: 0 },
    },
    players: {
      'player-1': {
        display_name: 'Alice',
        display_number: 1,
        is_governor: true,
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
        warehouse: { has_small_warehouse: false, has_large_warehouse: false, d_goods_storable: 1, protected_goods: [] },
        captain_first_load_done: false,
        wharf_used_this_phase: false,
        hacienda_used_this_phase: false,
      },
      'player-2': {
        display_name: 'Bob',
        display_number: 2,
        is_governor: false,
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
        warehouse: { has_small_warehouse: false, has_large_warehouse: false, d_goods_storable: 1, protected_goods: [] },
        captain_first_load_done: false,
        wharf_used_this_phase: false,
        hacienda_used_this_phase: false,
      },
      'player-3': {
        display_name: 'Cara',
        display_number: 3,
        is_governor: false,
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
        warehouse: { has_small_warehouse: false, has_large_warehouse: false, d_goods_storable: 1, protected_goods: [] },
        captain_first_load_done: false,
        wharf_used_this_phase: false,
        hacienda_used_this_phase: false,
      },
    },
    decision: { type: 'waiting', player: 'player-1', note: '' },
    history: [],
    bot_players: {},
    model_versions: {},
    result_summary: null,
    action_mask: [],
  };
}

async function loadApp() {
  vi.resetModules();
  return (await import('../App')).default;
}

describe('App refresh rejoin', () => {
  beforeEach(() => {
    localStorage.clear();
    useGameWebSocketMock.mockReset();
    MockWebSocket.instances = [];
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket);
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url === '/api/puco/auth/me') {
        return new Response(JSON.stringify({
          id: 'user-1',
          nickname: 'Alice',
          needs_nickname: false,
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url === '/api/puco/session/active-game') {
        return new Response(JSON.stringify({
          has_active_game: true,
          game_id: 'room-1',
          status: 'WAITING',
          is_host: true,
          is_player: true,
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      return new Response('Not found', { status: 404 });
    }));
    useGameWebSocketMock.mockImplementation(() => ({
      sendJson: () => true,
      getLatestRevision: () => 0,
    }));
    useGameWebSocketMock.mockImplementation((opts: {
      gameId: string | null;
      onStateUpdate: (state: unknown, actionMask: number[]) => void;
    }) => {
      if (opts.gameId) {
        queueMicrotask(() => opts.onStateUpdate(makeGameState(opts.gameId), []));
      }
      return {
        sendJson: () => true,
        getLatestRevision: () => 0,
      };
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it('returns to the lobby after refresh when the active lobby session is still valid', async () => {
    localStorage.setItem('access_token', 'saved-token');
    localStorage.setItem('active_game_session', JSON.stringify({
      gameId: 'room-1',
      screen: 'lobby',
      myPlayerId: 'user-1',
      myName: 'Alice',
      isSpectator: false,
      isMultiplayer: true,
    }));

    const App = await loadApp();
    render(<App />);

    expect(await screen.findByText('LOBBY_SCREEN')).toBeTruthy();

    await waitFor(() => {
      expect(MockWebSocket.instances).toHaveLength(1);
      expect(MockWebSocket.instances[0].url).toContain('/api/puco/ws/lobby/room-1');
    });
    const activeGameCall = vi.mocked(fetch).mock.calls.find(
      ([url]) => String(url) === '/api/puco/session/active-game',
    );
    expect(activeGameCall).toBeTruthy();
    const activeGameHeaders = new Headers((activeGameCall?.[1] as RequestInit | undefined)?.headers);
    expect(activeGameHeaders.get('Authorization')).toBe('Bearer saved-token');
  });

  it('returns to the game after refresh when the active game session is still valid', async () => {
    localStorage.setItem('access_token', 'saved-token');
    localStorage.setItem('active_game_session', JSON.stringify({
      gameId: 'room-2',
      screen: 'game',
      myPlayerId: 'player-1',
      myName: 'Alice',
      isSpectator: false,
      isMultiplayer: true,
    }));
    vi.mocked(fetch).mockImplementationOnce(async () => new Response(JSON.stringify({
      id: 'user-1',
      nickname: 'Alice',
      needs_nickname: false,
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })).mockImplementationOnce(async () => new Response(JSON.stringify({
      has_active_game: true,
      game_id: 'room-2',
      status: 'PROGRESS',
      is_host: true,
      is_player: true,
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));

    const App = await loadApp();
    render(<App />);

    expect(await screen.findByText('GAME_SCREEN')).toBeTruthy();

    await waitFor(() => {
      expect(useGameWebSocketMock).toHaveBeenCalled();
    });
    expect(useGameWebSocketMock.mock.calls.at(-1)?.[0]).toEqual(
      expect.objectContaining({ gameId: 'room-2', token: 'saved-token' }),
    );
  });

  it('falls back to rooms when the cached active session is stale', async () => {
    localStorage.setItem('access_token', 'saved-token');
    localStorage.setItem('active_game_session', JSON.stringify({
      gameId: 'room-3',
      screen: 'game',
      myPlayerId: 'player-1',
      myName: 'Alice',
      isSpectator: false,
      isMultiplayer: true,
    }));
    vi.mocked(fetch).mockImplementationOnce(async () => new Response(JSON.stringify({
      id: 'user-1',
      nickname: 'Alice',
      needs_nickname: false,
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })).mockImplementationOnce(async () => new Response(JSON.stringify({
      has_active_game: false,
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));

    const App = await loadApp();
    render(<App />);

    expect(await screen.findByText('ROOMS_SCREEN')).toBeTruthy();
    expect(localStorage.getItem('active_game_session')).toBeNull();
  });
});
