import type { TradingHouse as TradingHouseType } from '../types/gameState';

interface Props {
  tradingHouse: TradingHouseType;
}

const GOOD_CONFIG: Record<string, { fill: string; icon: string }> = {
  corn:    { fill: '#d4a017', icon: '🌽' },
  indigo:  { fill: '#3a4fa0', icon: '🫐' },
  sugar:   { fill: '#c8c8a0', icon: '🎋' },
  tobacco: { fill: '#8b5e3c', icon: '🍂' },
  coffee:  { fill: '#3d1f00', icon: '☕' },
};

const SLOT_W = 36;
const SLOT_H = 40;
const SLOT_GAP = 6;
const TOTAL_SLOTS = 4;
const PAD_X = 16;
const PAD_TOP = 40;
const PAD_BOT = 20;

export default function TradingHouse({ tradingHouse }: Props) {
  const bldgW = PAD_X * 2 + TOTAL_SLOTS * SLOT_W + (TOTAL_SLOTS - 1) * SLOT_GAP;
  const bldgH = PAD_TOP + SLOT_H + PAD_BOT;
  const roofPeak = 10;

  // Roof path: a triangle/trapezoid above the building
  const roofPath = [
    `M 0 ${PAD_TOP - 4}`,
    `L ${bldgW / 2} ${roofPeak}`,
    `L ${bldgW} ${PAD_TOP - 4}`,
    'Z',
  ].join(' ');

  const isFull = tradingHouse.d_is_full;

  return (
    <svg width={bldgW} height={bldgH + 16} viewBox={`0 0 ${bldgW} ${bldgH + 16}`}>
      {/* Building body */}
      <rect x={0} y={PAD_TOP - 4} width={bldgW} height={bldgH - PAD_TOP + 4}
        fill={isFull ? '#5a1a1a' : '#2a1e0e'}
        stroke={isFull ? '#cc4444' : '#8b6914'}
        strokeWidth={2}
      />

      {/* Roof */}
      <path d={roofPath}
        fill={isFull ? '#7a2020' : '#3d2a08'}
        stroke={isFull ? '#cc4444' : '#8b6914'}
        strokeWidth={2}
      />

      {/* Chimney */}
      <rect x={bldgW * 0.72} y={roofPeak + 4} width={8} height={14}
        fill={isFull ? '#7a2020' : '#3d2a08'}
        stroke={isFull ? '#cc4444' : '#8b6914'}
        strokeWidth={1.5}
      />

      {/* Good slots */}
      {Array.from({ length: TOTAL_SLOTS }).map((_, i) => {
        const x = PAD_X + i * (SLOT_W + SLOT_GAP);
        const y = PAD_TOP + 4;
        const good = tradingHouse.goods[i] ?? null;
        const cfg = good ? GOOD_CONFIG[good] : null;
        return (
          <g key={i}>
            <rect x={x} y={y} width={SLOT_W} height={SLOT_H} rx={4}
              fill={cfg ? cfg.fill : '#1a1208'}
              stroke={cfg ? '#ffffff55' : '#ffffff18'}
              strokeWidth={1}
            />
            {cfg && (
              <text x={x + SLOT_W / 2} y={y + SLOT_H / 2}
                textAnchor="middle" dominantBaseline="middle"
                fontSize={18} style={{ userSelect: 'none' }}>
                {cfg.icon}
              </text>
            )}
          </g>
        );
      })}

      {/* Label */}
      <text x={bldgW / 2} y={bldgH + 12}
        textAnchor="middle" fontSize={11} fill={isFull ? '#cc6666' : '#aaa'}
        style={{ userSelect: 'none' }}>
        {isFull ? 'FULL' : `${tradingHouse.d_spaces_used}/4`}
      </text>
    </svg>
  );
}
