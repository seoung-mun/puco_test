import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import CommonBoardPanel from '../CommonBoardPanel';
import type { CommonBoard } from '../../types/gameState';

function makeBoard(): CommonBoard {
  return {
    roles: {
      settler: { doubloons_on_role: 0, taken_by: null },
      mayor: { doubloons_on_role: 0, taken_by: null },
      builder: { doubloons_on_role: 0, taken_by: null },
      craftsman: { doubloons_on_role: 0, taken_by: null },
      trader: { doubloons_on_role: 0, taken_by: null },
      captain: { doubloons_on_role: 0, taken_by: null },
      prospector: { doubloons_on_role: 0, taken_by: null },
      prospector_2: { doubloons_on_role: 0, taken_by: null },
    },
    colonists: {
      ship: 0,
      supply: 0,
    },
    trading_house: {
      goods: [],
      d_spaces_used: 0,
      d_spaces_remaining: 4,
      d_is_full: false,
    },
    cargo_ships: [],
    available_plantations: {
      face_up: [{ type: 'corn', action_index: 8 }],
      draw_pile: {
        corn: 1,
        indigo: 1,
        sugar: 1,
        tobacco: 1,
        coffee: 1,
      },
    },
    available_buildings: {},
    quarry_supply_remaining: 8,
    goods_supply: {
      corn: 0,
      indigo: 0,
      sugar: 0,
      tobacco: 0,
      coffee: 0,
    },
  };
}

describe('CommonBoardPanel', () => {
  it('shows the hacienda follow-up guidance when the extra draw already resolved', () => {
    render(
      <CommonBoardPanel
        board={makeBoard()}
        playerNames={{}}
        numPlayers={3}
        phase="settler_action"
        onSettlePlantation={vi.fn()}
        canUseHacienda={false}
        showHaciendaFollowup
      />
    );

    expect(
      screen.getByText(/하시엔다로 추가 농지 1개를 받았습니다/i)
    ).toBeTruthy();
  });
});
