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
  }: {
    playerId: string;
    player: { display_name: string };
    isRolePicker?: boolean;
  }) => (
    <div data-testid={playerId}>
      {player.display_name}:{isRolePicker ? 'picker' : 'normal'}
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

describe('GameScreen', () => {
  it('marks the player who chose the active role', () => {
    render(
      <GameScreen
        backend=""
        state={makeState()}
        error={null}
        saving={false}
        passing={false}
        buildConfirm={null}
        pendingSettlement={null}
        roundFlash={null}
        discardProtected={[]}
        discardSingleExtra={null}
        finalScores={null}
        popups={[]}
        isAdmin={false}
        isSpectator={false}
        isMultiplayer
        myName="Alice"
        lobbyPlayers={[]}
        isMyTurn
        isBotTurn={false}
        isBlocked={false}
        interactionLocked={false}
        canPass
        onStateLoaded={vi.fn()}
        onGoToRoomsPreservingAuth={vi.fn()}
        onLogoutToLogin={vi.fn()}
        onExitSpectator={vi.fn()}
        onDismissError={vi.fn()}
        onClearPopups={vi.fn()}
        onConfirmBuild={vi.fn()}
        onCancelBuildConfirm={vi.fn()}
        onConfirmSettlement={vi.fn()}
        onSelectRole={vi.fn(async () => {})}
        onSettlePlantation={vi.fn()}
        onUseHacienda={vi.fn(async () => {})}
        onPlaceMayorColonist={vi.fn(async () => {})}
        onPassAction={vi.fn(async () => {})}
        onSellGood={vi.fn(async () => {})}
        onCraftsmanPrivilege={vi.fn(async () => {})}
        onLoadShip={vi.fn(async () => {})}
        onCaptainPass={vi.fn(async () => {})}
        onToggleDiscardProtected={vi.fn()}
        onSetDiscardSingleExtra={vi.fn()}
        onDoDiscardGoods={vi.fn(async () => {})}
        onRequestBuild={vi.fn()}
        onReturnToRooms={vi.fn()}
      />,
    );

    expect(screen.getByTestId('player_0').textContent).toContain('Alice:normal');
    expect(screen.getByTestId('player_1').textContent).toContain('Bob:picker');
    expect(screen.getByTestId('player_2').textContent).toContain('Cara:normal');
  });
});
