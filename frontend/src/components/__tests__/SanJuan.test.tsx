import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import i18n from '../../i18n';
import type { CommonBoard } from '../../types/gameState';
import SanJuan from '../SanJuan';

type BuilderInfo = NonNullable<Parameters<typeof SanJuan>[0]['builderInfo']>;

function makeGuildHallBoard(): CommonBoard['available_buildings'] {
  return {
    guild_hall: {
      cost: 10,
      max_colonists: 1,
      vp: 4,
      copies_remaining: 1,
      action_index: 34,
    },
  };
}

function makeBuilderInfo(overrides: Partial<BuilderInfo> = {}): BuilderInfo {
  return {
    player: 'player_0',
    activeQuarries: 0,
    isRolePicker: false,
    doubloons: 10,
    cityEmptySpaces: 2,
    ownedBuildings: [],
    ...overrides,
  };
}

describe('SanJuan guild hall presentation', () => {
  beforeEach(async () => {
    await act(async () => {
      await i18n.changeLanguage('en');
    });
  });

  afterEach(async () => {
    await act(async () => {
      await i18n.changeLanguage('ko');
    });
  });

  it('renders Guild Hall with the localized label and without sold-out masking when stock exists', () => {
    render(
      <SanJuan
        buildings={makeGuildHallBoard()}
        builderInfo={makeBuilderInfo()}
        onBuild={vi.fn()}
      />
    );

    const guildTile = screen.getByText('Guild').closest('g');
    expect(guildTile).not.toBeNull();
    expect(guildTile?.getAttribute('opacity')).toBe('1');
    expect(screen.queryByText(/guildhall/i)).toBeNull();
  });

  it('dims Guild Hall only after the player already owns it', () => {
    render(
      <SanJuan
        buildings={makeGuildHallBoard()}
        builderInfo={makeBuilderInfo({ ownedBuildings: ['guild_hall'] })}
        onBuild={vi.fn()}
      />
    );

    const guildTile = screen.getByText('Guild').closest('g');
    expect(guildTile?.getAttribute('opacity')).toBe('0.85');
  });
});
