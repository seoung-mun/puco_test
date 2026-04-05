import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import EndGamePanel from '../EndGamePanel';
import type { FinalScoreSummary, GameState } from '../../types/gameState';

function makeState(): GameState {
  return {
    meta: {
      round: 12,
      num_players: 3,
      player_order: ['player_0', 'player_1', 'player_2'],
      governor: 'player_0',
      phase: 'game_over',
      active_role: null,
      active_player: 'player_0',
      players_acted_this_phase: [],
      end_game_triggered: true,
      end_game_reason: null,
      vp_supply_remaining: 0,
      captain_consecutive_passes: 0,
    },
    common_board: {} as GameState['common_board'],
    players: {
      player_0: { display_name: 'Alice' } as GameState['players'][string],
      player_1: { display_name: 'Bob' } as GameState['players'][string],
      player_2: { display_name: 'Carol' } as GameState['players'][string],
    },
    decision: { type: 'game_over', player: 'player_0', note: '' },
    history: [],
    result_summary: null,
  };
}

function makeScores(): FinalScoreSummary {
  return {
    scores: {
      Alice: {
        vp_chips: 28,
        building_vp: 16,
        guild_hall_bonus: 2,
        residence_bonus: 4,
        fortress_bonus: 1,
        customs_house_bonus: 0,
        city_hall_bonus: 0,
        total: 51,
      },
      Bob: {
        vp_chips: 22,
        building_vp: 15,
        guild_hall_bonus: 0,
        residence_bonus: 0,
        fortress_bonus: 0,
        customs_house_bonus: 1,
        city_hall_bonus: 1,
        total: 39,
      },
    },
    winner: 'Alice',
    player_order: ['Alice', 'Bob'],
  };
}

describe('EndGamePanel', () => {
  it('renders terminal result summary and explicit return button', async () => {
    const onReturnToRooms = vi.fn();
    const user = userEvent.setup();

    render(
      <EndGamePanel
        state={makeState()}
        scores={makeScores()}
        onReturnToRooms={onReturnToRooms}
      />
    );

    expect(screen.getByText('🏁 게임 종료')).toBeTruthy();
    expect(screen.getByText('🏆 Alice')).toBeTruthy();
    expect(screen.getByRole('button', { name: '방 목록으로 돌아가기' })).toBeTruthy();

    await user.click(screen.getByRole('button', { name: '방 목록으로 돌아가기' }));
    expect(onReturnToRooms).toHaveBeenCalledOnce();
  });

  it('shows loading copy when fallback fetch has not completed yet', () => {
    render(
      <EndGamePanel
        state={makeState()}
        scores={null}
        onReturnToRooms={vi.fn()}
      />
    );

    expect(screen.getByText('점수 집계 중...')).toBeTruthy();
  });
});
