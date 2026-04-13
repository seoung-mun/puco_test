import HomeScreen from './HomeScreen';
import JoinScreen from './JoinScreen';
import LobbyScreen from './LobbyScreen';
import LoginScreen from './LoginScreen';
import RoomListScreen from './RoomListScreen';
import type { LobbyPlayer } from '../types/gameState';
import type { AuthUser } from '../hooks/useAuthBootstrap';

type Screen = 'loading' | 'login' | 'home' | 'rooms' | 'join' | 'lobby' | 'game';

interface Props {
  screen: Screen;
  backend: string;
  authToken: string | null;
  authUser: AuthUser | null;
  nicknameInput: string;
  nicknameError: string | null;
  error: string | null;
  myName: string | null;
  lobbyPlayers: LobbyPlayer[];
  lobbyHost: string | null;
  lobbyError: string | null;
  onGoogleLogin: (credentialResponse: { credential?: string }) => void;
  onGoogleLoginError: () => void;
  googleLoginAvailable: boolean;
  onNicknameChange: (value: string) => void;
  onSetNickname: () => void;
  onGoToRooms: () => void;
  onLogout: () => void;
  onCreateRoom: (title: string, isPrivate: boolean, password: string | null) => Promise<string | null>;
  onCreateBotGame: (botTypes: string[]) => Promise<string | null>;
  onJoinRoom: (roomId: string) => void;
  onJoin: (key: string, name: string, role: 'player' | 'spectator') => Promise<string | null>;
  onLobbyStart: () => Promise<void>;
  onLeaveLobbyToLogin: () => Promise<void>;
  onAddBot: (_botName: string, botType: string) => Promise<void>;
  onRemoveBot: (slotIndex: number) => Promise<void>;
  onBackFromLobby: () => Promise<void>;
}

export default function AppScreenGate({
  screen,
  backend,
  authToken,
  authUser,
  nicknameInput,
  nicknameError,
  error,
  myName,
  lobbyPlayers,
  lobbyHost,
  lobbyError,
  onGoogleLogin,
  onGoogleLoginError,
  googleLoginAvailable,
  onNicknameChange,
  onSetNickname,
  onGoToRooms,
  onLogout,
  onCreateRoom,
  onCreateBotGame,
  onJoinRoom,
  onJoin,
  onLobbyStart,
  onLeaveLobbyToLogin,
  onAddBot,
  onRemoveBot,
  onBackFromLobby,
}: Props) {
  if (screen === 'loading') {
    return <div style={{ color: '#eee', padding: 40, textAlign: 'center' }}>Loading...</div>;
  }
  if (screen === 'login') {
    return <LoginScreen
      onGoogleLogin={onGoogleLogin}
      onGoogleLoginError={onGoogleLoginError}
      googleLoginAvailable={googleLoginAvailable}
      isLoggedIn={!!authToken}
      needsNickname={authUser?.needs_nickname ?? false}
      nicknameInput={nicknameInput}
      onNicknameChange={onNicknameChange}
      onSetNickname={onSetNickname}
      nicknameError={nicknameError}
      error={error}
    />;
  }
  if (screen === 'home') {
    return <HomeScreen
      onMultiplayer={onGoToRooms}
      onLogout={onLogout}
      userNickname={authUser?.nickname ?? null}
      error={error}
    />;
  }
  if (screen === 'rooms') {
    return <RoomListScreen
      token={authToken ?? ''}
      userNickname={authUser?.nickname ?? null}
      onCreateRoom={onCreateRoom}
      onCreateBotGame={onCreateBotGame}
      onJoinRoom={onJoinRoom}
      onLogout={onLogout}
      error={error}
    />;
  }
  if (screen === 'join') {
    return <JoinScreen backendUrl={backend} onJoin={onJoin} />;
  }
  if (screen === 'lobby') {
    return <LobbyScreen
      players={lobbyPlayers}
      host={lobbyHost ?? ''}
      myName={myName ?? ''}
      onStart={onLobbyStart}
      onLogout={onLeaveLobbyToLogin}
      onAddBot={onAddBot}
      onRemoveBot={onRemoveBot}
      error={lobbyError}
      onBack={onBackFromLobby}
    />;
  }
  return null;
}
