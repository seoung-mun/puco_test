import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useEffect } from 'react';

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

vi.mock('../hooks/useGameWebSocket', () => ({
  useGameWebSocket: vi.fn(),
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
  default: ({ onJoinRoom }: { onJoinRoom: (roomId: string) => void }) => {
    useEffect(() => {
      onJoinRoom('room-1');
    }, [onJoinRoom]);
    return <div>ROOMS_SCREEN</div>;
  },
}));

vi.mock('../components/JoinScreen', () => ({
  default: () => <div>JOIN_SCREEN</div>,
}));

vi.mock('../components/LobbyScreen', () => ({
  default: ({ onStart }: { onStart: () => Promise<void> }) => {
    useEffect(() => {
      void onStart();
    }, [onStart]);
    return <div>LOBBY_SCREEN</div>;
  },
}));

vi.mock('../components/MetaPanel', () => ({
  default: () => null,
}));

vi.mock('../components/CommonBoardPanel', () => ({
  default: () => <div>COMMON_BOARD</div>,
}));

vi.mock('../components/PlayerPanel', () => ({
  default: () => null,
}));

vi.mock('../components/SanJuan', () => ({
  default: () => null,
}));

vi.mock('../components/AdminPanel', () => ({
  default: () => null,
}));

vi.mock('../components/PlayerAdvantages', () => ({
  default: () => null,
}));

vi.mock('../components/HistoryPanel', () => ({
  default: () => null,
}));

vi.mock('../components/EndGamePanel', () => ({
  default: () => null,
}));

import App from '../App';

function makeMayorState() {
  const basePlayer = {
    display_name: 'Alice',
    display_number: 1,
    is_governor: true,
    doubloons: 3,
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
      d_used_spaces: 2,
      d_empty_spaces: 10,
      d_active_quarries: 0,
      plantations: [
        { type: 'corn', colonized: false },
        { type: 'indigo', colonized: false },
      ],
    },
    city: {
      total_spaces: 12,
      d_used_spaces: 2,
      d_empty_spaces: 10,
      colonists_unplaced: 3,
      d_quarry_discount: 0,
      d_total_empty_colonist_slots: 3,
      buildings: [
        {
          name: 'wharf',
          max_colonists: 1,
          current_colonists: 0,
          empty_slots: 1,
          is_active: false,
          vp: 3,
        },
        {
          name: 'small_market',
          max_colonists: 1,
          current_colonists: 0,
          empty_slots: 1,
          is_active: false,
          vp: 1,
        },
      ],
    },
    production: {
      corn: { can_produce: true, amount: 1 },
      indigo: { can_produce: true, amount: 1 },
      sugar: { can_produce: false, amount: 0 },
      tobacco: { can_produce: false, amount: 0 },
      coffee: { can_produce: false, amount: 0 },
      d_total: 2,
    },
    warehouse: {
      has_small_warehouse: false,
      has_large_warehouse: false,
      d_goods_storable: 1,
      protected_goods: [],
    },
    captain_first_load_done: false,
    wharf_used_this_phase: false,
    hacienda_used_this_phase: false,
  };

  return {
    meta: {
      game_id: 'room-1',
      round: 1,
      step_count: 1,
      num_players: 3,
      player_order: ['player_0', 'player_1', 'player_2'],
      governor: 'player_0',
      phase: 'mayor_action',
      phase_id: 1,
      active_role: 'mayor',
      active_player: 'player_0',
      end_game_triggered: false,
      bot_thinking: false,
    },
    common_board: {
      roles: {
        settler: { taken_by: null },
        mayor: { taken_by: 'player_0' },
        builder: { taken_by: null },
        craftsman: { taken_by: null },
        trader: { taken_by: null },
        captain: { taken_by: null },
      },
      quarry_supply_remaining: 8,
      available_plantations: {
        draw_pile: { corn: 3, indigo: 3, sugar: 3, tobacco: 3, coffee: 3, quarry: 8 },
        face_up: [],
      },
      available_buildings: {},
      cargo_ships: [],
      trading_house: { goods: [], d_is_full: false },
      goods_supply: { corn: 10, indigo: 10, sugar: 10, tobacco: 10, coffee: 10 },
    },
    players: {
      player_0: basePlayer,
      player_1: { ...basePlayer, display_name: 'Bob', display_number: 2, is_governor: false },
      player_2: { ...basePlayer, display_name: 'Cara', display_number: 3, is_governor: false },
    },
    decision: {
      type: 'waiting',
      player: 'player_0',
      note: 'Mayor turn',
    },
    history: [],
    bot_players: {},
    model_versions: {},
    result_summary: null,
    action_mask: Array.from({ length: 200 }, (_, idx) => (idx >= 69 && idx <= 71 ? 1 : 0)),
  };
}

describe('App mayor flow', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('access_token', 'saved-token');
    vi.restoreAllMocks();
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/puco/auth/me')) {
        return {
          ok: true,
          json: async () => ({
            id: 'user-1',
            nickname: 'Alice',
            needs_nickname: false,
          }),
        } as Response;
      }
      if (url.endsWith('/api/puco/game/room-1/start')) {
        return {
          ok: true,
          json: async () => ({ state: makeMayorState() }),
        } as Response;
      }
      throw new Error(`Unexpected fetch: ${url}`);
    }));

    class MockWebSocket {
      onopen: (() => void) | null = null;
      onmessage: ((event: { data: string }) => void) | null = null;
      close() {}
      send() {}
    }

    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows the strategy-first mayor panel after lobby start enters a mayor turn', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Captain Focus/i })).toBeTruthy();
    });
    expect(screen.getByRole('button', { name: /Trade \/ Factory/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /Building Focus/i })).toBeTruthy();
  });
});
