import type { CargoShip } from '../types/gameState';

interface Props {
  ships: CargoShip[];
}

const GOOD_CONFIG: Record<string, { fill: string; icon: string }> = {
  corn:    { fill: '#f4b63f', icon: '🌽' },
  indigo:  { fill: '#00a9b7', icon: '🫐' },
  sugar:   { fill: '#7bbf91', icon: '🎋' },
  tobacco: { fill: '#ff745f', icon: '🍂' },
  coffee:  { fill: '#8c641d', icon: '☕' },
};

const SLOT_W = 28;
const SLOT_H = 32;
const SLOT_GAP = 5;
const SHIP_PAD_X = 18;
const SHIP_PAD_TOP = 24;
const SHIP_PAD_BOT = 28;

function Ship({ ship }: { ship: CargoShip }) {
  const cfg = ship.good ? GOOD_CONFIG[ship.good] : null;
  const slots = ship.capacity;
  const shipW = SHIP_PAD_X * 2 + slots * SLOT_W + (slots - 1) * SLOT_GAP;
  const shipH = SHIP_PAD_TOP + SLOT_H + SHIP_PAD_BOT;

  // Hull path: flat top, angled bottom
  const hullPath = [
    `M 8 ${SHIP_PAD_TOP - 6}`,
    `L ${shipW - 8} ${SHIP_PAD_TOP - 6}`,
    `L ${shipW - 8} ${shipH - 14}`,
    `Q ${shipW / 2} ${shipH} 8 ${shipH - 14}`,
    'Z',
  ].join(' ');

  // Mast
  const mastX = shipW / 2;

  return (
    <svg width={shipW} height={shipH + 20} viewBox={`0 0 ${shipW} ${shipH + 20}`}>
      {/* Mast */}
      <line x1={mastX} y1={4} x2={mastX} y2={SHIP_PAD_TOP - 6} stroke="#d49b34" strokeWidth={2.5} />
      {/* Sail */}
      <polygon
        points={`${mastX},6 ${mastX + 18},${SHIP_PAD_TOP - 10} ${mastX},${SHIP_PAD_TOP - 10}`}
        fill="#fff8e6" stroke="#f4b63f" strokeWidth={1}
      />

      {/* Hull */}
      <path d={hullPath} fill="#087b82" stroke="#006f75" strokeWidth={2} />

      {/* Cargo slots */}
      {Array.from({ length: slots }).map((_, i) => {
        const x = SHIP_PAD_X + i * (SLOT_W + SLOT_GAP);
        const y = SHIP_PAD_TOP;
        const filled = i < ship.d_filled;
        return (
          <g key={i}>
            <rect x={x} y={y} width={SLOT_W} height={SLOT_H} rx={4}
              fill={filled && cfg ? cfg.fill : 'rgba(255,255,255,0.45)'}
              stroke={filled ? 'rgba(255,255,255,0.78)' : 'rgba(255,255,255,0.36)'}
              strokeWidth={1}
            />
            {filled && cfg && (
              <text x={x + SLOT_W / 2} y={y + SLOT_H / 2}
                textAnchor="middle" dominantBaseline="middle"
                fontSize={14} style={{ userSelect: 'none' }}>
                {cfg.icon}
              </text>
            )}
          </g>
        );
      })}

      {/* Ship label */}
      <text x={shipW / 2} y={shipH + 14}
        textAnchor="middle" fontSize={11} fill="#5e766f"
        style={{ userSelect: 'none' }}>
        {ship.d_filled}/{ship.capacity}{ship.d_is_full ? ' FULL' : ''}
      </text>
    </svg>
  );
}

export default function CargoShips({ ships }: Props) {
  return (
    <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-end', flexWrap: 'wrap' }}>
      {ships.map((ship, i) => (
        <Ship key={i} ship={ship} />
      ))}
    </div>
  );
}
