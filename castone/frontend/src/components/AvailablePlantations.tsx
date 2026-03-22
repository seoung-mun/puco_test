import { useTranslation } from 'react-i18next';
import type { AvailablePlantations as AvailablePlantationsType } from '../types/gameState';

interface Props {
  plantations: AvailablePlantationsType;
  quarrySupplyRemaining: number;
  onPick?: (type: string) => void;
  canPickQuarry?: boolean;
  onPickQuarry?: () => void;
  canUseHacienda?: boolean;
  onUseHacienda?: () => void;
}

const TILE_CONFIG: Record<string, { bg: string; icon: string }> = {
  corn:    { bg: '#d4a017', icon: '🌽' },
  indigo:  { bg: '#3a4fa0', icon: '🫐' },
  sugar:   { bg: '#a0a060', icon: '🎋' },
  tobacco: { bg: '#8b5e3c', icon: '🍂' },
  coffee:  { bg: '#3d1f00', icon: '☕' },
  quarry:  { bg: '#607060', icon: '⛏️' },
};

const TILE_W = 64;
const TILE_H = 72;
const GAP = 8;
const SPECIAL_SEP = 24;
const PILE_GAP = 12;

export default function AvailablePlantations({
  plantations, quarrySupplyRemaining,
  onPick, canPickQuarry, onPickQuarry,
  canUseHacienda, onUseHacienda,
}: Props) {
  const { t } = useTranslation();
  const tiles = plantations.face_up;
  const quarryCfg = TILE_CONFIG['quarry'];

  const faceDownX = tiles.length > 0
    ? tiles.length * (TILE_W + GAP) + SPECIAL_SEP
    : 0;
  const quarryX = faceDownX + TILE_W + PILE_GAP;
  const svgW = quarryX + TILE_W;
  const svgH = TILE_H;

  const quarryClickable = !!canPickQuarry && quarrySupplyRemaining > 0;

  return (
    <div>
      <svg width={svgW} height={svgH} viewBox={`0 0 ${svgW} ${svgH}`}>
        {/* Face-up plantation tiles */}
        {tiles.map((type, i) => {
          const cfg = TILE_CONFIG[type] ?? { bg: '#555', icon: '?' };
          const x = i * (TILE_W + GAP);
          const clickable = !!onPick;
          const label = t(`plantations.${type}`, { defaultValue: type });
          return (
            <g key={i} onClick={clickable ? () => onPick!(type) : undefined}
              style={{ cursor: clickable ? 'pointer' : 'default' }}>
              <rect x={x} y={0} width={TILE_W} height={TILE_H} rx={6}
                fill={cfg.bg}
                stroke={clickable ? '#ffe066' : '#ffffff33'}
                strokeWidth={clickable ? 2 : 1} />
              <text x={x + TILE_W / 2} y={32}
                textAnchor="middle" dominantBaseline="middle"
                fontSize={22} style={{ userSelect: 'none' }}>
                {cfg.icon}
              </text>
              <text x={x + TILE_W / 2} y={TILE_H - 12}
                textAnchor="middle" fontSize={9} fill="#ffffffcc" fontWeight="bold"
                style={{ userSelect: 'none' }}>
                {label.toUpperCase()}
              </text>
            </g>
          );
        })}

        {tiles.length > 0 && (
          <line
            x1={tiles.length * (TILE_W + GAP) + SPECIAL_SEP / 2}
            y1={10} x2={tiles.length * (TILE_W + GAP) + SPECIAL_SEP / 2} y2={TILE_H - 10}
            stroke="#ffffff33" strokeWidth={1}
          />
        )}

        {/* Face-down pile (hacienda) */}
        <g
          onClick={canUseHacienda ? onUseHacienda : undefined}
          style={{ cursor: canUseHacienda ? 'pointer' : 'default', opacity: canUseHacienda ? 1 : 0.4 }}
        >
          <rect x={faceDownX - 4} y={4} width={TILE_W} height={TILE_H} rx={6} fill="#2a1a08" />
          <rect x={faceDownX - 2} y={2} width={TILE_W} height={TILE_H} rx={6} fill="#3a2510" />
          <rect x={faceDownX} y={0} width={TILE_W} height={TILE_H} rx={6}
            fill="#5a3a18"
            stroke={canUseHacienda ? '#ffe066' : '#ffffff22'}
            strokeWidth={canUseHacienda ? 2 : 1}
          />
          {[0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120].map(offset => (
            <line key={offset}
              x1={faceDownX + Math.max(0, offset - TILE_H)} y1={Math.min(TILE_H, offset)}
              x2={faceDownX + Math.min(TILE_W, offset)} y2={Math.max(0, offset - TILE_W)}
              stroke="#7a5028" strokeWidth={1.2}
              clipPath={`inset(0 0 0 ${faceDownX})`}
            />
          ))}
          <text x={faceDownX + TILE_W / 2} y={30}
            textAnchor="middle" dominantBaseline="middle"
            fontSize={24} fill={canUseHacienda ? '#ffe066' : '#ffffff55'}
            fontWeight="bold" style={{ userSelect: 'none' }}>
            ?
          </text>
          <text x={faceDownX + TILE_W / 2} y={TILE_H - 12}
            textAnchor="middle" fontSize={9} fill="#ffffffcc" fontWeight="bold"
            style={{ userSelect: 'none' }}>
            {t('buildings.hacienda').toUpperCase()}
          </text>
        </g>

        {/* Quarry pile */}
        <g
          onClick={quarryClickable ? onPickQuarry : undefined}
          style={{
            cursor: quarryClickable ? 'pointer' : 'default',
            opacity: quarrySupplyRemaining === 0 ? 0.3 : quarryClickable ? 1 : 0.45,
          }}
        >
          <rect x={quarryX} y={0} width={TILE_W} height={TILE_H} rx={6}
            fill={quarryCfg.bg}
            stroke={quarryClickable ? '#a0ffa0' : '#ffffff22'}
            strokeWidth={quarryClickable ? 2 : 1}
            strokeDasharray={quarryClickable ? '4 3' : undefined}
          />
          <text x={quarryX + TILE_W / 2} y={28}
            textAnchor="middle" dominantBaseline="middle"
            fontSize={22} style={{ userSelect: 'none' }}>
            {quarryCfg.icon}
          </text>
          <text x={quarryX + TILE_W / 2} y={TILE_H - (quarryClickable ? 20 : 12)}
            textAnchor="middle" fontSize={9} fill="#ffffffcc" fontWeight="bold"
            style={{ userSelect: 'none' }}>
            {t('plantations.quarry').toUpperCase()}
          </text>
          {quarryClickable && (
            <text x={quarryX + TILE_W / 2} y={TILE_H - 8}
              textAnchor="middle" fontSize={8} fill="#a0ffa0"
              style={{ userSelect: 'none' }}>
              ({t('rolePrivileges.settler.label').toLowerCase()})
            </text>
          )}
          <circle cx={quarryX + TILE_W - 10} cy={10} r={9}
            fill={quarrySupplyRemaining > 0 ? '#2a5a2a' : '#5a2a2a'} />
          <text x={quarryX + TILE_W - 10} y={10}
            textAnchor="middle" dominantBaseline="middle"
            fontSize={9} fill="#fff" fontWeight="bold"
            style={{ userSelect: 'none' }}>
            {quarrySupplyRemaining}
          </text>
        </g>
      </svg>

      <p style={{ margin: '4px 0 0', fontSize: 11, color: '#888' }}>
        {(() => {
          const dp = plantations.draw_pile;
          const total = dp.corn + dp.indigo + dp.sugar + dp.tobacco + dp.coffee;
          return `${t('board.drawPile')}: ${total} (🌽${dp.corn} 🌿${dp.indigo} 🍬${dp.sugar} 🚬${dp.tobacco} ☕${dp.coffee})`;
        })()}
      </p>
    </div>
  );
}
