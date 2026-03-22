import { useEffect, useRef, useState } from 'react';
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
import JoinScreen from './components/JoinScreen';
import LobbyScreen from './components/LobbyScreen';
import type { LobbyPlayer, ServerInfo } from './types/gameState';
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

export default function App() {
  const { t } = useTranslation();
  const isAdmin = new URLSearchParams(window.location.search).has('admin');
  const [state, setState] = useState<GameState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [showNewGame, setShowNewGame] = useState(false);
  const [buildConfirm, setBuildConfirm] = useState<{ name: string; cost: number; vp: number } | null>(null);
  const [newGamePlayers, setNewGamePlayers] = useState(3);
  const [newGameNames, setNewGameNames] = useState(['', '', '', '', '']);
  const [newGameBotTypes, setNewGameBotTypes] = useState(['', 'random', 'random', 'random', 'random']);
  const [botAgents, setBotAgents] = useState<{type: string; name: string}[]>([]);
  const [newGameLoading, setNewGameLoading] = useState(false);
  const [homeGameExists, setHomeGameExists] = useState(false);
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

  // --- Multiplayer / screen routing ---
  const [screen, setScreen] = useState<'loading' | 'home' | 'join' | 'lobby' | 'game'>('loading');
  const [myName, setMyName] = useState<string | null>(null);
  const [myPlayerId, setMyPlayerId] = useState<string | null>(null);
  const [isMultiplayer, setIsMultiplayer] = useState(false);
  const [mpKey, setMpKey] = useState<string | null>(null);
  const [sessionKeyDisplay, setSessionKeyDisplay] = useState<string | null>(null);
  const [lobbyPlayers, setLobbyPlayers] = useState<LobbyPlayer[]>([]);
  const [lobbyHost, setLobbyHost] = useState<string | null>(null);
  const [lobbyError, setLobbyError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${BACKEND}/api/bot-types`)
      .then(r => r.json())
      .then((data: {type: string; name: string}[]) => setBotAgents(data))
      .catch(() => {});
  }, []);

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
    if (!state?.meta.end_game_triggered) return;
    fetch(`${BACKEND}/api/final-score`)
      .then(r => r.json())
      .then(setFinalScores)
      .catch(() => {});
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [state?.meta.end_game_triggered]);

  useEffect(() => { initializeApp(); }, []);

  async function initializeApp() {
    try {
      const info: ServerInfo = await fetch(`${BACKEND}/api/server-info`).then(r => r.json());

      if (info.mode === 'idle') {
        setHomeGameExists(info.game_exists ?? false);
        setScreen('home');
        return;
      }

      if (info.mode === 'single') {
        if (info.game_exists) {
          const gs = await fetch(`${BACKEND}/api/game-state`).then(r => r.json());
          setState(gs);
        }
        setScreen('game');
        return;
      }

      // multiplayer
      const savedKey = localStorage.getItem('mp_key');
      const savedName = localStorage.getItem('mp_name');
      if (savedKey && savedName) {
        const hb = await fetch(`${BACKEND}/api/heartbeat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ key: savedKey, name: savedName }),
        });
        if (hb.ok) {
          const hbData = await hb.json();
          setMyName(savedName);
          setMpKey(savedKey);
          setIsMultiplayer(true);
          if (hbData.player_id) setMyPlayerId(hbData.player_id);
          const info2: ServerInfo = await fetch(`${BACKEND}/api/server-info`).then(r => r.json());
          setLobbyPlayers(info2.players ?? []);
          setLobbyHost(info2.host);
          if (hbData.lobby_status === 'playing') {
            const gs = await fetch(`${BACKEND}/api/game-state`).then(r => r.json());
            setState(gs);
            setScreen('game');
          } else {
            setScreen('lobby');
          }
          return;
        }
        localStorage.removeItem('mp_key');
        localStorage.removeItem('mp_name');
      }
      setScreen('join');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to connect to server');
      setScreen('home');
    }
  }

  // Polling: fetch game state in multiplayer game mode.
  // Poll faster (800ms) while a Gemini bot is thinking.
  useEffect(() => {
    if (screen !== 'game' || !isMultiplayer) return;
    const ms = state?.meta.bot_thinking ? 800 : 2500;
    const interval = setInterval(async () => {
      try {
        const [gs, info] = await Promise.all([
          fetch(`${BACKEND}/api/game-state`).then(r => r.json()),
          fetch(`${BACKEND}/api/server-info`).then(r => r.json()),
        ]);
        if (gs && gs.meta) {
          setState(gs);
        }
        setLobbyPlayers((info as ServerInfo).players ?? []);
      } catch { /* ignore */ }
    }, ms);
    return () => clearInterval(interval);
  }, [screen, isMultiplayer, state?.meta.bot_thinking]);

  // Polling: run bots and refresh state in offline single-player mode.
  // Each poll processes ONE bot role turn, giving ~2s visibility between moves.
  useEffect(() => {
    if (screen !== 'game' || isMultiplayer) return;
    const ms = state?.meta.bot_thinking ? 800 : 2000; // 2s gap between bot turns
    const interval = setInterval(async () => {
      try {
        const gs: GameState = await fetch(`${BACKEND}/api/run-bots`, { method: 'POST' }).then(r => r.json());
        if (!gs || !gs.meta) return;
        setState(prev => {
          if (prev && gs.history.length === prev.history.length && gs.meta.active_player === prev.meta.active_player) return prev;
          return gs;
        });
      } catch { /* ignore */ }
    }, ms);
    return () => clearInterval(interval);
  }, [screen, isMultiplayer, state?.meta.bot_thinking]);

  // Polling: refresh lobby every 2.5s when in lobby screen
  useEffect(() => {
    if (screen !== 'lobby') return;
    const interval = setInterval(async () => {
      try {
        const info: ServerInfo = await fetch(`${BACKEND}/api/server-info`).then(r => r.json());
        setLobbyPlayers(info.players ?? []);
        setLobbyHost(info.host);
        if (info.lobby_status === 'playing') {
          const me = info.players?.find(p => p.name === myName);
          if (me?.player_id) setMyPlayerId(me.player_id);
          const gs = await fetch(`${BACKEND}/api/game-state`).then(r => r.json());
          if (gs && gs.meta) {
            setState(gs);
          }
          setScreen('game');
        }
      } catch { /* ignore */ }
    }, 2500);
    return () => clearInterval(interval);
  }, [screen, myName]);

  // Heartbeat: keep-alive every 5s in multiplayer
  useEffect(() => {
    if (!isMultiplayer || !mpKey || !myName) return;
    const interval = setInterval(async () => {
      try {
        const hb = await fetch(`${BACKEND}/api/heartbeat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ key: mpKey, name: myName }),
        });
        if (hb.ok) {
          const data = await hb.json();
          if (data.player_id && !myPlayerId) setMyPlayerId(data.player_id);
        }
      } catch { /* ignore */ }
    }, 5000);
    return () => clearInterval(interval);
  }, [isMultiplayer, mpKey, myName, myPlayerId]);

  function logout(forceHome = false) {
    const isClient = isMultiplayer && myName !== lobbyHost;
    localStorage.removeItem('mp_key');
    localStorage.removeItem('mp_name');
    setMyName(null);
    setMyPlayerId(null);
    setMpKey(null);
    setSessionKeyDisplay(null);
    setIsMultiplayer(false);
    setLobbyPlayers([]);
    setLobbyHost(null);
    setState(null);
    setScreen(!forceHome && isClient ? 'join' : 'home');
  }

  async function handleSinglePlayer() {
    try {
      const res = await fetch(`${BACKEND}/api/set-mode/single`, { method: 'POST' });
      const data = await res.json();
      if (data.game_exists) {
        const gs = await fetch(`${BACKEND}/api/game-state`).then(r => r.json());
        setState(gs);
      }
      setScreen('game');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed');
    }
  }

  async function handleStartOffline(numPlayers: number, names: string[], botTypes: string[]) {
    try {
      await fetch(`${BACKEND}/api/set-mode/single`, { method: 'POST' });
      const res = await fetch(`${BACKEND}/api/new-game`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ num_players: numPlayers, player_names: names }),
      });
      if (!res.ok) { setError(await res.text()); return; }
      const data: GameState = await res.json();

      // Find and save the human player's ID before registering bots
      const humanIdx = botTypes.findIndex(bt => !bt);
      const humanPlayerId = humanIdx >= 0
        ? Object.entries(data.players).find(([, p]) => p.display_name === names[humanIdx])?.[0] ?? null
        : null;

      for (let i = 0; i < names.length; i++) {
        const botType = botTypes[i];
        if (botType) {
          // Use player_order index directly to avoid matching issues when multiple bots share a display name
          const playerId = data.meta.player_order?.[i] ?? `player_${i}`;
          const botRes = await fetch(`${BACKEND}/api/bot/set`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ player: playerId, bot_type: botType }),
          });
          if (!botRes.ok) {
            setError(await botRes.text());
            return;
          }
        }
      }

      // Run initial bot turns (in case governor is a bot)
      const runRes = await fetch(`${BACKEND}/api/run-bots`, { method: 'POST' });
      let finalState = data;
      if (runRes.ok) {
        const parsed = await runRes.json();
        if (parsed && parsed.meta) finalState = parsed;
      }

      prevHistoryLenRef.current = finalState.history.length;
      setMyPlayerId(humanPlayerId);
      setState(finalState);
      setScreen('game');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed');
    }
  }

  async function handleMultiplayerInit(hostName: string) {
    try {
      const res = await fetch(`${BACKEND}/api/multiplayer/init`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ host_name: hostName }),
      });
      if (!res.ok) { setError(await res.text()); return; }
      const data = await res.json();
      localStorage.setItem('mp_key', data.session_key);
      localStorage.setItem('mp_name', hostName);
      setMyName(hostName);
      setMpKey(data.session_key);
      setSessionKeyDisplay(data.session_key);
      setIsMultiplayer(true);
      const info: ServerInfo = await fetch(`${BACKEND}/api/server-info`).then(r => r.json());
      setLobbyPlayers(info.players ?? []);
      setLobbyHost(info.host);
      setScreen('lobby');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed');
    }
  }

  async function handleJoin(key: string, name: string, role: 'player' | 'spectator'): Promise<string | null> {
    try {
      const res = await fetch(`${BACKEND}/api/lobby/join`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key, name, role }),
      });
      if (!res.ok) return await res.text();
      const data = await res.json();
      localStorage.setItem('mp_key', key);
      localStorage.setItem('mp_name', name);
      setMyName(name);
      setMpKey(key);
      setIsMultiplayer(true);
      const info: ServerInfo = await fetch(`${BACKEND}/api/server-info`).then(r => r.json());
      setLobbyPlayers(info.players ?? []);
      setLobbyHost(info.host);
      if (data.reconnected) {
        if (data.player_id) setMyPlayerId(data.player_id);
        const gs = await fetch(`${BACKEND}/api/game-state`).then(r => r.json());
        setState(gs);
        setScreen('game');
      } else {
        setScreen('lobby');
      }
      return null;
    } catch (e) {
      return e instanceof Error ? e.message : 'Failed';
    }
  }

  async function handleAddBot(botName: string, botType: string) {
    if (!mpKey || !myName) return;
    setLobbyError(null);
    try {
      const res = await fetch(`${BACKEND}/api/lobby/add-bot`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: mpKey, host_name: myName, bot_name: botName, bot_type: botType }),
      });
      if (!res.ok) { setLobbyError(await res.text()); return; }
      const info: ServerInfo = await fetch(`${BACKEND}/api/server-info`).then(r => r.json());
      if (info.players) setLobbyPlayers(info.players);
    } catch (e) {
      setLobbyError(e instanceof Error ? e.message : 'Failed');
    }
  }

  async function handleRemoveBot(botName: string) {
    if (!mpKey || !myName) return;
    setLobbyError(null);
    try {
      const res = await fetch(`${BACKEND}/api/lobby/remove-bot`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: mpKey, host_name: myName, bot_name: botName }),
      });
      if (!res.ok) { setLobbyError(await res.text()); return; }
      const info: ServerInfo = await fetch(`${BACKEND}/api/server-info`).then(r => r.json());
      if (info.players) setLobbyPlayers(info.players);
    } catch (e) {
      setLobbyError(e instanceof Error ? e.message : 'Failed');
    }
  }

  async function handleLobbyStart() {
    if (!mpKey || !myName) return;
    setLobbyError(null);
    try {
      const res = await fetch(`${BACKEND}/api/lobby/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: mpKey, name: myName }),
      });
      if (!res.ok) { setLobbyError(await res.text()); return; }
      const gs = await res.json();
      setState(gs);
      const info: ServerInfo = await fetch(`${BACKEND}/api/server-info`).then(r => r.json());
      const me = info.players?.find(p => p.name === myName);
      if (me?.player_id) setMyPlayerId(me.player_id);
      setScreen('game');
    } catch (e) {
      setLobbyError(e instanceof Error ? e.message : 'Failed');
    }
  }

  function notMyTurn(): boolean {
    return isMultiplayer && myPlayerId !== null && myPlayerId !== state?.meta.active_player;
  }

  async function selectRole(role: string) {
    if (!state) return;
    if (notMyTurn()) return;
    setSaving(true);
    try {
      const res = await fetch(`${BACKEND}/api/action/select-role`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ player: state.meta.active_player, role }),
      });
      if (!res.ok) {
        const msg = await res.text();
        setError(msg);
        return;
      }
      const saved = await res.json();
      setState(saved);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  }

  async function passAction() {
    if (notMyTurn()) return;
    setPassing(true);
    setError(null);
    try {
      const res = await fetch(`${BACKEND}/api/action/pass`, { method: 'POST' });
      if (!res.ok) {
        setError(await res.text());
        return;
      }
      setState(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Request failed');
    } finally {
      setPassing(false);
    }
  }

  async function useHacienda() {
    if (notMyTurn()) return;
    setError(null);
    try {
      const res = await fetch(`${BACKEND}/api/action/use-hacienda`, { method: 'POST' });
      if (!res.ok) { setError(await res.text()); return; }
      setState(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Request failed');
    }
  }

  async function doSettlePlantation(type: string, useHospice: boolean) {
    if (!state) return;
    setError(null);
    try {
      const res = await fetch(`${BACKEND}/api/action/settle-plantation`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ player: state.meta.active_player, plantation: type, use_hospice: useHospice }),
      });
      if (!res.ok) { setError(await res.text()); return; }
      setState(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Request failed');
    }
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

  async function mayorPlaceColonist(targetType: 'plantation' | 'building', targetIndex: number) {
    if (!state || notMyTurn()) return;
    setError(null);
    try {
      const res = await fetch(`${BACKEND}/api/action/mayor-place-colonist`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ player: state.meta.active_player, target_type: targetType, target_index: targetIndex }),
      });
      if (!res.ok) { setError(await res.text()); return; }
      setState(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Request failed');
    }
  }

  async function mayorPickupColonist(targetType: 'plantation' | 'building', targetIndex: number) {
    if (!state || notMyTurn()) return;
    setError(null);
    try {
      const res = await fetch(`${BACKEND}/api/action/mayor-pickup-colonist`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ player: state.meta.active_player, target_type: targetType, target_index: targetIndex }),
      });
      if (!res.ok) { setError(await res.text()); return; }
      setState(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Request failed');
    }
  }

  async function mayorFinishPlacement() {
    if (!state || notMyTurn()) return;
    setError(null);
    try {
      const res = await fetch(`${BACKEND}/api/action/mayor-finish-placement`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ player: state.meta.active_player }),
      });
      if (!res.ok) { setError(await res.text()); return; }
      setState(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Request failed');
    }
  }

  async function sellGood(good: string) {
    if (notMyTurn()) return;
    setSellingGood(good);
    setError(null);
    try {
      const res = await fetch(`${BACKEND}/api/action/sell`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ good }),
      });
      if (!res.ok) { setError(await res.text()); return; }
      setState(await res.json());
      scrollToActionCard();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Request failed');
    } finally {
      setSellingGood(null);
    }
  }

  async function craftsmanPrivilege(good: string) {
    if (notMyTurn()) return;
    setError(null);
    try {
      const res = await fetch(`${BACKEND}/api/action/craftsman-privilege`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ good }),
      });
      if (!res.ok) { setError(await res.text()); return; }
      setState(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Request failed');
    }
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
    setError(null);
    try {
      const res = await fetch(`${BACKEND}/api/action/load-ship`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ player: state.meta.active_player, good, ship_index: shipIndex, use_wharf: useWharf }),
      });
      if (!res.ok) { setError(await res.text()); return; }
      setState(await res.json());
      scrollToActionCard();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Request failed');
    }
  }

  async function captainPass() {
    if (!state || notMyTurn()) return;
    setError(null);
    try {
      const res = await fetch(`${BACKEND}/api/action/captain-pass`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ player: state.meta.active_player }),
      });
      if (!res.ok) { setError(await res.text()); return; }
      setState(await res.json());
      scrollToActionCard();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Request failed');
    }
  }

  async function doDiscardGoods() {
    if (!state) return;
    setError(null);
    try {
      const res = await fetch(`${BACKEND}/api/action/discard-goods`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          player: state.meta.active_player,
          protected: discardProtected,
          single_extra: discardSingleExtra,
        }),
      });
      if (!res.ok) { setError(await res.text()); return; }
      setDiscardProtected([]);
      setDiscardSingleExtra(null);
      setState(await res.json());
      scrollToActionCard();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Request failed');
    }
  }

  function requestBuild(name: string, cost: number, vp: number) {
    setBuildConfirm({ name, cost, vp });
  }

  async function build(buildingName: string) {
    if (!state || notMyTurn()) return;
    setError(null);
    try {
      const res = await fetch(`${BACKEND}/api/action/build`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ player: state.meta.active_player, building: buildingName }),
      });
      if (!res.ok) { setError(await res.text()); return; }
      setState(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Request failed');
    }
  }

  async function startNewGame() {
    const names = newGameNames.slice(0, newGamePlayers).map(n => n.trim());
    if (names.some(n => n === '')) {
      setError('Inserisci un nome per ogni giocatore');
      return;
    }
    setNewGameLoading(true);
    setError(null);
    try {
      const res = await fetch(`${BACKEND}/api/new-game`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ num_players: newGamePlayers, player_names: names }),
      });
      if (!res.ok) {
        const text = await res.text();
        setError(text);
      } else {
        const data: GameState = await res.json();
        // Configure bot players based on the shuffled order returned by the backend
        const botTypes = newGameBotTypes.slice(0, newGamePlayers);
        for (let i = 0; i < names.length; i++) {
          const botType = botTypes[i];
          if (botType) {
            // Use player_order index directly to avoid matching issues when multiple bots share a display name
            const playerId = data.meta.player_order?.[i] ?? `player_${i}`;
            const botRes = await fetch(`${BACKEND}/api/bot/set`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ player: playerId, bot_type: botType }),
            });
            if (!botRes.ok) {
              const errText = await botRes.text();
              setError(errText);
              setNewGameLoading(false);
              return;
            }
          }
        }
        setState(data);
        setShowNewGame(false);
        setFinalScores(null);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Errore di rete');
    } finally {
      setNewGameLoading(false);
    }
  }


  const isBotTurn = !!(state?.bot_players && state?.decision?.player && state.bot_players[state.decision.player] !== undefined);
  const isMyTurn = !isMultiplayer
    ? !isBotTurn
    : (myPlayerId !== null && state?.decision?.player === myPlayerId);
  const isBlocked = !!state?.meta.bot_thinking || (!isMultiplayer && isBotTurn);

  if (screen === 'loading') {
    return <div style={{ color: '#eee', padding: 40, textAlign: 'center' }}>Loading...</div>;
  }
  if (screen === 'home') {
    return <HomeScreen
      gameExists={homeGameExists}
      onContinue={handleSinglePlayer}
      onStartOffline={handleStartOffline}
      onMultiplayer={handleMultiplayerInit}
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
      sessionKey={sessionKeyDisplay ?? undefined}
      onStart={handleLobbyStart}
      onLogout={() => logout()}
      onAddBot={handleAddBot}
      onRemoveBot={handleRemoveBot}
      error={lobbyError}
    />;
  }
  // screen === 'game' — need state from here on
  if (!state) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', gap: 16 }}>
        <p style={{ color: '#aab' }}>{t('game.noGame')}</p>
        <button
          style={{ background: '#2a5ab0', color: '#fff', border: 'none', borderRadius: 8, padding: '12px 24px', fontSize: 16, cursor: 'pointer' }}
          onClick={() => { setError(null); setShowNewGame(true); }}
        >
          {t('game.startNew')}
        </button>
        {showNewGame && (
          <div style={{ background: '#0d1117', border: '1px solid #2a2a5a', borderRadius: 8, padding: 24, display: 'flex', flexDirection: 'column', gap: 12 }}>
            <label style={{ color: '#aab' }}>{t('newGame.numPlayers')}
              <select value={newGamePlayers} onChange={e => setNewGamePlayers(Number(e.target.value))}
                style={{ marginLeft: 8, background: '#1a1a2e', color: '#eee', border: '1px solid #444', borderRadius: 4, padding: '4px 8px' }}>
                {[3,4,5].map(n => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
            {Array.from({ length: newGamePlayers }, (_, i) => (
              <input key={i} placeholder={t('newGame.playerName', { n: i + 1 })}
                value={newGameNames[i]}
                onChange={e => { const n = [...newGameNames]; n[i] = e.target.value; setNewGameNames(n); }}
                style={{ padding: '6px 10px', borderRadius: 4, border: '1px solid #444', background: '#1a1a2e', color: '#eee' }}
              />
            ))}
            {error && (
              <div className="new-game-error">{error}</div>
            )}
            <button onClick={startNewGame} disabled={newGameLoading}
              style={{ background: '#2a5ab0', color: '#fff', border: 'none', borderRadius: 6, padding: '8px 16px', cursor: 'pointer' }}>
              {newGameLoading ? t('newGame.starting') : t('newGame.start')}
            </button>
          </div>
        )}
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
            {isMultiplayer && (
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

      {showNewGame && (
        <div className="new-game-overlay" onClick={e => { if (e.target === e.currentTarget) setShowNewGame(false); }}>
          <div className="new-game-modal">
            <h2>{t('newGame.title')}</h2>

            <label>
              {t('newGame.numPlayers')}&nbsp;
              <select value={newGamePlayers} onChange={e => setNewGamePlayers(Number(e.target.value))}>
                <option value={3}>3</option>
                <option value={4}>4</option>
                <option value={5}>5</option>
              </select>
            </label>

            <div className="new-game-names">
              {Array.from({ length: newGamePlayers }, (_, i) => {
                const isBot = !!newGameBotTypes[i];
                return (
                  <div key={i} className="new-game-player-row">
                    <input
                      type="text"
                      placeholder={t('newGame.playerName', { n: i + 1 })}
                      value={newGameNames[i]}
                      readOnly={isBot}
                      onChange={e => {
                        if (isBot) return;
                        const updated = [...newGameNames];
                        updated[i] = e.target.value;
                        setNewGameNames(updated);
                      }}
                      onKeyDown={e => { if (e.key === 'Enter') startNewGame(); }}
                      style={isBot ? { opacity: 0.5, cursor: 'default' } : undefined}
                    />
                    <select
                      value={newGameBotTypes[i]}
                      onChange={e => {
                        const updated = [...newGameBotTypes];
                        updated[i] = e.target.value;
                        setNewGameBotTypes(updated);
                        // Auto-set name from agent config when switching to bot
                        if (e.target.value) {
                          const agent = botAgents.find(a => a.type === e.target.value);
                          const updatedNames = [...newGameNames];
                          updatedNames[i] = agent?.name ?? e.target.value;
                          setNewGameNames(updatedNames);
                        }
                      }}
                    >
                      <option value="">{t('newGame.human')}</option>
                      {botAgents.map(a => (
                        <option key={a.type} value={a.type}>{a.name}</option>
                      ))}
                    </select>
                  </div>
                );
              })}
            </div>

            <p className="new-game-hint">{t('newGame.govNote')}</p>

            {error && (
              <div className="new-game-error">{error}</div>
            )}

            <div className="new-game-actions">
              <button onClick={() => setShowNewGame(false)} className="btn-cancel">{t('newGame.cancel')}</button>
              <button onClick={startNewGame} disabled={newGameLoading} className="btn-start">
                {newGameLoading ? t('newGame.starting') : t('newGame.start')}
              </button>
            </div>
          </div>
        </div>
      )}
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
          {isMultiplayer && myName && (
            <span style={{ display: 'flex', alignItems: 'center', gap: 8, marginRight: 8, flexShrink: 0 }}>
              <span style={{ color: '#f0c040', fontWeight: 'bold', fontSize: 13, whiteSpace: 'nowrap' }}>
                👤 {myName}
              </span>
              {mpKey && (
                <span style={{ color: '#667', fontSize: 12, whiteSpace: 'nowrap' }}>
                  🔑 <span style={{ fontFamily: 'monospace', letterSpacing: 2 }}>{mpKey}</span>
                </span>
              )}
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
            {isMayorPhase && (
              <button onClick={mayorFinishPlacement} disabled={passing || mayorMustPlace || isBlocked} className="pass-btn mayor-finish-btn">
                {mayorMustPlace ? t('actions.finishMayorWait') : t('actions.finishMayor')}
              </button>
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
            onMayorPlace={id === state.meta.active_player ? mayorPlaceColonist : undefined}
            onMayorPickup={id === state.meta.active_player ? mayorPickupColonist : undefined}
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
