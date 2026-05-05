# Castone 배포 속도 및 실플레이 속도 최적화 설계 보고서

> 작성일: 2026-05-04
> 대상 브랜치: `prod`
> 목적: 실제 운영 성능을 해치지 않으면서 배포 시간과 봇 플레이 체감 속도를 함께 개선한다.

---

## 1. 요약

현재 코드베이스를 기준으로 보면, **프런트 번들 자체는 빠르지만 배포 파이프라인과 백엔드 런타임 경로에 불필요한 무게가 실려 있다.**

- 프런트 프로덕션 빌드는 실제 측정상 약 **957ms**로 매우 빠르다.
- 반면 `frontend/` 폴더는 약 **146MB**, 그중 `node_modules`가 약 **144MB**라서, 프런트 Docker 배포 시 빌드 컨텍스트 전송이 불필요하게 무거울 가능성이 높다.
- 백엔드 쪽은 `backend/Dockerfile.prod`에서 `torch`, `torchvision`을 포함한 Python 의존성을 매 빌드 때 설치하고, `PuCo_RL` 전체를 이미지에 복사한다.
- 실제 플레이 속도는 현재 추론 자체보다 **의도적으로 넣어 둔 UX 지연(기본 2~3초)** 의 영향이 더 크다.
- 또한 액션 1회마다 DB 로그, 리플레이 payload, JSONL 로그, Redis 상태 publish가 한 번에 일어나므로, 향후 동접/관전자 수가 늘면 I/O와 직렬화 비용이 플레이 템포를 떨어뜨릴 수 있다.

결론적으로, 가장 안전하고 효과적인 방향은 아래 두 축이다.

1. **배포 속도**: 빌드 컨텍스트 축소 + 의존성/모델 레이어 분리 + 프런트/백엔드 배포 경로 분리
2. **플레이 속도**: 모드별 봇 속도 정책 + 모델 warm-up + WebSocket/리플레이 직렬화 경량화

---

## 2. 현재 상태 점검

### 2.1 브랜치

- 현재 체크아웃 브랜치: `prod`

### 2.2 관측된 크기와 빌드 특성

- 저장소 전체 크기: 약 **1.3GB**
- `backend/`: 약 **38MB**
- `frontend/`: 약 **146MB**
- `frontend/node_modules`: 약 **144MB**
- `PuCo_RL/`: 약 **116MB**
- 루트 `models/`: 약 **8.9MB**

### 2.3 프런트 빌드 측정

`frontend/`에서 실제 프로덕션 빌드를 실행한 결과:

- build time: **957ms**
- JS 출력물: **399.85kB**
- gzip 기준 JS: **122.93kB**
- CSS 출력물: **19.63kB**

이 수치는 “프런트 배포가 느린 이유가 번들 최적화 부족”이 아니라, **배포 경로 자체가 무겁기 때문**이라는 해석을 강하게 뒷받침한다.

---

## 3. 코드 기준 병목 진단

## 3.1 배포 속도 병목

### A. 프런트 Docker 컨텍스트가 과도하게 클 가능성

- `frontend/Dockerfile`은 `context: ./frontend`로 빌드된다.
- 하지만 `frontend/.dockerignore`가 없고, 로컬 `frontend/node_modules`는 약 144MB다.
- 즉, 현재 구조에서는 프런트 소스보다 **의존성 폴더를 통째로 빌드 컨텍스트로 보내는 비용**이 더 클 수 있다.

### B. 백엔드 이미지 빌드가 무겁다

- `backend/Dockerfile.prod`는 `torch`, `torchvision`이 포함된 `requirements.txt`를 설치한다.
- 이 단계는 네트워크/압축 해제/휠 설치 비용이 커서, 캐시가 깨지면 배포 시간이 크게 늘어난다.
- 동시에 `COPY PuCo_RL /PuCo_RL`로 **서빙에 꼭 필요하지 않은 학습/평가 리소스까지 함께 이미지에 포함**될 수 있다.

### C. 모델 변경과 앱 배포가 강하게 결합돼 있다

- 현재 구조는 기본 champion bundle과 checkpoint를 이미지 내부에서 직접 참조한다.
- 향후 모델 버전 교체가 자주 일어나면, 코드 변경이 없어도 **이미지 재빌드/재배포**가 필요해진다.

### D. 앱 시작 시 migration이 항상 실행된다

- `backend/entrypoint.sh`는 컨테이너 시작 때마다 `alembic upgrade head`를 실행한다.
- 운영 안정성 관점에서는 안전한 기본값이지만, 배포/재기동 시 cold start를 늘리고 장애 면을 넓힌다.

## 3.2 실플레이 속도 병목

### A. 봇 UX 지연이 의도적으로 크다

`backend/app/services/bot_service.py` 기준:

- 역할 선택: 기본 **3.0초**
- 일반 액션: 기본 **2.0초**
- 이후 배속 값으로 나누는 구조

즉, 현재 플레이 템포의 가장 큰 원인은 추론 속도보다 **의도적 대기 시간**이다.

### B. 첫 추론 때 모델 로딩 비용이 발생한다

- `agent_registry.py`와 `adapter_runtime.py`는 LRU 캐시를 사용해 런타임/래퍼를 재사용한다.
- 방향은 맞지만, **첫 PPO 봇 턴**에서는 bundle manifest 로드, adapter import, checkpoint load가 한 번 발생한다.

### C. 액션 1회당 쓰기/직렬화 작업이 많다

`game_service.py` 기준으로 한 턴 처리 시 대략 아래 작업이 함께 발생한다.

- 엔진 step
- `GameLog` DB 저장
- compact summary 생성
- replay entry 생성
- `MLLogger` JSONL 기록
- replay payload 갱신
- Redis 상태 저장 + publish

### D. replay에 full rich state를 계속 누적한다

- `ReplayLogger.append_entry()`는 각 엔트리에 `rich_state`를 통째로 붙일 수 있다.
- 게임이 길어질수록 payload가 커지고, DB JSONB/file write 비용도 커진다.

### E. WebSocket broadcast가 연결 수 증가에 취약할 수 있다

- `ws_manager.py`는 현재 연결들을 순차적으로 `await connection.send_text(...)` 한다.
- 느린 클라이언트가 하나 있으면 broadcast 전체가 늘어질 수 있다.

---

## 4. 최적화 목표

이번 최적화의 목표는 단순히 “빠르게”가 아니라, 운영 리스크를 제어하는 것이다.

### 4.1 배포 목표

- 프런트 단독 배포 체감 시간을 현재 대비 크게 단축
- 백엔드 재배포 시 캐시 적중률을 높여 의존성 재설치를 최소화
- 모델 교체와 앱 코드 배포를 가능한 한 분리
- 재기동 시 migration 때문에 readiness가 불필요하게 늦어지지 않도록 개선

### 4.2 런타임 목표

- 봇전 관전 모드의 턴 간 대기 시간을 눈에 띄게 감소
- 혼합 게임에서는 “너무 빨라서 읽기 어려운” 회귀를 막음
- 첫 턴 spike, WebSocket fan-out, replay payload 비대화를 줄임
- 현재의 정합성 보장(로그/리플레이/복구 가능성)은 유지

---

## 5. 권장 설계

## 5.1 1순위: 거의 무위험, 바로 적용 가능한 배포 최적화

### 1) `frontend/.dockerignore` 추가

**권장 내용**

- `node_modules`
- `dist`
- `.git`
- `.DS_Store`
- `coverage`
- `*.log`

**기대 효과**

- 프런트 빌드 컨텍스트를 대폭 축소
- 로컬 환경에 따라 100MB 이상 전송 감소 가능
- 프런트 Docker 빌드 체감 시간 단축

**리스크**

- 매우 낮음
- Dockerfile이 `npm ci`를 사용하므로 런타임 동작에 영향 없음

### 2) 프런트는 가능하면 Vercel, 백엔드는 Render/Docker로 분리

현재 구조상 프런트는 정적 SPA이고 실제 빌드가 1초 내외이므로, Docker로 계속 묶는 것보다:

- 프런트: Vercel
- 백엔드: Render Web Service 또는 별도 Docker 호스팅

로 분리하는 것이 배포 속도와 운영 단순성 모두에 유리하다.

**기대 효과**

- 프런트 배포가 사실상 “정적 파일 업로드” 수준이 됨
- 백엔드 장애와 프런트 배포를 분리 가능

**리스크**

- CORS, `VITE_BACKEND_ORIGIN`, WebSocket origin 설정만 정확히 맞추면 낮음

## 5.2 2순위: 백엔드 이미지 슬림화

### 3) `PuCo_RL` 전체 복사 대신 serving subset만 포함

현재는 `COPY PuCo_RL /PuCo_RL`로 전체 디렉터리를 넣는다. 그러나 실제 서빙에는 보통 아래 범위만 필요하다.

- adapter가 참조하는 모듈
- env/game constants
- agent inference 코드
- 선택된 bundle/checkpoint

따라서 중기적으로는 다음 두 방식 중 하나로 가는 것이 좋다.

**안 A. serving 전용 서브셋 디렉터리 생성**

- 예: `PuCo_RL_serving/`
- 추론에 필요한 모듈과 manifest/checkpoint만 복사

**안 B. 모델 번들 자체를 self-contained artifact로 재구성**

- bundle 내부에 필요한 adapter metadata와 checkpoint를 함께 두고
- 백엔드 이미지는 bundle loader만 보유

**기대 효과**

- backend build context 축소
- image size 축소
- 모델 교체 시 영향 범위 축소

**리스크**

- import 경로와 adapter dependency를 정확히 파악해야 함
- 서빙 smoke test가 반드시 필요

### 4) 의존성 레이어를 “거의 안 바뀌는 베이스 이미지”로 분리

현재 가장 비싼 단계는 `uv pip install --system --no-cache -r requirements.txt`다.
특히 `torch`, `torchvision`은 캐시가 깨졌을 때 체감 비용이 매우 크다.

**권장안**

- `backend/Dockerfile.base` 또는 GHCR base image 운용
- Python + torch 계열 + OS 패키지까지 묶은 base image를 주기적으로만 갱신
- 앱 배포 시에는 app code layer만 얹는 형태로 분리

**기대 효과**

- 코드만 바뀌는 일반 배포에서 수 분 단위 절감 가능
- 네트워크 상태 영향을 덜 받음

**리스크**

- 베이스 이미지 관리가 하나 추가됨
- 하지만 운영 배포 빈도가 잦다면 충분히 가치가 큼

## 5.3 3순위: migration 경로 분리

### 5) `entrypoint.sh`의 migration을 release 단계로 분리

현재 구조는 “항상 안전하게 최신 스키마로”라는 장점이 있지만, 아래 단점이 있다.

- 재기동마다 startup 비용 발생
- migration 실패가 곧 앱 기동 실패로 연결
- scale-out 시 동시에 여러 인스턴스가 migration을 시도할 여지

**권장안**

- 배포 전용 migration job 또는 release command 도입
- 앱 컨테이너는 migration 완료 후 서버만 띄우도록 단순화

**적용 원칙**

- 지금 당장 필수는 아니다
- 단일 인스턴스 운영에서는 우선순위가 중간
- 다만 배포 지연과 장애 격리를 위해 중기적으로 분리하는 것이 맞다

## 5.4 4순위: 모델 배포와 앱 배포 분리

### 6) 모델 artifact를 이미지 밖으로 분리

향후 모델이 자주 바뀌거나 여러 champion/candidate를 동시에 써야 한다면, checkpoint를 이미지에 bake-in 하는 방식은 금방 느려진다.

**권장안**

- object storage 또는 persistent disk에 bundle 저장
- 앱은 `bundle_id` 또는 `manifest checksum` 기준으로 로드
- 최초 1회 다운로드 후 로컬 캐시

**기대 효과**

- 모델 교체만으로 전체 앱 재배포하지 않아도 됨
- 롤백이 쉬워짐
- A/B 테스트나 후보 모델 검증이 쉬워짐

**리스크**

- 캐시 무결성, checksum 검증, warm-up 전략이 함께 필요

---

## 6. 실플레이 속도 개선 설계

## 6.1 가장 중요한 개선: 게임 모드별 속도 정책 분리

현재는 기본 지연이 크고, 배속은 `1/2/4` 배율만 제공된다.
이 구조는 “사람이 보는 UX”에는 좋지만 “봇전 관전”과 “빠른 검증”에는 느리다.

### 권장 속도 프로파일

| 모드 | 역할 선택 | 일반 액션 | 목적 |
|---|---:|---:|---|
| 혼합 게임 기본 | 1.2s | 0.6s | 인간이 읽을 수 있는 템포 유지 |
| 봇전 관전 기본 | 0.6s | 0.25s | 흐름은 보이되 답답하지 않게 |
| 봇전 x4 | 0.2s | 0.08s | 빠른 관전 |
| 헤드리스/검증 | 0s | 0s | 자동 평가/스모크 테스트 |

### 설계 원칙

- **사람이 참여한 게임**과 **전원 봇 게임**은 속도 정책을 다르게 둔다.
- 배속 값은 단순 배율보다 “최소 지연 floor”를 함께 둬야 한다.
- 운영 기본값은 보수적으로 시작하고, 봇전에서만 공격적으로 낮춘다.

## 6.2 첫 턴 지연 제거: 비차단 warm-up

현재 adapter runtime과 checkpoint load는 lazy cache 구조라서 방향은 좋다.
다만 첫 PPO 턴에서만 지연이 튈 수 있다.

**권장안**

- 앱 startup 직후 readiness를 막지 않는 background warm-up 수행
- 기본 champion PPO bundle만 선로드
- health check는 warm-up 완료를 기다리지 않음

**기대 효과**

- 첫 봇 턴 latency 안정화
- 관전자 입장에서 “처음만 유난히 느린” 현상 제거

**리스크**

- startup 메모리 사용량이 약간 빨라짐
- 그러나 기본 모델 하나만 warm-up 하면 통제 가능

## 6.3 broadcast 경로 개선

### 1) WebSocket send를 병렬화

현재는 순차 send이므로 느린 connection 하나가 fan-out을 늘릴 수 있다.

**권장안**

- `asyncio.gather(..., return_exceptions=True)` 기반 병렬 전송
- connection별 timeout 또는 실패 카운트 도입

**기대 효과**

- 관전자 수가 늘어도 한 명의 느린 클라이언트가 전체 게임 템포를 늦추는 문제 감소

### 2) Redis publish용 JSON 재사용

현재는 state JSON과 event JSON을 여러 번 직렬화한다.

**권장안**

- 직렬화 payload를 한 번 만들어 재사용
- 필요하면 `orjson` 도입

**기대 효과**

- CPU 절감 자체는 크지 않지만 빈번한 턴 처리에서 누적 이득

## 6.4 replay/log 경량화

### 1) replay에 full `rich_state`를 매 턴 저장하지 않도록 조정

현재 설계는 복구와 디버깅에는 유리하지만, 운영 규모가 커지면 payload 비대화가 빠르게 온다.

**권장안**

- 모든 턴에 full `rich_state` 저장하지 않기
- 다음 중 하나를 선택
  - N턴마다 checkpoint frame만 저장
  - 마지막 state만 저장
  - replay frame에는 compact summary만 저장하고, 상세는 별도 조회

**기대 효과**

- DB JSONB/file write 비용 감소
- replay 조회 속도 개선

**리스크**

- 디버깅 편의성이 일부 줄어들 수 있음
- 따라서 “운영 replay”와 “디버그 replay”를 구분하는 것이 바람직

### 2) ML JSONL과 운영 replay의 책임을 분리 유지

`MLLogger`는 학습 재료 보존이 목적이므로, 이를 무조건 줄이는 것은 신중해야 한다.

**권장안**

- `MLLogger`는 유지
- 대신 replay payload 쪽을 줄이는 방향 우선
- 이후 필요 시 JSONL gzip rotation 또는 비동기 queue flush 도입

## 6.5 복구 경로 최적화

현재는 복구 시 journal을 처음부터 재생한다.
정합성 측면에서는 맞지만, 게임이 길어질수록 reconnect/recovery 시간이 길어진다.

**중기 권장안**

- N revision마다 engine snapshot 저장
- 복구 시 “가장 가까운 snapshot + 이후 journal replay” 방식으로 단축

이 항목은 배포 시간보다 실운영 안정성 개선 성격이 강하므로, 2차 단계로 두는 것이 적절하다.

---

## 7. 현재 구조에서 하면 안 되는 최적화

### 1) `uvicorn --workers`를 쉽게 늘리면 안 된다

현재 `GameService.active_engines`는 프로세스 메모리 기반이다.
즉, worker를 늘리면 게임 상태가 worker별로 분산돼 정합성이 깨질 수 있다.

**결론**

- 지금 아키텍처에서는 `workers=1` 유지가 맞다.
- 성능 문제를 worker 수로 덮는 접근은 금지

### 2) 모든 봇 지연을 0으로 없애면 안 된다

- 인간이 섞인 게임에서는 상태 변화가 너무 빨라 UX가 무너질 수 있다.
- 모드별 속도 정책으로 풀어야 한다.

### 3) 로그 저장을 성급히 전부 비동기 fire-and-forget으로 바꾸면 안 된다

- 현재는 game log와 replay 정합성이 중요하다.
- durability를 잃는 방식은 장애 분석과 recovery 신뢰도를 해칠 수 있다.

---

## 8. 우선순위 제안

## Phase 1. 이번 주 바로 적용

1. `frontend/.dockerignore` 추가
2. 프런트를 가능하면 Vercel 정적 배포로 분리
3. 봇전 관전 기본 지연값 하향 조정
4. PPO runtime background warm-up 도입

**특징**

- 효과 대비 리스크가 낮다
- 코드 복잡도 증가가 작다

## Phase 2. 다음 단계

1. WebSocket broadcast 병렬화
2. replay payload에서 full `rich_state` 저장 전략 축소
3. backend base image 분리
4. migration release 단계 분리

**특징**

- 운영 품질과 체감 속도를 함께 올림
- 검증 범위가 조금 넓어짐

## Phase 3. 구조 개선

1. serving subset/bundle 기반 백엔드 이미지 재구성
2. 모델 artifact 외부화
3. recovery snapshot 도입

**특징**

- 장기 운영/여러 모델 실험에 유리
- 설계와 테스트가 더 필요

---

## 9. 권장 검증 지표

최적화 후에는 아래를 반드시 수치로 확인해야 한다.

### 배포 지표

- 프런트 배포 시작부터 사용자 접속 가능까지의 시간
- 백엔드 이미지 빌드 시간
- 백엔드 cold start 시간
- migration 수행 시간

### 런타임 지표

- 첫 PPO 봇 턴 latency
- 일반 봇 턴 평균 latency
- Redis publish부터 프런트 state 반영까지의 지연
- replay payload 크기 증가량
- 게임 종료 시점의 DB/replay write 시간

### 운영 안정성 지표

- health check 실패율
- reconnect/recovery 성공률
- bot stall watchdog 발생 횟수
- WebSocket send 실패율

---

## 10. 최종 권고안

현 시점에서 가장 좋은 전략은 아래와 같다.

### 배포

- 프런트는 **Vercel 정적 배포**로 분리
- 백엔드는 **Docker 유지**, 대신
  - 프런트 `.dockerignore` 추가
  - backend dependency/base image 캐시 전략 도입
  - 중기적으로 `PuCo_RL` serving subset만 이미지에 포함

### 플레이 속도

- 혼합 게임은 읽을 수 있는 템포 유지
- 봇전 관전만 공격적으로 빠르게
- 첫 모델 로딩은 warm-up으로 숨기기
- replay와 WebSocket 경로는 점진적으로 경량화

이 방향이 현재 Castone의 아키텍처 제약을 존중하면서도, **배포 속도와 체감 플레이 속도를 동시에 개선하는 가장 현실적인 경로**다.
