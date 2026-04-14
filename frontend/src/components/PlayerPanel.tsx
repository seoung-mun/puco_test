import { useTranslation } from 'react-i18next';
import type { Player } from '../types/gameState';
import IslandGrid from './IslandGrid';
import CityGrid from './CityGrid';

const GOODS = ['corn', 'indigo', 'sugar', 'tobacco', 'coffee'] as const;

interface Props {
  playerId: string;
  player: Player;
  isActive: boolean;
  highlightLastPlantation?: boolean;
  isOffline?: boolean;
  isMe?: boolean;
  botType?: string;
  isRolePicker?: boolean;
  mayorLegalIslandSlots?: number[];
  mayorLegalCitySlots?: number[];
  onMayorIslandClick?: (slotIdx: number) => void;
  onMayorCityClick?: (slotIdx: number) => void;
}

export default function PlayerPanel({ playerId, player, isActive, highlightLastPlantation, isOffline, isMe, botType, isRolePicker, mayorLegalIslandSlots, mayorLegalCitySlots, onMayorIslandClick, onMayorCityClick }: Props) {
  const { t } = useTranslation();

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
        {(player.is_governor || isRolePicker) && (
          <span className="player-panel__status-icons">
            {player.is_governor && (
              <span
                aria-label={t('player.governor')}
                className="player-panel__badge player-panel__badge--governor"
                title={t('player.governor')}
              >
                👑
              </span>
            )}
            {isRolePicker && (
              <span
                aria-label={t('player.rolePicker', { defaultValue: 'Current role picker' })}
                className="player-panel__badge player-panel__badge--role-picker"
                title={t('player.rolePicker', { defaultValue: 'Current role picker' })}
              >
                ●
              </span>
            )}
          </span>
        )}
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
        highlightLastTile={highlightLastPlantation}
        mayorLegalSlots={mayorLegalIslandSlots}
        onMayorSlotClick={onMayorIslandClick}
      />

      <h3 id={`player-${playerId}-city`}>{t('player.city')}</h3>
      <CityGrid
        city={player.city}
        mayorLegalSlots={mayorLegalCitySlots}
        onMayorSlotClick={onMayorCityClick}
      />
    </section>
  );
}
