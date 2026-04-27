/**
 * RED — settler face_up corn 클릭 시 outbound action payload 검증.
 *
 * face_up entry에 engine_action_index=10, canonical_id="settler:tile_type:corn"이 들어
 * 있을 때, App.channelAction은 같은 의미값과 canonical_id를 함께 전송해야 한다.
 * 현재 production 코드는 canonical_id를 전송하지 않으므로 RED.
 *
 * Spec: docs/superpowers/specs/2026-04-27-action-index-contract-fix-design.md
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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

interface FaceUpEntry {
  type: string;
  engine_action_index?: number;
  action_index?: number;
  display_position?: number;
  canonical_id?: string;
}

interface GameScreenMockProps {
  state: {
    common_board: {
      available_plantations: { face_up: FaceUpEntry[] };
    };
  };
  onSettlePlantation: (type: string) => void;
}

vi.mock('../components/GameScreen', () => ({
  default: ({ state, onSettlePlantation }: GameScreenMockProps) => (
    <div data-testid="game-screen-mock">
      {state.common_board.available_plantations.face_up.map((entry) => (
        <button
          key={`face-up-${entry.type}-${entry.display_position ?? 0}`}
          onClick={() => onSettlePlantation(entry.type)}
        >
          {`face-up-${entry.type}`}
        </button>
      ))}
    </div>
  ),
}));

import App from '../App';

function makeSettlerState() {
  const basePlayer = {
    display_name: 'Alice',
    display_number: 1,
    is_governor: true,
    doubloons: 3,
    vp_chips: 0,
    goods: { corn: 0, indigo: 0, sugar: 0, tobacco: 0, coffee: 0, d_total: 0 },
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
      phase: 'settler_action',
      phase_id: 2,
      active_role: 'settler',
      active_player: 'player_0',
      end_game_triggered: false,
      bot_thinking: false,
    },
    common_board: {
      roles: {
        settler: { taken_by: 'player_0' },
        mayor: { taken_by: null },
        builder: { taken_by: null },
        craftsman: { taken_by: null },
        trader: { taken_by: null },
        captain: { taken_by: null },
      },
      quarry_supply_remaining: 8,
      colonists: { supply: 0, ship: 0 },
      available_plantations: {
        draw_pile: { corn: 3, indigo: 3, sugar: 3, tobacco: 3, coffee: 3, quarry: 8 },
        face_up: [
          {
            type: 'corn',
            engine_action_index: 10,
            action_index: 10,
            display_position: 0,
            canonical_id: 'settler:tile_type:corn',
          },
          {
            type: 'coffee',
            engine_action_index: 8,
            action_index: 8,
            display_position: 1,
            canonical_id: 'settler:tile_type:coffee',
          },
        ],
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
    decision: { type: 'waiting', player: 'player_0', note: 'Settler turn' },
    history: [],
    bot_players: {},
    model_versions: {},
    result_summary: null,
    action_mask: Array.from(
      { length: 200 },
      (_, idx) => (idx === 8 || idx === 10 || idx === 13 ? 1 : 0),
    ),
  };
}

describe('App settler corn click — action_index contract', () => {
  let actionFetchCalls: Array<{ url: string; body: any }>;

  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('access_token', 'saved-token');
    vi.restoreAllMocks();

    actionFetchCalls = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith('/api/puco/auth/me')) {
          return {
            ok: true,
            json: async () => ({ id: 'user-1', nickname: 'Alice', needs_nickname: false }),
          } as Response;
        }
        if (url.endsWith('/api/puco/game/room-1/start')) {
          return {
            ok: true,
            json: async () => ({ state: makeSettlerState() }),
          } as Response;
        }
        if (url.endsWith('/api/puco/game/room-1/action')) {
          const body = init?.body ? JSON.parse(String(init.body)) : null;
          actionFetchCalls.push({ url, body });
          return {
            ok: true,
            json: async () => ({ status: 'success', state: makeSettlerState(), action_mask: makeSettlerState().action_mask }),
          } as Response;
        }
        throw new Error(`Unexpected fetch: ${url}`);
      }),
    );

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

  it('sends engine_action_index=10 and canonical_id "settler:tile_type:corn" when corn face-up is clicked', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /face-up-corn/ })).toBeTruthy();
    });

    fireEvent.click(screen.getByRole('button', { name: /face-up-corn/ }));

    await waitFor(() => {
      expect(actionFetchCalls.length).toBeGreaterThan(0);
    });

    const last = actionFetchCalls[actionFetchCalls.length - 1];
    expect(last.body?.payload?.action_index).toBe(10);
    expect(last.body?.payload?.canonical_id).toBe('settler:tile_type:corn');
  });
});
