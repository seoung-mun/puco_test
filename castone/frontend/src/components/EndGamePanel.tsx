import { useTranslation } from 'react-i18next';

import type { FinalScoreSummary, GameState, PlayerScore } from '../types/gameState';

type EndGamePanelProps = {
  state: GameState;
  scores: FinalScoreSummary | null;
  onReturnToRooms: () => void;
};

const SCORE_COLUMNS: { key: keyof PlayerScore; labelKey: string }[] = [
  { key: 'vp_chips', labelKey: 'endGame.vpChips' },
  { key: 'building_vp', labelKey: 'endGame.buildings' },
  { key: 'guild_hall_bonus', labelKey: 'endGame.guildHall' },
  { key: 'residence_bonus', labelKey: 'endGame.residence' },
  { key: 'fortress_bonus', labelKey: 'endGame.fortress' },
  { key: 'customs_house_bonus', labelKey: 'endGame.customsHouse' },
  { key: 'city_hall_bonus', labelKey: 'endGame.cityHall' },
  { key: 'total', labelKey: 'endGame.total' },
];

export default function EndGamePanel({
  state,
  scores,
  onReturnToRooms,
}: EndGamePanelProps) {
  const { t } = useTranslation();
  const title = state.meta.end_game_reason
    ? t('endGame.title', { reason: state.meta.end_game_reason })
    : t('endGame.titleNoReason', '🏁 게임 종료');

  return (
    <div className="end-game-panel">
      <div className="end-game-panel__header">{title}</div>
      {scores ? (
        <table className="end-game-table">
          <thead>
            <tr>
              <th>{t('player.governor')}</th>
              {SCORE_COLUMNS.map((column) => (
                <th key={column.key}>{t(column.labelKey)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {scores.player_order.map((playerRef) => {
              const row = scores.scores[playerRef];
              if (!row) return null;
              const isWinner = playerRef === scores.winner;
              const displayName = scores.display_names?.[playerRef] ?? state.players[playerRef]?.display_name ?? playerRef;
              return (
                <tr key={playerRef} className={isWinner ? 'end-game-winner' : ''}>
                  <td>{isWinner ? '🏆 ' : ''}{displayName}</td>
                  {SCORE_COLUMNS.map((column) => (
                    <td
                      key={column.key}
                      className={column.key === 'total' ? 'end-game-total' : ''}
                    >
                      {row[column.key] > 0 || column.key === 'vp_chips' || column.key === 'total'
                        ? row[column.key]
                        : '—'}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : (
        <p className="end-game-loading">{t('endGame.loading', '점수 집계 중...')}</p>
      )}
      <div className="end-game-panel__actions">
        <button className="end-game-panel__button" onClick={onReturnToRooms}>
          {t('endGame.returnToRooms', '방 목록으로 돌아가기')}
        </button>
      </div>
    </div>
  );
}
