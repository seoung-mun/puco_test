import { useEffect, useRef, useState } from 'react';
import { useGameWebSocket } from './hooks/useGameWebSocket';
import { useGameSSE } from './hooks/useGameSSE';
import { useAuthBootstrap } from './hooks/useAuthBootstrap';
import { useTranslation } from 'react-i18next';
import type { FinalScoreSummary, GameState } from './types/gameState';
import AppScreenGate from './components/AppScreenGate';
import GameScreen from './components/GameScreen';
import type { LobbyPlayer } from './types/gameState';
import './App.css';

type Screen = 'loading' | 'login' | 'home' | 'rooms' | 'join' | 'lobby' | 'game';

// Maps history action → role key (for popup coloring)
const ACTION_TO_ROLE: Record<string, string> = {
  settle_plantation:   'settler',
  build:               'builder',
  craftsman_privilege: 'craftsman',
  sell:                'trader',
  load_ship:           'captain',
  discard:             'captain',
};

const BACKEND = '';
const _INTERNAL_KEY = (import.meta.env.VITE_INTERNAL_API_KEY as string) || '';

/** API 오류 응답을 한 줄 메시지로 파싱한다. */
async function parseApiError(res: Response): Promise<string> {
  const text = await res.text();
  try {
    const data = JSON.parse(text) as { detail?: unknown };
    const detail = data?.detail;
    if (typeof detail === 'string') return detail;
    if (typeof detail === 'object' && detail !== null) {
      const d = detail as Record<string, unknown>;
      const parts: string[] = [];
      if (typeof d.message === 'string') parts.push(d.message);
      if (d.slot_info !== undefined) parts.push(`슬롯: ${d.slot_info}`);
      if (d.slot_capacity !== undefined) parts.push(`용량: ${d.slot_capacity}`);
      if (Array.isArray(d.valid_amounts)) parts.push(`가능한 배치: [${(d.valid_amounts as number[]).join(', ')}]`);
      if (d.unplaced_colonists !== undefined) parts.push(`미배치: ${d.unplaced_colonists}명`);
      return parts.length > 0 ? parts.join(' | ') : text;
    }
  } catch { /* ignore parse error */ }
  return text;
}

/** Legacy API 호출 래퍼: INTERNAL_API_KEY 헤더를 자동으로 포함 */
function apiFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const headers = new Headers(options.headers as HeadersInit);
  if (_INTERNAL_KEY) headers.set('X-API-Key', _INTERNAL_KEY);
  return fetch(url, { ...options, headers });
}

/** Good name → Good enum value (matches PuCo_RL configs/constants.py) */
const GOOD_VALUE: Record<string, number> = {
  coffee: 0, tobacco: 1, corn: 2, sugar: 3, indigo: 4,
};

/** Channel API action_index helpers */
const channelActionIndex = {
  sell: (good: string): number => 39 + (GOOD_VALUE[good] ?? 0),
  loadShip: (good: string, shipIndex: number): number => 44 + shipIndex * 5 + (GOOD_VALUE[good] ?? 0),
  loadWharf: (good: string): number => 59 + (GOOD_VALUE[good] ?? 0),
  craftsmanPriv: (good: string): number => 93 + (GOOD_VALUE[good] ?? 0),
  storeWindrose: (good: string): number => 64 + (GOOD_VALUE[good] ?? 0),
  storeWarehouse: (good: string): number => 106 + (GOOD_VALUE[good] ?? 0),
};

export default function App() {
  const { t } = useTranslation();
  const isAdmin = new URLSearchParams(window.location.search).has('admin');
  const [state, setState] = useState<GameState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [buildConfirm, setBuildConfirm] = useState<{ name: string; cost: number; vp: number } | null>(null);
  const [passing, setPassing] = useState(false);
  const [pendingSettlement, setPendingSettlement] = useState<string | null>(null);
  const [roundFlash, setRoundFlash] = useState<number | null>(null);
  const [discardProtected, setDiscardProtected] = useState<string[]>([]);
  const [discardSingleExtra, setDiscardSingleExtra] = useState<string | null>(null);
  const [finalScores, setFinalScores] = useState<FinalScoreSummary | null>(null);
  const prevRoundRef = useRef<number | null>(null);
  const prevPhaseRef = useRef<string | null>(null);
  const prevActivePlayerRef = useRef<string | null>(null);
  const prevHaciendaUsedRef = useRef<boolean>(false);
  const [popups, setPopups] = useState<{ id: number; text: string; isRoundEnd: boolean; role: string | null }[]>([]);
  const popupTimersRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  const popupIdRef = useRef(0);
  const prevHistoryLenRef = useRef<number>(-1);
  const actionRequestSeqRef = useRef(0);

  const {
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
  } = useAuthBootstrap({ apiFetch, backend: BACKEND });

  // --- Multiplayer / screen routing ---
  const [screen, setScreen] = useState<Screen>('loading');
  const [gameId, setGameId] = useState<string | null>(null);
  const [myName, setMyName] = useState<string | null>(null);
  const [myPlayerId, setMyPlayerId] = useState<string | null>(null);
  const [isMultiplayer, setIsMultiplayer] = useState(false);
  const [isSpectator, setIsSpectator] = useState(false);
  const [lobbyPlayers, setLobbyPlayers] = useState<LobbyPlayer[]>([]);
  const [lobbyHost, setLobbyHost] = useState<string | null>(null);
  const [lobbyError, setLobbyError] = useState<string | null>(null);

  const lobbyWsRef = useRef<WebSocket | null>(null);


  useEffect(() => {
    if (!state) return;
    if (prevRoundRef.current !== null && state.meta.round !== prevRoundRef.current) {
      setRoundFlash(prevRoundRef.current);
      setTimeout(() => setRoundFlash(null), 3000);
    }
    prevRoundRef.current = state.meta.round;
  }, [state?.meta.round]);

  useEffect(() => {
    if (!state) return;
    const phase = state.meta.phase;
    const player = state.meta.active_player;
    if (phase === prevPhaseRef.current && player === prevActivePlayerRef.current) return;
    const isFirstLoad = prevPhaseRef.current === null;
    prevPhaseRef.current = phase;
    prevActivePlayerRef.current = player;
    if (isFirstLoad) return;

    let targetId: string;
    switch (phase) {
      case 'role_selection':
        targetId = 'common-board';
        break;
      case 'settler_action':
        targetId = 'section-plantations';
        break;
      case 'mayor_action':
        targetId = 'action-card';
        break;
      case 'builder_action':
        targetId = 'san-juan';
        break;
      case 'craftsman_action':
        targetId = `player-${player}`;
        break;
      case 'trader_action':
      case 'captain_action':
      case 'captain_discard':
        targetId = 'action-card';
        break;
      default:
        targetId = 'common-board';
    }

    const el = document.getElementById(targetId);
    if (el) {
      const block = targetId === 'action-card' ? 'end' : 'center';
      el.scrollIntoView({ behavior: 'smooth', block });
      el.classList.add('focus-highlight');
      setTimeout(() => el.classList.remove('focus-highlight'), 1800);
    }
  }, [state?.meta.phase, state?.meta.active_player]);

  // Scroll to island + highlight when hacienda ability is used
  useEffect(() => {
    if (!state) return;
    const player = state.meta.active_player;
    const usedNow = state.players[player]?.hacienda_used_this_phase ?? false;
    const usedBefore = prevHaciendaUsedRef.current;
    prevHaciendaUsedRef.current = usedNow;
    if (!usedBefore && usedNow && state.meta.phase === 'settler_action') {
      const el = document.getElementById(`player-${player}-island`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el.classList.add('focus-highlight');
        setTimeout(() => el.classList.remove('focus-highlight'), 1800);
      }
      setTimeout(() => {
        document.getElementById('section-plantations')
          ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }, 1600);
    }
  }, [state?.players[state?.meta?.active_player ?? '']?.hacienda_used_this_phase]);

  useEffect(() => {
    const newLen = state?.history?.length ?? 0;
    if (prevHistoryLenRef.current === -1) {
      prevHistoryLenRef.current = newLen;
      return;
    }
    if (newLen <= prevHistoryLenRef.current) return;

    const newEntries = state!.history.slice(prevHistoryLenRef.current);
    prevHistoryLenRef.current = newLen;

    // Cancel pending popup timers and clear existing popups
    popupTimersRef.current.forEach(clearTimeout);
    popupTimersRef.current = [];
    setPopups([]);

    const STAGGER = 200; // ms between each popup appearing
    const entries = newEntries.slice(0, 8); // max 8 popups

    entries.forEach((e, i) => {
      const roleKey: string | null = e.params.role ?? ACTION_TO_ROLE[e.action] ?? null;
      const params = { ...e.params };
      if (params.role)       params.role       = `<strong>${t(`roles.${params.role}`, { defaultValue: params.role })}</strong>`;
      if (params.player)     params.player     = `<strong>${params.player}</strong>`;
      if (params.good)       params.good       = t(`goods.${params.good}`,            { defaultValue: params.good });
      if (params.plantation) params.plantation = t(`plantations.${params.plantation}`,{ defaultValue: params.plantation });
      if (params.building)   params.building   = t(`buildings.${params.building}`,    { defaultValue: params.building });
      const text = t(`history.actions.${e.action}`, { ...params, defaultValue: e.action });
      const isRoundEnd = e.action === 'round_end';
      const id = ++popupIdRef.current;
      const showAt = i * STAGGER;
      const hideAt = showAt + 5000;

      const t1 = setTimeout(() => setPopups(prev => [...prev, { id, text, isRoundEnd, role: roleKey }]), showAt);
      const t2 = setTimeout(() => setPopups(prev => prev.filter(p => p.id !== id)), hideAt);
      popupTimersRef.current.push(t1, t2);
    });
  }, [state?.history?.length]);

  useEffect(() => {
    if (!state?.meta.end_game_triggered) return;
    window.scrollTo({ top: 0, behavior: 'smooth' });
    if (state.result_summary) return;
    if (!gameId || !authToken) return;

    let cancelled = false;
    fetch(`${BACKEND}/api/puco/game/${gameId}/final-score`, {
      headers: { 'Authorization': `Bearer ${authToken}` },
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(await parseApiError(response));
        }
        return response.json() as Promise<FinalScoreSummary>;
      })
      .then((data) => {
        if (!cancelled) {
          setFinalScores(data);
        }
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [authToken, gameId, state?.meta.end_game_triggered, state?.result_summary]);

  useEffect(() => {
    if (state?.meta.end_game_triggered) return;
    setFinalScores(null);
  }, [state?.meta.end_game_triggered, state?.meta.game_id]);

  useEffect(() => {
    let cancelled = false;
    void bootstrapAuth().then((nextScreen) => {
      if (!cancelled) {
        setScreen(nextScreen);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [bootstrapAuth]);

  async function handleGoogleLogin(credentialResponse: { credential?: string }) {
    if (!credentialResponse.credential) return;
    try {
      const res = await apiFetch(`${BACKEND}/api/puco/auth/google`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ credential: credentialResponse.credential }),
      });
      if (!res.ok) {
        const err = await res.json();
        setError(err.detail || 'Login failed');
        return;
      }
      const data = await res.json();
      localStorage.setItem('access_token', data.access_token);
      setAuthToken(data.access_token);
      setAuthUser(data.user);
      if (data.user.needs_nickname) {
        setNicknameInput('');
      }
      const nextScreen = await bootstrapAuth(data.access_token);
      setScreen(nextScreen);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Login failed');
    }
  }

  async function handleSetNickname() {
    if (!authToken || !nicknameInput.trim()) return;
    setNicknameError(null);
    try {
      const res = await apiFetch(`${BACKEND}/api/puco/auth/me/nickname`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${authToken}` },
        body: JSON.stringify({ nickname: nicknameInput.trim() }),
      });
      if (!res.ok) {
        const err = await res.json();
        setNicknameError(err.detail || 'Failed to set nickname');
        return;
      }
      const user = await res.json();
      setAuthUser({ id: user.id, nickname: user.nickname, needs_nickname: false });
    } catch (e) {
      setNicknameError(e instanceof Error ? e.message : 'Failed');
    }
  }

  // SSE: Channel 전환으로 비활성화 (sessionKey=null → 연결 안 함)
  useGameSSE({
    sessionKey: null,
    playerName: myName,
    backend: BACKEND,
    onStateUpdate: () => {},
    onLobbyUpdate: () => {},
  });

  // Channel WebSocket: game 화면에서 gameId가 있을 때 실시간 상태 수신
  useGameWebSocket({
    gameId: screen === 'game' ? gameId : null,
    token: authToken,
    onStateUpdate: (gs) => {
      console.warn('[STATE_TRACE] frontend_set_state_before', {
        active_player: gs.meta.active_player,
        bot_thinking: gs.meta.bot_thinking,
        phase: gs.meta.phase,
        history_length: gs.history.length,
      });
      setState(prev => {
        console.warn('[STATE_TRACE] frontend_set_state_applied', {
          prev_active_player: prev?.meta.active_player ?? null,
          next_active_player: gs.meta.active_player,
          next_bot_thinking: gs.meta.bot_thinking,
          next_phase: gs.meta.phase,
        });
        return gs;
      });
    },
    onGameEnded: () => {},
    onPlayerDisconnected: () => {},
  });

  // Channel mode: lobby 및 heartbeat 폴링 불필요 — WebSocket이 실시간 상태 전달

  useEffect(() => {
    if (!state) return;
    console.warn('[STATE_TRACE] frontend_render_state', {
      active_player: state.meta.active_player,
      bot_thinking: state.meta.bot_thinking,
      phase: state.meta.phase,
      game_id: state.meta.game_id,
    });
  }, [state?.meta.active_player, state?.meta.bot_thinking, state?.meta.phase, state?.meta.game_id]);

  useEffect(() => {
    if (!state) return;
    const isBotTurn = !!state.bot_players?.[state.meta.active_player];
    const isBlocked = !!state.meta.bot_thinking || isBotTurn;
    console.warn('[STATE_TRACE] frontend_ui_block_state', {
      game_id: state.meta.game_id,
      active_player: state.meta.active_player,
      bot_thinking: state.meta.bot_thinking,
      isBotTurn,
      isBlocked,
      phase: state.meta.phase,
    });
  }, [state?.meta.active_player, state?.meta.bot_thinking, state?.meta.phase, state?.meta.game_id, state?.bot_players]);

  async function leaveLobbyRoom() {
    if (!gameId || !authToken) return;
    try {
      await fetch(`/api/puco/rooms/${gameId}/leave`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${authToken}` },
      });
    } catch {
      // Best-effort cleanup; UI still needs to unwind local lobby state.
    }
  }

  function resetNavigationState(nextScreen: Exclude<Screen, 'loading'>, clearAuth = false) {
    closeLobbyWs();
    resetGameUiState();
    localStorage.removeItem('mp_key');
    localStorage.removeItem('mp_name');
    setMyName(null);
    setMyPlayerId(null);
    setIsMultiplayer(false);
    setIsSpectator(false);
    setLobbyPlayers([]);
    setLobbyHost(null);
    setState(null);
    setGameId(null);
    setError(null);
    if (clearAuth) {
      clearAuthSession();
    }
    setScreen(nextScreen);
  }

  function goToRoomsPreservingAuth() {
    if (!authToken) {
      resetNavigationState('login', true);
      return;
    }
    resetNavigationState('rooms');
  }

  function logoutToLogin() {
    resetNavigationState('login', true);
  }

  /** Channel API: 단일 action_index로 모든 게임 액션을 처리 */
  async function channelAction(actionIndex: number): Promise<void> {
    if (!gameId || !authToken) return;
    const requestSeq = ++actionRequestSeqRef.current;
    const maskAllowed = state?.action_mask?.[actionIndex] ?? null;
    console.warn('[ACTION_TRACE] frontend_action_submit', {
      gameId,
      requestSeq,
      actionIndex,
      phase: state?.meta.phase ?? null,
      activePlayer: state?.meta.active_player ?? null,
      maskAllowed,
    });
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`${BACKEND}/api/puco/game/${gameId}/action`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${authToken}`,
        },
        body: JSON.stringify({ payload: { action_index: actionIndex } }),
      });
      if (!res.ok) {
        setError(await parseApiError(res));
        return;
      }
      const data = await res.json();
      console.warn('[ACTION_TRACE] frontend_action_response', {
        gameId,
        requestSeq,
        actionIndex,
        responsePhase: data.state?.meta?.phase ?? null,
        responseActivePlayer: data.state?.meta?.active_player ?? null,
      });
      // Ignore late REST responses so the latest action state cannot be overwritten
      // by an older in-flight request during multi-step phases like Settler/Hacienda.
      if (data.state && requestSeq === actionRequestSeqRef.current) {
        setState(data.state as GameState);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Request failed');
    } finally {
      setSaving(false);
    }
  }

  /** 방 목록 화면으로 이동 */
  function handleGoToRooms() {
    goToRoomsPreservingAuth();
  }

  /** Channel: 방 생성 (RoomListScreen에서 호출) */
  async function handleCreateRoom(title: string, isPrivate: boolean, password: string | null): Promise<string | null> {
    if (!authToken) return 'Not logged in';
    try {
      const res = await fetch(`${BACKEND}/api/puco/rooms/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${authToken}` },
        body: JSON.stringify({ title, is_private: isPrivate, password: password ?? undefined }),
      });
      if (!res.ok) { return await parseApiError(res); }
      const room = await res.json();
      const gid: string = room.id;
      const myEntry = authUser?.nickname ?? authUser?.id ?? title;
      setGameId(gid);
      setMyName(myEntry);
      setIsMultiplayer(true);
      setLobbyHost(myEntry);
      setLobbyPlayers([{ name: myEntry, player_id: authUser?.id ?? '', connected: true }]);
      setScreen('lobby');
      connectLobbyWs(gid);
      return null;
    } catch (e) {
      return e instanceof Error ? e.message : 'Failed';
    }
  }

  /** Channel: 봇전 생성 — 선택한 BOT×3 자동 시작, 사용자는 관전자 */
  async function handleCreateBotGame(botTypes: string[]): Promise<string | null> {
    if (!authToken) return 'Not logged in';
    setError(null);
    try {
      const res = await fetch(`${BACKEND}/api/puco/rooms/bot-game`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify({ bot_types: botTypes }),
      });
      if (!res.ok) {
        const message = await parseApiError(res);
        setError(message);
        return message;
      }
      const data = await res.json();
      setState(data.state);
      setGameId(data.game_id);
      setIsSpectator(true);
      setIsMultiplayer(false);
      setScreen('game');
      return null;
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Failed';
      setError(message);
      return message;
    }
  }

  /** Channel: 방 참가 (RoomListScreen에서 API join 후 호출) */
  function handleJoinRoom(roomId: string) {
    const myEntry = authUser?.nickname ?? authUser?.id ?? 'Player';
    setGameId(roomId);
    setMyName(myEntry);
    setIsMultiplayer(true);
    setLobbyPlayers([{ name: myEntry, player_id: authUser?.id ?? '', connected: true }]);
    setScreen('lobby');
    connectLobbyWs(roomId);
  }

  /** Channel: 방 참가 (게임 ID로 직접) */
  async function handleJoin(key: string, name: string, role: 'player' | 'spectator'): Promise<string | null> {
    void role; // spectator mode not yet supported in channel API
    if (!authToken) return 'Not logged in';
    try {
      // key is game_id in channel mode
      setGameId(key);
      setMyName(name);
      setIsMultiplayer(true);
      setScreen('lobby');
      return null;
    } catch (e) {
      return e instanceof Error ? e.message : 'Failed';
    }
  }

  /** Channel: 봇 추가 */
  async function handleAddBot(_botName: string, botType: string) {
    if (!gameId || !authToken) return;
    setLobbyError(null);
    try {
      const res = await fetch(`${BACKEND}/api/puco/game/${gameId}/add-bot`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${authToken}` },
        body: JSON.stringify({ bot_type: botType }),
      });
      if (!res.ok) { setLobbyError(await res.text()); return; }
      // 로컬 상태 업데이트 제거 — Lobby WebSocket LOBBY_UPDATE가 서버의 정확한 목록을 브로드캐스트함
      await res.json();
    } catch (e) {
      setLobbyError(e instanceof Error ? e.message : 'Failed');
    }
  }

  /** Channel: 봇 제거 — 현재 channel API에서 미지원, 로컬 상태만 갱신 */
  async function handleRemoveBot(slotIndex: number) {
    if (!gameId || !authToken) return;
    setLobbyError(null);
    try {
      const res = await fetch(`${BACKEND}/api/puco/game/${gameId}/bots/${slotIndex}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (!res.ok) {
        setLobbyError(await parseApiError(res));
        return;
      }
      await res.json();
    } catch (e) {
      setLobbyError(e instanceof Error ? e.message : 'Failed');
    }
  }

  function connectLobbyWs(roomId: string) {
    if (lobbyWsRef.current) {
      lobbyWsRef.current.close();
    }
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${window.location.host}/api/puco/ws/lobby/${roomId}`);
    lobbyWsRef.current = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ token: authToken }));
    };

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === 'LOBBY_STATE' || msg.type === 'LOBBY_UPDATE') {
        setLobbyPlayers(msg.players ?? []);
        // Keep isHost working: lobbyHost stores the host's display name
        const hostPlayer = (msg.players ?? []).find((p: { is_host?: boolean }) => p.is_host);
        setLobbyHost(hostPlayer?.name ?? null);
      } else if (msg.type === 'ROOM_DELETED') {
        closeLobbyWs();
        setScreen('rooms');
        setLobbyError('방이 삭제되었습니다.');
      } else if (msg.type === 'GAME_STARTED') {
        const gs = msg.state as GameState;
        setState(gs);
        const humanEntry = Object.entries(gs.players).find(([, p]) => (p as { display_name?: string }).display_name === myName);
        if (humanEntry) setMyPlayerId(humanEntry[0]);
        closeLobbyWs();
        setScreen('game');
      }
    };
  }

  function closeLobbyWs() {
    lobbyWsRef.current?.close();
    lobbyWsRef.current = null;
  }

  function resetGameUiState() {
    actionRequestSeqRef.current += 1;
    popupTimersRef.current.forEach(clearTimeout);
    popupTimersRef.current = [];
    setPopups([]);
    setRoundFlash(null);
    setSaving(false);
    setPassing(false);
    setBuildConfirm(null);
    setPendingSettlement(null);
    setDiscardProtected([]);
    setDiscardSingleExtra(null);
    setFinalScores(null);
    setLobbyError(null);
    prevRoundRef.current = null;
    prevPhaseRef.current = null;
    prevActivePlayerRef.current = null;
    prevHaciendaUsedRef.current = false;
    prevHistoryLenRef.current = -1;
  }

  function handleReturnToRooms() {
    closeLobbyWs();
    resetGameUiState();
    setState(null);
    setGameId(null);
    setMyName(null);
    setMyPlayerId(null);
    setIsMultiplayer(false);
    setIsSpectator(false);
    setLobbyPlayers([]);
    setLobbyHost(null);
    setError(null);
    setScreen('rooms');
  }

  /** Channel: 게임 시작 */
  async function handleLobbyStart() {
    if (!gameId || !authToken) return;
    setLobbyError(null);
    try {
      const res = await fetch(`${BACKEND}/api/puco/game/${gameId}/start`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${authToken}` },
      });
      if (!res.ok) { setLobbyError(await parseApiError(res)); return; }
      const data = await res.json();
      const gs = data.state as GameState;
      setState(gs);
      const humanEntry = Object.entries(gs.players).find(([, p]) => p.display_name === myName);
      if (humanEntry) setMyPlayerId(humanEntry[0]);
      closeLobbyWs();
      setScreen('game');
    } catch (e) {
      setLobbyError(e instanceof Error ? e.message : 'Failed');
    }
  }

  function notMyTurn(): boolean {
    return isMultiplayer && myPlayerId !== null && myPlayerId !== state?.meta.active_player;
  }

  async function selectRole(role: string) {
    if (!state || notMyTurn() || saving) return;
    const roleData = state.common_board.roles[role as import('./types/gameState').RoleName];
    if (!roleData || roleData.action_index === undefined) return;
    await channelAction(roleData.action_index);
  }

  async function passAction() {
    if (notMyTurn() || !state || saving) return;
    setPassing(true);
    await channelAction(state.meta.pass_action_index ?? 15);
    setPassing(false);
  }

  async function useHacienda() {
    if (notMyTurn() || !state || saving) return;
    await channelAction(state.meta.hacienda_action_index ?? 105);
  }

  async function doSettlePlantation(type: string, useHospice: boolean) {
    void useHospice; // hospice colonist grant handled by engine
    if (!state || saving) return;
    if (type === 'quarry') {
      await channelAction(14);
      return;
    }
    const entry = state.common_board.available_plantations.face_up.find(p => p.type === type);
    if (entry) await channelAction(entry.action_index);
  }

  function settlePlantation(type: string) {
    if (!state || saving) return;
    const player = state.players[state.meta.active_player];
    const hasHospice = player?.city.buildings.some(b => b.name === 'hospice' && b.is_active) ?? false;
    const colonistAvailable = state.common_board.colonists.supply > 0 || state.common_board.colonists.ship > 0;
    if (hasHospice && colonistAvailable) {
      setPendingSettlement(type);
    } else {
      doSettlePlantation(type, false);
    }
  }

  function confirmSettlement(useHospice: boolean) {
    if (!pendingSettlement) return;
    const type = pendingSettlement;
    setPendingSettlement(null);
    doSettlePlantation(type, useHospice);
  }

  async function selectMayorStrategy(actionIndex: 69 | 70 | 71) {
    if (!state || notMyTurn()) return;
    await channelAction(actionIndex);
  }

  async function sellGood(good: string) {
    if (notMyTurn()) return;
    await channelAction(channelActionIndex.sell(good));
    scrollToActionCard();
  }

  async function craftsmanPrivilege(good: string) {
    if (notMyTurn()) return;
    await channelAction(channelActionIndex.craftsmanPriv(good));
  }

  function scrollToActionCard() {
    setTimeout(() => {
      const el = document.getElementById('action-card');
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'end' });
        el.classList.add('focus-highlight');
        setTimeout(() => el.classList.remove('focus-highlight'), 1800);
      }
    }, 50);
  }

  async function loadShip(good: string, shipIndex: number | null, useWharf: boolean) {
    if (!state || notMyTurn()) return;
    const actionIndex = useWharf
      ? channelActionIndex.loadWharf(good)
      : channelActionIndex.loadShip(good, shipIndex ?? 0);
    await channelAction(actionIndex);
    scrollToActionCard();
  }

  async function captainPass() {
    if (!state || notMyTurn()) return;
    await channelAction(15);
    scrollToActionCard();
  }

  async function doDiscardGoods() {
    if (!state) return;
    // Send warehouse stores first, then windrose, then pass
    for (const good of discardProtected) {
      await channelAction(channelActionIndex.storeWarehouse(good));
    }
    if (discardSingleExtra) {
      await channelAction(channelActionIndex.storeWindrose(discardSingleExtra));
    }
    setDiscardProtected([]);
    setDiscardSingleExtra(null);
    await channelAction(15);
    scrollToActionCard();
  }

  function requestBuild(name: string, cost: number, vp: number) {
    setBuildConfirm({ name, cost, vp });
  }

  async function build(buildingName: string) {
    if (!state || notMyTurn()) return;
    const buildingData = state.common_board.available_buildings[buildingName] as { action_index?: number } | undefined;
    if (!buildingData?.action_index) return;
    await channelAction(buildingData.action_index);
  }



  const isBotTurn = !!(state?.bot_players && state?.decision?.player && state.bot_players[state.decision.player] !== undefined);
  const isMyTurn = isSpectator
    ? false
    : !isMultiplayer
      ? !isBotTurn
      : (myPlayerId !== null && state?.decision?.player === myPlayerId);
  const isBlocked = !!state?.meta.bot_thinking || isBotTurn;
  const interactionLocked = isBlocked || saving;
  const canPass = (state?.action_mask?.[15] ?? 1) === 1;

  if (screen !== 'game') {
    return (
      <AppScreenGate
        screen={screen === 'login' || (authUser?.needs_nickname && authToken) ? 'login' : screen}
        backend={BACKEND}
        authToken={authToken}
        authUser={authUser}
        nicknameInput={nicknameInput}
        nicknameError={nicknameError}
        error={error}
        myName={myName}
        lobbyPlayers={lobbyPlayers}
        lobbyHost={lobbyHost}
        lobbyError={lobbyError}
        onGoogleLogin={handleGoogleLogin}
        onNicknameChange={setNicknameInput}
        onSetNickname={handleSetNickname}
        onGoToRooms={handleGoToRooms}
        onLogout={logoutToLogin}
        onCreateRoom={handleCreateRoom}
        onCreateBotGame={handleCreateBotGame}
        onJoinRoom={handleJoinRoom}
        onJoin={handleJoin}
        onLobbyStart={handleLobbyStart}
        onLeaveLobbyToLogin={async () => {
          await leaveLobbyRoom();
          logoutToLogin();
        }}
        onAddBot={handleAddBot}
        onRemoveBot={handleRemoveBot}
        onBackFromLobby={async () => {
          await leaveLobbyRoom();
          goToRoomsPreservingAuth();
        }}
      />
    );
  }
  if (!state) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', gap: 16 }}>
        <p style={{ color: '#aab' }}>{t('game.noGame')}</p>
        <button
          style={{ background: '#2a5ab0', color: '#fff', border: 'none', borderRadius: 8, padding: '12px 24px', fontSize: 16, cursor: 'pointer' }}
          onClick={goToRoomsPreservingAuth}
        >
          {t('game.startNew')}
        </button>
      </div>
    );
  }

  return (
    <GameScreen
      backend={BACKEND}
      state={state}
      error={error}
      saving={saving}
      passing={passing}
      buildConfirm={buildConfirm}
      pendingSettlement={pendingSettlement}
      roundFlash={roundFlash}
      discardProtected={discardProtected}
      discardSingleExtra={discardSingleExtra}
      finalScores={finalScores}
      popups={popups}
      isAdmin={isAdmin}
      isSpectator={isSpectator}
      isMultiplayer={isMultiplayer}
      myName={myName}
      lobbyPlayers={lobbyPlayers}
      isMyTurn={isMyTurn}
      isBotTurn={isBotTurn}
      isBlocked={isBlocked}
      interactionLocked={interactionLocked}
      canPass={canPass}
      onStateLoaded={setState}
      onGoToRoomsPreservingAuth={goToRoomsPreservingAuth}
      onLogoutToLogin={logoutToLogin}
      onExitSpectator={() => { setIsSpectator(false); logoutToLogin(); }}
      onDismissError={() => setError(null)}
      onClearPopups={() => {
        popupTimersRef.current.forEach(clearTimeout);
        popupTimersRef.current = [];
        setPopups([]);
      }}
      onConfirmBuild={(buildingName) => {
        build(buildingName);
        setBuildConfirm(null);
      }}
      onCancelBuildConfirm={() => setBuildConfirm(null)}
      onConfirmSettlement={confirmSettlement}
      onSelectRole={selectRole}
      onSettlePlantation={settlePlantation}
      onUseHacienda={useHacienda}
      onSelectMayorStrategy={selectMayorStrategy}
      onPassAction={passAction}
      onSellGood={sellGood}
      onCraftsmanPrivilege={craftsmanPrivilege}
      onLoadShip={loadShip}
      onCaptainPass={captainPass}
      onToggleDiscardProtected={(good) => {
        const maxProtected = (state.players[state.meta.active_player]?.city.buildings.some((b) => b.name === 'large_warehouse' && b.is_active) ? 2 : 0)
          + (state.players[state.meta.active_player]?.city.buildings.some((b) => b.name === 'small_warehouse' && b.is_active) ? 1 : 0);
        if (discardProtected.includes(good)) {
          setDiscardProtected((prev) => prev.filter((x) => x !== good));
          return;
        }
        if (discardProtected.length < maxProtected) {
          setDiscardProtected((prev) => [...prev, good]);
          if (discardSingleExtra === good) setDiscardSingleExtra(null);
        }
      }}
      onSetDiscardSingleExtra={setDiscardSingleExtra}
      onDoDiscardGoods={doDiscardGoods}
      onRequestBuild={requestBuild}
      onReturnToRooms={handleReturnToRooms}
    />
  );
}
