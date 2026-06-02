import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { buildApiUrl } from '../config';

export interface RoomPlayerInfo {
  display_name: string;
  is_bot: boolean;
}

export interface RoomInfo {
  id: string;
  title: string;
  status: string;
  is_private: boolean;
  current_players: number;
  max_players: number;
  player_names: RoomPlayerInfo[];
}

interface BotAgent {
  type: string;
  name: string;
}

const PUBLIC_BOT_TYPE_ORDER = ['random', 'action_value', 'shipping_rush', 'ppo'] as const;

const FALLBACK_BOT_AGENTS: BotAgent[] = [
  { type: 'random', name: 'Random Bot' },
  { type: 'action_value', name: 'Action Value Bot' },
  { type: 'shipping_rush', name: 'Shipping Rush Bot' },
  { type: 'ppo', name: 'PPO Bot' },
];

interface Props {
  token: string;
  userNickname?: string | null;
  onJoinRoom: (roomId: string) => void;
  onCreateRoom: (title: string, isPrivate: boolean, password: string | null) => Promise<string | null>;
  onCreateBotGame?: (botTypes: string[]) => Promise<string | null | void> | string | null | void;
  onOpenReplayList?: () => void;
  onLogout: () => void;
  error?: string | null;
}

export default function RoomListScreen({ token, userNickname, onJoinRoom, onCreateRoom, onCreateBotGame, onOpenReplayList, onLogout, error: externalError }: Props) {
  const { t } = useTranslation();
  const defaultBotTypes = ['random', 'action_value', 'shipping_rush'];
  const [rooms, setRooms] = useState<RoomInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Create room modal state
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newIsPrivate, setNewIsPrivate] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  // Create bot-game modal state
  const [showBotGame, setShowBotGame] = useState(false);
  const [botAgents, setBotAgents] = useState<BotAgent[]>([]);
  const [selectedBotTypes, setSelectedBotTypes] = useState<string[]>(defaultBotTypes);
  const [loadingBotTypes, setLoadingBotTypes] = useState(false);
  const [creatingBotGame, setCreatingBotGame] = useState(false);
  const [botGameError, setBotGameError] = useState<string | null>(null);

  // Password prompt for private rooms
  const [pendingJoinId, setPendingJoinId] = useState<string | null>(null);
  const [joinPassword, setJoinPassword] = useState('');
  const [joinError, setJoinError] = useState<string | null>(null);
  const [joining, setJoining] = useState(false);

  const fetchRooms = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(buildApiUrl('/api/puco/rooms/'), {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('방 목록을 불러오지 못했습니다');
      const data: RoomInfo[] = await res.json();
      setRooms(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : '오류');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { fetchRooms(); }, [fetchRooms]);

  useEffect(() => {
    if (!onCreateBotGame) return;

    let cancelled = false;

    async function fetchBotAgents() {
      setLoadingBotTypes(true);
      try {
        const res = await fetch(buildApiUrl('/api/bot-types'));
        if (!res.ok) throw new Error('봇 목록을 불러오지 못했습니다');
        const data: BotAgent[] = await res.json();
        if (cancelled) return;

        const nextAgents = data
          .filter(agent => PUBLIC_BOT_TYPE_ORDER.includes(agent.type as typeof PUBLIC_BOT_TYPE_ORDER[number]))
          .sort(
            (left, right) =>
              PUBLIC_BOT_TYPE_ORDER.indexOf(left.type as typeof PUBLIC_BOT_TYPE_ORDER[number])
              - PUBLIC_BOT_TYPE_ORDER.indexOf(right.type as typeof PUBLIC_BOT_TYPE_ORDER[number]),
          );
        const safeAgents = nextAgents.length > 0 ? nextAgents : FALLBACK_BOT_AGENTS;
        const defaultType = safeAgents.find(agent => agent.type === 'random')?.type ?? safeAgents[0].type;

        setBotAgents(safeAgents);
        setSelectedBotTypes(prev =>
          prev.map(type => (safeAgents.some(agent => agent.type === type) ? type : defaultType))
        );
      } catch {
        if (cancelled) return;
        setBotAgents(FALLBACK_BOT_AGENTS);
        setSelectedBotTypes(prev => prev.map(type => type || 'random'));
      } finally {
        if (!cancelled) setLoadingBotTypes(false);
      }
    }

    fetchBotAgents();
    return () => { cancelled = true; };
  }, [onCreateBotGame]);

  async function handleCreate() {
    if (!newTitle.trim()) return;
    if (newIsPrivate && newPassword.length !== 4) {
      setCreateError('비밀번호는 4자리 숫자여야 합니다');
      return;
    }
    setCreating(true);
    setCreateError(null);
    const err = await onCreateRoom(newTitle.trim(), newIsPrivate, newIsPrivate ? newPassword : null);
    setCreating(false);
    if (err) {
      setCreateError(err);
    } else {
      setShowCreate(false);
      setNewTitle('');
      setNewIsPrivate(false);
      setNewPassword('');
    }
  }

  function openBotGameModal() {
    setBotGameError(null);
    setShowBotGame(true);
  }

  function closeBotGameModal() {
    if (creatingBotGame) return;
    setShowBotGame(false);
    setBotGameError(null);
  }

  function handleBotTypeChange(index: number, botType: string) {
    setSelectedBotTypes(prev => prev.map((value, slot) => (slot === index ? botType : value)));
  }

  async function handleCreateBotGameConfirm() {
    if (!onCreateBotGame) return;

    setCreatingBotGame(true);
    setBotGameError(null);
    try {
      const err = await onCreateBotGame(selectedBotTypes);
      if (typeof err === 'string' && err) {
        setBotGameError(err);
        return;
      }
      setShowBotGame(false);
    } finally {
      setCreatingBotGame(false);
    }
  }

  function handleRoomClick(room: RoomInfo) {
    if (room.current_players >= room.max_players) return;
    if (room.is_private) {
      setPendingJoinId(room.id);
      setJoinPassword('');
      setJoinError(null);
    } else {
      doJoin(room.id, null);
    }
  }

  async function doJoin(roomId: string, password: string | null) {
    setJoining(true);
    setJoinError(null);
    try {
      const res = await fetch(buildApiUrl(`/api/puco/rooms/${roomId}/join`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ password }),
      });
      if (!res.ok) {
        const data = await res.json();
        setJoinError(data.detail || '입장 실패');
        setJoining(false);
        return;
      }
      setPendingJoinId(null);
      onJoinRoom(roomId);
    } catch (e) {
      setJoinError(e instanceof Error ? e.message : '오류');
      setJoining(false);
    }
  }

  return (
    <div className="resort-page-shell">
      {/* Header */}
      <div className="resort-app-header">
        <h1 className="resort-page-title">Puerto Rico</h1>
        <div className="resort-header-actions">
          {userNickname && <span className="resort-user-pill">{userNickname}</span>}
          <button
            onClick={() => { setShowCreate(true); setCreateError(null); }}
            className="resort-btn-primary"
            style={{ width: 'auto', padding: '8px 20px', fontSize: 14 }}
          >
            + {t('rooms.createRoom', '방 만들기')}
          </button>
          {onCreateBotGame && (
            <button
              onClick={openBotGameModal}
              className="resort-btn-tropical"
            >
              🤖 {t('rooms.createBotGame', '봇전')}
            </button>
          )}
          {onOpenReplayList && (
            <button
              onClick={onOpenReplayList}
              className="resort-btn-ghost"
            >
              🎬 {t('replay.title')}
            </button>
          )}
          <button onClick={fetchRooms} className="resort-btn-ghost">
            {t('rooms.refresh', '새로고침')}
          </button>
          <button onClick={onLogout} className="resort-btn-link">
            {t('home.logout', '로그아웃')}
          </button>
        </div>
      </div>

      {/* Room list */}
      <div className="resort-page-content">
        {(externalError || error) && (
          <p className="resort-error" style={{ marginBottom: 16 }}>{externalError || error}</p>
        )}
        {loading && <p className="resort-muted">불러오는 중...</p>}

        {!loading && rooms.length === 0 && (
          <div className="resort-empty-state">
            <p style={{ fontSize: 16 }}>{t('rooms.noRooms', '방이 없습니다. 새 방을 만들어보세요!')}</p>
          </div>
        )}

        <div className="resort-grid">
          {rooms.map(room => {
            const full = room.current_players >= room.max_players;
            return (
              <div
                key={room.id}
                className={`room-card${full ? ' room-card--full' : ''}`}
              >
                {/* Top row: title + lock/count */}
                <div className="room-card__top">
                  <span className="room-card__title">
                    {room.title}
                  </span>
                  <span className="room-card__meta">
                    {room.is_private && <span title="비밀방">🔒</span>}
                    {room.current_players}/{room.max_players}
                  </span>
                </div>

                {/* Player list */}
                <div className="room-card__players">
                  {room.player_names.map((p, i) => (
                    <div key={i} className={`room-card__player${p.is_bot ? ' room-card__player--bot' : ''}`}>
                      <span>{p.is_bot ? '🤖' : '👤'}</span>
                      <span>{p.display_name}</span>
                    </div>
                  ))}
                  {Array.from({ length: room.max_players - room.current_players }).map((_, i) => (
                    <div key={`empty-${i}`} className="room-card__empty">— 빈 자리</div>
                  ))}
                </div>

                {/* Join button */}
                <button
                  onClick={() => handleRoomClick(room)}
                  disabled={full}
                  className="resort-btn-primary"
                  style={{
                    opacity: full ? 0.4 : 1,
                    cursor: full ? 'not-allowed' : 'pointer',
                    marginTop: 4,
                    fontSize: 14,
                    padding: '8px 0',
                  }}
                >
                  {full ? t('rooms.full', '정원 초과') : t('rooms.join', '입장하기')}
                </button>
              </div>
            );
          })}
        </div>
      </div>

      {/* Create Room Modal */}
      {showCreate && (
        <div className="resort-modal-backdrop" onClick={() => setShowCreate(false)}>
          <div className="resort-modal" onClick={e => e.stopPropagation()}>
            <h3 className="resort-modal-title">{t('rooms.createRoom', '방 만들기')}</h3>

            <div>
              <label className="resort-field-label">방 이름</label>
              <input
                value={newTitle}
                onChange={e => setNewTitle(e.target.value)}
                placeholder="방 이름 (최대 30자)"
                maxLength={30}
                autoFocus
                className="resort-input"
                onKeyDown={e => e.key === 'Enter' && handleCreate()}
              />
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <label className="resort-check-row">
                <input
                  type="checkbox"
                  checked={newIsPrivate}
                  onChange={e => { setNewIsPrivate(e.target.checked); setNewPassword(''); }}
                  style={{ width: 16, height: 16 }}
                />
                🔒 비밀방
              </label>
            </div>

            {newIsPrivate && (
              <div>
                <label className="resort-field-label">비밀번호 (4자리 숫자)</label>
                <input
                  value={newPassword}
                  onChange={e => setNewPassword(e.target.value.replace(/\D/g, '').slice(0, 4))}
                  placeholder="0000"
                  maxLength={4}
                  className="resort-input resort-input--pin"
                />
              </div>
            )}

            {createError && <p className="resort-error" style={{ margin: 0 }}>{createError}</p>}

            <button
              onClick={handleCreate}
              disabled={!newTitle.trim() || creating || (newIsPrivate && newPassword.length !== 4)}
              className="resort-btn-primary"
              style={{ opacity: (!newTitle.trim() || creating || (newIsPrivate && newPassword.length !== 4)) ? 0.5 : 1 }}
            >
              {creating ? '생성 중...' : t('rooms.create', '만들기')}
            </button>
            <button onClick={() => setShowCreate(false)} className="resort-btn-secondary">취소</button>
          </div>
        </div>
      )}

      {/* Private Room Password Modal */}
      {pendingJoinId && (
        <div className="resort-modal-backdrop" onClick={() => { setPendingJoinId(null); setJoinError(null); }}>
          <div className="resort-modal" onClick={e => e.stopPropagation()}>
            <h3 className="resort-modal-title">🔒 비밀방</h3>
            <p className="resort-modal-copy">비밀번호를 입력하세요</p>
            <input
              value={joinPassword}
              onChange={e => setJoinPassword(e.target.value.replace(/\D/g, '').slice(0, 4))}
              placeholder="0000"
              maxLength={4}
              autoFocus
              className="resort-input resort-input--pin"
              onKeyDown={e => e.key === 'Enter' && joinPassword.length === 4 && doJoin(pendingJoinId, joinPassword)}
            />
            {joinError && <p className="resort-error" style={{ margin: 0 }}>{joinError}</p>}
            <button
              onClick={() => doJoin(pendingJoinId, joinPassword)}
              disabled={joinPassword.length !== 4 || joining}
              className="resort-btn-primary"
              style={{ opacity: joinPassword.length !== 4 || joining ? 0.5 : 1 }}
            >
              {joining ? '입장 중...' : '입장하기'}
            </button>
            <button onClick={() => { setPendingJoinId(null); setJoinError(null); }} className="resort-btn-secondary">취소</button>
          </div>
        </div>
      )}

      {showBotGame && onCreateBotGame && (
        <div className="resort-modal-backdrop" onClick={closeBotGameModal}>
          <div className="resort-modal" onClick={e => e.stopPropagation()}>
            <h3 className="resort-modal-title">{t('rooms.botGameSetup', '봇전 구성')}</h3>
            <p className="resort-modal-copy" style={{ fontSize: 13 }}>
              {t('rooms.botGameHint', '각 슬롯의 봇 유형을 고르면 바로 관전용 봇전을 시작합니다.')}
            </p>

            {selectedBotTypes.map((botType, index) => (
              <div key={`bot-slot-${index}`}>
                <label className="resort-field-label">
                  {t('rooms.botSlot', { n: index + 1, defaultValue: `플레이어 ${index + 1} 봇` })}
                </label>
                <select
                  value={botType}
                  onChange={e => handleBotTypeChange(index, e.target.value)}
                  className="resort-select"
                  disabled={loadingBotTypes || creatingBotGame || botAgents.length === 0}
                >
                  {botAgents.map(agent => (
                    <option key={`${index}-${agent.type}`} value={agent.type}>
                      {agent.name}
                    </option>
                  ))}
                </select>
              </div>
            ))}

            {loadingBotTypes && (
              <p className="resort-modal-copy" style={{ fontSize: 13 }}>
                {t('rooms.loadingBotTypes', '봇 목록을 불러오는 중...')}
              </p>
            )}

            {!loadingBotTypes && botAgents.length === 0 && (
              <p className="resort-error" style={{ margin: 0 }}>
                {t('rooms.noBotTypes', '사용 가능한 봇이 없습니다.')}
              </p>
            )}

            {botGameError && <p className="resort-error" style={{ margin: 0 }}>{botGameError}</p>}

            <div className="resort-actions" style={{ marginTop: 4 }}>
              <button
                onClick={handleCreateBotGameConfirm}
                disabled={creatingBotGame || loadingBotTypes || botAgents.length === 0}
                className="resort-btn-primary"
                style={{
                  flex: 1,
                  opacity: creatingBotGame || loadingBotTypes || botAgents.length === 0 ? 0.6 : 1,
                  cursor: creatingBotGame || loadingBotTypes || botAgents.length === 0 ? 'not-allowed' : 'pointer',
                }}
              >
                {creatingBotGame
                  ? t('rooms.creatingBotGame', '봇전 생성 중...')
                  : t('rooms.startBotGame', '봇전 시작')}
              </button>
              <button onClick={closeBotGameModal} disabled={creatingBotGame} className="resort-btn-secondary" style={{ flex: 1 }}>
                {t('newGame.cancel', '취소')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
