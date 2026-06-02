import { useTranslation } from 'react-i18next';
import type { Island } from '../types/gameState';

interface Props {
  island: Island;
  highlightLastTile?: boolean;
  mayorLegalSlots?: number[];
  onMayorSlotClick?: (slotIdx: number) => void;
}

const TILE_CONFIG: Record<string, { bg: string; icon: string }> = {
  corn:    { bg: '#f4c85f', icon: '🌽' },
  indigo:  { bg: '#36a8c7', icon: '🫐' },
  sugar:   { bg: '#b7d978', icon: '🎋' },
  tobacco: { bg: '#d7925b', icon: '🍂' },
  coffee:  { bg: '#8b6b4d', icon: '☕' },
  quarry:  { bg: '#93a696', icon: '⛏️' },
};

const COLS = 3;
const TILE_W = 72;
const TILE_H = 64;
const GAP = 8;

export default function IslandGrid({ island, highlightLastTile, mayorLegalSlots, onMayorSlotClick }: Props) {
  const { t } = useTranslation();
  const totalSlots = island.total_spaces;
  const slots: (typeof island.plantations[0] | null)[] = [...island.plantations];
  while (slots.length < totalSlots) slots.push(null);

  const numRows = Math.ceil(totalSlots / COLS);
  const gridW = COLS * TILE_W + (COLS - 1) * GAP;
  const gridH = numRows * TILE_H + (numRows - 1) * GAP;
  const PAD = 28;
  const svgW = gridW + PAD * 2;
  const svgH = gridH + PAD * 2 + 16;

  return (
    <div>
      <svg width={svgW} height={svgH} viewBox={`0 0 ${svgW} ${svgH}`}>
        {/* Island shape */}
        <ellipse
          cx={svgW / 2} cy={svgH / 2 + 8}
          rx={svgW / 2 - 4} ry={svgH / 2 - 2}
          fill="#dff7ee"
        />
        {/* Sand border */}
        <ellipse
          cx={svgW / 2} cy={svgH / 2 + 8}
          rx={svgW / 2 - 2} ry={svgH / 2}
          fill="none" stroke="#ead9b9" strokeWidth={4}
        />

        {/* Plantation tiles */}
        {slots.map((slot, i) => {
          const col = i % COLS;
          const row = Math.floor(i / COLS);
          const x = PAD + col * (TILE_W + GAP);
          const y = PAD + row * (TILE_H + GAP);
          const cfg = slot ? (TILE_CONFIG[slot.type] ?? { bg: '#9fb7ad', icon: '?' }) : null;
          const label = slot ? t(`plantations.${slot.type}`, { defaultValue: slot.type }) : '';
          const colonized = slot?.colonized ?? false;

          if (!cfg) {
            return (
              <g key={i}>
                <rect x={x} y={y} width={TILE_W} height={TILE_H} rx={6}
                  fill="rgba(255,255,255,0.44)" stroke="rgba(0,137,139,0.26)" strokeWidth={1} strokeDasharray="4 3" />
              </g>
            );
          }

          const legalSet = mayorLegalSlots ? new Set(mayorLegalSlots) : null;
          const isMayorLegal = legalSet != null && legalSet.has(i);
          const tileStroke = isMayorLegal ? '#4f9f4a' : colonized ? '#fffdf7' : 'rgba(23,59,58,0.26)';
          const tileStrokeW = isMayorLegal ? 3 : colonized ? 2 : 1;

          return (
            <g key={i}
              onClick={isMayorLegal && onMayorSlotClick ? () => onMayorSlotClick(i) : undefined}
              style={isMayorLegal ? { cursor: 'pointer' } : undefined}
            >
              {/* Tile card */}
              <rect x={x} y={y} width={TILE_W} height={TILE_H} rx={6}
                fill={cfg.bg} stroke={tileStroke} strokeWidth={tileStrokeW}
                opacity={colonized ? 1 : isMayorLegal ? 0.9 : 0.6}
              />
              {/* Icon */}
              <text x={x + TILE_W / 2} y={y + TILE_H / 2 - 6}
                textAnchor="middle" dominantBaseline="middle"
                fontSize={22} style={{ userSelect: 'none' }}>
                {cfg.icon}
              </text>
              {/* Label */}
              <text x={x + TILE_W / 2} y={y + TILE_H - 14}
                textAnchor="middle" fontSize={9} fill="#173b3a" fontWeight="bold"
                style={{ userSelect: 'none' }}>
                {label.toUpperCase()}
              </text>
              {/* Hacienda highlight overlay on last tile */}
              {highlightLastTile && i === island.plantations.length - 1 && (
                <rect x={x} y={y} width={TILE_W} height={TILE_H} rx={6}
                  fill="none" stroke="#f4b63f" strokeWidth={3}
                  className="svg-tile-glow"
                  style={{ pointerEvents: 'none' }}
                />
              )}
              <g>
                <circle
                  cx={x + TILE_W - 12}
                  cy={y + 12}
                  r={8}
                  fill={colonized ? '#fff2cc' : 'rgba(255,255,255,0.42)'}
                  stroke={colonized ? '#d49b34' : 'rgba(0,137,139,0.24)'}
                  strokeWidth={1.5}
                />
                {colonized && (
                  <text
                    x={x + TILE_W - 12}
                    y={y + 12}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fontSize={9}
                    style={{ userSelect: 'none' }}
                  >
                    👤
                  </text>
                )}
              </g>
            </g>
          );
        })}
      </svg>
      <p className="resort-muted" style={{ margin: '2px 0 0', fontSize: 12 }}>
        {island.d_used_spaces}/{island.total_spaces} · {t('island.activeQuarries', { n: island.d_active_quarries, suffix: island.d_active_quarries === 1 ? 'y' : 'ies' })}
      </p>
    </div>
  );
}
