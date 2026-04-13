# 02. Non-Functional Requirements (NFR)

**이 문서가 존재하는 이유**: "얼마나 빠르게", "얼마나 안정적으로", "얼마나 안전하게" 같은 정량 기준이 없으면 라이트사이징·모니터링·알림 임계치를 정할 수 없다. 여기에 박힌 숫자가 **Phase 5 (라이트사이징), Phase 6 (MLOps 대시보드), Phase 12 (런북 알림 정책)** 의 기준이 된다.

---

## 총괄 테이블

| 카테고리 | 항목 | 목표 값 | 측정 방법 |
|---|---|---|---|
| **성능** | 페이지 로드 (LCP) | < 3초 | Chrome Lighthouse 실측, 분기당 1회 |
| | API p50 | < 150ms | Grafana Prometheus `histogram_quantile(0.5, ...)` |
| | API p95 | < 500ms | Grafana Prometheus `histogram_quantile(0.95, ...)` |
| | API p99 | < 1,500ms | Grafana Prometheus `histogram_quantile(0.99, ...)` |
| | WebSocket 메시지 | < 100ms (로컬 네트워크 기준) | 직접 계측 어려움, 체감 기준 |
| **규모** | 동시 사용자 (평시) | 1~5명 | Grafana `castone_active_sessions` gauge |
| | 동시 사용자 (홍보 피크) | 30명 내외 | 피크 시 측정 |
| | 동시 게임 | 평시 1~3, 피크 10 | Grafana `castone_active_games` gauge |
| | 일일 총 게임 수 | 10~100 | Grafana Postgres 쿼리 |
| **가용성** | 가용성 목표 | **99%** (월 다운타임 7.2시간 허용) | UptimeRobot 월 리포트 |
| | 계획된 배포 다운타임 | 허용 (재시작 시 ~30초) | 자체 측정 |
| | RTO (복구 시간 목표) | 30분 | 분기당 1회 리허설 |
| | RPO (데이터 손실 허용) | 24시간 (pg_dump 일 1회) | 백업 스케줄 검증 |
| **신뢰성** | 백엔드 OOM kill 빈도 | 0회/월 | `docker events` 또는 Grafana |
| | 5xx 에러 비율 | < 0.5% | Grafana API 지표 |
| | Cloudflare Tunnel 재연결 | 드물게 허용 | Cloudflare 대시보드 |
| **보안** | HTTPS 강제 | 100% (HTTP는 자동 리다이렉트) | Cloudflare TLS 모드 "Full (strict)" |
| | 시크릿의 git 저장 | 금지 | 커밋 훅 `gitleaks`, 코드리뷰 |
| | DB/Redis 공인 노출 | 금지 (내부 Docker 네트워크만) | `docker-compose.prod.yml` 검증 |
| | SSH 접근 제한 | 본인 IP만 또는 IAP 터널 | GCP 방화벽 규칙 |
| | Secret Manager 접근 | Workload Identity만, 키 파일 없음 | IAM 바인딩 검증 |
| | OAuth 인증 | Google 로그인만, 자체 비밀번호 없음 | 코드 검토 |
| **관측성** | 메트릭 수집 간격 | 15초 | Prometheus scrape interval |
| | 로그 보존 (운영) | 7일 (Grafana Cloud Free 한도) | Loki 보존 정책 |
| | 로그 보존 (게임/리플레이) | 영구 (GCS Standard) | GCS Lifecycle |
| | 다운 알림 도달 시간 | < 5분 (UptimeRobot 주기) | UptimeRobot 설정 |
| **비용** | 월 총 지출 상한 | 30,000원 | GCP Billing Alert |
| | 평시 월 지출 | ~27,000원 | 월말 수동 확인 |
| **유지보수** | 시크릿 로테이션 주기 | 분기 1회 (3개월) | 캘린더 알림 |
| | 백업 복원 리허설 | 분기 1회 | 캘린더 알림 |
| | OS / Docker 이미지 보안 업데이트 | 주 1회 자동 (unattended-upgrades) | VM cron |

---

## 세부 근거와 주의사항

### 성능 (Performance)

**API p95 < 500ms** 근거:
- e2-small(0.5~2 vCPU burst)에서 FastAPI + PuCo_RL 봇 추론이 같은 VM에서 돌아감
- PuCo_RL 추론이 CPU에서 모델 forward 한 번당 수십~수백 ms 예상
- 사람 턴 API는 DB 쿼리만 하므로 100ms 내외 예상
- **p95 기준은 "사람이 체감하기에 빠르다"는 수준**이지 상용 기준은 아님
- 초과 시 대응: 봇 추론을 별도 worker 프로세스로 분리 (라이트사이징과 충돌, 권장 안 함) → e2-medium 승격

**WebSocket 메시지 < 100ms**:
- 게임 턴 진행을 WebSocket으로 푸시한다고 가정 (현재 구현 확인 필요)
- Cloudflare Tunnel 경유해도 Seoul 리전 ↔ 국내 유저 간 레이턴시는 낮음
- 봇 추론 시간은 별도 (이건 "생각 중..." 인디케이터로 커버)

### 규모 (Scale)

**평시 1~5명 vs 피크 30명**:
- 큰 편차지만, 이게 동아리 홍보 시나리오의 현실
- **e2-small은 30명을 여유 있게 못 감당**할 수 있음. 피크 시 API p95가 2배 정도 느려지는 것을 허용
- **피크 대응 플랜**: 홍보 당일 e2-medium으로 임시 승격 → Terraform `machine_type = "e2-medium"` 한 줄 변경 + `terraform apply` → 다음 날 되돌림
- 이 절차는 [12_runbook.md](./12_runbook.md) 에 명시

**일일 게임 10~100**:
- 게임 이벤트 테이블(`game_events`)의 행 증가 속도 추정용
- 한 게임당 턴 수 × 이벤트 수 ≈ 100~300 이벤트 가정
- 최대치: 100게임 × 300 = 30,000 행/일, 월 약 90만 행
- Postgres 1년 누적 약 1,000만 행 → 여전히 작음. **아카이빙 불필요**

### 가용성 (Availability)

**99% 목표 근거**:
- 99.9% (월 44분)는 포트폴리오/동아리엔 과투자
- 99% (월 7.2시간)면 여유 있게 달성 가능
- 의도적 재배포 시간이 월 몇십 분 ~ 1시간이라 99%에 수렴

**RTO 30분 근거**:
- "VM 완전 손실 → Terraform apply → GCS에서 백업 복원 → 이미지 pull → 컨테이너 기동"
- 각 단계가 약 3~5분. 합산 15~25분. 여유 5분 포함 30분
- 리허설로 검증한 수치가 30분 초과하면 목표를 50분으로 조정

**RPO 24시간 근거**:
- pg_dump가 일 1회 (새벽 4시) 실행 → 최악의 경우 24시간 분 데이터 손실
- 리플레이 로그는 GCS에도 실시간 업로드하는 옵션이 있으나 복잡도↑
- **트레이드오프**: RPO 1시간 원하면 pg_dump를 매시간 실행 → GCS 스토리지와 전송 비용↑, 여전히 수천원 수준이라 여력 있으면 가능
- **결정**: 24시간 유지. 필요 시 Phase 10 (운영 개선) 에서 재검토

### 신뢰성 (Reliability)

**OOM kill 0회/월**:
- 라이트사이징(Phase 5)이 잘못되면 쉽게 발생
- Grafana 알림: `increase(container_oom_kill_count[1h]) > 0` → 즉시 Telegram
- 발생 시 해당 서비스의 `mem_limit` 즉시 상향 + `--workers`, `shared_buffers` 등 튜닝 재검토

**5xx < 0.5%**:
- 실수로 깨진 마이그레이션, 외부 API 장애(Google OAuth), 봇 추론 예외 등
- Grafana 대시보드에 상시 게이지
- 0.5% 초과 시 자동 알림은 설정 안 함 (노이즈 많음). 수동 확인

### 보안 (Security)

**HTTPS 100%**:
- Cloudflare "Full (strict)" 모드: 엣지-오리진 간에도 TLS 필요
- Cloudflare Tunnel은 기본적으로 암호화되므로 이 조건 자동 충족
- HTTP 접근은 Cloudflare가 자동 301 리다이렉트

**시크릿 git 저장 금지**:
- `gitleaks` pre-commit hook 설정 권장
- `.env`, `.env.prod`, `secrets.json` 같은 이름은 `.gitignore` 포함
- 실수로 커밋된 경우: BFG 또는 `git filter-repo` 로 히스토리 정리 + 해당 시크릿 즉시 회전

**SSH 접근 제한**:
- **옵션 A (권장)**: GCP 방화벽 규칙 `source_ranges = [본인 공인 IP/32]`. 단점: 본인 IP 바뀌면 수동 갱신
- **옵션 B**: IAP 터널 (`gcloud compute ssh --tunnel-through-iap`). 본인 IP 무관, 구글 계정 기반 인증
- **결정**: B 선호 (포트폴리오 어필 포인트). 단, 첫 배포 때는 A로 시작해도 됨

### 관측성 (Observability)

**수집 간격 15초**:
- Prometheus 기본값 1분 → 너무 성김. 15초로 설정
- node-exporter, promtail의 scrape interval 동일
- Grafana Cloud Free의 10k active series 한도: 서비스 4개 × 메트릭 ~50개 × labels ~5 = ~1000 series, 여유 충분

**로그 보존 (운영) 7일**:
- Grafana Cloud Free 한도 (50GB) 안에서 충분
- 중요: **게임 이벤트 로그를 Loki로 보내면 안 됨**. Postgres + GCS에만 저장
- promtail 설정에서 `/data/logs/games/` 경로 필터로 제외

### 비용 (Cost)

상세는 [13_cost_model.md](./13_cost_model.md).

### 유지보수 (Maintenance)

**시크릿 로테이션 분기 1회**:
- Workload Identity Federation 덕에 GitHub→GCP 인증 키는 로테이션 불필요 (자동)
- 로테이션 대상: `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `SECRET_KEY`, `INTERNAL_API_KEY`, `CLOUDFLARE_TUNNEL_TOKEN`
- 절차: Secret Manager에 새 버전 추가 → VM 재시작 → 이전 버전 비활성화
- 캘린더 알림: 2026-07-10, 2026-10-10, 2027-01-10, ...

**백업 복원 리허설 분기 1회**:
- 실제 프로덕션 DB를 임시 sandbox VM에 복원 → 행 수 확인 → 삭제
- 복원 실패하는 백업은 백업이 아니다 (유명 격언)
- 리허설 결과를 [12_runbook.md](./12_runbook.md) 하단에 로그로 기록

**OS/Docker 보안 업데이트**:
- VM에 `unattended-upgrades` 설치 (Ubuntu/Debian)
- Docker 이미지는 `backend/Dockerfile.prod` 의 base `python:3.12-slim`이 자동 업데이트되지 않음 → **월 1회 Actions에서 `--no-cache` 빌드 강제**로 해결
- 또는 Dependabot / Renovate 설정 (포폴 어필 추가)

---

## NFR 위반 시 에스컬레이션 정책

| 위반 항목 | 심각도 | 자동 알림? | 대응 시한 |
|---|---|---|---|
| `/health` 다운 | 🔴 Critical | UptimeRobot → 이메일 + Telegram | 즉시 (< 1h) |
| OOM kill 발생 | 🟠 High | Grafana → Telegram | 24h 이내 |
| p95 > 1,000ms (1시간 이상) | 🟡 Medium | Grafana → 이메일 | 48h 이내 |
| 월 지출 80% 도달 | 🟠 High | GCP Billing → 이메일 | 24h 이내 |
| 월 지출 100% 초과 | 🔴 Critical | GCP Billing → 이메일 + Telegram | 즉시 조사 |
| 5xx > 1% (1시간) | 🟡 Medium | Grafana → 이메일 | 48h 이내 |
| 디스크 사용률 > 85% | 🟠 High | Grafana → 이메일 | 24h 이내 |
| 디스크 사용률 > 95% | 🔴 Critical | Grafana → Telegram | 즉시 |
| 백업 실패 (연속 2회) | 🟠 High | cron → 이메일 | 24h 이내 |

**대응 시한이 지켜지지 않아도 괜찮음**. 이건 상용 SLA가 아니라 본인 운영 가이드라인이다. 다만 **위반 로그를 남겨서 분기 회고 때 패턴을 본다**.

---

## 변경 정책

NFR 수치를 바꿀 때는:
1. 여기서 먼저 수정
2. 변경 사유를 하단 "변경 이력"에 기록
3. 영향받는 다른 문서(알림 설정, 런북)에 반영

수치의 자의적 변경을 막기 위해 **라이브 데이터 2주 이상 관찰 후에만 완화**한다.

### 변경 이력

| 일자 | 항목 | 이전 → 이후 | 사유 |
|---|---|---|---|
| 2026-04-10 | 초안 | N/A | 브레인스토밍 13라운드 Q12 합의 |
