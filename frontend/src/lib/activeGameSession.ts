export type ActiveGameSession = {
  gameId: string;
  screen: 'lobby' | 'game';
  myPlayerId: string | null;
  myName: string | null;
  isSpectator: boolean;
  isMultiplayer: boolean;
};

const STORAGE_KEY = 'active_game_session';

function hasLocalStorage(): boolean {
  return typeof localStorage !== 'undefined';
}

export function readActiveGameSession(): ActiveGameSession | null {
  if (!hasLocalStorage()) return null;
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;

  try {
    const parsed = JSON.parse(raw) as Partial<ActiveGameSession>;
    if (
      typeof parsed.gameId !== 'string' ||
      (parsed.screen !== 'lobby' && parsed.screen !== 'game')
    ) {
      return null;
    }

    return {
      gameId: parsed.gameId,
      screen: parsed.screen,
      myPlayerId: typeof parsed.myPlayerId === 'string' ? parsed.myPlayerId : null,
      myName: typeof parsed.myName === 'string' ? parsed.myName : null,
      isSpectator: parsed.isSpectator === true,
      isMultiplayer: parsed.isMultiplayer === true,
    };
  } catch {
    return null;
  }
}

export function writeActiveGameSession(session: ActiveGameSession): void {
  if (!hasLocalStorage()) return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function clearActiveGameSession(): void {
  if (!hasLocalStorage()) return;
  localStorage.removeItem(STORAGE_KEY);
}
