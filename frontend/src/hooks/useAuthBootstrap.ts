import { useCallback, useState } from 'react';

export type AuthUser = {
  id: string;
  nickname: string | null;
  needs_nickname: boolean;
};

type ScreenAfterBootstrap = 'login' | 'rooms';

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
    setAuthToken(null);
    setAuthUser(null);
    setNicknameInput('');
    setNicknameError(null);
  }, []);

  const bootstrapAuth = useCallback(async (tokenOverride?: string): Promise<ScreenAfterBootstrap> => {
    const currentToken = tokenOverride ?? authToken;
    if (!currentToken) {
      return 'login';
    }

    try {
      const meRes = await apiFetch(`${backend}/api/puco/auth/me`, {
        headers: { Authorization: `Bearer ${currentToken}` },
      });
      if (!meRes.ok) {
        clearAuthSession();
        return 'login';
      }
      const user = await meRes.json() as AuthUser;
      setAuthUser(user);
      return 'rooms';
    } catch {
      clearAuthSession();
      return 'login';
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
