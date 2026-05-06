import { useCallback, useState } from 'react';
import {
  clearActiveGameSession,
  readActiveGameSession,
  type ActiveGameSession,
} from '../lib/activeGameSession';

export type AuthUser = {
  id: string;
  nickname: string | null;
  needs_nickname: boolean;
};

type ScreenAfterBootstrap = 'login' | 'rooms' | 'lobby' | 'game';

type ActiveGameBootstrapResult = {
  screen: ScreenAfterBootstrap;
  activeGameSession: ActiveGameSession | null;
};

interface UseAuthBootstrapOptions {
  apiFetch: (url: string, options?: RequestInit) => Promise<Response>;
  backend: string;
}

export function useAuthBootstrap({ apiFetch, backend }: UseAuthBootstrapOptions) {
  const [authToken, setAuthToken] = useState<string | null>(() => localStorage.getItem('access_token'));
  const [authUser, setAuthUser] = useState<AuthUser | null>(null);
  const [nicknameInput, setNicknameInput] = useState('');
  const [nicknameError, setNicknameError] = useState<string | null>(null);

  const clearAuthSession = useCallback(() => {
    localStorage.removeItem('access_token');
    clearActiveGameSession();
    setAuthToken(null);
    setAuthUser(null);
    setNicknameInput('');
    setNicknameError(null);
  }, []);

  const bootstrapAuth = useCallback(async (tokenOverride?: string): Promise<ActiveGameBootstrapResult> => {
    const currentToken = tokenOverride ?? authToken;
    if (!currentToken) {
      return { screen: 'login', activeGameSession: null };
    }

    try {
      const meRes = await apiFetch(`${backend}/api/puco/auth/me`, {
        headers: { Authorization: `Bearer ${currentToken}` },
      });
      if (!meRes.ok) {
        clearAuthSession();
        return { screen: 'login', activeGameSession: null };
      }
      const user = await meRes.json() as AuthUser;
      setAuthUser(user);

      const activeSession = readActiveGameSession();
      if (!activeSession) {
        return { screen: 'rooms', activeGameSession: null };
      }

      try {
        const activeGameRes = await apiFetch(`${backend}/api/puco/session/active-game`, {
          headers: { Authorization: `Bearer ${currentToken}` },
        });
        if (!activeGameRes.ok) {
          clearActiveGameSession();
          return { screen: 'rooms', activeGameSession: null };
        }

        const activeGame = await activeGameRes.json() as {
          has_active_game?: boolean;
          game_id?: string;
          status?: string;
          is_host?: boolean;
          is_player?: boolean;
        };

        if (
          activeGame?.has_active_game !== true ||
          activeGame.game_id !== activeSession.gameId ||
          typeof activeGame.status !== 'string'
        ) {
          clearActiveGameSession();
          return { screen: 'rooms', activeGameSession: null };
        }

        const restoredScreen: ScreenAfterBootstrap =
          activeGame.status === 'WAITING' ? 'lobby' : 'game';
        return {
          screen: restoredScreen,
          activeGameSession: {
            ...activeSession,
            screen: restoredScreen,
          },
        };
      } catch {
        return { screen: 'rooms', activeGameSession: null };
      }
    } catch {
      clearAuthSession();
      return { screen: 'login', activeGameSession: null };
    }
  }, [apiFetch, authToken, backend, clearAuthSession]);

  return {
    authToken,
    setAuthToken,
    authUser,
    setAuthUser,
    nicknameInput,
    setNicknameInput,
    nicknameError,
    setNicknameError,
    bootstrapAuth,
    clearAuthSession,
  };
}
