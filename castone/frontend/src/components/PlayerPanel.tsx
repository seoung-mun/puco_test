import { useTranslation } from 'react-i18next';
import type { PhaseType, Player } from '../types/gameState';
import IslandGrid from './IslandGrid';
import CityGrid from './CityGrid';

const GOODS = ['corn', 'indigo', 'sugar', 'tobacco', 'coffee'] as const;

interface Props {
  playerId: string;
  player: Player;
  isActive: boolean;
  phase: PhaseType;
  // 토글 모드 (인간 플레이어)
  mayorPending?: number[] | null;
  mayorLocalUnplaced?: number;
  onMayorToggle?: (slotIdx: number, delta: 1 | -1) => void;
  // 순차 모드 (봇 대기 or 멀티 상대방)
  onMayorPlace?: (amount: number) => void;
  mayorSlotIdx?: number | null;
  highlightLastPlantation?: boolean;
  isOffline?: boolean;
  isMe?: boolean;
  botType?: string;
}

export default function PlayerPanel({ playerId, player, isActive, phase, mayorPending, mayorLocalUnplaced = 0, onMayorToggle, onMayorPlace, mayorSlotIdx, highlightLastPlantation, isOffline, isMe, botType }: Props) {
  const { t } = useTranslation();
  const isMayorActive = phase === 'mayor_action' && isActive;
  const isMayorToggle = isMayorActive && mayorPending !== null && mayorPending !== undefined;

  const sectionStyle: React.CSSProperties = {
    ...(isOffline ? { opacity: 0.45, filter: 'grayscale(0.7)' } : {}),
    ...(isMe ? { background: '#0d1a30' } : {}),
  };

  return (
    <section
      id={`player-${playerId}`}
      className={`panel player-panel ${isActive ? 'active-player' : ''}`}
      style={Object.keys(sectionStyle).length ? sectionStyle : undefined}
    >
      <h2>
        {isOffline && <span title="offline" style={{ marginRight: 6 }}>📵</span>}
        <span style={isMe ? { textDecoration: 'underline', textDecorationColor: '#f0c040' } : undefined}>
          {player.display_name}
        </span>
        {botType === 'gemini'  && <span style={{ marginLeft: 4, fontSize: '0.85em' }}>🤖</span>}
        {botType === 'scoring' && <span style={{ marginLeft: 4, fontSize: '0.85em' }}>⚙️</span>}
        {botType === 'random'  && <span style={{ marginLeft: 4, fontSize: '0.85em' }}>🎲</span>}
        {player.is_governor && ' 👑'}
        {isActive && ` ◀ ${t('player.active')}`}
      </h2>

      <div className="player-stats">
        <div className="player-stats__left">
          <span>💰 {player.doubloons}</span>
          <span>⭐ {player.vp_chips} VP</span>
        </div>
        <span className={`player-stats__colonists${player.city.colonists_unplaced > 0 ? ' player-stats__colonists--active' : ''}`}>
          👤 {player.city.colonists_unplaced}
        </span>
      </div>

      <h3>{t('player.goods')}</h3>
      <table>
        <tbody>
          <tr>
            {GOODS.map(g => <th key={g}>{t(`goods.${g}`)}</th>)}
            <th>{t('goods.total')}</th>
          </tr>
          <tr>
            {GOODS.map(g => <td key={g}>{player.goods[g]}</td>)}
            <td>{player.goods.d_total}</td>
          </tr>
        </tbody>
      </table>

      <h3>{t('player.production')}</h3>
      <table>
        <tbody>
          <tr>
            {GOODS.map(g => <th key={g}>{t(`goods.${g}`)}</th>)}
            <th>{t('goods.total')}</th>
          </tr>
          <tr>
            {GOODS.map(g => (
              <td key={g} className={player.production[g].can_produce ? 'can-produce' : 'no-produce'}>
                {player.production[g].amount}
              </td>
            ))}
            <td>{player.production.d_total}</td>
          </tr>
        </tbody>
      </table>

      <h3 id={`player-${playerId}-island`}>{t('player.island')}</h3>
      <IslandGrid
        island={player.island}
        // 토글 모드
        mayorPending={isMayorToggle ? (mayorPending ?? []).slice(0, 12) : null}
        mayorLocalUnplaced={isMayorToggle ? mayorLocalUnplaced : 0}
        onMayorToggle={isMayorToggle ? (i, d) => onMayorToggle?.(i, d) : undefined}
        // 순차 모드
        currentMayorSlot={isMayorActive && !isMayorToggle && mayorSlotIdx != null && mayorSlotIdx < 12 ? mayorSlotIdx : null}
        onMayorPlace={isMayorActive && !isMayorToggle ? onMayorPlace : undefined}
        hasUnplacedColonists={player.city.colonists_unplaced > 0}
        highlightLastTile={highlightLastPlantation}
      />

      <h3 id={`player-${playerId}-city`}>{t('player.city')}</h3>
      <CityGrid
        city={player.city}
        // 토글 모드
        mayorPending={isMayorToggle ? (mayorPending ?? []).slice(12, 24) : null}
        mayorLocalUnplaced={isMayorToggle ? mayorLocalUnplaced : 0}
        onMayorToggle={isMayorToggle ? (i, d) => onMayorToggle?.(12 + i, d) : undefined}
        // 순차 모드
        currentMayorSlot={isMayorActive && !isMayorToggle && mayorSlotIdx != null && mayorSlotIdx >= 12 ? mayorSlotIdx - 12 : null}
        onMayorPlace={isMayorActive && !isMayorToggle ? onMayorPlace : undefined}
      />
    </section>
  );
}
