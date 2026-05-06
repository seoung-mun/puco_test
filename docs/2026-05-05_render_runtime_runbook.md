# Render Runtime Runbook

## 1. 어떤 엔드포인트를 봐야 하나

- `/health`
  - 목적: Render liveness probe
  - 의미: 프로세스와 이벤트 루프가 살아 있는가
  - 특성: 항상 가볍고, PostgreSQL / Redis / serving readiness를 판정하지 않음

- `/health/runtime`
  - 목적: 운영자 진단용 readiness/runtime 뷰
  - 확인 항목:
    - `postgresql`
    - `redis`
    - `serving`
    - `runtime.progress_games_without_engine`
    - `runtime.running_bot_tasks`
    - `runtime.active_bot_stall_watchdogs`

## 2. 자주 헷갈리는 로그 해석

`INFO: Shutting down` 직후 보이는 `Redis listener error ... Connection closed by server.` 는 대개 프로세스 종료 중 예상 가능한 후행 증상이다.

- 이 로그만으로 PostgreSQL 장애나 Redis TTL 만료를 근본 원인으로 단정하지 않는다.
- 먼저 같은 시각의 Render deploy / restart 이벤트가 있었는지 확인한다.

## 3. Redis TTL 900초에 대한 해석

- `game:*` Redis 키의 900초 TTL은 캐시/팬아웃 계층의 만료 정책이다.
- 이것은 프로세스 종료의 직접 원인을 설명하지 않는다.
- 장기 유휴 후 장애를 볼 때는 TTL만 보지 말고 `/health/runtime` 와 Render 이벤트 로그를 같이 본다.

## 4. 기본 진단 순서

1. `/health` 가 `200` 인지 확인한다.
2. `/health/runtime` 의 `postgresql`, `redis`, `serving` 상태를 본다.
3. `runtime.progress_games_without_engine` 가 0보다 큰지 확인한다.
4. 같은 시간대 Render deploy / restart 이벤트를 확인한다.
5. 봇 멈춤이 의심되면 앱 로그의 구조화된 watchdog / scheduler 로그를 함께 본다.

## 5. 운영 해석 기준

- `/health=200`, `/health/runtime=ok`
  - 프로세스와 주요 런타임 의존성이 모두 정상

- `/health=200`, `/health/runtime=degraded`
  - 프로세스는 살아 있지만 게임플레이 readiness는 저하
  - 이 경우 `/health` 만 보고 "정상"이라고 판단하면 안 된다

- `progress_games_without_engine > 0`
  - `PROGRESS` 로 보이는 게임 중 인메모리 엔진이 없는 게임이 존재
  - recovery/liveness 경로를 우선 의심한다
