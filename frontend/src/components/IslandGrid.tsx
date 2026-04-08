import { useTranslation } from 'react-i18next';
import type { Island } from '../types/gameState';

interface Props {
  island: Island;
  highlightLastTile?: boolean;
}

const TILE_CONFIG: Record<string, { bg: string; icon: string }> = {
  corn:    { bg: '#d4a017', icon: '🌽' },
  indigo:  { bg: '#3a4fa0', icon: '🫐' },
  sugar:   { bg: '#c8c8a0', icon: '🎋' },
  tobacco: { bg: '#8b5e3c', icon: '🍂' },
  coffee:  { bg: '#3d1f00', icon: '☕' },
  quarry:  { bg: '#607060', icon: '⛏️' },
};

const COLS = 3;
const TILE_W = 72;
const TILE_H = 64;
const GAP = 8;

export default function IslandGrid({ island, highlightLastTile }: Props) {
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
          fill="#2d6a2d"
        />
        {/* Sand border */}
        <ellipse
          cx={svgW / 2} cy={svgH / 2 + 8}
          rx={svgW / 2 - 2} ry={svgH / 2}
          fill="none" stroke="#c8a832" strokeWidth={4}
        />

        {/* Plantation tiles */}
        {slots.map((slot, i) => {
          const col = i % COLS;
          const row = Math.floor(i / COLS);
          const x = PAD + col * (TILE_W + GAP);
          const y = PAD + row * (TILE_H + GAP);
          const cfg = slot ? (TILE_CONFIG[slot.type] ?? { bg: '#555', icon: '?' }) : null;
          const label = slot ? t(`plantations.${slot.type}`, { defaultValue: slot.type }) : '';
          const colonized = slot?.colonized ?? false;

          if (!cfg) {
            return (
              <g key={i}>
                <rect x={x} y={y} width={TILE_W} height={TILE_H} rx={6}
                  fill="#1a3d1a" stroke="#2a5a2a" strokeWidth={1} strokeDasharray="4 3" />
              </g>
            );
          }

          return (
            <g key={i}>
              {/* Tile card */}
              <rect x={x} y={y} width={TILE_W} height={TILE_H} rx={6}
                fill={cfg.bg} stroke={colonized ? '#fff' : '#00000055'} strokeWidth={colonized ? 2 : 1}
                opacity={colonized ? 1 : 0.6}
              />
              {/* Icon */}
              <text x={x + TILE_W / 2} y={y + TILE_H / 2 - 6}
                textAnchor="middle" dominantBaseline="middle"
                fontSize={22} style={{ userSelect: 'none' }}>
                {cfg.icon}
              </text>
              {/* Label */}
              <text x={x + TILE_W / 2} y={y + TILE_H - 14}
                textAnchor="middle" fontSize={9} fill="#ffffffcc" fontWeight="bold"
                style={{ userSelect: 'none' }}>
                {label.toUpperCase()}
              </text>
              {/* Hacienda highlight overlay on last tile */}
              {highlightLastTile && i === island.plantations.length - 1 && (
                <rect x={x} y={y} width={TILE_W} height={TILE_H} rx={6}
                  fill="none" stroke="#ffe066" strokeWidth={3}
                  className="svg-tile-glow"
                  style={{ pointerEvents: 'none' }}
                />
              )}
              <g>
                <circle
                  cx={x + TILE_W - 12}
                  cy={y + 12}
                  r={8}
                  fill={colonized ? '#f5deb3' : '#00000033'}
                  stroke={colonized ? '#8b4513' : '#ffffff22'}
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
      <p style={{ margin: '2px 0 0', fontSize: 12, color: '#888' }}>
        {island.d_used_spaces}/{island.total_spaces} · {t('island.activeQuarries', { n: island.d_active_quarries, suffix: island.d_active_quarries === 1 ? 'y' : 'ies' })}
      </p>
    </div>
  );
}
