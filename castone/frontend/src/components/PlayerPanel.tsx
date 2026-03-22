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
  onMayorPlace?: (targetType: 'plantation' | 'building', targetIndex: number) => void;
  onMayorPickup?: (targetType: 'plantation' | 'building', targetIndex: number) => void;
  highlightLastPlantation?: boolean;
  isOffline?: boolean;
  isMe?: boolean;
  botType?: string;
}

export default function PlayerPanel({ playerId, player, isActive, phase, onMayorPlace, onMayorPickup, highlightLastPlantation, isOffline, isMe, botType }: Props) {
  const { t } = useTranslation();
  const isMayorActive = phase === 'mayor_action' && isActive;

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
        onPlace={isMayorActive ? (i) => onMayorPlace?.('plantation', i) : undefined}
        onPickup={isMayorActive ? (i) => onMayorPickup?.('plantation', i) : undefined}
        hasUnplacedColonists={player.city.colonists_unplaced > 0}
        highlightLastTile={highlightLastPlantation}
      />

      <h3 id={`player-${playerId}-city`}>{t('player.city')}</h3>
      <CityGrid
        city={player.city}
        onPlace={isMayorActive ? (i) => onMayorPlace?.('building', i) : undefined}
        onPickup={isMayorActive ? (i) => onMayorPickup?.('building', i) : undefined}
      />
    </section>
  );
}
