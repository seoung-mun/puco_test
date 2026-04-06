import type { Colonists } from '../types/gameState';

interface Props {
  colonists: Colonists;
  numPlayers: number;
}

const SLOT_R = 11;
const SLOT_DIAM = SLOT_R * 2;
const SLOT_GAP = 8;
const SHIP_PAD_X = 18;
const SHIP_PAD_TOP = 32;
const SHIP_PAD_BOT = 30;

export default function ColonistShip({ colonists, numPlayers }: Props) {
  const capacity = numPlayers;
  const shipW = SHIP_PAD_X * 2 + capacity * SLOT_DIAM + (capacity - 1) * SLOT_GAP;
  const shipH = SHIP_PAD_TOP + SLOT_DIAM + SHIP_PAD_BOT;
  const mastX = shipW / 2;

  const hullPath = [
    `M 8 ${SHIP_PAD_TOP - 8}`,
    `L ${shipW - 8} ${SHIP_PAD_TOP - 8}`,
    `L ${shipW - 8} ${shipH - 14}`,
    `Q ${shipW / 2} ${shipH} 8 ${shipH - 14}`,
    'Z',
  ].join(' ');

  const supplyW = 56;
  const supplyH = shipH + 20;
  const stackCount = Math.min(colonists.supply, 6);

  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 16 }}>

      {/* Colonist ship */}
      <svg width={shipW} height={shipH + 20} viewBox={`0 0 ${shipW} ${shipH + 20}`}>
        {/* Mast */}
        <line x1={mastX} y1={4} x2={mastX} y2={SHIP_PAD_TOP - 8} stroke="#8b6914" strokeWidth={2.5} />
        {/* Sail */}
        <polygon
          points={`${mastX},6 ${mastX + 18},${SHIP_PAD_TOP - 12} ${mastX},${SHIP_PAD_TOP - 12}`}
          fill="#f5e6c8" stroke="#c8a832" strokeWidth={1}
        />
        {/* Hull — purple/navy to distinguish from cargo ships */}
        <path d={hullPath} fill="#3a2860" stroke="#7050b0" strokeWidth={2} />

        {/* Colonist slots */}
        {Array.from({ length: capacity }).map((_, i) => {
          const cx = SHIP_PAD_X + SLOT_R + i * (SLOT_DIAM + SLOT_GAP);
          const cy = SHIP_PAD_TOP + SLOT_R;
          const filled = i < colonists.ship;
          return (
            <g key={i}>
              <circle cx={cx} cy={cy} r={SLOT_R}
                fill={filled ? '#f5deb3' : '#1e1030'}
                stroke={filled ? '#8b4513' : '#7050b055'}
                strokeWidth={1.5}
              />
              {filled && (
                <text x={cx} y={cy}
                  textAnchor="middle" dominantBaseline="middle"
                  fontSize={12} style={{ userSelect: 'none' }}>
                  👤
                </text>
              )}
            </g>
          );
        })}

        {/* Label */}
        <text x={shipW / 2} y={shipH + 14}
          textAnchor="middle" fontSize={11} fill="#aaa" style={{ userSelect: 'none' }}>
          ship: {colonists.ship}/{capacity}
        </text>
      </svg>

      {/* Supply stack */}
      <svg width={supplyW} height={supplyH} viewBox={`0 0 ${supplyW} ${supplyH}`}>
        {/* Stacked colonist circles (up to 6) */}
        {Array.from({ length: stackCount }).map((_, i) => {
          const cx = supplyW / 2;
          const cy = supplyH - 32 - i * 9;
          return (
            <g key={i}>
              <circle cx={cx} cy={cy} r={10}
                fill="#f5deb3" stroke="#8b4513" strokeWidth={1.5}
                opacity={0.4 + (i / Math.max(stackCount - 1, 1)) * 0.6}
              />
              {i === stackCount - 1 && (
                <text x={cx} y={cy}
                  textAnchor="middle" dominantBaseline="middle"
                  fontSize={10} style={{ userSelect: 'none' }}>
                  👤
                </text>
              )}
            </g>
          );
        })}
        {/* Count badge */}
        <rect x={supplyW / 2 - 13} y={supplyH - 18} width={26} height={15} rx={4}
          fill="#2a2a2a" stroke="#555" strokeWidth={1}
        />
        <text x={supplyW / 2} y={supplyH - 10}
          textAnchor="middle" dominantBaseline="middle"
          fontSize={10} fill="#fff" fontWeight="bold" style={{ userSelect: 'none' }}>
          ×{colonists.supply}
        </text>
        <text x={supplyW / 2} y={supplyH + 8}
          textAnchor="middle" fontSize={10} fill="#888" style={{ userSelect: 'none' }}>
          supply
        </text>
      </svg>

    </div>
  );
}
