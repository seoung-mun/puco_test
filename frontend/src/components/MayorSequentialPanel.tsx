import { useTranslation } from 'react-i18next';
import type { Player, Meta } from '../types/gameState';

interface Props {
  player: Player;
  meta: Meta;
  actionMask?: number[];
  disabled?: boolean;
  onPlaceColonist?: (actionIndex: number, canonicalId?: string) => void;
}

/** Legacy fallback bases (used only when meta.mayor_*_actions are absent). */
const ISLAND_BASE = 120;
const CITY_BASE = 140;

function slotLabel(type: 'island' | 'city', idx: number, player: Player, t: (key: string, opts?: Record<string, unknown>) => string): string {
  if (type === 'island') {
    const plantation = player.island.plantations[idx];
    if (plantation) {
      return t(`plantations.${plantation.type}`, { defaultValue: plantation.type });
    }
    return `Island ${idx}`;
  }
  const building = player.city.buildings[idx];
  if (building) {
    return t(`buildings.${building.name}`, { defaultValue: building.name.replace(/_/g, ' ') });
  }
  return `City ${idx}`;
}

export default function MayorSequentialPanel({
  player,
  meta,
  actionMask,
  disabled = false,
  onPlaceColonist,
}: Props) {
  const { t } = useTranslation();

  const islandActions = meta.mayor_island_actions;
  const cityActions = meta.mayor_city_actions;
  const legalIsland = meta.mayor_legal_island_slots ?? [];
  const legalCity = meta.mayor_legal_city_slots ?? [];
  const remaining = meta.mayor_remaining_colonists ?? player.city.colonists_unplaced;

  return (
    <div id="action-card" className="action-card mayor-sequential-card">
      <div className="action-card__header">
        <span>
          <strong>{t('roles.mayor', { defaultValue: 'Mayor' })}</strong>
          {' — '}
          {player.display_name}
        </span>
        <span className="action-card__badges">
          <span className="badge badge-gold">
            {remaining} colonist{remaining !== 1 ? 's' : ''} to place
          </span>
        </span>
      </div>

      <p className="mayor-sequential-card__intro">
        Choose an empty slot to place a colonist. Each placement is final and cannot be undone.
      </p>

      {(islandActions ? islandActions.length > 0 : legalIsland.length > 0) && (
        <div className="mayor-sequential-section">
          <h4 className="mayor-sequential-section__title">Island</h4>
          <div className="mayor-sequential-slots">
            {islandActions
              ? islandActions.map((entry) => {
                  const isLegal = (actionMask?.[entry.engine_action_index] ?? 0) === 1;
                  return (
                    <button
                      key={`island-${entry.display_position}`}
                      type="button"
                      className="mayor-slot-btn mayor-slot-btn--island"
                      disabled={disabled || !isLegal}
                      onClick={() => isLegal && onPlaceColonist?.(entry.engine_action_index, entry.canonical_id)}
                    >
                      {slotLabel('island', entry.display_position, player, t)}
                    </button>
                  );
                })
              : legalIsland.map((idx) => {
                  const actionIdx = ISLAND_BASE + idx;
                  const isLegal = (actionMask?.[actionIdx] ?? 0) === 1;
                  return (
                    <button
                      key={`island-${idx}`}
                      type="button"
                      className="mayor-slot-btn mayor-slot-btn--island"
                      disabled={disabled || !isLegal}
                      onClick={() => isLegal && onPlaceColonist?.(actionIdx)}
                    >
                      {slotLabel('island', idx, player, t)}
                    </button>
                  );
                })}
          </div>
        </div>
      )}

      {(cityActions ? cityActions.length > 0 : legalCity.length > 0) && (
        <div className="mayor-sequential-section">
          <h4 className="mayor-sequential-section__title">City</h4>
          <div className="mayor-sequential-slots">
            {cityActions
              ? cityActions.map((entry) => {
                  const building = player.city.buildings[entry.display_position];
                  const isLegal = (actionMask?.[entry.engine_action_index] ?? 0) === 1;
                  const capacityInfo = building
                    ? `(${building.current_colonists}/${building.max_colonists})`
                    : '';
                  return (
                    <button
                      key={`city-${entry.display_position}`}
                      type="button"
                      className="mayor-slot-btn mayor-slot-btn--city"
                      disabled={disabled || !isLegal}
                      onClick={() => isLegal && onPlaceColonist?.(entry.engine_action_index, entry.canonical_id)}
                    >
                      {slotLabel('city', entry.display_position, player, t)} {capacityInfo}
                    </button>
                  );
                })
              : legalCity.map((idx) => {
                  const building = player.city.buildings[idx];
                  const engineSlot = building?.engine_slot_idx ?? idx;
                  const actionIdx = CITY_BASE + engineSlot;
                  const isLegal = (actionMask?.[actionIdx] ?? 0) === 1;
                  const capacityInfo = building
                    ? `(${building.current_colonists}/${building.max_colonists})`
                    : '';
                  return (
                    <button
                      key={`city-${idx}`}
                      type="button"
                      className="mayor-slot-btn mayor-slot-btn--city"
                      disabled={disabled || !isLegal}
                      onClick={() => isLegal && onPlaceColonist?.(actionIdx)}
                    >
                      {slotLabel('city', idx, player, t)} {capacityInfo}
                    </button>
                  );
                })}
          </div>
        </div>
      )}

      {((islandActions ? islandActions.length === 0 : legalIsland.length === 0)
        && (cityActions ? cityActions.length === 0 : legalCity.length === 0)) && (
        <p className="mayor-sequential-card__empty">No legal slots available.</p>
      )}
    </div>
  );
}
