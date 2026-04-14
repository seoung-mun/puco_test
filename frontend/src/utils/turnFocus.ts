import type { PhaseType } from '../types/gameState';

export function getTurnFocusTargetId(phase: PhaseType, player: string): string {
  switch (phase) {
    case 'role_selection':
      return 'common-board';
    case 'settler_action':
      return 'section-plantations';
    case 'mayor_action':
      return `player-${player}`;
    case 'builder_action':
      return 'san-juan';
    case 'craftsman_action':
      return `player-${player}`;
    case 'trader_action':
    case 'captain_action':
    case 'captain_discard':
      return 'action-card';
    default:
      return 'common-board';
  }
}

export function getTurnFocusBlock(targetId: string): ScrollLogicalPosition {
  return targetId === 'action-card' ? 'end' : 'center';
}

type ShouldAutoFocusTurnInput = {
  isFirstLoad: boolean;
  isMyTurn: boolean;
  phaseChanged: boolean;
  playerChanged: boolean;
  didBecomeMyTurn: boolean;
};

export function shouldAutoFocusTurn({
  isFirstLoad,
  isMyTurn,
  phaseChanged,
  playerChanged,
  didBecomeMyTurn,
}: ShouldAutoFocusTurnInput): boolean {
  if (isFirstLoad || !isMyTurn) {
    return false;
  }

  return phaseChanged || playerChanged || didBecomeMyTurn;
}
