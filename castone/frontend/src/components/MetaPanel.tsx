import { useTranslation } from 'react-i18next';
import type { Meta } from '../types/gameState';

interface Props {
  meta: Meta;
  playerNames: Record<string, string>;
  botPlayers?: Record<string, string>;
}

export default function MetaPanel({ meta, playerNames, botPlayers }: Props) {
  const { t } = useTranslation();

  function nameWithBot(playerId: string) {
    const name = playerNames[playerId] ?? playerId;
    return botPlayers && botPlayers[playerId] !== undefined ? name + ' 🤖' : name;
  }

  const items = [
    { key: 'round',    label: t('meta.round'),    value: String(meta.round) },
    { key: 'phase',    label: t('meta.phase'),    value: t(`phases.${meta.phase}`, { defaultValue: meta.phase.replace(/_/g, ' ') }), bold: true },
    { key: 'governor', label: t('meta.governor'), value: nameWithBot(meta.governor) },
    { key: 'active',   label: t('meta.active'),   value: nameWithBot(meta.active_player), gold: true },
    { key: 'vp',       label: t('meta.vpSupply'), value: String(meta.vp_supply_remaining) },
  ] as const;

  return (
    <div className="meta-bar">
      {items.map(item => (
        <span key={`lbl-${item.key}`} className="meta-label">{item.label}</span>
      ))}
      {items.map(item => (
        <span key={`val-${item.key}`}
          className={`meta-value${'gold' in item ? ' meta-active' : ''}${'bold' in item ? ' meta-bold' : ''}`}>
          {item.value}
        </span>
      ))}
      {meta.end_game_triggered && (
        <span className="meta-endgame" style={{ gridColumn: '1 / -1' }}>⚠️ {meta.end_game_reason}</span>
      )}
    </div>
  );
}
