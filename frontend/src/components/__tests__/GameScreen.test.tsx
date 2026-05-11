import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import GameScreen from '../GameScreen';
import type { GameState, Player } from '../../types/gameState';

vi.mock('../MetaPanel', () => ({
  default: () => null,
}));

vi.mock('../CommonBoardPanel', () => ({
  default: () => null,
}));

vi.mock('../PlayerPanel', () => ({
  default: ({
    playerId,
    player,
    isRolePicker,
    mayorLegalIslandSlots,
    mayorLegalCitySlots,
  }: {
    playerId: string;
    player: { display_name: string };
    isRolePicker?: boolean;
    mayorLegalIslandSlots?: number[];
    mayorLegalCitySlots?: number[];
  }) => (
    <div data-testid={playerId}>
      {player.display_name}:{isRolePicker ? 'picker' : 'normal'}
      {mayorLegalIslandSlots ? `:island=${mayorLegalIslandSlots.join(',')}` : ''}
      {mayorLegalCitySlots ? `:city=${mayorLegalCitySlots.join(',')}` : ''}
    </div>
  ),
}));

vi.mock('../SanJuan', () => ({
  default: () => null,
}));

vi.mock('../AdminPanel', () => ({
  default: () => null,
}));

vi.mock('../PlayerAdvantages', () => ({
  default: () => null,
}));

vi.mock('../HistoryPanel', () => ({
  default: () => null,
}));

vi.mock('../EndGamePanel', () => ({
  default: () => null,
}));

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

function makeState(): GameState {
  return {
    meta: {
      round: 3,
      num_players: 3,
      player_order: ['player_0', 'player_1', 'player_2'],
      governor: 'player_2',
      phase: 'builder_action',
      active_role: 'builder',
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
      player: 'player_0',
      note: 'Builder turn',
    },
    history: [],
    action_mask: Array.from({ length: 200 }, () => 0),
    bot_players: {},
    model_versions: {},
    result_summary: null,
  };
}

function commonProps(overrides: Partial<React.ComponentProps<typeof GameScreen>> = {}) {
  return {
    backend: '',
    state: makeState(),
    error: null,
    saving: false,
    passing: false,
    buildConfirm: null,
    pendingSettlement: null,
    roundFlash: null,
    discardProtected: [],
    discardSingleExtra: null,
    finalScores: null,
    popups: [],
    isAdmin: false,
    isSpectator: false,
    isMultiplayer: true,
    myName: 'Alice',
    lobbyPlayers: [],
    isMyTurn: true,
    isBotTurn: false,
    isBlocked: false,
    interactionLocked: false,
    canPass: true,
    isBotGame: false,
    playbackSpeed: 1,
    playbackPaused: false,
    onSpeedChange: vi.fn(),
    onPauseToggle: vi.fn(),
    onStateLoaded: vi.fn(),
    onGoToRoomsPreservingAuth: vi.fn(),
    onLogoutToLogin: vi.fn(),
    onExitSpectator: vi.fn(),
    onDismissError: vi.fn(),
    onClearPopups: vi.fn(),
    onConfirmBuild: vi.fn(),
    onCancelBuildConfirm: vi.fn(),
    onConfirmSettlement: vi.fn(),
    onSelectRole: vi.fn(async () => {}),
    onSettlePlantation: vi.fn(),
    onUseHacienda: vi.fn(async () => {}),
    onPlaceMayorColonist: vi.fn(async () => {}),
    onPassAction: vi.fn(async () => {}),
    onSellGood: vi.fn(async () => {}),
    onCraftsmanPrivilege: vi.fn(async () => {}),
    onLoadShip: vi.fn(async () => {}),
    onCaptainPass: vi.fn(async () => {}),
    onToggleDiscardProtected: vi.fn(),
    onSetDiscardSingleExtra: vi.fn(),
    onDoDiscardGoods: vi.fn(async () => {}),
    onRequestBuild: vi.fn(),
    onReturnToRooms: vi.fn(),
    ...overrides,
  } as React.ComponentProps<typeof GameScreen>;
}

describe('GameScreen', () => {
  it('marks the player who chose the active role', () => {
    render(<GameScreen {...commonProps()} />);
    expect(screen.getByTestId('player_0').textContent).toContain('Alice:normal');
    expect(screen.getByTestId('player_1').textContent).toContain('Bob:picker');
    expect(screen.getByTestId('player_2').textContent).toContain('Cara:normal');
  });

  it('disables pass button when replayMode=true', () => {
    render(<GameScreen {...commonProps({ replayMode: true })} />);
    const passBtn = document.querySelector('.pass-btn') as HTMLButtonElement | null;
    expect(passBtn).not.toBeNull();
    expect(passBtn?.disabled).toBe(true);
  });

  it('enables pass button when replayMode is absent and canPass', () => {
    render(<GameScreen {...commonProps()} />);
    const passBtn = document.querySelector('.pass-btn') as HTMLButtonElement | null;
    expect(passBtn?.disabled).toBe(false);
  });

  it('hides trader action card for non-active multiplayer viewers', () => {
    const state = makeState();
    state.meta.phase = 'trader_action';
    state.meta.active_role = 'trader';
    state.meta.active_player = 'player_0';
    state.players.player_0.goods.corn = 1;
    state.players.player_0.goods.d_total = 1;

    render(
      <GameScreen
        {...commonProps({
          state,
          isMyTurn: false,
          isMultiplayer: true,
        })}
      />,
    );

    expect(document.querySelector('#action-card')).toBeNull();
  });

  it('hides craftsman privilege overlay for non-active multiplayer viewers', () => {
    const state = makeState();
    state.meta.phase = 'craftsman_action';
    state.meta.active_role = 'craftsman';
    state.common_board.roles.craftsman.taken_by = 'player_0';

    render(
      <GameScreen
        {...commonProps({
          state,
          isMyTurn: false,
          isMultiplayer: true,
        })}
      />,
    );

    expect(document.querySelector('.hospice-overlay')).toBeNull();
  });

  it('hides captain action card for non-active multiplayer viewers', () => {
    const state = makeState();
    state.meta.phase = 'captain_action';
    state.meta.active_role = 'captain';
    state.meta.active_player = 'player_0';
    state.common_board.roles.captain.taken_by = 'player_0';
    state.players.player_0.goods.corn = 2;
    state.players.player_0.goods.d_total = 2;
    state.common_board.cargo_ships = [
      { capacity: 4, good: null, d_filled: 0, d_remaining_space: 4, d_is_empty: true, d_is_full: false },
    ];

    render(
      <GameScreen
        {...commonProps({
          state,
          isMyTurn: false,
          isMultiplayer: true,
        })}
      />,
    );

    expect(document.querySelector('#action-card')).toBeNull();
  });

  it('hides captain discard action card for non-active multiplayer viewers', () => {
    const state = makeState();
    state.meta.phase = 'captain_discard';
    state.meta.active_role = 'captain';
    state.meta.active_player = 'player_0';
    state.players.player_0.goods.corn = 2;
    state.players.player_0.goods.sugar = 1;
    state.players.player_0.goods.d_total = 3;
    state.players.player_0.city.buildings = [
      { name: 'small_warehouse', vp: 1, cost: 3, workers: 0, max_workers: 1, occupied: false, is_active: true },
    ];

    render(
      <GameScreen
        {...commonProps({
          state,
          isMyTurn: false,
          isMultiplayer: true,
        })}
      />,
    );

    expect(document.querySelector('#action-card')).toBeNull();
  });

  it('does not pass mayor legal slots to non-active multiplayer viewers', () => {
    const state = makeState();
    state.meta.phase = 'mayor_action';
    state.meta.active_role = 'mayor';
    state.meta.active_player = 'player_0';
    state.meta.mayor_legal_island_slots = [0, 1];
    state.meta.mayor_legal_city_slots = [0];

    render(
      <GameScreen
        {...commonProps({
          state,
          isMyTurn: false,
          isMultiplayer: true,
        })}
      />,
    );

    expect(screen.getByTestId('player_0').textContent).toContain('Alice:normal');
    expect(screen.getByTestId('player_0').textContent).not.toContain(':island=0,1');
    expect(screen.getByTestId('player_0').textContent).not.toContain(':city=0');
  });

  it('shows trader action card to the active multiplayer player', () => {
    const state = makeState();
    state.meta.phase = 'trader_action';
    state.meta.active_role = 'trader';
    state.meta.active_player = 'player_0';
    state.players.player_0.goods.corn = 1;
    state.players.player_0.goods.d_total = 1;

    render(
      <GameScreen
        {...commonProps({
          state,
          isMyTurn: true,
          isMultiplayer: true,
        })}
      />,
    );

    expect(document.querySelector('#action-card')).not.toBeNull();
  });
});

describe('Playback controls', () => {
  function botGameState() {
    const state = makeState();
    state.meta.player_order = ['BOT_ppo', 'BOT_random', 'BOT_random'];
    state.players = {
      BOT_ppo: makePlayer('PPO Bot', 1),
      BOT_random: makePlayer('Random Bot', 2),
      BOT_random_2: makePlayer('Random Bot 2', 3),
    };
    return state;
  }

  it('shows speed/pause buttons in bot spectator mode', () => {
    render(
      <GameScreen
        {...commonProps({
          state: botGameState(),
          isSpectator: true,
          isBotGame: true,
        })}
      />,
    );
    expect(screen.getByTestId('playback-speed-btn')).toBeDefined();
    expect(screen.getByTestId('playback-pause-btn')).toBeDefined();
  });

  it('hides speed/pause buttons in normal game', () => {
    render(<GameScreen {...commonProps({ isSpectator: false, isBotGame: false })} />);
    expect(screen.queryByTestId('playback-speed-btn')).toBeNull();
    expect(screen.queryByTestId('playback-pause-btn')).toBeNull();
  });

  it('speed button cycles x1 -> x2', () => {
    const onSpeedChange = vi.fn();
    render(
      <GameScreen
        {...commonProps({
          state: botGameState(),
          isSpectator: true,
          isBotGame: true,
          playbackSpeed: 1,
          onSpeedChange,
        })}
      />,
    );
    screen.getByTestId('playback-speed-btn').click();
    expect(onSpeedChange).toHaveBeenCalledWith(2);
  });

  it('pause button toggles icon', () => {
    const { rerender } = render(
      <GameScreen
        {...commonProps({
          state: botGameState(),
          isSpectator: true,
          isBotGame: true,
          playbackPaused: false,
        })}
      />,
    );
    expect(screen.getByTestId('playback-pause-btn').textContent).toContain('⏸');

    rerender(
      <GameScreen
        {...commonProps({
          state: botGameState(),
          isSpectator: true,
          isBotGame: true,
          playbackPaused: true,
        })}
      />,
    );
    expect(screen.getByTestId('playback-pause-btn').textContent).toContain('▶');
  });

  it('hides controls when spectating a human game', () => {
    render(
      <GameScreen {...commonProps({ isSpectator: true, isBotGame: false })} />,
    );
    expect(screen.queryByTestId('playback-speed-btn')).toBeNull();
    expect(screen.queryByTestId('playback-pause-btn')).toBeNull();
  });

  it('pause button calls onPauseToggle', () => {
    const onPauseToggle = vi.fn();
    render(
      <GameScreen
        {...commonProps({
          state: botGameState(),
          isSpectator: true,
          isBotGame: true,
          onPauseToggle,
        })}
      />,
    );
    screen.getByTestId('playback-pause-btn').click();
    expect(onPauseToggle).toHaveBeenCalled();
  });
});
