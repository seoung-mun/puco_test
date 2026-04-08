import { useTranslation } from 'react-i18next';

import type { Player } from '../types/gameState';

type StrategyAction = 69 | 70 | 71;

interface Props {
  player: Player;
  actionMask?: number[];
  disabled?: boolean;
  onSelectStrategy?: (actionIndex: StrategyAction) => void;
}

interface StrategyConfig {
  actionIndex: StrategyAction;
  id: 'captain_focus' | 'trade_factory_focus' | 'building_focus';
  title: string;
  summary: string;
  accentClass: string;
  priorityBuildings: string[];
}

const LARGE_VP_BUILDINGS = ['guild_hall', 'residence', 'fortress', 'customs_house', 'city_hall'] as const;

const PRODUCTION_PAIRS: Array<{ good: string; buildings: string[] }> = [
  { good: 'coffee', buildings: ['coffee_roaster'] },
  { good: 'tobacco', buildings: ['tobacco_storage'] },
  { good: 'sugar', buildings: ['sugar_mill', 'small_sugar_mill'] },
  { good: 'indigo', buildings: ['indigo_plant', 'small_indigo_plant'] },
  { good: 'corn', buildings: [] },
];

const STRATEGIES: StrategyConfig[] = [
  {
    actionIndex: 69,
    id: 'captain_focus',
    title: 'Captain Focus',
    summary: 'Wharf, harbor, warehouses, then high-value production pairs.',
    accentClass: 'mayor-strategy-option--captain',
    priorityBuildings: ['wharf', 'harbor', 'large_warehouse', 'small_warehouse'],
  },
  {
    actionIndex: 70,
    id: 'trade_factory_focus',
    title: 'Trade / Factory',
    summary: 'Office, markets, factory, then goods that monetize quickly.',
    accentClass: 'mayor-strategy-option--trade',
    priorityBuildings: ['office', 'large_market', 'small_market', 'factory'],
  },
  {
    actionIndex: 71,
    id: 'building_focus',
    title: 'Building Focus',
    summary: 'University, hospice, construction hut, hacienda, then support production.',
    accentClass: 'mayor-strategy-option--building',
    priorityBuildings: ['university', 'hospice', 'construction_hut', 'hacienda'],
  },
];

function dedupe(values: string[]): string[] {
  return Array.from(new Set(values));
}

function formatFallbackLabel(value: string): string {
  return value
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function collectPriorityTargets(player: Player, strategy: StrategyConfig): string[] {
  const preferred = new Set([...LARGE_VP_BUILDINGS, ...strategy.priorityBuildings]);
  return dedupe(
    player.city.buildings
      .filter((building) => preferred.has(building.name) && building.empty_slots > 0)
      .map((building) => building.name),
  );
}

function collectProductionPairs(player: Player): string[] {
  const openPlantations = new Set(
    player.island.plantations
      .filter((plantation) => !plantation.colonized)
      .map((plantation) => plantation.type),
  );

  return PRODUCTION_PAIRS
    .filter(({ good, buildings }) => {
      if (!openPlantations.has(good)) {
        return false;
      }
      if (good === 'corn') {
        return true;
      }
      return player.city.buildings.some(
        (building) => buildings.includes(building.name) && building.empty_slots > 0,
      );
    })
    .map(({ good }) => good);
}

function StrategyPreview({
  title,
  values,
  fallback,
  renderValue,
}: {
  title: string;
  values: string[];
  fallback: string;
  renderValue: (value: string) => string;
}) {
  return (
    <div className="mayor-strategy-preview">
      <div className="mayor-strategy-preview__title">{title}</div>
      {values.length > 0 ? (
        <div className="mayor-strategy-preview__chips">
          {values.map((value) => (
            <span key={value} className="mayor-strategy-chip">
              {renderValue(value)}
            </span>
          ))}
        </div>
      ) : (
        <p className="mayor-strategy-preview__empty">{fallback}</p>
      )}
    </div>
  );
}

export default function MayorStrategyPanel({
  player,
  actionMask,
  disabled = false,
  onSelectStrategy,
}: Props) {
  const { t } = useTranslation();
  const productionPairs = collectProductionPairs(player);

  return (
    <div id="action-card" className="action-card mayor-strategy-card">
      <div className="action-card__header">
        <span>
          <strong>{t('roles.mayor', { defaultValue: 'Mayor' })}</strong>
          {' — '}
          {player.display_name}
        </span>
        <span className="action-card__badges">
          <span className="badge badge-gold">
            {t('actions.mayorUnplaced', {
              defaultValue: `${player.city.colonists_unplaced} colonists to assign`,
            })}
          </span>
          <span className="badge badge-blue">
            {t('actions.mayorCapacity', {
              defaultValue: `${player.city.d_total_empty_colonist_slots} open slots`,
            })}
          </span>
        </span>
      </div>

      <p className="mayor-strategy-card__intro">
        {t('actions.mayorStrategyIntro', {
          defaultValue: 'Pick one strategy. The engine applies the full Mayor allocation in a single action.',
        })}
      </p>

      <div className="mayor-strategy-grid">
        {STRATEGIES.map((strategy) => {
          const priorityTargets = collectPriorityTargets(player, strategy);
          const isAvailable = (actionMask?.[strategy.actionIndex] ?? 0) === 1;
          const buttonDisabled = disabled || !isAvailable;

          return (
            <button
              key={strategy.actionIndex}
              type="button"
              className={`mayor-strategy-option ${strategy.accentClass}`}
              disabled={buttonDisabled}
              onClick={() => {
                if (!buttonDisabled) {
                  onSelectStrategy?.(strategy.actionIndex);
                }
              }}
            >
              <div className="mayor-strategy-option__top">
                <span className="mayor-strategy-option__title">{strategy.title}</span>
                <span className="mayor-strategy-option__index">#{strategy.actionIndex}</span>
              </div>

              <p className="mayor-strategy-option__summary">{strategy.summary}</p>

              <StrategyPreview
                title={t('actions.mayorPriorityNow', { defaultValue: 'Priority targets now' })}
                values={priorityTargets}
                fallback={t('actions.mayorPriorityFallback', {
                  defaultValue: 'No matching empty building right now. The engine will fall back to general priorities.',
                })}
                renderValue={(buildingName) =>
                  t(`buildings.${buildingName}`, {
                    defaultValue: formatFallbackLabel(buildingName),
                  })
                }
              />

              <StrategyPreview
                title={t('actions.mayorProductionPairs', { defaultValue: 'Production follow-up' })}
                values={productionPairs}
                fallback={t('actions.mayorProductionFallback', {
                  defaultValue: 'No open production pair detected. Remaining colonists will fill any legal slots.',
                })}
                renderValue={(good) =>
                  t(`goods.${good}`, {
                    defaultValue: formatFallbackLabel(good),
                  })
                }
              />
            </button>
          );
        })}
      </div>
    </div>
  );
}
