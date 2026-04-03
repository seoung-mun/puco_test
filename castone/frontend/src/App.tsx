import { useEffect, useRef, useState } from 'react';
import { useGameWebSocket } from './hooks/useGameWebSocket';
import { useGameSSE } from './hooks/useGameSSE';
import { useTranslation } from 'react-i18next';
import i18n from './i18n';
import type { GameState } from './types/gameState';
import MetaPanel from './components/MetaPanel';
import CommonBoardPanel from './components/CommonBoardPanel';
import PlayerPanel from './components/PlayerPanel';
import SanJuan from './components/SanJuan';
import AdminPanel from './components/AdminPanel';
import PlayerAdvantages from './components/PlayerAdvantages';
import HistoryPanel from './components/HistoryPanel';
import HomeScreen from './components/HomeScreen';
import RoomListScreen from './components/RoomListScreen';
import JoinScreen from './components/JoinScreen';
import LobbyScreen from './components/LobbyScreen';
import LoginScreen from './components/LoginScreen';
import type { LobbyPlayer } from './types/gameState';
import './App.css';

type Advantage = { label: string; tooltip: string; cls: string };

type PlayerScore = {
  vp_chips: number;
  building_vp: number;
  guild_hall_bonus: number;
  residence_bonus: number;
  fortress_bonus: number;
  customs_house_bonus: number;
  city_hall_bonus: number;
  total: number;
};
type FinalScoreResponse = {
  scores: Record<string, PlayerScore>;
  winner: string;
  player_order: string[];
};

// CSS classes only — labels/tooltips come from i18n
const ROLE_PRIVILEGE_CLASSES: Record<string, string> = {
  settler: 'adv-settler', mayor: 'adv-mayor', builder: 'adv-builder',
  craftsman: 'adv-craftsman', trader: 'adv-trader', captain: 'adv-captain',
};

// Maps history action → role key (for popup coloring)
const ACTION_TO_ROLE: Record<string, string> = {
  settle_plantation:   'settler',
  build:               'builder',
  craftsman_privilege: 'craftsman',
  sell:                'trader',
  load_ship:           'captain',
  discard:             'captain',
};

const CAPTAIN_PHASES = ['captain_action', 'captain_discard'];

const BUILDING_ADVANTAGE_META: Record<string, { cls: string; phases: string[] }> = {
  hacienda:         { cls: 'adv-settler',   phases: ['settler_action'] },
  hospice:          { cls: 'adv-settler',   phases: ['settler_action'] },
  construction_hut: { cls: 'adv-settler',   phases: ['settler_action'] },
  small_market:     { cls: 'adv-trader',    phases: ['trader_action'] },
  large_market:     { cls: 'adv-trader',    phases: ['trader_action'] },
  office:           { cls: 'adv-trader',    phases: ['trader_action'] },
  factory:          { cls: 'adv-craftsman', phases: ['craftsman_action'] },
  small_warehouse:  { cls: 'adv-captain',   phases: CAPTAIN_PHASES },
  large_warehouse:  { cls: 'adv-captain',   phases: CAPTAIN_PHASES },
  harbor:           { cls: 'adv-captain',   phases: CAPTAIN_PHASES },
  wharf:            { cls: 'adv-captain',   phases: CAPTAIN_PHASES },
  university:       { cls: 'adv-builder',   phases: ['builder_action'] },
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
  mayorIsland: (slotIndex: number): number => 69 + slotIndex,
  mayorCity: (slotIndex: number): number => 81 + slotIndex,
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
  const [sellingGood, setSellingGood] = useState<string | null>(null);
  const [roundFlash, setRoundFlash] = useState<number | null>(null);
  const [discardProtected, setDiscardProtected] = useState<string[]>([]);
  const [discardSingleExtra, setDiscardSingleExtra] = useState<string | null>(null);
  const [finalScores, setFinalScores] = useState<FinalScoreResponse | null>(null);
  const prevRoundRef = useRef<number | null>(null);
  const prevPhaseRef = useRef<string | null>(null);
  const prevActivePlayerRef = useRef<string | null>(null);
  const prevHaciendaUsedRef = useRef<boolean>(false);
  const [popups, setPopups] = useState<{ id: number; text: string; isRoundEnd: boolean; role: string | null }[]>([]);
  const popupTimersRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  const popupIdRef = useRef(0);
  const prevHistoryLenRef = useRef<number>(-1);

  // --- Auth state ---
  const [authToken, setAuthToken] = useState<string | null>(() => localStorage.getItem('access_token'));
  const [authUser, setAuthUser] = useState<{ id: string; nickname: string | null; needs_nickname: boolean } | null>(null);
  const [nicknameInput, setNicknameInput] = useState('');
  const [nicknameError, setNicknameError] = useState<string | null>(null);

  // --- Multiplayer / screen routing ---
  const [screen, setScreen] = useState<'loading' | 'login' | 'home' | 'rooms' | 'join' | 'lobby' | 'game'>('loading');
  const [gameId, setGameId] = useState<string | null>(null);
  const [myName, setMyName] = useState<string | null>(null);
  const [myPlayerId, setMyPlayerId] = useState<string | null>(null);
  const [isMultiplayer, setIsMultiplayer] = useState(false);
  const [isSpectator, setIsSpectator] = useState(false);
  const [lobbyPlayers, setLobbyPlayers] = useState<LobbyPlayer[]>([]);
  const [lobbyHost, setLobbyHost] = useState<string | null>(null);
  const [lobbyError, setLobbyError] = useState<string | null>(null);

  const lobbyWsRef = useRef<WebSocket | null>(null);

  // Mayor 토글 모드 (인간 플레이어 전용)
  const [mayorPending, setMayorPending] = useState<number[] | null>(null);
  // 이전 라운드 배치를 기억해서 다음 시장 페이즈에 재사용
  const lastMayorDistRef = useRef<number[] | null>(null);

  // Mayor 토글 상태 초기화/정리
  useEffect(() => {
    if (!state) return;
    const isMayorTurn = state.meta.phase === 'mayor_action'
      && !notMyTurn()
      && !state.bot_players?.[state.meta.active_player];
    if (isMayorTurn && mayorPending === null) {
      const player = state.players[state.meta.active_player];
      const available = player?.city.colonists_unplaced ?? 0;
      let init = new Array(24).fill(0);
      if (lastMayorDistRef.current && player) {
        // 이전 배치를 현재 슬롯 capacity에 맞게 클리핑
        const clipped = lastMayorDistRef.current.map((v, idx) => {
          if (idx < 12) return Math.min(v, idx < player.island.plantations.length ? 1 : 0);
          const b = player.city.buildings[idx - 12];
          return Math.min(v, b ? b.max_colonists : 0);
        });
        // 총합이 available을 초과하면 뒤쪽 슬롯부터 줄임
        let excess = clipped.reduce((a, b) => a + b, 0) - available;
        if (excess > 0) {
          for (let i = clipped.length - 1; i >= 0 && excess > 0; i--) {
            const cut = Math.min(clipped[i], excess);
            clipped[i] -= cut;
            excess -= cut;
          }
        }
        init = clipped;
      }
      setMayorPending(init);
    }
    if (state.meta.phase !== 'mayor_action') {
      setMayorPending(null);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state?.meta.phase, state?.meta.active_player]);


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
      case 'mayor_distribution':
      case 'mayor_action':
        targetId = `player-${player}-island`;
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
    if (!state?.meta.end_game_triggered || !gameId || !authToken) return;
    fetch(`${BACKEND}/api/puco/game/${gameId}/final-score`, {
      headers: { 'Authorization': `Bearer ${authToken}` },
    })
      .then(r => r.json())
      .then(setFinalScores)
      .catch(() => {});
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [state?.meta.end_game_triggered]);

  useEffect(() => { initializeApp(); }, []);

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
      initializeApp(data.access_token);
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

  async function initializeApp(token?: string) {
    const currentToken = token || authToken;
    // Check auth first
    if (!currentToken) {
      setScreen('login');
      return;
    }
    // Validate token
    try {
      const meRes = await apiFetch(`${BACKEND}/api/puco/auth/me`, {
        headers: { 'Authorization': `Bearer ${currentToken}` },
      });
      if (!meRes.ok) {
        localStorage.removeItem('access_token');
        setAuthToken(null);
        setScreen('login');
        return;
      }
      const user = await meRes.json();
      setAuthUser(user);
    } catch {
      setScreen('login');
      return;
    }

    // Channel mode: always go to home after auth (no legacy server-info needed)
    setScreen('home');
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

  function logout(forceHome = false) {
    const isClient = isMultiplayer && myName !== lobbyHost;
    closeLobbyWs();
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
    setScreen(!forceHome && isClient ? 'join' : 'home');
  }

  /** Channel API: 단일 action_index로 모든 게임 액션을 처리 */
  async function channelAction(actionIndex: number): Promise<void> {
    if (!gameId || !authToken) return;
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
      if (data.state) setState(data.state as GameState);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Request failed');
    } finally {
      setSaving(false);
    }
  }

  /** 방 목록 화면으로 이동 */
  function handleGoToRooms() {
    setScreen('rooms');
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

  /** Channel: 봇전 생성 — BOT×3 자동 시작, 사용자는 관전자 */
  async function handleCreateBotGame() {
    if (!authToken) return;
    setError(null);
    try {
      const res = await fetch(`${BACKEND}/api/puco/rooms/bot-game`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (!res.ok) { setError(await res.text()); return; }
      const data = await res.json();
      setState(data.state);
      setGameId(data.game_id);
      setIsSpectator(true);
      setIsMultiplayer(false);
      setScreen('game');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed');
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
  async function handleRemoveBot(botName: string) {
    setLobbyPlayers(prev => prev.filter(p => p.name !== botName));
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
    if (!state || notMyTurn()) return;
    const roleData = state.common_board.roles[role as import('./types/gameState').RoleName];
    if (!roleData || roleData.action_index === undefined) return;
    await channelAction(roleData.action_index);
  }

  async function passAction() {
    if (notMyTurn() || !state) return;
    setPassing(true);
    await channelAction(state.meta.pass_action_index ?? 15);
    setPassing(false);
  }

  async function useHacienda() {
    if (notMyTurn() || !state) return;
    await channelAction(state.meta.hacienda_action_index ?? 105);
  }

  async function doSettlePlantation(type: string, useHospice: boolean) {
    void useHospice; // hospice colonist grant handled by engine
    if (!state) return;
    if (type === 'quarry') {
      await channelAction(14);
      return;
    }
    const entry = state.common_board.available_plantations.face_up.find(p => p.type === type);
    if (entry) await channelAction(entry.action_index);
  }

  function settlePlantation(type: string) {
    if (!state) return;
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

  // Mayor 토글 UI 헬퍼
  function getMayorSlotCapacity(slotIdx: number): number {
    if (!state) return 0;
    const player = state.players[state.meta.active_player];
    if (!player) return 0;
    if (slotIdx < 12) {
      // island slot: 해당 인덱스에 plantation이 있으면 capacity=1
      return slotIdx < player.island.plantations.length ? 1 : 0;
    } else {
      // city slot: building의 max_colonists
      const cityIdx = slotIdx - 12;
      const building = player.city.buildings[cityIdx];
      return building ? building.max_colonists : 0;
    }
  }

  function toggleMayorSlot(slotIdx: number, delta: 1 | -1) {
    if (!mayorPending || !state) return;
    const player = state.players[state.meta.active_player];
    if (!player) return;
    const totalColonists = player.city.colonists_unplaced;
    const totalPending = mayorPending.reduce((a, b) => a + b, 0);
    const localUnplaced = totalColonists - totalPending;
    const cap = getMayorSlotCapacity(slotIdx);
    const cur = mayorPending[slotIdx];
    if (delta > 0 && (cur >= cap || localUnplaced <= 0)) return;
    if (delta < 0 && cur <= 0) return;
    const next = [...mayorPending];
    next[slotIdx] = cur + delta;
    setMayorPending(next);
  }

  async function confirmMayorDistribution() {
    if (!state || !mayorPending || notMyTurn()) return;
    // Channel API: send individual slot placements for each slot with colonists
    // mayorPending[0-11] = island slots, [12-23] = city slots
    lastMayorDistRef.current = [...mayorPending];
    setMayorPending(null);
    // Submit each slot toggle in order; engine will handle placement vs skip
    for (let i = 0; i < 12; i++) {
      for (let j = 0; j < mayorPending[i]; j++) {
        await channelAction(channelActionIndex.mayorIsland(i));
      }
    }
    for (let i = 0; i < 12; i++) {
      for (let j = 0; j < mayorPending[12 + i]; j++) {
        await channelAction(channelActionIndex.mayorCity(i));
      }
    }
    // Finish with pass
    await channelAction(15);
  }

  async function mayorPlaceAmount(amount: number) {
    void amount; // Legacy mayor-place: no direct channel equivalent; use pass to finish
    if (!state || notMyTurn()) return;
    await channelAction(15);
  }

  async function mayorFinishPlacement() {
    if (!state || notMyTurn()) return;
    await channelAction(15);
  }

  async function sellGood(good: string) {
    if (notMyTurn()) return;
    setSellingGood(good);
    await channelAction(channelActionIndex.sell(good));
    setSellingGood(null);
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
  const isBlocked = !!state?.meta.bot_thinking || (!isMultiplayer && isBotTurn);

  if (screen === 'loading') {
    return <div style={{ color: '#eee', padding: 40, textAlign: 'center' }}>Loading...</div>;
  }
  if (screen === 'login' || (authUser?.needs_nickname && authToken)) {
    return <LoginScreen
      onGoogleLogin={handleGoogleLogin}
      isLoggedIn={!!authToken}
      needsNickname={authUser?.needs_nickname ?? false}
      nicknameInput={nicknameInput}
      onNicknameChange={setNicknameInput}
      onSetNickname={handleSetNickname}
      nicknameError={nicknameError}
      error={error}
    />;
  }
  if (screen === 'home') {
    return <HomeScreen
      onMultiplayer={handleGoToRooms}
      onLogout={() => {
        localStorage.removeItem('access_token');
        setAuthToken(null);
        setAuthUser(null);
        setScreen('login');
      }}
      userNickname={authUser?.nickname ?? null}
      error={error}
    />;
  }
  if (screen === 'rooms') {
    return <RoomListScreen
      token={authToken ?? ''}
      userNickname={authUser?.nickname ?? null}
      onCreateRoom={handleCreateRoom}
      onCreateBotGame={handleCreateBotGame}
      onJoinRoom={handleJoinRoom}
      onLogout={() => logout(true)}
      error={error}
    />;
  }
  if (screen === 'join') {
    return <JoinScreen backendUrl={BACKEND} onJoin={handleJoin} />;
  }
  if (screen === 'lobby') {
    return <LobbyScreen
      players={lobbyPlayers}
      host={lobbyHost ?? ''}
      myName={myName ?? ''}
      onStart={handleLobbyStart}
      onLogout={async () => {
        if (gameId) {
          try {
            await fetch(`/api/puco/rooms/${gameId}/leave`, {
              method: 'POST',
              headers: { Authorization: `Bearer ${authToken}` },
            });
          } catch (_) { /* best-effort */ }
        }
        closeLobbyWs();
        setScreen('rooms');
      }}
      onAddBot={handleAddBot}
      onRemoveBot={handleRemoveBot}
      error={lobbyError}
      onBack={async () => {
        if (gameId) {
          try {
            await fetch(`/api/puco/rooms/${gameId}/leave`, {
              method: 'POST',
              headers: { Authorization: `Bearer ${authToken}` },
            });
          } catch (_) { /* best-effort */ }
        }
        closeLobbyWs();
        setScreen('rooms');
      }}
    />;
  }
  // screen === 'game' — need state from here on
  if (!state) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', gap: 16 }}>
        <p style={{ color: '#aab' }}>{t('game.noGame')}</p>
        <button
          style={{ background: '#2a5ab0', color: '#fff', border: 'none', borderRadius: 8, padding: '12px 24px', fontSize: 16, cursor: 'pointer' }}
          onClick={() => logout(true)}
        >
          {t('game.startNew')}
        </button>
      </div>
    );
  }

  const playerNames = Object.fromEntries(
    Object.entries(state.players).map(([id, p]) => [id, p.display_name])
  );

  const canSelectRole = state.meta.phase === 'role_selection' && !state.meta.end_game_triggered && isMyTurn;
  const isMayorPhase = state.meta.phase === 'mayor_action';
  const isSettlerPhase = state.meta.phase === 'settler_action';
  const isBuilderPhase = state.meta.phase === 'builder_action';
  const isCraftsmanPrivilege = state.meta.phase === 'craftsman_action'
    && state.common_board.roles['craftsman']?.taken_by === state.meta.active_player;
  const isTraderPhase = state.meta.phase === 'trader_action';
  const isCaptainPhase = state.meta.phase === 'captain_action';
  const isCaptainDiscard = state.meta.phase === 'captain_discard';
  const captainRolePicker = state.common_board.roles['captain']?.taken_by ?? null;

  const settlerRolePicker = state.common_board.roles['settler']?.taken_by ?? null;
  const builderRolePicker = state.common_board.roles['builder']?.taken_by ?? null;
  const activePlayer = state.players[state.meta.active_player];
  const builderInfo = isBuilderPhase && activePlayer ? {
    player: activePlayer.display_name,
    activeQuarries: activePlayer.island.d_active_quarries,
    isRolePicker: state.meta.active_player === builderRolePicker,
    doubloons: activePlayer.doubloons,
    cityEmptySpaces: activePlayer.city.d_empty_spaces,
    ownedBuildings: activePlayer.city.buildings.map(b => b.name),
  } : undefined;
  const canPickQuarry = isSettlerPhase
    && (state.meta.active_player === settlerRolePicker
      || activePlayer?.city.buildings.some(b => b.name === 'construction_hut' && b.is_active) === true)
    && state.common_board.quarry_supply_remaining > 0;

  const canUseHacienda = isSettlerPhase
    && activePlayer?.city.buildings.some(b => b.name === 'hacienda' && b.is_active) === true
    && !activePlayer?.hacienda_used_this_phase
    && Object.values(state.common_board.available_plantations.draw_pile).reduce((a, b) => a + b, 0) > 0
    && (activePlayer?.island.d_empty_spaces ?? 0) > 0;

  // Advantages for the current active player
  const advantages: Advantage[] = [];
  if (activePlayer) {
    if (state.meta.active_role) {
      const roleKey = state.meta.active_role as string;
      if (state.common_board.roles[state.meta.active_role]?.taken_by === state.meta.active_player) {
        const cls = ROLE_PRIVILEGE_CLASSES[roleKey];
        if (cls) advantages.push({
          label:   t(`rolePrivileges.${roleKey}.label`),
          tooltip: t(`rolePrivileges.${roleKey}.tip`),
          cls,
        });
      }
    }
    const phase = state.meta.phase;
    const showAll = phase === 'role_selection';
    for (const building of activePlayer.city.buildings) {
      const meta = BUILDING_ADVANTAGE_META[building.name];
      if (building.is_active && meta && (showAll || meta.phases.includes(phase))) {
        advantages.push({
          label:   t(`buildingAdvantages.${building.name}.label`),
          tooltip: t(`buildingAdvantages.${building.name}.tip`),
          cls:     meta.cls,
        });
      }
    }

    if (isBuilderPhase) {
      advantages.push({ label: `💰 ${activePlayer.doubloons}`, cls: 'adv-info', tooltip: t('player.goods') });
      advantages.push({ label: `⛏ ${activePlayer.island.d_active_quarries}`, cls: 'adv-info', tooltip: t('plantations.quarry') });
    }
  }

  const activeMayorPlayer = isMayorPhase ? state.players[state.meta.active_player] : null;
  // 토글 모드일 때는 pending 기준으로 남은 이주민과 빈 슬롯을 계산
  const isMayorToggleMode = isMayorPhase && mayorPending !== null;
  const mayorTotalColonists = activeMayorPlayer?.city.colonists_unplaced ?? 0;
  const mayorTotalPending = mayorPending?.reduce((a, b) => a + b, 0) ?? 0;
  const mayorLocalUnplaced = mayorTotalColonists - mayorTotalPending;
  const mayorAvailableCapacity = isMayorToggleMode
    ? Array.from({ length: 24 }, (_, i) => getMayorSlotCapacity(i) - (mayorPending![i] ?? 0))
        .filter(v => v > 0).length
    : 0;
  // 확정 버튼 비활성 조건: 남은 이주민 있고 빈 슬롯도 있을 때
  const mayorCannotConfirm = mayorLocalUnplaced > 0 && mayorAvailableCapacity > 0;
  // 순차 모드(봇 or 멀티에서 상대방 화면)용 기존 체크
  const mayorMustPlace = activeMayorPlayer != null
    && activeMayorPlayer.city.colonists_unplaced > 0
    && (
      activeMayorPlayer.island.plantations.some(pl => !pl.colonized)
      || activeMayorPlayer.city.buildings.some(b => b.empty_slots > 0)
    );

  return (
    <div className="app">
      {popups.length > 0 && (
        <div
          style={{ position: 'fixed', top: 72, left: '50%', transform: 'translateX(-50%)', zIndex: 300, display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'center', cursor: 'pointer' }}
          onClick={() => { popupTimersRef.current.forEach(clearTimeout); popupTimersRef.current = []; setPopups([]); }}
        >
          {popups.map(p => (
            <div
              key={p.id}
              className={`action-popup${p.isRoundEnd ? ' action-popup--round-end' : p.role ? ` action-popup--${p.role}` : ''}`}
              dangerouslySetInnerHTML={{ __html: p.text }}
            />
          ))}
        </div>
      )}
      {state?.meta.bot_thinking && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, background: '#1a1218', borderBottom: '2px solid #7a3a7a', padding: '8px 20px', textAlign: 'center', color: '#c080e0', zIndex: 400, fontSize: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10 }}>
          <span style={{ display: 'inline-block', animation: 'spin 1s linear infinite', fontSize: 18 }}>⚙</span>
          {t('game.geminiThinking')}
        </div>
      )}
      {!isMyTurn && state && (
        <div style={{ position: 'fixed', bottom: 0, left: 0, right: 0, background: '#1a1030', borderTop: '2px solid #2a2a5a', padding: '10px 20px', textAlign: 'center', color: '#aab', zIndex: 200, fontSize: 14 }}>
          {t('game.waitingTurn', { name: state.players[state.decision.player]?.display_name ?? state.decision.player })}
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
        <h1 style={{ margin: 0 }}>Puerto Rico</h1>
        <button className="btn-new-game" onClick={() => logout(true)}>🎮 {t('newGame.title')}</button>
        <button
          className="btn-new-game"
          style={{ background: '#444', fontSize: '0.8em', padding: '4px 10px' }}
          onClick={() => { 
            const cycle: Record<string, string> = { 'ko': 'en', 'en': 'it', 'it': 'ko' };
            const next = cycle[i18n.language] || 'ko';
            i18n.changeLanguage(next); 
            localStorage.setItem('lang', next); 
          }}
        >
          {t('langToggle')}
        </button>
            {isSpectator && (
              <span style={{ background: '#1a3a2a', border: '1px solid #2a5a3a', borderRadius: 4, color: '#4f8', padding: '2px 8px', fontSize: 12 }}>
                👁 {t('rooms.spectating', '관전 중')}
              </span>
            )}
            {isSpectator && (
              <button onClick={() => { setIsSpectator(false); logout(true); }} style={{ background: 'none', border: '1px solid #334', borderRadius: 4, color: '#667', cursor: 'pointer', padding: '2px 8px', fontSize: 12 }}>
                {t('lobby.logout')}
              </button>
            )}
            {isMultiplayer && !isSpectator && (
              <button onClick={() => logout()} style={{ background: 'none', border: '1px solid #334', borderRadius: 4, color: '#667', cursor: 'pointer', padding: '2px 8px', fontSize: 12 }}>
                {t('lobby.logout')}
              </button>
            )}
      </div>
      {isAdmin && <AdminPanel backend={BACKEND} onStateLoaded={setState} />}

      {buildConfirm && state && (() => {
        const cfg: Record<string, { icon: string; color: string }> = {
          small_indigo_plant: { icon: '🫐', color: '#3a4fa0' }, indigo_plant: { icon: '🫐', color: '#2a3f90' },
          small_sugar_mill: { icon: '🎋', color: '#a0a060' }, sugar_mill: { icon: '🎋', color: '#808040' },
          small_market: { icon: '🏪', color: '#a06020' }, large_market: { icon: '🏪', color: '#804010' },
          hacienda: { icon: '🏡', color: '#6a8a3a' }, construction_hut: { icon: '🔨', color: '#7a5a2a' },
          small_warehouse: { icon: '📦', color: '#5a4a2a' }, large_warehouse: { icon: '📦', color: '#3a2a1a' },
          tobacco_storage: { icon: '🍂', color: '#8b5e3c' }, coffee_roaster: { icon: '☕', color: '#3d1f00' },
          hospice: { icon: '⚕️', color: '#2a6a6a' }, office: { icon: '📜', color: '#4a4a8a' },
          factory: { icon: '⚙️', color: '#5a5a5a' }, university: { icon: '🎓', color: '#4a2a8a' },
          harbor: { icon: '⚓', color: '#1a3a6a' }, wharf: { icon: '🚢', color: '#1a2a5a' },
          guild_hall: { icon: '🏛️', color: '#6a4a00' }, residence: { icon: '🏠', color: '#5a3a1a' },
          fortress: { icon: '🏰', color: '#3a3a3a' }, customs_house: { icon: '🏦', color: '#2a4a2a' },
          city_hall: { icon: '🏛️', color: '#8a6a00' },
        };
        const { name, cost, vp } = buildConfirm;
        const tileCfg = cfg[name] ?? { icon: '🏗️', color: '#555' };
        const label = t(`buildings.${name}`, { defaultValue: name.replace(/_/g, ' ') });
        const tip = t(`buildingAdvantages.${name}.tip`, { defaultValue: '' });
        return (
          <div className="new-game-overlay" onClick={e => { if (e.target === e.currentTarget) setBuildConfirm(null); }}>
            <div className="new-game-modal" style={{ maxWidth: 360 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 16 }}>
                <div style={{ background: tileCfg.color, borderRadius: 8, width: 52, height: 52, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 26, flexShrink: 0 }}>
                  {tileCfg.icon}
                </div>
                <div>
                  <div style={{ fontSize: 18, fontWeight: 'bold', color: '#f0e0b0' }}>{label}</div>
                  <div style={{ display: 'flex', gap: 12, marginTop: 4 }}>
                    <span style={{ color: '#f0c040', fontWeight: 'bold' }}>💰 {cost}</span>
                    <span style={{ color: '#ffe066', fontWeight: 'bold' }}>⭐ {vp} VP</span>
                  </div>
                </div>
              </div>
              {tip && <p style={{ color: '#aab', fontSize: 13, margin: '0 0 20px', lineHeight: 1.5 }}>{tip}</p>}
              <div style={{ display: 'flex', gap: 10 }}>
                <button
                  style={{ flex: 1, padding: '10px 0', background: '#2a5ab0', border: 'none', borderRadius: 8, color: '#fff', fontSize: 15, fontWeight: 'bold', cursor: 'pointer' }}
                  onClick={() => { build(name); setBuildConfirm(null); }}
                >
                  {t('newGame.confirm', { defaultValue: '✓ Conferma' })}
                </button>
                <button
                  style={{ flex: 1, padding: '10px 0', background: '#1a1a3a', border: '1px solid #3a3a6a', borderRadius: 8, color: '#aab', fontSize: 15, cursor: 'pointer' }}
                  onClick={() => setBuildConfirm(null)}
                >
                  {t('newGame.cancel')}
                </button>
              </div>
            </div>
          </div>
        );
      })()}

      {roundFlash !== null && (
        <div className="round-flash">{t('actions.roundCompleted', { n: roundFlash })}</div>
      )}
      {state.meta.end_game_triggered && (
        <div className="end-game-panel">
          <div className="end-game-panel__header">
            {t('endGame.title', { reason: state.meta.end_game_reason })}
          </div>
          {finalScores ? (() => {
            const cols: { key: keyof PlayerScore; label: string }[] = [
              { key: 'vp_chips',            label: t('endGame.vpChips') },
              { key: 'building_vp',         label: t('endGame.buildings') },
              { key: 'guild_hall_bonus',    label: t('endGame.guildHall') },
              { key: 'residence_bonus',     label: t('endGame.residence') },
              { key: 'fortress_bonus',      label: t('endGame.fortress') },
              { key: 'customs_house_bonus', label: t('endGame.customsHouse') },
              { key: 'city_hall_bonus',     label: t('endGame.cityHall') },
              { key: 'total',               label: t('endGame.total') },
            ];
            return (
              <table className="end-game-table">
                <thead>
                  <tr>
                    <th>{t('player.governor')}</th>
                    {cols.map(c => <th key={c.key}>{c.label}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {finalScores.player_order.map(pid => {
                    const s = finalScores.scores[pid];
                    const isWinner = pid === finalScores.winner;
                    const name = state.players[pid]?.display_name ?? pid;
                    return (
                      <tr key={pid} className={isWinner ? 'end-game-winner' : ''}>
                        <td>{isWinner ? '🏆 ' : ''}{name}</td>
                        {cols.map(c => (
                          <td key={c.key} className={c.key === 'total' ? 'end-game-total' : ''}>
                            {s[c.key] > 0 || c.key === 'vp_chips' || c.key === 'total' ? s[c.key] : '—'}
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            );
          })() : <p className="end-game-loading">Calcolo punteggi...</p>}
        </div>
      )}
      {error && (
        <div className="error-banner">
          <span>Error: {error}</span>
          <button onClick={() => setError(null)} className="error-dismiss">✕</button>
        </div>
      )}

      {pendingSettlement && !isBlocked && (
        <div className="hospice-overlay">
          <div className="hospice-dialog">
            <p dangerouslySetInnerHTML={{ __html: t('hospiceDialog.message', {
              plantation: t(`plantations.${pendingSettlement}`, { defaultValue: pendingSettlement.replace(/_/g, ' ') })
            }) }} />
            <div className="hospice-dialog__btns">
              <button className="hospice-yes" onClick={() => confirmSettlement(true)}>
                {t('hospiceDialog.yes')}
              </button>
              <button className="hospice-no" onClick={() => confirmSettlement(false)}>
                {t('hospiceDialog.no')}
              </button>
            </div>
          </div>
        </div>
      )}

      {isCraftsmanPrivilege && !isBlocked && (() => {
        const privilegeGoods = (['corn', 'indigo', 'sugar', 'tobacco', 'coffee'] as const)
          .filter(g => activePlayer && activePlayer.production[g].amount > 0 && state.common_board.goods_supply[g] > 0);
        return (
          <div className="hospice-overlay">
            <div className="hospice-dialog">
              <p dangerouslySetInnerHTML={{ __html: t('craftsmanDialog.message') }} />
              <div className="hospice-dialog__btns">
                {privilegeGoods.map(g => (
                  <button key={g} className="hospice-yes" onClick={() => craftsmanPrivilege(g)}>
                    {t(`goods.${g}`)}
                  </button>
                ))}
                <button className="hospice-no" onClick={passAction}>
                  {t('craftsmanDialog.skip')}
                </button>
              </div>
            </div>
          </div>
        );
      })()}



      {/* Sticky bar */}
      <div className="sticky-bar">
        <div className="sticky-bar__main">
          {isSpectator && (
            <span style={{ display: 'flex', alignItems: 'center', gap: 8, marginRight: 8, flexShrink: 0 }}>
              <span style={{ background: '#1a3a2a', border: '1px solid #2a5a3a', borderRadius: 4, color: '#4f8', padding: '2px 8px', fontSize: 12, whiteSpace: 'nowrap' }}>
                👁 {t('rooms.spectating', '관전 중')}
              </span>
              <button onClick={() => { setIsSpectator(false); logout(true); }} style={{ background: 'none', border: '1px solid #334', borderRadius: 4, color: '#667', cursor: 'pointer', padding: '2px 8px', fontSize: 12, whiteSpace: 'nowrap' }}>
                {t('lobby.logout')}
              </button>
            </span>
          )}
          {isMultiplayer && !isSpectator && myName && (
            <span style={{ display: 'flex', alignItems: 'center', gap: 8, marginRight: 8, flexShrink: 0 }}>
              <span style={{ color: '#f0c040', fontWeight: 'bold', fontSize: 13, whiteSpace: 'nowrap' }}>
                👤 {myName}
              </span>
              <button onClick={() => logout()} style={{ background: 'none', border: '1px solid #334', borderRadius: 4, color: '#667', cursor: 'pointer', padding: '2px 8px', fontSize: 12, whiteSpace: 'nowrap' }}>
                {t('lobby.logout')}
              </button>
            </span>
          )}
          <MetaPanel meta={state.meta} playerNames={playerNames} botPlayers={state.bot_players} />
          <div className="sticky-bar__nav">
            {[
              { id: 'section-roles',   icon: '🎭', label: t('nav.roles') },
              { id: 'section-cargo',   icon: '🚢', label: t('nav.cargo') },
              { id: `player-${state.meta.active_player}-island`, icon: '🏝️', label: t('nav.island') },
              { id: `player-${state.meta.active_player}-city`,   icon: '🏛️', label: t('nav.city') },
              { id: 'san-juan',        icon: '🏪', label: t('nav.sanJuan') },
            ].map(({ id, icon, label }) => (
              <button key={id} className="nav-btn" title={label}
                onClick={() => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'center' })}>
                <span>{icon}</span>
                <span className="nav-btn__label">{label}</span>
              </button>
            ))}
            <button className="nav-btn nav-btn--focus" title={t('nav.focus')}
              onClick={() => {
                const phase = state.meta.phase;
                const player = state.meta.active_player;
                let targetId: string;
                switch (phase) {
                  case 'role_selection':    targetId = 'common-board'; break;
                  case 'settler_action':    targetId = 'section-plantations'; break;
                  case 'mayor_distribution':
                  case 'mayor_action':      targetId = `player-${player}-island`; break;
                  case 'builder_action':    targetId = 'san-juan'; break;
                  case 'craftsman_action':  targetId = `player-${player}`; break;
                  case 'trader_action':
                  case 'captain_action':
                  case 'captain_discard':   targetId = 'action-card'; break;
                  default:                  targetId = 'common-board';
                }
                const el = document.getElementById(targetId);
                if (el) el.scrollIntoView({ behavior: 'smooth', block: targetId === 'action-card' ? 'end' : 'center' });
              }}>
              <span>🎯</span>
              <span className="nav-btn__label">{t('nav.focus')}</span>
            </button>
          </div>
        </div>
        <div className="sticky-bar__row2">
          <span className="decision-inline">
            {t(`decision.${state.decision.type}`, {
              player: state.players[state.decision.player]?.display_name ?? state.decision.player,
              defaultValue: state.decision.note,
            })}
          </span>
          <PlayerAdvantages advantages={advantages} />
          <div className="sticky-bar__actions">
            {saving && <span className="saving">{t('actions.saving')}</span>}
            {state.meta.phase !== 'role_selection' && !isMayorPhase && !isCraftsmanPrivilege && !isTraderPhase && !isCaptainPhase && !isCaptainDiscard && (
              <button onClick={passAction} disabled={passing || isBlocked} className="pass-btn">
                {passing ? t('actions.advancing') : t('actions.next', { phase: t(`phases.${state.meta.phase}`, { defaultValue: state.meta.phase.replace(/_/g, ' ') }) })}
              </button>
            )}
            {/* 인간 Mayor 토글 모드: 확정 버튼 */}
            {isMayorToggleMode && (
              <button
                onClick={confirmMayorDistribution}
                disabled={passing || isBlocked || mayorCannotConfirm}
                className="pass-btn mayor-finish-btn"
                title={mayorCannotConfirm ? `이주민 ${mayorLocalUnplaced}명을 더 배치해야 합니다` : undefined}
              >
                {mayorCannotConfirm
                  ? t('actions.finishMayorWait', { defaultValue: `배치 완료 (${mayorLocalUnplaced}명 남음)` })
                  : t('actions.confirmMayor', { defaultValue: '배치 완료' })}
              </button>
            )}
            {/* 순차 모드 (봇 차례 대기 or 멀티에서 상대방 화면) */}
            {isMayorPhase && !isMayorToggleMode && !notMyTurn() && (
              <>
                <button
                  onClick={() => mayorPlaceAmount(0)}
                  disabled={passing || isBlocked || !state.meta.mayor_can_skip}
                  className="pass-btn"
                  style={{ marginRight: 4 }}
                  title={!state.meta.mayor_can_skip ? '이 슬롯에는 이주민을 배치해야 합니다' : undefined}
                >
                  {t('actions.mayorSkipSlot', { defaultValue: 'Skip Slot' })}
                </button>
                <button onClick={mayorFinishPlacement} disabled={passing || mayorMustPlace || isBlocked} className="pass-btn mayor-finish-btn">
                  {mayorMustPlace ? t('actions.finishMayorWait') : t('actions.finishMayor')}
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Row 1: Common Board */}
      <div id="common-board" className="layout-top">
        <CommonBoardPanel
          board={state.common_board}
          playerNames={playerNames}
          numPlayers={state.meta.num_players}
          phase={state.meta.phase}
          onSelectRole={canSelectRole && !isBlocked ? selectRole : undefined}
          onSettlePlantation={isSettlerPhase && !isBlocked ? settlePlantation : undefined}
          canPickQuarry={canPickQuarry && !isBlocked}
          canUseHacienda={canUseHacienda && !isBlocked}
          onUseHacienda={canUseHacienda && !isBlocked ? useHacienda : undefined}
        />
      </div>

      {/* Action card — hidden while Gemini is thinking */}
      {!isBlocked && (isTraderPhase || isCaptainPhase || isCaptainDiscard) && (() => {

        // --- TRADER ---
        if (isTraderPhase) {
          const BASE_PRICES: Record<string, number> = { corn: 0, indigo: 1, sugar: 2, tobacco: 3, coffee: 4 };
          const traderRolePicker = state.common_board.roles['trader']?.taken_by ?? null;
          const isRolePicker = state.meta.active_player === traderRolePicker;
          const hasSmallMarket = activePlayer?.city.buildings.some(b => b.name === 'small_market' && b.is_active) ?? false;
          const hasLargeMarket = activePlayer?.city.buildings.some(b => b.name === 'large_market' && b.is_active) ?? false;
          const hasOffice = activePlayer?.city.buildings.some(b => b.name === 'office' && b.is_active) ?? false;
          const goodsInHouse = new Set(state.common_board.trading_house.goods as string[]);
          const isHouseFull = state.common_board.trading_house.d_is_full;
          const goods = (['corn', 'indigo', 'sugar', 'tobacco', 'coffee'] as const).map(g => {
            const qty = activePlayer?.goods[g] ?? 0;
            const base = BASE_PRICES[g];
            const bonus = (hasSmallMarket ? 1 : 0) + (hasLargeMarket ? 2 : 0) + (isRolePicker ? 1 : 0);
            const total = base + bonus;
            const inHouse = goodsInHouse.has(g);
            const canSell = qty > 0 && !isHouseFull && (!inHouse || hasOffice);
            return { g, qty, base, bonus, total, canSell, inHouse };
          }).filter(({ qty }) => qty > 0);

          return (
            <div id="action-card" className="action-card">
              <div className="action-card__header">
                <span><strong>{t('trader.title')}</strong> — {activePlayer?.display_name}</span>
                <span className="action-card__badges">
                  {isRolePicker && <span className="badge badge-gold">{t('trader.privilegeBadge')}</span>}
                  {hasSmallMarket && <span className="badge badge-gold">{t('trader.smallMarket')}</span>}
                  {hasLargeMarket && <span className="badge badge-gold">{t('trader.largeMarket')}</span>}
                  {hasOffice && <span className="badge badge-blue">{t('trader.office')}</span>}
                  {isHouseFull && <span className="badge badge-dim">{t('trader.houseFull')}</span>}
                </span>
              </div>
              {goods.length === 0 && <p className="action-card__empty">{t('trader.noGoods')}</p>}
              {goods.length > 0 && (
                <table className="trader-table">
                  <thead>
                    <tr><th>{t('trader.good')}</th><th>{t('trader.qty')}</th><th>{t('trader.base')}</th><th>{t('trader.bonus')}</th><th>{t('trader.total')}</th><th></th></tr>
                  </thead>
                  <tbody>
                    {goods.map(({ g, qty, base, bonus, total, canSell, inHouse }) => (
                      <tr key={g} className={canSell ? '' : 'trader-row--disabled'}>
                        <td>{t(`goods.${g}`)}{inHouse && !hasOffice ? ' ⚠' : ''}</td>
                        <td>{qty}</td>
                        <td>{base}</td>
                        <td style={{ color: bonus > 0 ? '#fa0' : '#666' }}>+{bonus}</td>
                        <td style={{ color: canSell ? '#6f6' : '#888', fontWeight: 'bold' }}>{total} 💰</td>
                        <td>
                          <button
                            className={canSell ? 'hospice-yes trader-sell-btn' : 'hospice-no trader-sell-btn'}
                            disabled={!canSell || sellingGood !== null}
                            onClick={() => sellGood(g)}
                          >
                            {sellingGood === g ? '...' : t('trader.sell')}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <div className="action-card__footer">
                <button className="hospice-no" onClick={passAction} disabled={passing}>
                  {t('trader.pass')}
                </button>
              </div>
            </div>
          );
        }

        // --- CAPTAIN LOAD ---
        if (isCaptainPhase) {
          const ships = state.common_board.cargo_ships;
          const validShipsForGood = (good: string): number[] => {
            const assigned = ships.findIndex(s => s.good === good);
            if (assigned !== -1) return ships[assigned].d_is_full ? [] : [assigned];
            return ships.map((s, i) => s.d_is_empty ? i : -1).filter(i => i !== -1);
          };
          const hasWharf = activePlayer?.city.buildings.some(b => b.name === 'wharf' && b.is_active) ?? false;
          const wharfUsed = activePlayer?.wharf_used_this_phase ?? true;
          const isRolePicker = state.meta.active_player === captainRolePicker;
          const firstLoadDone = activePlayer?.captain_first_load_done ?? true;
          const goodRows = (['corn', 'indigo', 'sugar', 'tobacco', 'coffee'] as const)
            .map(g => ({ g, qty: activePlayer?.goods[g] ?? 0, validShips: validShipsForGood(g) }))
            .filter(({ qty }) => qty > 0);
          const canLoadAny = goodRows.some(({ validShips }) => validShips.length > 0)
            || (hasWharf && !wharfUsed && (activePlayer?.goods.d_total ?? 0) > 0);

          return (
            <div id="action-card" className="action-card">
              <div className="action-card__header">
                <span><strong>{t('captain.title')}</strong> — {activePlayer?.display_name}</span>
                <span className="action-card__badges">
                  {isRolePicker && !firstLoadDone && <span className="badge badge-gold">{t('captain.privilegeBadge')}</span>}
                  {activePlayer?.city.buildings.some(b => b.name === 'harbor' && b.is_active) && <span className="badge badge-blue">{t('captain.harbor')}</span>}
                </span>
              </div>
              {goodRows.length === 0 && <p className="action-card__empty">{t('captain.noGoods')}</p>}
              {goodRows.map(({ g, qty, validShips }) => (
                <div key={g} className="captain-good-row">
                  <span className="captain-good-name">{t(`goods.${g}`)} ×{qty}</span>
                  <div className="captain-ship-btns">
                    {validShips.map(idx => {
                      const ship = ships[idx];
                      const toLoad = Math.min(qty, ship.d_remaining_space);
                      return (
                        <button key={idx} className="hospice-yes captain-ship-btn"
                          onClick={() => loadShip(g, idx, false)}>
                          {t('captain.shipBtn', { idx: idx + 1, filled: ship.d_filled, cap: ship.capacity, qty: toLoad })}
                        </button>
                      );
                    })}
                    {validShips.length === 0 && !hasWharf && <span style={{ color: '#888' }}>{t('captain.noValidShip')}</span>}
                    {hasWharf && !wharfUsed && (
                      <button className="hospice-yes captain-ship-btn captain-wharf-btn"
                        onClick={() => loadShip(g, null, true)}>
                        {t('captain.wharfBtn', { qty })}
                      </button>
                    )}
                  </div>
                </div>
              ))}
              <div className="action-card__footer">
                <button className="hospice-no" onClick={captainPass} disabled={canLoadAny}>
                  {canLoadAny ? t('captain.mustLoad') : t('captain.pass')}
                </button>
              </div>
            </div>
          );
        }

        // --- CAPTAIN DISCARD ---
        const hasLargeWh = activePlayer?.city.buildings.some(b => b.name === 'large_warehouse' && b.is_active) ?? false;
        const hasSmallWh = activePlayer?.city.buildings.some(b => b.name === 'small_warehouse' && b.is_active) ?? false;
        const maxProtected = (hasLargeWh ? 2 : 0) + (hasSmallWh ? 1 : 0);
        const ownedGoods = (['corn', 'indigo', 'sugar', 'tobacco', 'coffee'] as const)
          .map(g => ({ g, qty: activePlayer?.goods[g] ?? 0 }))
          .filter(({ qty }) => qty > 0);
        const toggleProtected = (g: string) => {
          if (discardProtected.includes(g)) {
            setDiscardProtected(prev => prev.filter(x => x !== g));
          } else if (discardProtected.length < maxProtected) {
            setDiscardProtected(prev => [...prev, g]);
            if (discardSingleExtra === g) setDiscardSingleExtra(null);
          }
        };
        const kept = ownedGoods.map(({ g, qty }) => {
          if (discardProtected.includes(g)) return { g, keep: qty, discard: 0 };
          if (discardSingleExtra === g) return { g, keep: Math.min(1, qty), discard: qty - Math.min(1, qty) };
          return { g, keep: 0, discard: qty };
        });

        return (
          <div id="action-card" className="action-card">
            <div className="action-card__header">
              <span><strong>{t('discard.title')}</strong> — {activePlayer?.display_name}</span>
              <span className="action-card__badges">
                {maxProtected > 0
                  ? <span className="badge badge-blue">{t('discard.warehouse', { n: maxProtected })}</span>
                  : <span className="badge badge-dim">{t('discard.noWarehouse')}</span>}
              </span>
            </div>
            {ownedGoods.length === 0 && <p className="action-card__empty">{t('discard.noGoods')}</p>}
            {ownedGoods.length > 0 && (
              <table className="captain-discard-table">
                <thead>
                  <tr>
                    <th>{t('discard.good')}</th><th>{t('discard.qty')}</th>
                    {maxProtected > 0 && <th>{t('discard.warehouseCol', { used: discardProtected.length, max: maxProtected })}</th>}
                    <th>{t('discard.extraCol')}</th>
                    <th>{t('discard.discardCol')}</th>
                  </tr>
                </thead>
                <tbody>
                  {kept.map(({ g, discard }) => (
                    <tr key={g} style={{ color: discard > 0 ? '#f88' : '#6f6' }}>
                      <td>{t(`goods.${g}`)}</td>
                      <td>{activePlayer?.goods[g as keyof typeof activePlayer.goods] ?? 0}</td>
                      {maxProtected > 0 && (
                        <td>
                          <input type="checkbox"
                            checked={discardProtected.includes(g)}
                            disabled={!discardProtected.includes(g) && discardProtected.length >= maxProtected}
                            onChange={() => toggleProtected(g)}
                          />
                        </td>
                      )}
                      <td>
                        <input type="radio"
                          name="single_extra"
                          checked={discardSingleExtra === g}
                          disabled={discardProtected.includes(g)}
                          onChange={() => setDiscardSingleExtra(g)}
                        />
                      </td>
                      <td style={{ fontWeight: 'bold' }}>{discard > 0 ? `${discard} ✗` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <div className="action-card__footer">
              <button className="hospice-yes" onClick={doDiscardGoods}>
                {t('discard.confirm')}
              </button>
            </div>
          </div>
        );
      })()}

      {/* Row 2: Players */}
      <div className="layout-players">
        {state.meta.player_order.map(id => (
          <PlayerPanel
            key={id}
            playerId={id}
            player={state.players[id]}
            isActive={id === state.meta.active_player}
            phase={state.meta.phase}
            mayorPending={id === state.meta.active_player ? mayorPending : null}
            mayorLocalUnplaced={id === state.meta.active_player ? mayorLocalUnplaced : 0}
            onMayorToggle={id === state.meta.active_player && isMayorToggleMode ? toggleMayorSlot : undefined}
            onMayorPlace={id === state.meta.active_player && !isMayorToggleMode ? mayorPlaceAmount : undefined}
            mayorSlotIdx={id === state.meta.active_player && !isMayorToggleMode ? (state.meta.mayor_slot_idx ?? null) : null}
            highlightLastPlantation={
              isSettlerPhase && id === state.meta.active_player &&
              (state.players[id]?.hacienda_used_this_phase ?? false)
            }
            isOffline={isMultiplayer
              ? lobbyPlayers.find(lp => lp.name === state.players[id]?.display_name)?.connected === false
              : undefined}
            isMe={isMultiplayer ? state.players[id]?.display_name === myName : undefined}
            botType={state.bot_players ? state.bot_players[id] : undefined}
          />
        ))}
      </div>

      {/* San Juan full width */}
      <section id="san-juan" className={`panel layout-sanjuan${state.meta.phase === 'builder_action' ? ' board-active' : ''}`}>
        <h2>{t('sanJuan.title')}</h2>
        <div style={{ display: 'flex', gap: '24px', alignItems: 'flex-start' }}>
          <SanJuan buildings={state.common_board.available_buildings}
            builderInfo={builderInfo}
            onBuild={isBuilderPhase ? requestBuild : undefined} />
          <table style={{ flexShrink: 0, tableLayout: 'fixed', width: 350 }}>
            <colgroup>
              <col style={{ width: 260 }} />
              <col style={{ width: 36 }} />
              <col style={{ width: 28 }} />
              <col style={{ width: 28 }} />
              <col style={{ width: 28 }} />
            </colgroup>
            <thead>
              <tr><th>{t('sanJuan.building')}</th><th>{t('sanJuan.cost')}</th><th>{t('sanJuan.vp')}</th><th>{t('sanJuan.colonists')}</th><th>{t('sanJuan.copies')}</th></tr>
            </thead>
            <tbody>
              {([ 'small_indigo_plant','indigo_plant','small_sugar_mill','sugar_mill','tobacco_storage','coffee_roaster','small_market','large_market','hacienda','construction_hut','small_warehouse','large_warehouse','hospice','office','factory','university','harbor','wharf','guild_hall','residence','fortress','customs_house','city_hall'] as const)
                .filter(name => state.common_board.available_buildings[name]?.copies_remaining > 0)
                .map(name => { const b = state.common_board.available_buildings[name]; return (
                  <tr key={name}>
                    <td style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {t(`buildings.${name}`, { defaultValue: name.replace(/_/g, ' ') })}
                    </td>
                    <td>{b.cost}</td>
                    <td>{b.vp}</td>
                    <td>{b.max_colonists}</td>
                    <td>{b.copies_remaining}</td>
                  </tr>
                ); })}
            </tbody>
          </table>
        </div>
      </section>

      {/* History */}
      <section className="panel">
        <h2>{t('history.title')}</h2>
        <HistoryPanel history={state.history ?? []} />
      </section>

    </div>
  );
}
