import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { City } from '../types/gameState';

interface Props {
  city: City;
  mayorLegalSlots?: number[];
  onMayorSlotClick?: (slotIdx: number) => void;
}

const BUILDING_CONFIG: Record<string, { icon: string; color: string }> = {
  small_indigo_plant: { icon: '🫐', color: '#4a6984' },
  indigo_plant:       { icon: '🫐', color: '#2b435a' },
  small_sugar_mill:   { icon: '🎋', color: '#868e65' },
  sugar_mill:         { icon: '🎋', color: '#535e38' },
  small_market:       { icon: '🏪', color: '#e9c46a' },
  large_market:       { icon: '🏪', color: '#e76f51' },
  hacienda:           { icon: '🏡', color: '#708238' },
  construction_hut:   { icon: '🔨', color: '#cb997e' },
  small_warehouse:    { icon: '📦', color: '#b7b7a4' },
  large_warehouse:    { icon: '📦', color: '#a3b19b' },
  tobacco_storage:    { icon: '🍂', color: '#ad6b38' },
  coffee_roaster:     { icon: '☕', color: '#563c2b' },
  hospice:            { icon: '⚕️', color: '#6f8695' },
  office:             { icon: '📜', color: '#8ea8bd' },
  factory:            { icon: '⚙️', color: '#9a8c98' },
  university:         { icon: '🎓', color: '#8ea8bd' },
  harbor:             { icon: '⚓', color: '#4f5d75' },
  wharf:              { icon: '🚢', color: '#606c38' },
  guild_hall:         { icon: '🏛️', color: '#dda15e' },
  residence:          { icon: '🏠', color: '#bc6c25' },
  fortress:           { icon: '🏰', color: '#6b705c' },
  customs_house:      { icon: '🏦', color: '#606c38' },
  city_hall:          { icon: '🏛️', color: '#dda15e' },
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

function BuildingTile({ building, x, y, tileH, onHover, onLeave, mayorLegal, onMayorClick }: {
  building: City['buildings'][0];
  x: number; y: number; tileH: number;
  onHover?: (name: string, e: React.MouseEvent) => void;
  onLeave?: () => void;
  mayorLegal?: boolean;
  onMayorClick?: () => void;
}) {
  const { t } = useTranslation();
  const cfg = BUILDING_CONFIG[building.name] ?? { icon: '🏗️', color: '#9fb7ad' };
  const label = t(`buildings.${building.name}`, { defaultValue: building.name.replace(/_/g, ' ') });
  const [line1, line2] = wrapLabel(label);
  const midY = y + tileH / 2;

  const strokeColor = mayorLegal ? '#4f9f4a' : building.is_active ? '#f4b63f' : 'rgba(255,255,255,0.62)';
  const strokeW = mayorLegal ? 3 : building.is_active ? 2.5 : 1;

  return (
    <g
      onMouseEnter={onHover ? e => onHover(building.name, e) : undefined}
      onMouseLeave={onLeave}
      onClick={mayorLegal && onMayorClick ? onMayorClick : undefined}
      style={mayorLegal ? { cursor: 'pointer' } : undefined}
    >
      <rect x={x} y={y} width={TILE_W} height={tileH} rx={6}
        fill={cfg.color}
        stroke={strokeColor}
        strokeWidth={strokeW}
      />
      {building.is_active && (
        <rect x={x} y={y} width={TILE_W} height={tileH} rx={6}
          fill="none" stroke="#f4b63f" strokeWidth={1} opacity={0.55}
          transform={`translate(-2,-2) scale(${(TILE_W + 4) / TILE_W}, ${(tileH + 4) / tileH})`}
        />
      )}
      <text x={x + TILE_W / 2} y={midY - 16}
        textAnchor="middle" dominantBaseline="middle"
        fontSize={18} style={{ userSelect: 'none' }}>
        {cfg.icon}
      </text>
      <text x={x + TILE_W / 2} y={midY - 2}
        textAnchor="middle" fontSize={8} fill="#173b3a" fontWeight="bold"
        style={{ userSelect: 'none' }}>
        {line1}
      </text>
      {line2 && (
        <text x={x + TILE_W / 2} y={midY + 9}
          textAnchor="middle" fontSize={8} fill="#173b3a" fontWeight="bold"
          style={{ userSelect: 'none' }}>
          {line2}
        </text>
      )}
      <g>
        {Array.from({ length: building.max_colonists }).map((_, i) => {
          const slotSize = 15;
          const totalW = building.max_colonists * slotSize + (building.max_colonists - 1) * 4;
          const slotX = x + (TILE_W - totalW) / 2 + i * (slotSize + 4);
          const slotY = y + tileH - slotSize - 5;
          const serverFilled = i < building.current_colonists;
          return (
            <g key={i}>
              <circle cx={slotX + slotSize / 2} cy={slotY + slotSize / 2} r={slotSize / 2}
                fill={serverFilled ? '#fff2cc' : 'rgba(255,255,255,0.46)'}
                stroke={serverFilled ? '#d49b34' : 'rgba(255,255,255,0.58)'}
                strokeWidth={1}
              />
              {serverFilled && (
                <text x={slotX + slotSize / 2} y={slotY + slotSize / 2}
                  textAnchor="middle" dominantBaseline="middle"
                  fontSize={7} style={{ userSelect: 'none' }}>👤</text>
              )}
            </g>
          );
        })}
      </g>
      <rect x={x + TILE_W - 18} y={y + 4} width={14} height={14} rx={3} fill="#fff2cc" />
      <text x={x + TILE_W - 11} y={y + 11}
        textAnchor="middle" dominantBaseline="middle"
        fontSize={9} fill="#173b3a" fontWeight="bold" style={{ userSelect: 'none' }}>
        {building.vp}
      </text>
    </g>
  );
}

function EmptySlot({ x, y, tileH }: { x: number; y: number; tileH: number }) {
  return (
    <rect x={x} y={y} width={TILE_W} height={tileH} rx={6}
      fill="rgba(255,255,255,0.44)" stroke="rgba(110,85,66,0.3)" strokeWidth={1} strokeDasharray="4 3"
    />
  );
}

export default function CityGrid({ city, mayorLegalSlots, onMayorSlotClick }: Props) {
  const { t } = useTranslation();
  const [tooltip, setTooltip] = useState<{ text: string; x: number; y: number } | null>(null);
  const rowsPerCol = Math.ceil(city.total_spaces / COLS);
  const layout = buildColumnLayout(city.buildings, city.total_spaces);
  const svgW = PAD * 2 + COLS * TILE_W + (COLS - 1) * GAP;
  const svgH = PAD * 2 + rowsPerCol * TILE_H + (rowsPerCol - 1) * GAP;

  function handleHover(name: string, e: React.MouseEvent) {
    const tip = t(`buildingAdvantages.${name}.tip`, { defaultValue: '' });
    if (tip) setTooltip({ text: tip, x: e.clientX, y: e.clientY });
  }

  return (
    <div style={{ position: 'relative' }}>
      <svg width={svgW} height={svgH} viewBox={`0 0 ${svgW} ${svgH}`}>
        <rect x={4} y={4} width={svgW - 8} height={svgH - 8} rx={10}
          fill="#f3ede2" stroke="rgba(110,85,66,0.24)" strokeWidth={2}
        />
        {layout.map((entry, i) => {
          const x = PAD + entry.col * (TILE_W + GAP);
          const y = PAD + entry.unitRow * (TILE_H + GAP);
          const tileH = entry.large ? LARGE_TILE_H : TILE_H;
          const legalSet = mayorLegalSlots ? new Set(mayorLegalSlots) : null;
          const isLegal = legalSet != null && entry.building != null && legalSet.has(entry.originalIndex);
          return entry.building
            ? <BuildingTile key={i} building={entry.building} x={x} y={y} tileH={tileH}
                onHover={handleHover} onLeave={() => setTooltip(null)}
                mayorLegal={isLegal}
                onMayorClick={isLegal && onMayorSlotClick ? () => onMayorSlotClick(entry.building!.engine_slot_idx) : undefined} />
            : <EmptySlot key={i} x={x} y={y} tileH={tileH} />;
        })}
      </svg>
      {tooltip && (
        <div className="city-grid-tooltip" style={{
          position: 'fixed', left: tooltip.x + 14, top: tooltip.y + 10, zIndex: 999,
          padding: '7px 12px', fontSize: 13, maxWidth: 300,
          pointerEvents: 'none', lineHeight: 1.5,
        }}>
          {tooltip.text}
        </div>
      )}
      <p className="resort-muted" style={{ margin: '2px 0 0', fontSize: 12 }}>
        {city.d_used_spaces}/{city.total_spaces} · discount: {city.d_quarry_discount}
        {city.colonists_unplaced > 0 && ` · ${city.colonists_unplaced} unplaced colonists`}
      </p>
    </div>
  );
}
