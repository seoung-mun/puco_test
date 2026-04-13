import { useTranslation } from 'react-i18next';
import i18n from '../i18n';
import type { FinalScoreSummary, GameState, LobbyPlayer } from '../types/gameState';
import MetaPanel from './MetaPanel';
import CommonBoardPanel from './CommonBoardPanel';
import PlayerPanel from './PlayerPanel';
import SanJuan from './SanJuan';
import AdminPanel from './AdminPanel';
import PlayerAdvantages from './PlayerAdvantages';
import HistoryPanel from './HistoryPanel';
import EndGamePanel from './EndGamePanel';

type Advantage = { label: string; tooltip: string; cls: string };
type BuildConfirm = { name: string; cost: number; vp: number } | null;
type PopupEntry = { id: number; text: string; isRoundEnd: boolean; role: string | null };

type Props = {
  backend: string;
  state: GameState;
  error: string | null;
  saving: boolean;
  passing: boolean;
  buildConfirm: BuildConfirm;
  pendingSettlement: string | null;
  roundFlash: number | null;
  discardProtected: string[];
  discardSingleExtra: string | null;
  finalScores: FinalScoreSummary | null;
  popups: PopupEntry[];
  isAdmin: boolean;
  isSpectator: boolean;
  isMultiplayer: boolean;
  myName: string | null;
  lobbyPlayers: LobbyPlayer[];
  isMyTurn: boolean;
  isBotTurn: boolean;
  isBlocked: boolean;
  interactionLocked: boolean;
  canPass: boolean;
  onStateLoaded: (state: GameState) => void;
  onGoToRoomsPreservingAuth: () => void;
  onLogoutToLogin: () => void;
  onExitSpectator: () => void;
  onDismissError: () => void;
  onClearPopups: () => void;
  onConfirmBuild: (buildingName: string) => void;
  onCancelBuildConfirm: () => void;
  onConfirmSettlement: (useHospice: boolean) => void;
  onSelectRole: (role: string) => Promise<void>;
  onSettlePlantation: (type: string) => void;
  onUseHacienda: () => Promise<void>;
  onPlaceMayorColonist: (actionIndex: number) => Promise<void>;
  onPassAction: () => Promise<void>;
  onSellGood: (good: string) => Promise<void>;
  onCraftsmanPrivilege: (good: string) => Promise<void>;
  onLoadShip: (good: string, shipIndex: number | null, useWharf: boolean) => Promise<void>;
  onCaptainPass: () => Promise<void>;
  onToggleDiscardProtected: (good: string) => void;
  onSetDiscardSingleExtra: (good: string | null) => void;
  onDoDiscardGoods: () => Promise<void>;
  onRequestBuild: (name: string, cost: number, vp: number) => void;
  onReturnToRooms: () => void;
};

const ROLE_PRIVILEGE_CLASSES: Record<string, string> = {
  settler: 'adv-settler', mayor: 'adv-mayor', builder: 'adv-builder',
  craftsman: 'adv-craftsman', trader: 'adv-trader', captain: 'adv-captain',
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

const GOOD_VALUE: Record<string, number> = {
  coffee: 0, tobacco: 1, corn: 2, sugar: 3, indigo: 4,
};

const channelActionIndex = {
  sell: (good: string): number => 39 + (GOOD_VALUE[good] ?? 0),
  loadShip: (good: string, shipIndex: number): number => 44 + shipIndex * 5 + (GOOD_VALUE[good] ?? 0),
  loadWharf: (good: string): number => 59 + (GOOD_VALUE[good] ?? 0),
};

export default function GameScreen({
  backend,
  state,
  error,
  saving,
  passing,
  buildConfirm,
  pendingSettlement,
  roundFlash,
  discardProtected,
  discardSingleExtra,
  finalScores,
  popups,
  isAdmin,
  isSpectator,
  isMultiplayer,
  myName,
  lobbyPlayers,
  isMyTurn,
  isBotTurn,
  isBlocked,
  interactionLocked,
  canPass,
  onStateLoaded,
  onGoToRoomsPreservingAuth,
  onLogoutToLogin,
  onExitSpectator,
  onDismissError,
  onClearPopups,
  onConfirmBuild,
  onCancelBuildConfirm,
  onConfirmSettlement,
  onSelectRole,
  onSettlePlantation,
  onUseHacienda,
  onPlaceMayorColonist,
  onPassAction,
  onSellGood,
  onCraftsmanPrivilege,
  onLoadShip,
  onCaptainPass,
  onToggleDiscardProtected,
  onSetDiscardSingleExtra,
  onDoDiscardGoods,
  onRequestBuild,
  onReturnToRooms,
}: Props) {
  const { t } = useTranslation();

  const playerNames = Object.fromEntries(
    Object.entries(state.players).map(([id, p]) => [id, p.display_name]),
  );

  const canSelectRole = state.meta.phase === 'role_selection' && !state.meta.end_game_triggered && isMyTurn;
  const isMayorPhase = state.meta.phase === 'mayor_action';
  const isSettlerPhase = state.meta.phase === 'settler_action';
  const isBuilderPhase = state.meta.phase === 'builder_action';
  const isCraftsmanPrivilege = state.meta.phase === 'craftsman_action'
    && state.common_board.roles.craftsman?.taken_by === state.meta.active_player;
  const isTraderPhase = state.meta.phase === 'trader_action';
  const isCaptainPhase = state.meta.phase === 'captain_action';
  const isCaptainDiscard = state.meta.phase === 'captain_discard';
  const captainRolePicker = state.common_board.roles.captain?.taken_by ?? null;

  const settlerRolePicker = state.common_board.roles.settler?.taken_by ?? null;
  const builderRolePicker = state.common_board.roles.builder?.taken_by ?? null;
  const activePlayer = state.players[state.meta.active_player];
  const builderInfo = isBuilderPhase && activePlayer ? {
    player: activePlayer.display_name,
    activeQuarries: activePlayer.island.d_active_quarries,
    isRolePicker: state.meta.active_player === builderRolePicker,
    doubloons: activePlayer.doubloons,
    cityEmptySpaces: activePlayer.city.d_empty_spaces,
    ownedBuildings: activePlayer.city.buildings.map((b) => b.name),
  } : undefined;

  const canPickQuarry = isSettlerPhase
    && (state.meta.active_player === settlerRolePicker
      || activePlayer?.city.buildings.some((b) => b.name === 'construction_hut' && b.is_active) === true)
    && state.common_board.quarry_supply_remaining > 0;

  const canUseHacienda = isSettlerPhase
    && activePlayer?.city.buildings.some((b) => b.name === 'hacienda' && b.is_active) === true
    && !activePlayer?.hacienda_used_this_phase
    && Object.values(state.common_board.available_plantations.draw_pile).reduce((a, b) => a + b, 0) > 0
    && (activePlayer?.island.d_empty_spaces ?? 0) > 0;

  const advantages: Advantage[] = [];
  if (activePlayer) {
    if (state.meta.active_role) {
      const roleKey = state.meta.active_role as string;
      if (state.common_board.roles[state.meta.active_role]?.taken_by === state.meta.active_player) {
        const cls = ROLE_PRIVILEGE_CLASSES[roleKey];
        if (cls) {
          advantages.push({
            label: t(`rolePrivileges.${roleKey}.label`),
            tooltip: t(`rolePrivileges.${roleKey}.tip`),
            cls,
          });
        }
      }
    }
    const phase = state.meta.phase;
    const showAll = phase === 'role_selection';
    for (const building of activePlayer.city.buildings) {
      const meta = BUILDING_ADVANTAGE_META[building.name];
      if (building.is_active && meta && (showAll || meta.phases.includes(phase))) {
        advantages.push({
          label: t(`buildingAdvantages.${building.name}.label`),
          tooltip: t(`buildingAdvantages.${building.name}.tip`),
          cls: meta.cls,
        });
      }
    }

    if (isBuilderPhase) {
      advantages.push({ label: `💰 ${activePlayer.doubloons}`, cls: 'adv-info', tooltip: t('player.goods') });
      advantages.push({ label: `⛏ ${activePlayer.island.d_active_quarries}`, cls: 'adv-info', tooltip: t('plantations.quarry') });
    }
  }

  const activeMayorPlayer = isMayorPhase ? state.players[state.meta.active_player] : null;
  const showMayorPanel = isMayorPhase && activeMayorPlayer != null && !isBotTurn;

  return (
    <div className="app">
      {popups.length > 0 && (
        <div
          style={{ position: 'fixed', top: 72, left: '50%', transform: 'translateX(-50%)', zIndex: 300, display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'center', cursor: 'pointer' }}
          onClick={onClearPopups}
        >
          {popups.map((p) => (
            <div
              key={p.id}
              className={`action-popup${p.isRoundEnd ? ' action-popup--round-end' : p.role ? ` action-popup--${p.role}` : ''}`}
              dangerouslySetInnerHTML={{ __html: p.text }}
            />
          ))}
        </div>
      )}
      {state.meta.bot_thinking && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, background: '#1a1218', borderBottom: '2px solid #7a3a7a', padding: '8px 20px', textAlign: 'center', color: '#c080e0', zIndex: 400, fontSize: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10 }}>
          <span style={{ display: 'inline-block', animation: 'spin 1s linear infinite', fontSize: 18 }}>⚙</span>
          {t('game.geminiThinking')}
        </div>
      )}
      {!isMyTurn && (
        <div style={{ position: 'fixed', bottom: 0, left: 0, right: 0, background: '#1a1030', borderTop: '2px solid #2a2a5a', padding: '10px 20px', textAlign: 'center', color: '#aab', zIndex: 200, fontSize: 14 }}>
          {t('game.waitingTurn', { name: state.players[state.decision.player]?.display_name ?? state.decision.player })}
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
        <h1 style={{ margin: 0 }}>Puerto Rico</h1>
        <button className="btn-new-game" onClick={onGoToRoomsPreservingAuth}>🎮 {t('newGame.title')}</button>
        <button
          className="btn-new-game"
          style={{ background: '#444', fontSize: '0.8em', padding: '4px 10px' }}
          onClick={() => {
            const cycle: Record<string, string> = { ko: 'en', en: 'it', it: 'ko' };
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
          <button onClick={onExitSpectator} style={{ background: 'none', border: '1px solid #334', borderRadius: 4, color: '#667', cursor: 'pointer', padding: '2px 8px', fontSize: 12 }}>
            {t('home.logout', '로그아웃')}
          </button>
        )}
        {isMultiplayer && !isSpectator && (
          <button onClick={onLogoutToLogin} style={{ background: 'none', border: '1px solid #334', borderRadius: 4, color: '#667', cursor: 'pointer', padding: '2px 8px', fontSize: 12 }}>
            {t('home.logout', '로그아웃')}
          </button>
        )}
      </div>

      {isAdmin && <AdminPanel backend={backend} onStateLoaded={onStateLoaded} />}

      {buildConfirm && (() => {
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
          <div className="new-game-overlay" onClick={(e) => { if (e.target === e.currentTarget) onCancelBuildConfirm(); }}>
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
                  onClick={() => onConfirmBuild(name)}
                >
                  {t('newGame.confirm', { defaultValue: '✓ Conferma' })}
                </button>
                <button
                  style={{ flex: 1, padding: '10px 0', background: '#1a1a3a', border: '1px solid #3a3a6a', borderRadius: 8, color: '#aab', fontSize: 15, cursor: 'pointer' }}
                  onClick={onCancelBuildConfirm}
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
        <EndGamePanel
          state={state}
          scores={state.result_summary ?? finalScores}
          onReturnToRooms={onReturnToRooms}
        />
      )}
      {error && (
        <div className="error-banner">
          <span>Error: {error}</span>
          <button onClick={onDismissError} className="error-dismiss">✕</button>
        </div>
      )}

      {pendingSettlement && !isBlocked && (
        <div className="hospice-overlay">
          <div className="hospice-dialog">
            <p dangerouslySetInnerHTML={{ __html: t('hospiceDialog.message', {
              plantation: t(`plantations.${pendingSettlement}`, { defaultValue: pendingSettlement.replace(/_/g, ' ') }),
            }) }}
            />
            <div className="hospice-dialog__btns">
              <button className="hospice-yes" onClick={() => onConfirmSettlement(true)}>
                {t('hospiceDialog.yes')}
              </button>
              <button className="hospice-no" onClick={() => onConfirmSettlement(false)}>
                {t('hospiceDialog.no')}
              </button>
            </div>
          </div>
        </div>
      )}

      {isCraftsmanPrivilege && !isBlocked && (() => {
        const privilegeGoods = (['corn', 'indigo', 'sugar', 'tobacco', 'coffee'] as const)
          .filter((g) => activePlayer && activePlayer.production[g].amount > 0 && state.common_board.goods_supply[g] > 0);
        return (
          <div className="hospice-overlay">
            <div className="hospice-dialog">
              <p dangerouslySetInnerHTML={{ __html: t('craftsmanDialog.message') }} />
              <div className="hospice-dialog__btns">
                {privilegeGoods.map((g) => (
                  <button key={g} className="hospice-yes" onClick={() => onCraftsmanPrivilege(g)}>
                    {t(`goods.${g}`)}
                  </button>
                ))}
                <button className="hospice-no" onClick={onPassAction}>
                  {t('craftsmanDialog.skip')}
                </button>
              </div>
            </div>
          </div>
        );
      })()}

      <div className="sticky-bar">
        <div className="sticky-bar__main">
          {isSpectator && (
            <span style={{ display: 'flex', alignItems: 'center', gap: 8, marginRight: 8, flexShrink: 0 }}>
              <span style={{ background: '#1a3a2a', border: '1px solid #2a5a3a', borderRadius: 4, color: '#4f8', padding: '2px 8px', fontSize: 12, whiteSpace: 'nowrap' }}>
                👁 {t('rooms.spectating', '관전 중')}
              </span>
              <button onClick={onExitSpectator} style={{ background: 'none', border: '1px solid #334', borderRadius: 4, color: '#667', cursor: 'pointer', padding: '2px 8px', fontSize: 12, whiteSpace: 'nowrap' }}>
                {t('home.logout', '로그아웃')}
              </button>
            </span>
          )}
          {isMultiplayer && !isSpectator && myName && (
            <span style={{ display: 'flex', alignItems: 'center', gap: 8, marginRight: 8, flexShrink: 0 }}>
              <span style={{ color: '#f0c040', fontWeight: 'bold', fontSize: 13, whiteSpace: 'nowrap' }}>
                👤 {myName}
              </span>
              <button onClick={onLogoutToLogin} style={{ background: 'none', border: '1px solid #334', borderRadius: 4, color: '#667', cursor: 'pointer', padding: '2px 8px', fontSize: 12, whiteSpace: 'nowrap' }}>
                {t('home.logout', '로그아웃')}
              </button>
            </span>
          )}
          <MetaPanel meta={state.meta} playerNames={playerNames} botPlayers={state.bot_players} />
          <div className="sticky-bar__nav">
            {[
              { id: 'section-roles', icon: '🎭', label: t('nav.roles') },
              { id: 'section-cargo', icon: '🚢', label: t('nav.cargo') },
              { id: `player-${state.meta.active_player}-island`, icon: '🏝️', label: t('nav.island') },
              { id: `player-${state.meta.active_player}-city`, icon: '🏛️', label: t('nav.city') },
              { id: 'san-juan', icon: '🏪', label: t('nav.sanJuan') },
            ].map(({ id, icon, label }) => (
              <button
                key={id}
                className="nav-btn"
                title={label}
                onClick={() => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'center' })}
              >
                <span>{icon}</span>
                <span className="nav-btn__label">{label}</span>
              </button>
            ))}
            <button
              className="nav-btn nav-btn--focus"
              title={t('nav.focus')}
              onClick={() => {
                const phase = state.meta.phase;
                const player = state.meta.active_player;
                let targetId: string;
                switch (phase) {
                  case 'role_selection':    targetId = 'common-board'; break;
                  case 'settler_action':    targetId = 'section-plantations'; break;
                  case 'mayor_action':      targetId = 'action-card'; break;
                  case 'builder_action':    targetId = 'san-juan'; break;
                  case 'craftsman_action':  targetId = `player-${player}`; break;
                  case 'trader_action':
                  case 'captain_action':
                  case 'captain_discard':   targetId = 'action-card'; break;
                  default:                  targetId = 'common-board';
                }
                const el = document.getElementById(targetId);
                if (el) el.scrollIntoView({ behavior: 'smooth', block: targetId === 'action-card' ? 'end' : 'center' });
              }}
            >
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
              <button onClick={onPassAction} disabled={passing || interactionLocked || !canPass} className="pass-btn">
                {passing ? t('actions.advancing') : t('actions.next', { phase: t(`phases.${state.meta.phase}`, { defaultValue: state.meta.phase.replace(/_/g, ' ') }) })}
              </button>
            )}
          </div>
        </div>
      </div>

      <div id="common-board" className="layout-top">
        <CommonBoardPanel
          board={state.common_board}
          playerNames={playerNames}
          numPlayers={state.meta.num_players}
          phase={state.meta.phase}
          onSelectRole={canSelectRole && !interactionLocked ? onSelectRole : undefined}
          onSettlePlantation={isSettlerPhase && isMyTurn && !interactionLocked ? onSettlePlantation : undefined}
          canPickQuarry={isMyTurn && canPickQuarry && !interactionLocked}
          canUseHacienda={isMyTurn && canUseHacienda && !interactionLocked}
          onUseHacienda={isMyTurn && canUseHacienda && !interactionLocked ? onUseHacienda : undefined}
          showHaciendaFollowup={isSettlerPhase && isMyTurn && (activePlayer?.hacienda_used_this_phase ?? false)}
        />
      </div>

      {/* Mayor: 그리드 타일 직접 클릭으로 일꾼 배치 (MayorSequentialPanel 제거) */}

      {!isBlocked && (isTraderPhase || isCaptainPhase || isCaptainDiscard) && (() => {
        if (isTraderPhase) {
          const BASE_PRICES: Record<string, number> = { corn: 0, indigo: 1, sugar: 2, tobacco: 3, coffee: 4 };
          const traderRolePicker = state.common_board.roles.trader?.taken_by ?? null;
          const isRolePicker = state.meta.active_player === traderRolePicker;
          const hasSmallMarket = activePlayer?.city.buildings.some((b) => b.name === 'small_market' && b.is_active) ?? false;
          const hasLargeMarket = activePlayer?.city.buildings.some((b) => b.name === 'large_market' && b.is_active) ?? false;
          const hasOffice = activePlayer?.city.buildings.some((b) => b.name === 'office' && b.is_active) ?? false;
          const goodsInHouse = new Set(state.common_board.trading_house.goods as string[]);
          const isHouseFull = state.common_board.trading_house.d_is_full;
          const goods = (['corn', 'indigo', 'sugar', 'tobacco', 'coffee'] as const).map((g) => {
            const qty = activePlayer?.goods[g] ?? 0;
            const base = BASE_PRICES[g];
            const bonus = (hasSmallMarket ? 1 : 0) + (hasLargeMarket ? 2 : 0) + (isRolePicker ? 1 : 0);
            const total = base + bonus;
            const inHouse = goodsInHouse.has(g);
            const actionIndex = channelActionIndex.sell(g);
            const canSell = qty > 0
              && !isHouseFull
              && (!inHouse || hasOffice)
              && (state.action_mask?.[actionIndex] ?? 0) === 1;
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
                    <tr><th>{t('trader.good')}</th><th>{t('trader.qty')}</th><th>{t('trader.base')}</th><th>{t('trader.bonus')}</th><th>{t('trader.total')}</th><th /></tr>
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
                            disabled={!canSell || saving}
                            onClick={() => onSellGood(g)}
                          >
                            {t('trader.sell')}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <div className="action-card__footer">
                <button className="hospice-no" onClick={onPassAction} disabled={passing}>
                  {t('trader.pass')}
                </button>
              </div>
            </div>
          );
        }

        if (isCaptainPhase) {
          const ships = state.common_board.cargo_ships;
          const validShipsForGood = (good: string): number[] => {
            const assigned = ships.findIndex((s) => s.good === good);
            if (assigned !== -1) return ships[assigned].d_is_full ? [] : [assigned];
            return ships.map((s, i) => s.d_is_empty ? i : -1).filter((i) => i !== -1);
          };
          const hasWharf = activePlayer?.city.buildings.some((b) => b.name === 'wharf' && b.is_active) ?? false;
          const wharfUsed = activePlayer?.wharf_used_this_phase ?? true;
          const isRolePicker = state.meta.active_player === captainRolePicker;
          const firstLoadDone = activePlayer?.captain_first_load_done ?? true;
          const goodRows = (['corn', 'indigo', 'sugar', 'tobacco', 'coffee'] as const)
            .map((g) => ({ g, qty: activePlayer?.goods[g] ?? 0, validShips: validShipsForGood(g) }))
            .filter(({ qty }) => qty > 0);
          const canLoadAny = goodRows.some(({ validShips }) => validShips.length > 0)
            || (hasWharf && !wharfUsed && (activePlayer?.goods.d_total ?? 0) > 0);

          return (
            <div id="action-card" className="action-card">
              <div className="action-card__header">
                <span><strong>{t('captain.title')}</strong> — {activePlayer?.display_name}</span>
                <span className="action-card__badges">
                  {isRolePicker && !firstLoadDone && <span className="badge badge-gold">{t('captain.privilegeBadge')}</span>}
                  {activePlayer?.city.buildings.some((b) => b.name === 'harbor' && b.is_active) && <span className="badge badge-blue">{t('captain.harbor')}</span>}
                </span>
              </div>
              {goodRows.length === 0 && <p className="action-card__empty">{t('captain.noGoods')}</p>}
              {goodRows.map(({ g, qty, validShips }) => (
                <div key={g} className="captain-good-row">
                  <span className="captain-good-name">{t(`goods.${g}`)} ×{qty}</span>
                  <div className="captain-ship-btns">
                    {validShips.map((idx) => {
                      const ship = ships[idx];
                      const toLoad = Math.min(qty, ship.d_remaining_space);
                      return (
                        <button key={idx} className="hospice-yes captain-ship-btn" onClick={() => onLoadShip(g, idx, false)}>
                          {t('captain.shipBtn', { idx: idx + 1, filled: ship.d_filled, cap: ship.capacity, qty: toLoad })}
                        </button>
                      );
                    })}
                    {validShips.length === 0 && !hasWharf && <span style={{ color: '#888' }}>{t('captain.noValidShip')}</span>}
                    {hasWharf && !wharfUsed && (
                      <button className="hospice-yes captain-ship-btn captain-wharf-btn" onClick={() => onLoadShip(g, null, true)}>
                        {t('captain.wharfBtn', { qty })}
                      </button>
                    )}
                  </div>
                </div>
              ))}
              <div className="action-card__footer">
                <button className="hospice-no" onClick={onCaptainPass} disabled={canLoadAny}>
                  {canLoadAny ? t('captain.mustLoad') : t('captain.pass')}
                </button>
              </div>
            </div>
          );
        }

        const hasLargeWh = activePlayer?.city.buildings.some((b) => b.name === 'large_warehouse' && b.is_active) ?? false;
        const hasSmallWh = activePlayer?.city.buildings.some((b) => b.name === 'small_warehouse' && b.is_active) ?? false;
        const maxProtected = (hasLargeWh ? 2 : 0) + (hasSmallWh ? 1 : 0);
        const ownedGoods = (['corn', 'indigo', 'sugar', 'tobacco', 'coffee'] as const)
          .map((g) => ({ g, qty: activePlayer?.goods[g] ?? 0 }))
          .filter(({ qty }) => qty > 0);
        const kept = ownedGoods.map(({ g, qty }) => {
          if (discardProtected.includes(g)) return { g, discard: 0 };
          if (discardSingleExtra === g) return { g, discard: qty - Math.min(1, qty) };
          return { g, discard: qty };
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
                          <input
                            type="checkbox"
                            checked={discardProtected.includes(g)}
                            disabled={!discardProtected.includes(g) && discardProtected.length >= maxProtected}
                            onChange={() => onToggleDiscardProtected(g)}
                          />
                        </td>
                      )}
                      <td>
                        <input
                          type="radio"
                          name="single_extra"
                          checked={discardSingleExtra === g}
                          disabled={discardProtected.includes(g)}
                          onChange={() => onSetDiscardSingleExtra(g)}
                        />
                      </td>
                      <td style={{ fontWeight: 'bold' }}>{discard > 0 ? `${discard} ✗` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <div className="action-card__footer">
              <button className="hospice-yes" onClick={onDoDiscardGoods}>
                {t('discard.confirm')}
              </button>
            </div>
          </div>
        );
      })()}

      <div className="layout-players">
        {state.meta.player_order.map((id) => (
          <PlayerPanel
            key={id}
            playerId={id}
            player={state.players[id]}
            isActive={id === state.meta.active_player}
            highlightLastPlantation={
              isSettlerPhase && id === state.meta.active_player
              && (state.players[id]?.hacienda_used_this_phase ?? false)
            }
            isOffline={isMultiplayer
              ? lobbyPlayers.find((lp) => lp.name === state.players[id]?.display_name)?.connected === false
              : undefined}
            isMe={isMultiplayer ? state.players[id]?.display_name === myName : undefined}
            botType={state.bot_players ? state.bot_players[id] : undefined}
            mayorLegalIslandSlots={
              showMayorPanel && id === state.meta.active_player
                ? state.meta.mayor_legal_island_slots
                : undefined
            }
            mayorLegalCitySlots={
              showMayorPanel && id === state.meta.active_player
                ? state.meta.mayor_legal_city_slots
                : undefined
            }
            onMayorIslandClick={
              showMayorPanel && id === state.meta.active_player && isMyTurn && !interactionLocked
                ? (slotIdx) => onPlaceMayorColonist(120 + slotIdx)
                : undefined
            }
            onMayorCityClick={
              showMayorPanel && id === state.meta.active_player && isMyTurn && !interactionLocked
                ? (slotIdx) => onPlaceMayorColonist(140 + slotIdx)
                : undefined
            }
          />
        ))}
      </div>

      <section id="san-juan" className={`panel layout-sanjuan${state.meta.phase === 'builder_action' ? ' board-active' : ''}`}>
        <h2>{t('sanJuan.title')}</h2>
        <div style={{ display: 'flex', gap: '24px', alignItems: 'flex-start' }}>
          <SanJuan
            buildings={state.common_board.available_buildings}
            builderInfo={builderInfo}
            onBuild={isBuilderPhase && isMyTurn && !interactionLocked ? onRequestBuild : undefined}
          />
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
              {(['small_indigo_plant', 'indigo_plant', 'small_sugar_mill', 'sugar_mill', 'tobacco_storage', 'coffee_roaster', 'small_market', 'large_market', 'hacienda', 'construction_hut', 'small_warehouse', 'large_warehouse', 'hospice', 'office', 'factory', 'university', 'harbor', 'wharf', 'guild_hall', 'residence', 'fortress', 'customs_house', 'city_hall'] as const)
                .filter((name) => state.common_board.available_buildings[name]?.copies_remaining > 0)
                .map((name) => {
                  const b = state.common_board.available_buildings[name];
                  return (
                    <tr key={name}>
                      <td style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {t(`buildings.${name}`, { defaultValue: name.replace(/_/g, ' ') })}
                      </td>
                      <td>{b.cost}</td>
                      <td>{b.vp}</td>
                      <td>{b.max_colonists}</td>
                      <td>{b.copies_remaining}</td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <h2>{t('history.title')}</h2>
        <HistoryPanel history={state.history ?? []} />
      </section>
    </div>
  );
}
