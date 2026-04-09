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
    accentClass: 'mayor-strategy-option--captain',
    priorityBuildings: ['wharf', 'harbor', 'large_warehouse', 'small_warehouse'],
  },
  {
    actionIndex: 70,
    id: 'trade_factory_focus',
    accentClass: 'mayor-strategy-option--trade',
    priorityBuildings: ['office', 'large_market', 'small_market', 'factory'],
  },
  {
    actionIndex: 71,
    id: 'building_focus',
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

type TranslateFn = (key: string, options?: Record<string, unknown>) => string;

function collectPriorityBuildings(player: Player, strategy: StrategyConfig) {
  const preferred = new Set([...LARGE_VP_BUILDINGS, ...strategy.priorityBuildings]);
  return player.city.buildings.filter(
    (building) => preferred.has(building.name) && building.empty_slots > 0,
  );
}

function collectPriorityTargets(player: Player, strategy: StrategyConfig): string[] {
  return dedupe(collectPriorityBuildings(player, strategy).map((building) => building.name));
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

function formatLocalizedList(
  values: string[],
  prefix: 'buildings' | 'goods',
  t: TranslateFn,
): string {
  return values
    .map((value) =>
      t(`${prefix}.${value}`, {
        defaultValue: formatFallbackLabel(value),
      }),
    )
    .join(', ');
}

function getStrategyCopy(strategy: StrategyConfig, t: TranslateFn) {
  switch (strategy.id) {
    case 'captain_focus':
      return {
        title: t('actions.mayorStrategies.captainFocus.title', {
          defaultValue: 'Captain Focus',
        }),
        summary: t('actions.mayorStrategies.captainFocus.summary', {
          defaultValue: 'Wharf, harbor, warehouses, then high-value production pairs.',
        }),
      };
    case 'trade_factory_focus':
      return {
        title: t('actions.mayorStrategies.tradeFactoryFocus.title', {
          defaultValue: 'Trade / Factory',
        }),
        summary: t('actions.mayorStrategies.tradeFactoryFocus.summary', {
          defaultValue: 'Office, markets, factory, then goods that monetize quickly.',
        }),
      };
    case 'building_focus':
      return {
        title: t('actions.mayorStrategies.buildingFocus.title', {
          defaultValue: 'Building Focus',
        }),
        summary: t('actions.mayorStrategies.buildingFocus.summary', {
          defaultValue: 'University, hospice, construction hut, hacienda, then support production.',
        }),
      };
  }
}

function buildOutcomeDetails({
  player,
  t,
  priorityTargets,
  prioritySlotCount,
  productionPairs,
}: {
  player: Player;
  t: TranslateFn;
  priorityTargets: string[];
  prioritySlotCount: number;
  productionPairs: string[];
}): string[] {
  const totalUnplaced = player.city.colonists_unplaced;
  const totalOpenSlots = player.city.d_total_empty_colonist_slots;
  const assignableNow = Math.min(totalUnplaced, totalOpenSlots);
  const priorityAssigned = Math.min(assignableNow, prioritySlotCount);
  const remainingAfterPriority = Math.max(assignableNow - priorityAssigned, 0);
  const overflow = Math.max(totalUnplaced - assignableNow, 0);

  const priorityTargetLabels = formatLocalizedList(priorityTargets, 'buildings', t);
  const productionLabels = formatLocalizedList(productionPairs, 'goods', t);

  const details: string[] = [];

  if (prioritySlotCount > 0 && priorityTargets.length > 0) {
    details.push(
      t('actions.mayorOutcomePriorityDetailed', {
        defaultValue: `${priorityAssigned} of ${assignableNow} assignable colonists will first fill ${prioritySlotCount} priority slot(s): ${priorityTargetLabels}.`,
        assigned: priorityAssigned,
        assignable: assignableNow,
        slots: prioritySlotCount,
        targets: priorityTargetLabels,
      }),
    );
  } else {
    details.push(
      t('actions.mayorOutcomePriorityFallbackDetailed', {
        defaultValue: 'There are no open signature buildings for this plan, so the engine starts from the general legal placement order.',
      }),
    );
  }

  if (productionPairs.length > 0 && remainingAfterPriority > 0) {
    details.push(
      t('actions.mayorOutcomeProductionDetailed', {
        defaultValue: `Then the remaining ${remainingAfterPriority} colonist(s) will support ${productionLabels} production lines or any other legal empty slot.`,
        remaining: remainingAfterPriority,
        goods: productionLabels,
      }),
    );
  } else if (productionPairs.length > 0) {
    details.push(
      t('actions.mayorOutcomeProductionPriorityReady', {
        defaultValue: `Priority slots already consume the current assignment, with ${productionLabels} lines as the next fallback.`,
        goods: productionLabels,
      }),
    );
  } else {
    details.push(
      t('actions.mayorOutcomeProductionFallbackDetailed', {
        defaultValue:
          remainingAfterPriority > 0
            ? `The remaining ${remainingAfterPriority} colonist(s) will be placed into other legal empty slots because no open production pair is visible right now.`
            : 'No open production pair is visible right now, so this plan stays on general legal slots only.',
        remaining: remainingAfterPriority,
      }),
    );
  }

  if (overflow > 0) {
    details.push(
      t('actions.mayorOutcomeOverflowDetailed', {
        defaultValue: `Only ${assignableNow} colonist(s) can be assigned immediately because there are ${totalOpenSlots} open slot(s). ${overflow} colonist(s) may remain waiting.`,
        assignable: assignableNow,
        slots: totalOpenSlots,
        remaining: overflow,
      }),
    );
  } else {
    details.push(
      t('actions.mayorOutcomeSingleStepDetailed', {
        defaultValue: 'After you choose, the engine completes the full Mayor allocation in one step.',
      }),
    );
  }

  return details;
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
              count: player.city.colonists_unplaced,
            })}
          </span>
          <span className="badge badge-blue">
            {t('actions.mayorCapacity', {
              defaultValue: `${player.city.d_total_empty_colonist_slots} open slots`,
              count: player.city.d_total_empty_colonist_slots,
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
          const strategyCopy = getStrategyCopy(strategy, t);
          const priorityBuildings = collectPriorityBuildings(player, strategy);
          const priorityTargets = collectPriorityTargets(player, strategy);
          const prioritySlotCount = priorityBuildings.reduce(
            (sum, building) => sum + Math.max(0, building.empty_slots),
            0,
          );
          const isAvailable = (actionMask?.[strategy.actionIndex] ?? 0) === 1;
          const buttonDisabled = disabled || !isAvailable;
          const outcomeDetails = buildOutcomeDetails({
            player,
            t,
            priorityTargets,
            prioritySlotCount,
            productionPairs,
          });

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
                <span className="mayor-strategy-option__title">{strategyCopy.title}</span>
                <span className="mayor-strategy-option__index">#{strategy.actionIndex}</span>
              </div>

              <p className="mayor-strategy-option__summary">{strategyCopy.summary}</p>

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

              <div className="mayor-strategy-preview">
                <div className="mayor-strategy-preview__title">
                  {t('actions.mayorOutcomeTitle', { defaultValue: 'Predicted allocation' })}
                </div>
                <div className="mayor-strategy-preview__details">
                  {outcomeDetails.map((detail) => (
                    <p key={detail} className="mayor-strategy-preview__detail">
                      {detail}
                    </p>
                  ))}
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
