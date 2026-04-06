import { useTranslation } from 'react-i18next';
import type { CommonBoard, RoleName } from '../types/gameState';
import CargoShips from './CargoShips';
import AvailablePlantations from './AvailablePlantations';
import ColonistShip from './ColonistShip';
import TradingHouse from './TradingHouse';

interface Props {
  board: CommonBoard;
  playerNames: Record<string, string>;
  numPlayers: number;
  phase: string;
  onSelectRole?: (role: string) => void;
  onSettlePlantation?: (type: string) => void;
  canPickQuarry?: boolean;
  canUseHacienda?: boolean;
  onUseHacienda?: () => void;
  showHaciendaFollowup?: boolean;
}

const ROLE_DISPLAY_ORDER: RoleName[] = ['settler', 'mayor', 'builder', 'craftsman', 'trader', 'captain', 'prospector', 'prospector_2'];

const ROLE_COLORS: Record<RoleName, string> = {
  settler:      '#80e0a0',
  mayor:        '#e05858',
  builder:      '#c07840',
  craftsman:    '#c080e0',
  trader:       '#e0c840',
  captain:      '#60d0e0',
  prospector:   '#aaaaaa',
  prospector_2: '#888888',
};

const GOODS_CONFIG = [
  { key: 'corn',    icon: '🌽', max: 10 },
  { key: 'indigo',  icon: '🫐', max: 11 },
  { key: 'sugar',   icon: '🎋', max: 11 },
  { key: 'tobacco', icon: '🍂', max: 9  },
  { key: 'coffee',  icon: '☕', max: 9  },
] as const;

export default function CommonBoardPanel({
  board,
  playerNames,
  numPlayers,
  phase,
  onSelectRole,
  onSettlePlantation,
  canPickQuarry,
  canUseHacienda,
  onUseHacienda,
  showHaciendaFollowup,
}: Props) {
  const { t } = useTranslation();
  const isActive = (p: string | string[]) =>
    Array.isArray(p) ? p.includes(phase) : phase === p;

  return (
    <section className="panel">
      <h2>{t('board.title')}</h2>

      <div className={`board-section${isActive('role_selection') ? ' board-active' : ''}`}>
        <h3 id="section-roles">
          {t('board.roles')}
          {onSelectRole && <span style={{ fontWeight: 'normal', fontSize: '0.85em', color: '#888' }}> {t('board.clickToSelect')}</span>}
        </h3>
        <table>
          <thead>
            <tr><th>{t('board.roleCol')}</th><th>{t('board.doubloonsCol')}</th><th>{t('board.takenByCol')}</th></tr>
          </thead>
          <tbody>
            {ROLE_DISPLAY_ORDER.filter(role => role in board.roles).map(role => {
              const r = board.roles[role];
              const available = !r.taken_by && !!onSelectRole;
              return (
                <tr
                  key={role}
                  className={r.taken_by ? 'taken' : available ? 'selectable' : ''}
                  onClick={available ? () => onSelectRole(role) : undefined}
                  style={available ? { cursor: 'pointer' } : undefined}
                >
                  <td>
                    <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: ROLE_COLORS[role], marginRight: 6, verticalAlign: 'middle', flexShrink: 0 }} />
                    {t(`roles.${role}`, { defaultValue: role })}
                  </td>
                  <td>{r.doubloons_on_role > 0 ? `💰 ${r.doubloons_on_role}` : '—'}</td>
                  <td>{r.taken_by ? playerNames[r.taken_by] ?? r.taken_by : '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="common-row">
        <div className={`common-col${isActive(['mayor_distribution', 'mayor_action']) ? ' board-active' : ''}`}>
          <h3>{t('board.colonists')}</h3>
          <ColonistShip colonists={board.colonists} numPlayers={numPlayers} />
        </div>
        <div className="common-vsep" />
        <div id="section-trading-house" className={`common-col${isActive('trader_action') ? ' board-active' : ''}`}>
          <h3>{t('board.tradingHouse')}</h3>
          <TradingHouse tradingHouse={board.trading_house} />
        </div>
        <div className="common-vsep" />
        <div className={`common-col${isActive('craftsman_action') ? ' board-active' : ''}`}>
          <h3>{t('board.goodsSupply')}</h3>
          {GOODS_CONFIG.map(({ key, icon, max }) => {
            const qty = board.goods_supply[key];
            const ratio = qty / max;
            const color = qty === 0 ? '#c03030' : ratio < 0.3 ? '#c87820' : '#aaa';
            return (
              <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 }}>
                <span style={{ fontSize: 14 }}>{icon}</span>
                <div style={{ width: 48, height: 5, background: '#333', borderRadius: 3, overflow: 'hidden' }}>
                  <div style={{ width: `${(qty / max) * 100}%`, height: '100%', background: color, borderRadius: 3, transition: 'width 0.3s' }} />
                </div>
                <span style={{ fontSize: '0.85em', color, fontWeight: qty === 0 ? 'bold' : 'normal', minWidth: 18 }}>
                  {qty}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      <div className={`common-centered${isActive(['captain_action', 'captain_discard']) ? ' board-active' : ''}`}>
        <h3 id="section-cargo">{t('board.cargoShips')}</h3>
        <CargoShips ships={board.cargo_ships} />
      </div>

      <div id="section-plantations" className={`common-centered${isActive('settler_action') ? ' board-active' : ''}`}>
        <h3>
          {t('board.plantations')}
          {onSettlePlantation && <span style={{ fontWeight: 'normal', fontSize: '0.85em', color: '#ffe066' }}> {t('board.clickToPick')}</span>}
        </h3>
        {showHaciendaFollowup && (
          <p style={{ margin: '0 0 8px', fontSize: 12, color: '#ffe066' }}>
            {t('board.haciendaFollowup')}
          </p>
        )}
        <AvailablePlantations
          plantations={board.available_plantations}
          quarrySupplyRemaining={board.quarry_supply_remaining}
          onPick={onSettlePlantation}
          canPickQuarry={canPickQuarry}
          onPickQuarry={canPickQuarry ? () => onSettlePlantation?.('quarry') : undefined}
          canUseHacienda={canUseHacienda}
          onUseHacienda={onUseHacienda}
        />
      </div>

    </section>
  );
}
