import { describe, expect, it } from 'vitest';

import {
  getTurnFocusBlock,
  getTurnFocusTargetId,
  shouldAutoFocusTurn,
} from '../utils/turnFocus';

describe('turnFocus helpers', () => {
  it('focuses the current player panel during mayor turns', () => {
    expect(getTurnFocusTargetId('mayor_action', 'player_1')).toBe('player-player_1');
    expect(getTurnFocusBlock('player-player_1')).toBe('center');
  });

  it('does not auto-focus when it is not my turn', () => {
    expect(
      shouldAutoFocusTurn({
        isFirstLoad: false,
        isMyTurn: false,
        phaseChanged: true,
        playerChanged: true,
        didBecomeMyTurn: false,
      }),
    ).toBe(false);
  });

  it('auto-focuses once the turn becomes mine even without a phase change', () => {
    expect(
      shouldAutoFocusTurn({
        isFirstLoad: false,
        isMyTurn: true,
        phaseChanged: false,
        playerChanged: false,
        didBecomeMyTurn: true,
      }),
    ).toBe(true);
  });
});
