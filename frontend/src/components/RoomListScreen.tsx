import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';

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
  const defaultBotTypes = ['random', 'random', 'random'];
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
      const res = await fetch('/api/puco/rooms/', {
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
    const fallbackAgents: BotAgent[] = [{ type: 'random', name: 'Random Bot' }];

    async function fetchBotAgents() {
      setLoadingBotTypes(true);
      try {
        const res = await fetch('/api/bot-types');
        if (!res.ok) throw new Error('봇 목록을 불러오지 못했습니다');
        const data: BotAgent[] = await res.json();
        if (cancelled) return;

        const nextAgents = data.length > 0 ? data : fallbackAgents;
        const defaultType = nextAgents.find(agent => agent.type === 'random')?.type ?? nextAgents[0].type;

        setBotAgents(nextAgents);
        setSelectedBotTypes(prev =>
          prev.map(type => (nextAgents.some(agent => agent.type === type) ? type : defaultType))
        );
      } catch {
        if (cancelled) return;
        setBotAgents(fallbackAgents);
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
      const res = await fetch(`/api/puco/rooms/${roomId}/join`, {
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

  // --- styles ---
  const overlay: React.CSSProperties = {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
    display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
  };
  const modal: React.CSSProperties = {
    background: '#0d1117', border: '1px solid #2a2a5a', borderRadius: 12,
    padding: '28px 32px', width: 340, display: 'flex', flexDirection: 'column', gap: 14,
  };
  const inputStyle: React.CSSProperties = {
    padding: '8px 12px', borderRadius: 6, border: '1px solid #444',
    background: '#1a1a2e', color: '#eee', fontSize: 14, width: '100%', boxSizing: 'border-box',
  };
  const btnPrimary: React.CSSProperties = {
    background: '#2a5ab0', color: '#fff', border: 'none', borderRadius: 8,
    padding: '10px 0', fontSize: 15, cursor: 'pointer', width: '100%',
  };
  const btnSecondary: React.CSSProperties = {
    background: 'none', border: '1px solid #2a2a5a', color: '#aab', borderRadius: 8,
    padding: '10px 0', fontSize: 14, cursor: 'pointer', width: '100%',
  };

  return (
    <div style={{ minHeight: '100vh', background: '#070d18', color: '#dde', fontFamily: 'sans-serif' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '20px 32px', borderBottom: '1px solid #1a1a3a' }}>
        <h1 style={{ color: '#f0c040', margin: 0, fontSize: 24 }}>Puerto Rico</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          {userNickname && <span style={{ color: '#88a', fontSize: 13 }}>{userNickname}</span>}
          <button
            onClick={() => { setShowCreate(true); setCreateError(null); }}
            style={{ ...btnPrimary, width: 'auto', padding: '8px 20px', fontSize: 14 }}
          >
            + {t('rooms.createRoom', '방 만들기')}
          </button>
          {onCreateBotGame && (
            <button
              onClick={openBotGameModal}
              style={{ background: '#1a3a2a', border: '1px solid #2a5a3a', borderRadius: 6, color: '#4f8', cursor: 'pointer', padding: '8px 16px', fontSize: 14 }}
            >
              🤖 {t('rooms.createBotGame', '봇전')}
            </button>
          )}
          {onOpenReplayList && (
            <button
              onClick={onOpenReplayList}
              style={{ background: 'none', border: '1px solid #2a5a8a', borderRadius: 6, color: '#8cf', cursor: 'pointer', padding: '7px 14px', fontSize: 13 }}
            >
              🎬 {t('replay.title')}
            </button>
          )}
          <button onClick={fetchRooms} style={{ background: 'none', border: '1px solid #2a2a5a', borderRadius: 6, color: '#88a', cursor: 'pointer', padding: '7px 14px', fontSize: 13 }}>
            {t('rooms.refresh', '새로고침')}
          </button>
          <button onClick={onLogout} style={{ background: 'none', border: 'none', color: '#556', cursor: 'pointer', fontSize: 13 }}>
            {t('home.logout', '로그아웃')}
          </button>
        </div>
      </div>

      {/* Room list */}
      <div style={{ padding: '28px 32px' }}>
        {(externalError || error) && (
          <p style={{ color: '#f66', marginBottom: 16 }}>{externalError || error}</p>
        )}
        {loading && <p style={{ color: '#667' }}>불러오는 중...</p>}

        {!loading && rooms.length === 0 && (
          <div style={{ textAlign: 'center', marginTop: 80, color: '#445' }}>
            <p style={{ fontSize: 16 }}>{t('rooms.noRooms', '방이 없습니다. 새 방을 만들어보세요!')}</p>
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 16 }}>
          {rooms.map(room => {
            const full = room.current_players >= room.max_players;
            return (
              <div
                key={room.id}
                style={{
                  background: '#0d1117', border: '1px solid #2a2a5a', borderRadius: 10,
                  padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 10,
                  opacity: full ? 0.6 : 1,
                }}
              >
                {/* Top row: title + lock/count */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontWeight: 'bold', color: '#eef', fontSize: 15, maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {room.title}
                  </span>
                  <span style={{ fontSize: 13, color: '#88a', display: 'flex', alignItems: 'center', gap: 4, flexShrink: 0 }}>
                    {room.is_private && <span title="비밀방">🔒</span>}
                    {room.current_players}/{room.max_players}
                  </span>
                </div>

                {/* Player list */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minHeight: 60 }}>
                  {room.player_names.map((p, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: p.is_bot ? '#6af' : '#ccf' }}>
                      <span>{p.is_bot ? '🤖' : '👤'}</span>
                      <span>{p.display_name}</span>
                    </div>
                  ))}
                  {Array.from({ length: room.max_players - room.current_players }).map((_, i) => (
                    <div key={`empty-${i}`} style={{ fontSize: 13, color: '#333', fontStyle: 'italic' }}>— 빈 자리</div>
                  ))}
                </div>

                {/* Join button */}
                <button
                  onClick={() => handleRoomClick(room)}
                  disabled={full}
                  style={{
                    ...btnPrimary,
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
        <div style={overlay} onClick={() => setShowCreate(false)}>
          <div style={modal} onClick={e => e.stopPropagation()}>
            <h3 style={{ color: '#f0c040', margin: 0 }}>{t('rooms.createRoom', '방 만들기')}</h3>

            <div>
              <label style={{ color: '#aab', fontSize: 12, display: 'block', marginBottom: 4 }}>방 이름</label>
              <input
                value={newTitle}
                onChange={e => setNewTitle(e.target.value)}
                placeholder="방 이름 (최대 30자)"
                maxLength={30}
                autoFocus
                style={inputStyle}
                onKeyDown={e => e.key === 'Enter' && handleCreate()}
              />
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', color: '#aab', fontSize: 14 }}>
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
                <label style={{ color: '#aab', fontSize: 12, display: 'block', marginBottom: 4 }}>비밀번호 (4자리 숫자)</label>
                <input
                  value={newPassword}
                  onChange={e => setNewPassword(e.target.value.replace(/\D/g, '').slice(0, 4))}
                  placeholder="0000"
                  maxLength={4}
                  style={{ ...inputStyle, letterSpacing: 8, textAlign: 'center', fontSize: 20 }}
                />
              </div>
            )}

            {createError && <p style={{ color: '#f88', margin: 0, fontSize: 13 }}>{createError}</p>}

            <button
              onClick={handleCreate}
              disabled={!newTitle.trim() || creating || (newIsPrivate && newPassword.length !== 4)}
              style={{ ...btnPrimary, opacity: (!newTitle.trim() || creating || (newIsPrivate && newPassword.length !== 4)) ? 0.5 : 1 }}
            >
              {creating ? '생성 중...' : t('rooms.create', '만들기')}
            </button>
            <button onClick={() => setShowCreate(false)} style={btnSecondary}>취소</button>
          </div>
        </div>
      )}

      {/* Private Room Password Modal */}
      {pendingJoinId && (
        <div style={overlay} onClick={() => { setPendingJoinId(null); setJoinError(null); }}>
          <div style={modal} onClick={e => e.stopPropagation()}>
            <h3 style={{ color: '#f0c040', margin: 0 }}>🔒 비밀방</h3>
            <p style={{ color: '#aab', margin: 0, fontSize: 14 }}>비밀번호를 입력하세요</p>
            <input
              value={joinPassword}
              onChange={e => setJoinPassword(e.target.value.replace(/\D/g, '').slice(0, 4))}
              placeholder="0000"
              maxLength={4}
              autoFocus
              style={{ ...inputStyle, letterSpacing: 8, textAlign: 'center', fontSize: 20 }}
              onKeyDown={e => e.key === 'Enter' && joinPassword.length === 4 && doJoin(pendingJoinId, joinPassword)}
            />
            {joinError && <p style={{ color: '#f88', margin: 0, fontSize: 13 }}>{joinError}</p>}
            <button
              onClick={() => doJoin(pendingJoinId, joinPassword)}
              disabled={joinPassword.length !== 4 || joining}
              style={{ ...btnPrimary, opacity: joinPassword.length !== 4 || joining ? 0.5 : 1 }}
            >
              {joining ? '입장 중...' : '입장하기'}
            </button>
            <button onClick={() => { setPendingJoinId(null); setJoinError(null); }} style={btnSecondary}>취소</button>
          </div>
        </div>
      )}

      {showBotGame && onCreateBotGame && (
        <div style={overlay} onClick={closeBotGameModal}>
          <div style={modal} onClick={e => e.stopPropagation()}>
            <h3 style={{ color: '#4f8', margin: 0 }}>{t('rooms.botGameSetup', '봇전 구성')}</h3>
            <p style={{ color: '#88a', fontSize: 13, margin: 0 }}>
              {t('rooms.botGameHint', '각 슬롯의 봇 유형을 고르면 바로 관전용 봇전을 시작합니다.')}
            </p>

            {selectedBotTypes.map((botType, index) => (
              <div key={`bot-slot-${index}`}>
                <label style={{ color: '#aab', fontSize: 12, display: 'block', marginBottom: 4 }}>
                  {t('rooms.botSlot', { n: index + 1, defaultValue: `플레이어 ${index + 1} 봇` })}
                </label>
                <select
                  value={botType}
                  onChange={e => handleBotTypeChange(index, e.target.value)}
                  style={inputStyle}
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
              <p style={{ color: '#88a', margin: 0, fontSize: 13 }}>
                {t('rooms.loadingBotTypes', '봇 목록을 불러오는 중...')}
              </p>
            )}

            {!loadingBotTypes && botAgents.length === 0 && (
              <p style={{ color: '#f66', margin: 0, fontSize: 13 }}>
                {t('rooms.noBotTypes', '사용 가능한 봇이 없습니다.')}
              </p>
            )}

            {botGameError && <p style={{ color: '#f66', margin: 0, fontSize: 13 }}>{botGameError}</p>}

            <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
              <button
                onClick={handleCreateBotGameConfirm}
                disabled={creatingBotGame || loadingBotTypes || botAgents.length === 0}
                style={{
                  ...btnPrimary,
                  flex: 1,
                  opacity: creatingBotGame || loadingBotTypes || botAgents.length === 0 ? 0.6 : 1,
                  cursor: creatingBotGame || loadingBotTypes || botAgents.length === 0 ? 'not-allowed' : 'pointer',
                }}
              >
                {creatingBotGame
                  ? t('rooms.creatingBotGame', '봇전 생성 중...')
                  : t('rooms.startBotGame', '봇전 시작')}
              </button>
              <button onClick={closeBotGameModal} disabled={creatingBotGame} style={{ ...btnSecondary, flex: 1 }}>
                {t('newGame.cancel', '취소')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
