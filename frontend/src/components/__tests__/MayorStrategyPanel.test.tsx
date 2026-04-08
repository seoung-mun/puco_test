import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import MayorStrategyPanel from '../MayorStrategyPanel';
import type { Player } from '../../types/gameState';

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
        {
          name: 'construction_hut',
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

describe('MayorStrategyPanel', () => {
  it('renders three strategy buttons with current-board previews', () => {
    render(
      <MayorStrategyPanel
        player={makePlayer()}
        actionMask={Array.from({ length: 200 }, (_, idx) => (idx >= 69 && idx <= 71 ? 1 : 0))}
      />,
    );

    expect(screen.getByRole('button', { name: /Captain Focus/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /Trade \/ Factory/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /Building Focus/i })).toBeTruthy();
    expect(screen.getByText('Wharf')).toBeTruthy();
    expect(screen.getByText('Small Market')).toBeTruthy();
    expect(screen.getByText('Construction Hut')).toBeTruthy();
    expect(screen.getAllByText('Corn').length).toBeGreaterThan(0);
  });

  it('dispatches the selected strategy action when enabled', async () => {
    const user = userEvent.setup();
    const onSelectStrategy = vi.fn();

    render(
      <MayorStrategyPanel
        player={makePlayer()}
        actionMask={Array.from({ length: 200 }, (_, idx) => (idx >= 69 && idx <= 71 ? 1 : 0))}
        onSelectStrategy={onSelectStrategy}
      />,
    );

    await user.click(screen.getByRole('button', { name: /Trade \/ Factory/i }));

    expect(onSelectStrategy).toHaveBeenCalledWith(70);
  });

  it('disables unavailable strategies and respects the panel disabled state', () => {
    render(
      <MayorStrategyPanel
        player={makePlayer()}
        actionMask={Array.from({ length: 200 }, (_, idx) => (idx === 69 ? 1 : 0))}
        disabled
      />,
    );

    const captain = screen.getByRole('button', { name: /Captain Focus/i });
    const trade = screen.getByRole('button', { name: /Trade \/ Factory/i });

    expect((captain as HTMLButtonElement).disabled).toBe(true);
    expect((trade as HTMLButtonElement).disabled).toBe(true);
  });
});
