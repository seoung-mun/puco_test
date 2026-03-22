import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { City } from '../types/gameState';

interface Props {
  city: City;
  onPlace?: (buildingIndex: number) => void;
  onPickup?: (buildingIndex: number) => void;
}

const BUILDING_CONFIG: Record<string, { icon: string; color: string }> = {
  small_indigo_plant: { icon: '🫐', color: '#3a4fa0' },
  indigo_plant:       { icon: '🫐', color: '#2a3f90' },
  small_sugar_mill:   { icon: '🎋', color: '#a0a060' },
  sugar_mill:         { icon: '🎋', color: '#808040' },
  small_market:       { icon: '🏪', color: '#a06020' },
  large_market:       { icon: '🏪', color: '#804010' },
  hacienda:           { icon: '🏡', color: '#6a8a3a' },
  construction_hut:   { icon: '🔨', color: '#7a5a2a' },
  small_warehouse:    { icon: '📦', color: '#5a4a2a' },
  large_warehouse:    { icon: '📦', color: '#3a2a1a' },
  tobacco_storage:    { icon: '🍂', color: '#8b5e3c' },
  coffee_roaster:     { icon: '☕', color: '#3d1f00' },
  hospice:            { icon: '⚕️', color: '#2a6a6a' },
  office:             { icon: '📜', color: '#4a4a8a' },
  factory:            { icon: '⚙️', color: '#5a5a5a' },
  university:         { icon: '🎓', color: '#4a2a8a' },
  harbor:             { icon: '⚓', color: '#1a3a6a' },
  wharf:              { icon: '🚢', color: '#1a2a5a' },
  guild_hall:         { icon: '🏛️', color: '#6a4a00' },
  residence:          { icon: '🏠', color: '#5a3a1a' },
  fortress:           { icon: '🏰', color: '#3a3a3a' },
  customs_house:      { icon: '🏦', color: '#2a4a2a' },
  city_hall:          { icon: '🏛️', color: '#8a6a00' },
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

const COLS = 3;
const TILE_W = 80;
const TILE_H = 84;
const GAP = 8;
const PAD = 20;
const LARGE_TILE_H = 2 * TILE_H + GAP;

interface SlotEntry {
  building: City['buildings'][0] | null;
  originalIndex: number;
  col: number;
  unitRow: number;
  large: boolean;
}

function buildColumnLayout(buildings: City['buildings'], totalSpaces: number): SlotEntry[] {
  const rowsPerCol = Math.ceil(totalSpaces / COLS);
  const colFill = [0, 0, 0];
  const entries: SlotEntry[] = [];

  buildings.forEach((b, origIdx) => {
    const large = b.vp === 4;
    const size = large ? 2 : 1;
    for (let col = 0; col < COLS; col++) {
      if (colFill[col] + size <= rowsPerCol) {
        entries.push({ building: b, originalIndex: origIdx, col, unitRow: colFill[col], large });
        colFill[col] += size;
        break;
      }
    }
  });

  for (let col = 0; col < COLS; col++) {
    let unitRow = colFill[col];
    while (unitRow < rowsPerCol) {
      entries.push({ building: null, originalIndex: -1, col, unitRow, large: false });
      unitRow += 1;
    }
  }

  return entries;
}

function BuildingTile({ building, x, y, tileH, buildingIndex, hasUnplaced, onPlace, onPickup, onHover, onLeave }: {
  building: City['buildings'][0];
  x: number; y: number; tileH: number;
  buildingIndex: number;
  hasUnplaced: boolean;
  onPlace?: (index: number) => void;
  onPickup?: (index: number) => void;
  onHover?: (name: string, e: React.MouseEvent) => void;
  onLeave?: () => void;
}) {
  const { t } = useTranslation();
  const cfg = BUILDING_CONFIG[building.name] ?? { icon: '🏗️', color: '#555' };
  const label = t(`buildings.${building.name}`, { defaultValue: building.name.replace(/_/g, ' ') });
  const [line1, line2] = wrapLabel(label);
  const midY = y + tileH / 2;

  return (
    <g
      onMouseEnter={onHover ? e => onHover(building.name, e) : undefined}
      onMouseLeave={onLeave}
    >
      <rect x={x} y={y} width={TILE_W} height={tileH} rx={6}
        fill={cfg.color}
        stroke={building.is_active ? '#ffe066' : '#ffffff33'}
        strokeWidth={building.is_active ? 2.5 : 1}
      />
      {building.is_active && (
        <rect x={x} y={y} width={TILE_W} height={tileH} rx={6}
          fill="none" stroke="#ffe066" strokeWidth={1} opacity={0.4}
          transform={`translate(-2,-2) scale(${(TILE_W + 4) / TILE_W}, ${(tileH + 4) / tileH})`}
        />
      )}
      <text x={x + TILE_W / 2} y={midY - 16}
        textAnchor="middle" dominantBaseline="middle"
        fontSize={18} style={{ userSelect: 'none' }}>
        {cfg.icon}
      </text>
      <text x={x + TILE_W / 2} y={midY - 2}
        textAnchor="middle" fontSize={8} fill="#ffffffcc" fontWeight="bold"
        style={{ userSelect: 'none' }}>
        {line1}
      </text>
      {line2 && (
        <text x={x + TILE_W / 2} y={midY + 9}
          textAnchor="middle" fontSize={8} fill="#ffffffcc" fontWeight="bold"
          style={{ userSelect: 'none' }}>
          {line2}
        </text>
      )}
      <g>
        {Array.from({ length: building.max_colonists }).map((_, i) => {
          const slotSize = 10;
          const totalW = building.max_colonists * slotSize + (building.max_colonists - 1) * 3;
          const slotX = x + (TILE_W - totalW) / 2 + i * (slotSize + 3);
          const slotY = y + tileH - 16;
          const filled = i < building.current_colonists;
          const canPlace = !filled && !!onPlace && hasUnplaced;
          const canPickup = filled && !!onPickup;
          const interactive = canPlace || canPickup;
          return (
            <g key={i}
              onClick={canPlace ? () => onPlace!(buildingIndex) : canPickup ? () => onPickup!(buildingIndex) : undefined}
              style={{ cursor: interactive ? 'pointer' : 'default' }}
            >
              <circle cx={slotX + slotSize / 2} cy={slotY + slotSize / 2} r={slotSize / 2}
                fill={filled ? '#f5deb3' : canPlace ? '#ffffff33' : '#00000055'}
                stroke={filled ? '#8b4513' : canPlace ? '#ffffffaa' : '#ffffff44'}
                strokeWidth={1}
              />
              {filled && (
                <text x={slotX + slotSize / 2} y={slotY + slotSize / 2}
                  textAnchor="middle" dominantBaseline="middle"
                  fontSize={7} style={{ userSelect: 'none' }}>👤</text>
              )}
              {canPlace && (
                <text x={slotX + slotSize / 2} y={slotY + slotSize / 2}
                  textAnchor="middle" dominantBaseline="middle"
                  fontSize={8} fill="#ffffffbb" fontWeight="bold" style={{ userSelect: 'none' }}>+</text>
              )}
            </g>
          );
        })}
      </g>
      <rect x={x + TILE_W - 18} y={y + 4} width={14} height={14} rx={3} fill="#ffe066" />
      <text x={x + TILE_W - 11} y={y + 11}
        textAnchor="middle" dominantBaseline="middle"
        fontSize={9} fill="#333" fontWeight="bold" style={{ userSelect: 'none' }}>
        {building.vp}
      </text>
    </g>
  );
}

function EmptySlot({ x, y, tileH }: { x: number; y: number; tileH: number }) {
  return (
    <rect x={x} y={y} width={TILE_W} height={tileH} rx={6}
      fill="#1a2a1a" stroke="#2a4a2a" strokeWidth={1} strokeDasharray="4 3"
    />
  );
}

export default function CityGrid({ city, onPlace, onPickup }: Props) {
  const { t } = useTranslation();
  const [tooltip, setTooltip] = useState<{ text: string; x: number; y: number } | null>(null);
  const rowsPerCol = Math.ceil(city.total_spaces / COLS);
  const layout = buildColumnLayout(city.buildings, city.total_spaces);
  const svgW = PAD * 2 + COLS * TILE_W + (COLS - 1) * GAP;
  const svgH = PAD * 2 + rowsPerCol * TILE_H + (rowsPerCol - 1) * GAP;
  const hasUnplaced = city.colonists_unplaced > 0;

  function handleHover(name: string, e: React.MouseEvent) {
    const tip = t(`buildingAdvantages.${name}.tip`, { defaultValue: '' });
    if (tip) setTooltip({ text: tip, x: e.clientX, y: e.clientY });
  }

  return (
    <div style={{ position: 'relative' }}>
      <svg width={svgW} height={svgH} viewBox={`0 0 ${svgW} ${svgH}`}>
        <rect x={4} y={4} width={svgW - 8} height={svgH - 8} rx={10}
          fill="#1e2a1e" stroke="#3a5a3a" strokeWidth={2}
        />
        {layout.map((entry, i) => {
          const x = PAD + entry.col * (TILE_W + GAP);
          const y = PAD + entry.unitRow * (TILE_H + GAP);
          const tileH = entry.large ? LARGE_TILE_H : TILE_H;
          return entry.building
            ? <BuildingTile key={i} building={entry.building} x={x} y={y} tileH={tileH}
                buildingIndex={entry.originalIndex} hasUnplaced={hasUnplaced}
                onPlace={onPlace} onPickup={onPickup}
                onHover={handleHover} onLeave={() => setTooltip(null)} />
            : <EmptySlot key={i} x={x} y={y} tileH={tileH} />;
        })}
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
      <p style={{ margin: '2px 0 0', fontSize: 12, color: '#888' }}>
        {city.d_used_spaces}/{city.total_spaces} · discount: {city.d_quarry_discount}
        {city.colonists_unplaced > 0 && ` · ${city.colonists_unplaced} unplaced colonists`}
      </p>
    </div>
  );
}
