# PuCo Analytics CLI 사용법

이 문서는 DB에 쌓인 PuCo 대국 데이터를 `backend` 컨테이너 안의 `scripts.analytics_cli`로 조회하는 방법을 정리합니다.

## 실행 Prefix

운영 서버에서 실행할 때:

```bash
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.analytics_cli
```

개발/로컬 compose에서 실행할 때:

```bash
docker compose exec -T backend python -m scripts.analytics_cli
```

아래 예시는 운영 서버 기준입니다. 로컬에서 돌릴 때는 `docker compose -f docker-compose.prod.yml` 부분을 `docker compose`로 바꾸면 됩니다.

## 도움말

전체 명령 확인:

```bash
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.analytics_cli --help
```

특정 명령 도움말:

```bash
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.analytics_cli ppo-lineup-games --help
```

## 1. 유저 목록 확인

최근 FINISHED 게임 수가 많은 유저부터 봅니다.

```bash
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.analytics_cli list-users --limit 50
```

JSON으로 저장:

```bash
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.analytics_cli list-users --limit 50 --json > analytics_users.json
```

주요 컬럼:

- `user_id`: 사용자 UUID
- `nickname`: 닉네임
- `total_games`: FINISHED 게임 수
- `last_game_at`: 마지막 완료 게임 시각

## 2. 유저별 봇 상대 승률

닉네임 기준:

```bash
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.analytics_cli win-rate-by-bot --nickname "<NICKNAME>"
```

UUID 기준:

```bash
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.analytics_cli win-rate-by-bot --user-id "<USER_UUID>"
```

JSON으로 저장:

```bash
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.analytics_cli win-rate-by-bot --nickname "<NICKNAME>" --json > win_rate_by_bot.json
```

주요 컬럼:

- `bot_type`: 상대 봇 타입
- `games`: 해당 봇 타입이 포함된 게임 수
- `wins`: 해당 유저 승리 수
- `win_rate`: 승률

## 3. 유저별 누적 판수 승률

기본 버킷은 5판입니다.

```bash
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.analytics_cli win-rate-by-count --nickname "<NICKNAME>"
```

10판 단위로 보기:

```bash
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.analytics_cli win-rate-by-count --nickname "<NICKNAME>" --bucket 10
```

JSON으로 저장:

```bash
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.analytics_cli win-rate-by-count --nickname "<NICKNAME>" --bucket 10 --json > win_rate_by_count.json
```

주요 컬럼:

- `game_range`: 판수 구간
- `games`: 해당 시점의 누적 게임 수
- `cumulative_wins`: 누적 승수
- `win_rate`: 누적 승률

## 4. 유저별 최근 게임 상세

최근 20판:

```bash
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.analytics_cli recent-games --nickname "<NICKNAME>" --limit 20
```

최근 100판 JSON 저장:

```bash
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.analytics_cli recent-games --nickname "<NICKNAME>" --limit 100 --json > recent_games.json
```

주요 컬럼:

- `game_id`: 게임 ID
- `created_at`: 생성 시각
- `result`: 유저 기준 `win`, `loss`, `draw`
- `opponent_bots`: 포함된 봇 타입 목록
- `winner_display_name`: 승자 표시 이름
- `ordered_players`: 좌석 순서대로 표시한 플레이어
- `my_seat`: 유저의 좌석 번호, 1부터 시작
- `my_rank`, `my_vp`, `vp_gap`: replay final score가 있을 때 계산되는 성적 정보
- `score_data_available`: replay final score 사용 가능 여부

## 5. 유저별 조합 요약

3인전에서 좌석 순서와 조합별 승률/VP 차이를 요약합니다.

```bash
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.analytics_cli lineup-summary --nickname "<NICKNAME>"
```

JSON으로 저장:

```bash
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.analytics_cli lineup-summary --nickname "<NICKNAME>" --json > lineup_summary.json
```

주요 컬럼:

- `lineup`: 좌석 순서가 반영된 표시 이름 조합
- `ordered_players`: 좌석 순서 배열
- `my_seat`: 유저 좌석 번호
- `games`, `wins`, `losses`, `draws`, `win_rate`
- `avg_vp_gap`: replay 점수가 있는 게임의 평균 VP 차이
- `vp_gap_games`: VP 차이 계산에 사용된 게임 수
- `last_played_at`: 해당 조합의 마지막 게임 시각

## 6. 유저별 게임 단위 조합 상세

특정 유저가 참여한 FINISHED 게임을 게임 단위로 봅니다.

```bash
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.analytics_cli lineup-games --nickname "<NICKNAME>" --limit 100
```

JSON으로 저장:

```bash
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.analytics_cli lineup-games --nickname "<NICKNAME>" --limit 100 --json > lineup_games.json
```

특정 표시 이름 순서만 필터:

```bash
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.analytics_cli lineup-games --nickname "<NICKNAME>" --lineup "Alice,ppo,Bob" --json > lineup_games_filtered.json
```

주의:

- `lineup-games --lineup`은 표시 이름 기준 exact match입니다.
- 사람은 실제 닉네임, 봇은 replay 표시 이름 또는 bot type 표시를 사용합니다.

주요 컬럼:

- `game_id`
- `created_at`
- `lineup`
- `winner_display_name`
- `first_place_vp`
- `second_place_vp`
- `first_second_vp_gap`
- `my_rank`
- `my_vp`

## 7. PPO 대국 총정리

PPO가 포함된 FINISHED 3인 대국을 전체 DB 기준으로 게임당 1행씩 정리합니다. 특정 유저를 지정하지 않습니다.

최근 100개:

```bash
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.analytics_cli ppo-lineup-games --limit 100
```

최근 100개 JSON 저장:

```bash
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.analytics_cli ppo-lineup-games --limit 100 --json > ppo_lineup_games.json
```

전체 출력:

```bash
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.analytics_cli ppo-lineup-games --limit 0 --json > ppo_lineup_games_all.json
```

사람, PPO, random 순서만 보기:

```bash
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.analytics_cli ppo-lineup-games --lineup "human,ppo,random" --json > ppo_human_ppo_random.json
```

PPO, PPO, random 순서만 보기:

```bash
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.analytics_cli ppo-lineup-games --lineup "ppo,ppo,random" --json > ppo_ppo_random.json
```

주의:

- `ppo-lineup-games --lineup`은 타입 기준 exact match입니다.
- 사람은 항상 `human`으로 적습니다.
- 봇은 `ppo`, `random`, `action_value`, `shipping_rush` 같은 bot type으로 적습니다.
- `best_ppo_vp_gap`은 `best_ppo_vp - best_non_ppo_vp`입니다. 양수면 최고 PPO가 비-PPO 최고 점수보다 앞선 것이고, 음수면 뒤진 것입니다.

주요 컬럼:

- `game_id`: 게임 ID
- `created_at`: 생성 시각
- `lineup`: 좌석 순서가 반영된 표시 이름 조합
- `lineup_signature`: 타입 기준 좌석 순서 조합
- `ordered_players`: 좌석 순서 배열
- `ppo_seats`: PPO 좌석 번호 목록, 1부터 시작
- `ppo_count`: 해당 게임의 PPO 수
- `ppo_result`: PPO 기준 `win`, `loss`, `draw`
- `winner_display_name`: 승자 표시 이름
- `best_ppo_rank`: PPO 중 최고 순위
- `best_ppo_vp`: PPO 중 최고 VP
- `best_non_ppo_vp`: 비-PPO 중 최고 VP
- `best_ppo_vp_gap`: `best_ppo_vp - best_non_ppo_vp`
- `score_data_available`: replay final score 사용 가능 여부

## 8. 추천 실행 순서

## 8. PPO vs 사람 승률 시각화

PPO가 사람이 포함된 FINISHED 3인 대국에서 기록한 승률을 SVG 막대 차트로 만듭니다. 별도 시각화 라이브러리 없이 pure Python으로 SVG를 생성합니다.

기본 차트는 좌석 순서를 무시하고 아래 두 조합을 따로 집계합니다.

- `human + ppo + action_value`: 모든 인간 플레이어 + PPO + action_value 조합 전체
- `human + ppo + ppo`: 인간 1명 + PPO 2명 조합 전체

기본 SVG 생성:

```bash
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.visualize_ppo_human_winrate --output /tmp/ppo_human_winrate.svg
```

SVG와 JSON 요약을 같이 생성:

```bash
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.visualize_ppo_human_winrate \
  --output /tmp/ppo_human_winrate.svg \
  --json-output /tmp/ppo_human_winrate.json
```

최소 5게임 이상 쌓인 조합만 차트에 표시:

```bash
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.visualize_ppo_human_winrate \
  --output /tmp/ppo_human_winrate_min5.svg \
  --json-output /tmp/ppo_human_winrate_min5.json \
  --min-games 5
```

생성된 SVG를 컨테이너 밖으로 복사:

```bash
docker cp puco_backend:/tmp/ppo_human_winrate.svg ./ppo_human_winrate.svg
docker cp puco_backend:/tmp/ppo_human_winrate.json ./ppo_human_winrate.json
```

좌석 순서별 전체 상세 차트를 보고 싶을 때:

```bash
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.visualize_ppo_human_winrate \
  --output /tmp/ppo_human_winrate_all_lineups.svg \
  --json-output /tmp/ppo_human_winrate_all_lineups.json \
  --all-lineups
```

차트 구성:

- 기본 모드: `human + ppo + action_value`, `human + ppo + ppo`
- `--all-lineups` 모드: `overall`, `human > ppo > random` 같은 타입별 좌석 조합 행
- 막대 길이: PPO 승률
- 상세 텍스트: 게임 수, PPO 승/패/무

JSON 컬럼:

- `lineup_signature`: 전체 또는 타입 기준 좌석 조합
- `games`: 게임 수
- `ppo_wins`: PPO 승리 수
- `ppo_losses`: PPO 패배 수
- `draws`: 무승부 수
- `win_rate`: PPO 승률

## 8-1. 로컬에서 서버에 시각화 스크립트만 보내기

로컬 현재 위치가 repo 루트라면 key 파일은 `./puco_capstone.pem`입니다. `./Users/...`처럼 앞에 점을 붙이면 현재 폴더 아래의 `Users`를 찾으려 해서 실패합니다.

스크립트만 서버 `/tmp`로 전송:

```bash
scp -i ./puco_capstone.pem \
  backend/scripts/visualize_ppo_human_winrate.py \
  ubuntu@54.116.144.226:/tmp/visualize_ppo_human_winrate.py
```

서버의 실행 중인 backend 컨테이너 안으로 복사:

```bash
ssh -i ./puco_capstone.pem ubuntu@54.116.144.226 \
  "docker cp /tmp/visualize_ppo_human_winrate.py puco_backend:/app/scripts/visualize_ppo_human_winrate.py"
```

서버에서 SVG/JSON 생성:

```bash
ssh -i ./puco_capstone.pem ubuntu@54.116.144.226 \
  "docker exec -T puco_backend python -m scripts.visualize_ppo_human_winrate --output /tmp/ppo_human_winrate.svg --json-output /tmp/ppo_human_winrate.json"
```

결과 파일을 컨테이너에서 서버 `/tmp`로 꺼내고, 다시 로컬로 복사:

```bash
ssh -i ./puco_capstone.pem ubuntu@54.116.144.226 \
  "docker cp puco_backend:/tmp/ppo_human_winrate.svg /tmp/ppo_human_winrate.svg && docker cp puco_backend:/tmp/ppo_human_winrate.json /tmp/ppo_human_winrate.json"

scp -i ./puco_capstone.pem \
  ubuntu@54.116.144.226:/tmp/ppo_human_winrate.* \
  .
```

## 9. 추천 실행 순서

전체 분석을 한 번에 뽑을 때:

```bash
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.analytics_cli list-users --limit 100 --json > analytics_users.json
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.analytics_cli ppo-lineup-games --limit 0 --json > ppo_lineup_games_all.json
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.visualize_ppo_human_winrate --output /tmp/ppo_human_winrate.svg --json-output /tmp/ppo_human_winrate.json
docker cp puco_backend:/tmp/ppo_human_winrate.svg ./ppo_human_winrate.svg
docker cp puco_backend:/tmp/ppo_human_winrate.json ./ppo_human_winrate.json
```

특정 유저를 정해서 추가 분석:

```bash
NICKNAME="<NICKNAME>"

docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.analytics_cli win-rate-by-bot --nickname "$NICKNAME" --json > "${NICKNAME}_win_rate_by_bot.json"
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.analytics_cli win-rate-by-count --nickname "$NICKNAME" --bucket 10 --json > "${NICKNAME}_win_rate_by_count.json"
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.analytics_cli recent-games --nickname "$NICKNAME" --limit 100 --json > "${NICKNAME}_recent_games.json"
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.analytics_cli lineup-summary --nickname "$NICKNAME" --json > "${NICKNAME}_lineup_summary.json"
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.analytics_cli lineup-games --nickname "$NICKNAME" --limit 100 --json > "${NICKNAME}_lineup_games.json"
```

결과 파일 묶기:

```bash
tar -czf analytics_exports.tar.gz *.json
```

SVG까지 같이 묶기:

```bash
tar -czf analytics_exports.tar.gz *.json *.svg
```

## 10. 문제 확인

backend 컨테이너가 떠 있는지 확인:

```bash
docker compose -f docker-compose.prod.yml ps backend
```

DB 연결 오류가 나면 `.env`의 `POSTGRES_PASSWORD`, `POSTGRES_USER`, `DATABASE_URL` 관련 값을 확인합니다. compose 환경에서는 backend 컨테이너에 `DATABASE_URL`이 자동 주입되어야 합니다.
