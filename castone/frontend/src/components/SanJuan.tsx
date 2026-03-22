import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { CommonBoard } from '../types/gameState';

interface BuilderInfo {
  player: string;
  activeQuarries: number;
  isRolePicker: boolean;
  doubloons: number;
  cityEmptySpaces: number;
  ownedBuildings: string[];
}

interface Props {
  buildings: CommonBoard['available_buildings'];
  builderInfo?: BuilderInfo;
  onBuild?: (name: string, cost: number, vp: number) => void;
}

function effectiveCost(b: CommonBoard['available_buildings'][string], info: BuilderInfo): number {
  const quarryDiscount = Math.min(info.activeQuarries, b.vp);
  const privilege = info.isRolePicker ? 1 : 0;
  return Math.max(0, b.cost - quarryDiscount - privilege);
}

function canBuild(name: string, b: CommonBoard['available_buildings'][string], info: BuilderInfo): boolean {
  if (b.copies_remaining === 0) return false;
  if (info.ownedBuildings.includes(name)) return false;
  if (info.doubloons < effectiveCost(b, info)) return false;
  const spacesNeeded = b.vp === 4 ? 2 : 1;
  if (info.cityEmptySpaces < spacesNeeded) return false;
  return true;
}

const BUILDING_CONFIG: Record<string, { icon: string; color?: string }> = {
  small_indigo_plant: { icon: '🫐', color: '#3a4fa0' },
  indigo_plant:       { icon: '🫐', color: '#2a3f90' },
  small_sugar_mill:   { icon: '🎋', color: '#a0a060' },
  sugar_mill:         { icon: '🎋', color: '#808040' },
  tobacco_storage:    { icon: '🍂', color: '#8b5e3c' },
  coffee_roaster:     { icon: '☕', color: '#3d1f00' },
  small_market:       { icon: '🏪' },
  large_market:       { icon: '🏪' },
  hacienda:           { icon: '🏡' },
  construction_hut:   { icon: '🔨' },
  small_warehouse:    { icon: '📦' },
  large_warehouse:    { icon: '📦' },
  hospice:            { icon: '⚕️' },
  office:             { icon: '📜' },
  factory:            { icon: '⚙️' },
  university:         { icon: '🎓' },
  harbor:             { icon: '⚓' },
  wharf:              { icon: '🚢' },
  guild_hall:         { icon: '🏛️' },
  residence:          { icon: '🏠' },
  fortress:           { icon: '🏰' },
  customs_house:      { icon: '🏦' },
  city_hall:          { icon: '🏛️' },
};

function wrapLabel(label: string): [string, string] {
  const words = label.split(' ');
  if (words.length === 1) return [label, ''];
  const total = label.length;
  let best = 1;
  let bestDiff = Infinity;
  for (let i = 1; i < words.length; i++) {
    const diff = Math.abs(words.slice(0, i).join(' ').length - total / 2);
    if (diff < bestDiff) { bestDiff = diff; best = i; }
  }
  return [words.slice(0, best).join(' '), words.slice(best).join(' ')];
}

function buildingColor(name: string, cost: number): string {
  const cfg = BUILDING_CONFIG[name];
  if (cfg?.color) return cfg.color;
  // Blue gradient: cost 1 (mid-light) → cost 10 (mid-dark), reduced contrast
  const t = Math.min(1, Math.max(0, (cost - 1) / 9));
  const r = Math.round(90 - t * 55);
  const g = Math.round(145 - t * 80);
  const b = Math.round(195 - t * 85);
  return `rgb(${r},${g},${b})`;
}

// Cols 0-2: normal buildings (6 rows)
const NORMAL_GRID: (string | null)[][] = [
  ['small_indigo_plant', 'indigo_plant',    'tobacco_storage'],
  ['small_sugar_mill',   'sugar_mill',      'coffee_roaster' ],
  ['small_market',       'hospice',         'factory'        ],
  ['hacienda',           'office',          'university'     ],
  ['construction_hut',   'large_market',    'harbor'         ],
  ['small_warehouse',    'large_warehouse', 'wharf'          ],
];

// Cols 3-4: large buildings (double height, 1 city space each)
const LARGE_COLS: string[][] = [
  ['guild_hall', 'residence', 'fortress'],  // col 3
  ['customs_house', 'city_hall'],           // col 4
];

// Max VP per column — determines max quarry discount for that column
const COL_MAX_VP = [1, 2, 3, 4, 4];

const TILE_W = 152;
const TILE_H = 92;
const GAP = 8;
const PAD = 16;
const LARGE_TILE_H = 2 * TILE_H + GAP; // aligns exactly with 2 normal rows

function BuildingTile({ name, x, y, tileH, b, builderOverlay, onBuild, onHover, onLeave }: {
  name: string; x: number; y: number; tileH: number;
  b: CommonBoard['available_buildings'][string] | undefined;
  builderOverlay?: { buildable: boolean; cost: number };
  onBuild?: (name: string, cost: number, vp: number) => void;
  onHover?: (name: string, e: React.MouseEvent) => void;
  onLeave?: () => void;
}) {
  const { t } = useTranslation();
  const cfg = BUILDING_CONFIG[name] ?? { icon: '🏗️' };
  const color = buildingColor(name, b?.cost ?? 5);
  const label = t(`buildings.${name}`, { defaultValue: name.replace(/_/g, ' ') });
  const [line1, line2] = wrapLabel(label);
  const soldOut = !b || b.copies_remaining === 0;
  const notAffordable = !soldOut && builderOverlay != null && !builderOverlay.buildable;
  const midY = y + tileH / 2;
  const clickable = builderOverlay?.buildable && !!onBuild;

  // soldOut: very faded (can't buy at all — no stock)
  // notAffordable: slightly dimmed (stock exists, but can't build right now)
  const opacity = soldOut ? 0.2 : notAffordable ? 0.85 : 1;

  // Cost badge: gold when sold out or outside builder phase, green=buildable, red=can't afford
  const costBadgeFill = soldOut || !builderOverlay
    ? '#c8a832'
    : builderOverlay.buildable ? '#4caf50' : '#b03030';

  return (
    <g opacity={opacity}
      onClick={clickable ? () => onBuild!(name, builderOverlay!.cost, b!.vp) : undefined}
      style={{ cursor: clickable ? 'pointer' : 'default' }}
      onMouseEnter={onHover ? e => onHover(name, e) : undefined}
      onMouseLeave={onLeave}>
      <rect x={x} y={y} width={TILE_W} height={tileH} rx={6}
        fill={color}
        stroke={clickable ? '#ffe066' : '#ffffff22'}
        strokeWidth={clickable ? 2 : 1} />
      {soldOut && (
        <rect x={x} y={y} width={TILE_W} height={tileH} rx={6} fill="#00000066" />
      )}
      <text x={x + TILE_W / 2} y={midY - 19}
        textAnchor="middle" dominantBaseline="middle"
        fontSize={18} style={{ userSelect: 'none' }}>
        {cfg.icon}
      </text>
      <text x={x + TILE_W / 2} y={midY + 2}
        textAnchor="middle" fontSize={11} fill="#ffffff" fontWeight="bold" stroke="#00000066" strokeWidth={0.4} paintOrder="stroke"
        style={{ userSelect: 'none' }}>
        {line1}
      </text>
      {line2 && (
        <text x={x + TILE_W / 2} y={midY + 15}
          textAnchor="middle" fontSize={11} fill="#ffffff" fontWeight="bold" stroke="#00000066" strokeWidth={0.4} paintOrder="stroke"
          style={{ userSelect: 'none' }}>
          {line2}
        </text>
      )}
      {b && (
        <>
          {/* Cost badge: show effective cost during builder phase */}
          <rect x={x + 4} y={y + tileH - 23} width={34} height={20} rx={4}
            fill={costBadgeFill} />
          <text x={x + 21} y={y + tileH - 13}
            textAnchor="middle" dominantBaseline="middle"
            fontSize={11} fill="#fff" fontWeight="bold" style={{ userSelect: 'none' }}>
            💰{builderOverlay ? builderOverlay.cost : b.cost}
          </text>
          <rect x={x + TILE_W - 38} y={y + tileH - 23} width={34} height={20} rx={4} fill="#ffe066" />
          <text x={x + TILE_W - 21} y={y + tileH - 13}
            textAnchor="middle" dominantBaseline="middle"
            fontSize={11} fill="#333" fontWeight="bold" style={{ userSelect: 'none' }}>
            ⭐{b.vp}
          </text>
          {b.copies_remaining > 1 && (
            <>
              <circle cx={x + TILE_W - 13} cy={y + 13} r={11} fill="#ffffff33" stroke="#ffffff55" strokeWidth={1} />
              <text x={x + TILE_W - 13} y={y + 13}
                textAnchor="middle" dominantBaseline="middle"
                fontSize={10} fill="#fff" fontWeight="bold" style={{ userSelect: 'none' }}>
                ×{b.copies_remaining}
              </text>
            </>
          )}
          {Array.from({ length: b.max_colonists }).map((_, si) => (
            <circle key={si} cx={x + 12 + si * 15} cy={y + 13} r={6}
              fill="#00000055" stroke="#ffffff44" strokeWidth={1} />
          ))}
        </>
      )}
    </g>
  );
}

export default function SanJuan({ buildings, builderInfo, onBuild }: Props) {
  const { t } = useTranslation();
  const [tooltip, setTooltip] = useState<{ text: string; x: number; y: number } | null>(null);
  const totalCols = 5;

  function handleHover(name: string, e: React.MouseEvent) {
    const tip = t(`buildingAdvantages.${name}.tip`, { defaultValue: '' });
    if (tip) setTooltip({ text: tip, x: e.clientX, y: e.clientY });
  }
  const numRows = NORMAL_GRID.length;
  const svgW = PAD * 2 + totalCols * TILE_W + (totalCols - 1) * GAP;
  const svgH = PAD * 2 + numRows * TILE_H + (numRows - 1) * GAP;

  return (
    <div style={{ flexShrink: 0, width: svgW, position: 'relative' }}>
      {/* Quarry discount headers — shown only during builder phase */}
      {builderInfo && (
        <div style={{ display: 'flex', paddingLeft: PAD, paddingRight: PAD, marginBottom: 4 }}>
          {COL_MAX_VP.map((maxVp, colIdx) => (
            <div key={colIdx} style={{
              width: TILE_W,
              flexShrink: 0,
              marginRight: colIdx < COL_MAX_VP.length - 1 ? GAP : 0,
              textAlign: 'center',
              fontSize: 11,
              fontWeight: 'bold',
              color: '#c8a832',
            }}>
              {t('sanJuan.quarryMax', { n: maxVp })}
            </div>
          ))}
        </div>
      )}

      <svg width={svgW} height={svgH} viewBox={`0 0 ${svgW} ${svgH}`}>
        <rect x={4} y={4} width={svgW - 8} height={svgH - 8} rx={10}
          fill="#1e1e2e" stroke="#4a4a6a" strokeWidth={2} />

        {/* Normal buildings: cols 0-2 */}
        {NORMAL_GRID.map((row, rowIdx) =>
          row.map((name, colIdx) => {
            if (!name) return null;
            const x = PAD + colIdx * (TILE_W + GAP);
            const y = PAD + rowIdx * (TILE_H + GAP);
            const b = buildings[name as keyof typeof buildings];
            const bInfo = builderInfo && b ? { buildable: canBuild(name, b, builderInfo), cost: effectiveCost(b, builderInfo) } : undefined;
            return <BuildingTile key={name} name={name} x={x} y={y} tileH={TILE_H} b={b}
              builderOverlay={bInfo} onBuild={onBuild}
              onHover={handleHover} onLeave={() => setTooltip(null)} />;
          })
        )}

        {/* Large buildings: cols 3-4, double height */}
        {LARGE_COLS.map((col, largColIdx) =>
          col.map((name, tileIdx) => {
            const colIdx = 3 + largColIdx;
            const x = PAD + colIdx * (TILE_W + GAP);
            const y = PAD + tileIdx * (LARGE_TILE_H + GAP);
            const b = buildings[name as keyof typeof buildings];
            const bInfo = builderInfo && b ? { buildable: canBuild(name, b, builderInfo), cost: effectiveCost(b, builderInfo) } : undefined;
            return <BuildingTile key={name} name={name} x={x} y={y} tileH={LARGE_TILE_H} b={b}
              builderOverlay={bInfo} onBuild={onBuild}
              onHover={handleHover} onLeave={() => setTooltip(null)} />;
          })
        )}
      </svg>
      {tooltip && (
        <div style={{
          position: 'fixed', left: tooltip.x + 14, top: tooltip.y + 10, zIndex: 999,
          background: '#12192e', border: '1px solid #3a4a7a', borderRadius: 8,
          padding: '7px 12px', color: '#ccd8f0', fontSize: 13, maxWidth: 300,
          boxShadow: '0 4px 18px rgba(0,0,0,0.8)', pointerEvents: 'none', lineHeight: 1.5,
        }}>
          {tooltip.text}
        </div>
      )}
    </div>
  );
}
