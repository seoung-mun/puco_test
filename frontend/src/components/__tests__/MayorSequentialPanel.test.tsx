import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import MayorSequentialPanel from '../MayorSequentialPanel';
import type { Meta, Player } from '../../types/gameState';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { defaultValue?: string }) => options?.defaultValue ?? key,
  }),
}));

function makePlayer(): Player {
  return {
    display_name: 'Alice',
    display_number: 1,
    is_governor: false,
    doubloons: 2,
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
      d_used_spaces: 3,
      d_empty_spaces: 9,
      colonists_unplaced: 3,
      d_quarry_discount: 0,
      d_total_empty_colonist_slots: 4,
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
}

function makeMeta(): Meta {
  return {
    round: 1,
    num_players: 3,
    player_order: ['player_0', 'player_1', 'player_2'],
    governor: 'player_0',
    phase: 'mayor_action',
    active_role: 'mayor',
    active_player: 'player_0',
    players_acted_this_phase: [],
    end_game_triggered: false,
    end_game_reason: null,
    vp_supply_remaining: 75,
    captain_consecutive_passes: 0,
    mayor_phase_mode: 'slot-direct',
    mayor_remaining_colonists: 3,
    mayor_legal_island_slots: [0, 1],
    mayor_legal_city_slots: [0, 1],
  };
}

describe('MayorSequentialPanel', () => {
  it('renders legal island and city slot actions', () => {
    render(
      <MayorSequentialPanel
        player={makePlayer()}
        meta={makeMeta()}
        actionMask={Array.from(
          { length: 200 },
          (_, idx) => (idx === 120 || idx === 121 || idx === 140 || idx === 141 ? 1 : 0),
        )}
      />,
    );

    expect(screen.getByRole('button', { name: /^corn$/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /^indigo$/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /wharf/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /small market/i })).toBeTruthy();
  });

  it('dispatches the mapped slot action index when a legal slot is clicked', async () => {
    const user = userEvent.setup();
    const onPlaceColonist = vi.fn();

    render(
      <MayorSequentialPanel
        player={makePlayer()}
        meta={makeMeta()}
        actionMask={Array.from(
          { length: 200 },
          (_, idx) => (idx === 120 || idx === 121 || idx === 140 || idx === 141 ? 1 : 0),
        )}
        onPlaceColonist={onPlaceColonist}
      />,
    );

    await user.click(screen.getByRole('button', { name: /^indigo$/i }));
    await user.click(screen.getByRole('button', { name: /wharf/i }));

    expect(onPlaceColonist).toHaveBeenNthCalledWith(1, 121);
    expect(onPlaceColonist).toHaveBeenNthCalledWith(2, 140);
  });

  it('disables illegal slots and respects the panel disabled state', () => {
    render(
      <MayorSequentialPanel
        player={makePlayer()}
        meta={makeMeta()}
        actionMask={Array.from(
          { length: 200 },
          (_, idx) => (idx === 120 || idx === 140 ? 1 : 0),
        )}
        disabled
      />,
    );

    expect((screen.getByRole('button', { name: /^corn$/i }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole('button', { name: /^indigo$/i }) as HTMLButtonElement).disabled).toBe(true);
  });
});
