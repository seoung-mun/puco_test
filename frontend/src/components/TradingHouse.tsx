import type { TradingHouse as TradingHouseType } from '../types/gameState';

interface Props {
  tradingHouse: TradingHouseType;
}

const GOOD_CONFIG: Record<string, { fill: string; icon: string }> = {
  corn:    { fill: '#f4b63f', icon: '🌽' },
  indigo:  { fill: '#00a9b7', icon: '🫐' },
  sugar:   { fill: '#7bbf91', icon: '🎋' },
  tobacco: { fill: '#ff745f', icon: '🍂' },
  coffee:  { fill: '#8c641d', icon: '☕' },
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
        fill={isFull ? 'rgba(255,116,95,0.16)' : '#fff8e6'}
        stroke={isFull ? '#ff745f' : '#d49b34'}
        strokeWidth={2}
      />

      {/* Roof */}
      <path d={roofPath}
        fill={isFull ? 'rgba(255,116,95,0.28)' : '#f4b63f'}
        stroke={isFull ? '#ff745f' : '#d49b34'}
        strokeWidth={2}
      />

      {/* Chimney */}
      <rect x={bldgW * 0.72} y={roofPeak + 4} width={8} height={14}
        fill={isFull ? '#ff745f' : '#f4b63f'}
        stroke={isFull ? '#b84d3d' : '#d49b34'}
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
              fill={cfg ? cfg.fill : 'rgba(255,255,255,0.58)'}
              stroke={cfg ? 'rgba(255,255,255,0.8)' : 'rgba(0,137,139,0.22)'}
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
        textAnchor="middle" fontSize={11} fill={isFull ? '#b84d3d' : '#5e766f'}
        style={{ userSelect: 'none' }}>
        {isFull ? 'FULL' : `${tradingHouse.d_spaces_used}/4`}
      </text>
    </svg>
  );
}
