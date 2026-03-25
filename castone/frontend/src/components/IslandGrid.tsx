import { useTranslation } from 'react-i18next';
import type { Island } from '../types/gameState';

interface Props {
  island: Island;
  // 토글 모드 (인간)
  mayorPending?: number[] | null;          // 슬롯별 pending 값 [0..11]
  mayorLocalUnplaced?: number;
  onMayorToggle?: (slotIdx: number, delta: 1 | -1) => void;
  // 순차 모드 (봇 대기)
  currentMayorSlot?: number | null;
  onMayorPlace?: (amount: number) => void;
  hasUnplacedColonists?: boolean;
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

export default function IslandGrid({ island, mayorPending, mayorLocalUnplaced = 0, onMayorToggle, currentMayorSlot, onMayorPlace, hasUnplacedColonists, highlightLastTile }: Props) {
  const isToggleMode = mayorPending !== null && mayorPending !== undefined;
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
              {/* Colonist slot — toggle mode (human) or sequential mode (bot) */}
              {(() => {
                const cx = x + TILE_W - 12;
                const cy = y + 12;

                if (isToggleMode) {
                  const pending = mayorPending?.[i] ?? 0;
                  const isPending = pending > 0;
                  const canAdd = !colonized && !isPending && (mayorLocalUnplaced ?? 0) > 0;
                  const canRemove = !colonized && isPending;
                  return (
                    <g
                      onClick={canAdd ? () => onMayorToggle!(i, 1) : canRemove ? () => onMayorToggle!(i, -1) : undefined}
                      style={{ cursor: (canAdd || canRemove) ? 'pointer' : 'default' }}
                    >
                      <circle cx={cx} cy={cy} r={8}
                        fill={colonized ? '#f5deb3' : isPending ? '#ffe066bb' : '#00000033'}
                        stroke={colonized ? '#8b4513' : isPending ? '#ffe066' : '#ffffff22'}
                        strokeWidth={isPending ? 2 : 1.5}
                      />
                      {(colonized || isPending) && (
                        <text x={cx} y={cy}
                          textAnchor="middle" dominantBaseline="middle"
                          fontSize={9} style={{ userSelect: 'none' }}>
                          👤
                        </text>
                      )}
                      {canAdd && (
                        <text x={cx} y={cy}
                          textAnchor="middle" dominantBaseline="middle"
                          fontSize={12} fill="#ffe066" fontWeight="bold" style={{ userSelect: 'none' }}>
                          +
                        </text>
                      )}
                    </g>
                  );
                }

                // Sequential mode
                const isCurrent = currentMayorSlot === i;
                const canPlace = isCurrent && !!onMayorPlace && !!hasUnplacedColonists;
                const canSkip = isCurrent && !!onMayorPlace && !hasUnplacedColonists;
                return (
                  <g
                    onClick={canPlace ? () => onMayorPlace!(1) : canSkip ? () => onMayorPlace!(0) : undefined}
                    style={{ cursor: (canPlace || canSkip) ? 'pointer' : 'default' }}
                  >
                    <circle cx={cx} cy={cy} r={8}
                      fill={colonized ? '#f5deb3' : isCurrent ? '#ffe06644' : '#00000033'}
                      stroke={colonized ? '#8b4513' : isCurrent ? '#ffe066' : '#ffffff22'}
                      strokeWidth={isCurrent ? 2 : 1.5}
                    />
                    {colonized && (
                      <text x={cx} y={cy}
                        textAnchor="middle" dominantBaseline="middle"
                        fontSize={9} style={{ userSelect: 'none' }}>
                        👤
                      </text>
                    )}
                    {canPlace && (
                      <text x={cx} y={cy}
                        textAnchor="middle" dominantBaseline="middle"
                        fontSize={12} fill="#ffe066" fontWeight="bold" style={{ userSelect: 'none' }}>
                        +
                      </text>
                    )}
                    {canSkip && (
                      <text x={cx} y={cy}
                        textAnchor="middle" dominantBaseline="middle"
                        fontSize={9} fill="#ffffff66" style={{ userSelect: 'none' }}>
                        —
                      </text>
                    )}
                  </g>
                );
              })()}
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
