# 03. Decision Log

**이 문서가 존재하는 이유**: 설계서는 "무엇을 한다"만 쓰고, **"왜 그걸 골랐는지"** 는 브레인스토밍 대화에 묻혀 사라진다. 나중에 "왜 Kubernetes 안 쓰고 단일 VM?" 같은 질문이 나왔을 때 **대답이 여기 있어야 한다**. 리뷰어·면접관·미래의 본인을 위한 참조 문서다.

각 결정은 다음 구조로 기록된다:

- **Decision**: 무엇을 결정했는가
- **Context**: 왜 이 결정이 필요했는가
- **Alternatives**: 대안들
- **Why this option**: 왜 이걸 골랐는가
- **Consequences**: 이 결정이 만드는 제약과 트레이드오프
- **Revisit triggers**: 어떤 신호가 있으면 이 결정을 재검토할지

---

## Decision 1: 배포 규모 / 목적 = A~B (동아리 홍보 + 포트폴리오)

**Context**: 배포 형태 전체(클라우드, DB, 관측성)를 좌우하는 1차 질문. "혼자 데모 vs 베타 vs 프로덕션" 중 어디냐에 따라 아키텍처가 전면 달라진다.

**Alternatives**:
- A. 개인/지인 데모 (≤5명)
- **B. 소규모 베타 (10~50명)**
- C. 본격 프로덕션 (100명+)
- D. 혼자만 쓰는 내부 학습 환경

**Why this option**: 과동아리 홍보 대상이므로 A~B 스펙트럼. 데이터 보존은 필수(실제 유저 기록), 하지만 HA/SLA는 과투자.

**Consequences**:
- 관리형 DB를 쓰지 않아도 됨 (Decision 2)
- 단일 VM으로 충분 (Decision 3)
- 스테이징 환경 생략 가능 (Decision 12)
- 피크 트래픽은 일시적 VM 승격으로 대응 (런북 명시)

**Revisit triggers**:
- 월간 활성 유저 > 100명
- 동시 게임 수 > 10개가 상시화
- SLA 요구 발생 (예: 학교 프로젝트 평가용)

---

## Decision 2: DB 전략 = 컨테이너 Postgres + GCS 자동 백업

**Context**: TODO 4번 첫 항목이 "외부 DB 서버가 필요한지 결정". A~B 규모에서 관리형 DB는 과투자지만, 컨테이너 DB는 데이터 손실 위험.

**Alternatives**:
- A. 컨테이너 Postgres, 백업 없음
- **B. 컨테이너 Postgres + `pg_dump` → GCS 자동 백업**
- C. 관리형 DB (Cloud SQL)
- D. Supabase 무료 티어

**Why this option**:
- 월 비용 수백 원만 추가 (GCS 스토리지)
- 데이터 손실 리스크 제거
- 나중에 관리형 DB로 이전 시 백업 파일 그대로 import 가능 (락인 無)
- 포폴 스토리: "RPO 24시간 목표로 pg_dump 기반 백업 파이프라인 구축, 분기 1회 복원 리허설"

**Consequences**:
- 백업 복원은 수동 절차 (런북 필수)
- VM 디스크 손실 시 최대 24시간 데이터 손실 (RPO 24h)
- `pg_dump` 중 DB 부하 (새벽 4시 스케줄로 완화)

**Revisit triggers**:
- 유저가 100명 초과
- RPO 24시간이 부족하다는 요구 발생
- 백업/복원 리허설이 반복적으로 실패

---

## Decision 3: 클라우드 플랫폼 = GCP e2-small (Seoul)

**Context**: 저렴한 인프라 + 포폴 어필 + 로컬 레이턴시 균형.

**Alternatives**:
- A. Oracle Cloud Free Tier (영구 무료)
- **B. GCP e2-small (Seoul)**
- C. AWS t4g.small (ARM)
- D. 국내 VPS
- E. Fly.io

**Why this option**:
- 팀 컨벤션이 GCP
- 한국 리전 있어 레이턴시 최적
- AWS 미경험, 학습 부담
- Oracle Free Tier는 정책 변경 리스크와 재고 불확실
- $300 크레딧으로 첫 90일 사실상 무료

**Consequences**:
- 12개월 프리티어 만료 후 월 ~18,000원 고정비
- x86 기반이라 Mac(Apple Silicon) 크로스 빌드 설정 필요 없음 (Actions에서 빌드하므로 어쨌든 무관)
- AWS 경험 부재는 별도 사이드 프로젝트로 보완 가능

**Revisit triggers**:
- GCP 과금이 상한 초과
- 팀 합류자가 AWS 선호
- 프리티어 만료 시점에 대체 검토

---

## Decision 4: 배포 흐름 = GHCR + GitHub Actions (C), 이후 태그 릴리즈 (D)로 진화

**Context**: "git을 활용해 CI/CD 사이클 만들기" (TODO 4번). e2-small에서 직접 빌드하면 OOM 위험.

**Alternatives**:
- A. 완전 수동 (`docker save` + `scp`)
- B. VM에서 `git pull` + 빌드
- **C. GitHub Actions → GHCR → VM pull & up**
- D. C + 태그 기반 릴리즈 게이트
- E. Cloud Build + Cloud Run

**Why this option**:
- VM 빌드는 2GB RAM에서 OOM 직행
- A/B는 포폴 가치 약함
- E(Cloud Run)는 현재 아키텍처(웹소켓, 장기 세션, 컨테이너 Postgres)와 궁합 나쁨
- C는 분량과 어필 사이 스위트 스폿
- D는 C 안정화 후 자연스럽게 얹을 수 있는 "보너스 레벨"

**Consequences**:
- GHCR 사용으로 repo가 public이어야 무료 (포폴 공개 의도와 일치)
- VM에 배포 트리거 수신 메커니즘 필요 (SSH via WIF + IAP, 또는 polling)
- Actions yaml 유지보수 부담

**Revisit triggers**:
- public repo 전환 불가능해짐 (회사 내부 규정 등)
- 배포 빈도가 일 10회 이상으로 증가 → Cloud Run 재고려

---

## Decision 5: HTTPS / 도메인 = Cloudflare Tunnel + Cloudflare Registrar

**Context**: Google OAuth가 HTTPS를 요구함. 공인 IP 개방은 보안 리스크. certbot 자동 갱신은 실수 여지.

**Alternatives**:
- A. Nginx + Let's Encrypt (certbot)
- B. Caddy 리버스 프록시
- **C. Cloudflare Tunnel (cloudflared)**
- D. GCP HTTPS Load Balancer

**Why this option**:
- VM에 공인 IP/열린 포트 불필요 → SSH 외에 공격 표면 없음
- 무료 (Tunnel, DNS, TLS 전부)
- Cloudflare가 DDoS·캐싱·방화벽 덤으로 제공
- 포폴 어필: "제로 트러스트 터널로 VM 포트 0개 개방"
- 배포 초심자에게 certbot 갱신 실수 여지 제거

**Consequences**:
- Cloudflare 의존성 (장애 시 전체 다운)
- Tunnel 재연결 이슈 드물게 발생 가능 (재기동으로 해결)
- 도메인은 별도 구매 (Cloudflare Registrar .com 약 14,000원/년)
- 대시보드 일부 클릭 필요 (Terraform provider로 일부 자동화 가능)

**Revisit triggers**:
- Cloudflare 장애가 반복적으로 서비스에 영향
- DDoS 공격 패턴이 Tunnel로 커버 안 되는 형태
- 규모 커져서 로드밸런서 필요

---

## Decision 6: 모델 전달 = GCS + entrypoint 다운로드 (Workload Identity)

**Context**: 현재 `Dockerfile.prod`가 `COPY PuCo_RL /PuCo_RL` 로 모델을 이미지에 번들링. 모델 교체 = 이미지 재빌드, 500MB+ 이미지가 GHCR과 GitHub Actions 캐시 한도 압박.

**Alternatives**:
- A. 현재 상태 유지 (이미지 번들)
- **B. 엔진 코드만 이미지, 모델은 GCS에서 다운로드**
- C. GCS Fuse 마운트
- D. 모델을 이미지 태그로 버전 고정
- E. VM 볼륨 + 수동 업로드

**Why this option**:
- "PuCo_RL 폴더 건드리지 마" 제약 → 내부 구조 수정 불가, 하지만 `.dockerignore`로 모델만 제외하는 건 PuCo_RL 수정 아님
- 이미지 크기 500MB → ~100MB 대로 축소
- 모델 업데이트가 재시작만으로 가능
- **Windows 한글 경로 이슈와 자동 해결** (파일시스템 의존 사라짐)
- Workload Identity로 키 파일 불필요 (포폴 어필)
- GCS 스토리지 비용 무시 가능 (수백 원/월)

**Consequences**:
- VM 첫 기동 시 모델 다운로드 지연 → HEALTHCHECK `start_period` 20s → 60s로 완화
- `entrypoint.sh`에 `gsutil` 또는 Python GCS 클라이언트 의존성 추가
- PuCo_RL 팀이 GCS 버킷에 직접 업로드하는 워크플로 수용 필요

**Revisit triggers**:
- 모델 파일이 GB 단위로 커져서 GCS 전송이 VM 시작을 지연시킴
- PuCo_RL 팀이 GCS 대신 다른 채널을 선호

---

## Decision 7: IaC = Terraform (GCP + Cloudflare provider, GCS backend)

**Context**: "클릭 배포 vs 코드 배포"는 포폴 어필도에서 가장 큰 갭 중 하나.

**Alternatives**:
- A. GCP 콘솔 클릭
- B. `gcloud` CLI 스크립트
- **C. Terraform**
- D. Pulumi / CDK

**Why this option**:
- 포폴 ROI 최고 (채용 시장에서 Terraform은 거의 표준)
- 리소스 양이 작아서(50~80줄) 학습 부담 현실적
- 실수 복구 쉬움 (`destroy` + `apply`)
- Cloudflare provider로 터널 설정까지 코드화 가능
- `terraform plan` PR 코멘트로 인프라 변경도 GitOps화 가능

**Consequences**:
- Terraform state 저장소 필요 → GCS backend (닭/달걀 문제는 부트스트랩 스크립트로 해결)
- 복수 provider 관리 복잡도 (gcp, cloudflare) → 디렉토리 분리로 완화
- 초기 러닝커브 2~4시간

**Revisit triggers**:
- 멀티 클라우드 요구 발생 → Pulumi 재검토
- Terraform state corruption 반복 발생

---

## Decision 8: 시크릿 관리 = GCP Secret Manager + Workload Identity / WIF

**Context**: 시크릿이 로컬/CI/VM 3곳에 존재해야 하고, 키 파일 관리가 가장 큰 보안 부채.

**Alternatives**:
- A. GitHub Secrets + VM `.env` 수동 복사
- **B. GCP Secret Manager + WIF**
- C. SOPS + age
- D. Hashicorp Vault

**Why this option**:
- Decision 6의 Workload Identity를 그대로 재사용
- `.env` 파일이 VM에 영구 저장되지 않음 (기동 시 생성)
- Secret 로테이션이 단순 (버전 추가 + VM 재시작)
- Terraform으로 "시크릿 존재"만 관리, 값은 수동 주입 → git에 값 없음
- 무료 한도(6 active versions, 10k ops/month) 안
- 포폴 어필: "Workload Identity Federation으로 키 파일 없는 시크릿 관리"

**Consequences**:
- 첫 시크릿 값 주입은 수동 1회 작업
- GitHub Actions가 GCP에 접근할 때 OIDC federation 설정 필요 (1회성)
- 로컬 dev는 여전히 `.env` 파일 기반 (의도적 단순화)

**Revisit triggers**:
- 시크릿 수가 50개 초과 → Vault 재고려
- 로컬 dev에서도 중앙화 요구

---

## Decision 9: 관측성 = UptimeRobot + Grafana Cloud Free

**Context**: "배포했다" 와 "관측하고 있다" 사이의 갭이 포폴에서 큰 차이를 만듦.

**Alternatives**:
- A. 아무것도 안 함 (`docker logs`)
- B. 헬스체크 + UptimeRobot만
- **C. Grafana Cloud Free (Prometheus + Loki + Grafana)**
- D. GCP Cloud Logging + Cloud Monitoring
- E. 자체 Prometheus/Grafana를 VM에 설치

**Why this option**: B + C 병행
- B: 외부 헬스 폴링 (VM 자체가 죽어도 알림 받음)
- C: 앱 메트릭, 로그, 대시보드 (포폴 시각적 임팩트)
- E는 단일 VM 안티패턴 (VM 죽으면 관측도 죽음)
- D는 GCP 로깅 과금 위험
- 우리 규모에서 Grafana Cloud Free 한도 넘지 않음

**Consequences**:
- promtail + node-exporter 컨테이너 추가 → 메모리 ~100MB 소비
- 백엔드에 `/metrics` 엔드포인트 필요 (`prometheus-fastapi-instrumentator` 한 줄)
- 게임 이벤트 로그는 Loki로 보내지 않음 (용량 폭증 방지)
- 외부 서비스 의존 (Grafana Cloud, UptimeRobot)

**Revisit triggers**:
- Grafana Cloud Free 한도 초과
- 외부 서비스 신뢰성 저하
- 자체 Prometheus가 필요한 규모

---

## Decision 10: VM 사이즈 = e2-small + 공격적 라이트사이징

**Context**: 현재 `docker-compose.prod.yml`의 `mem_limit` 합계가 3.15GB인데 e2-small은 2GB. **지금 그대로 올리면 즉시 OOM**.

**Alternatives**:
- **A. e2-small + 라이트사이징 (목표 총 1.5GB)**
- B. e2-medium 승격 (4GB RAM)
- C. e2-custom-2-3072 (3GB)
- D. Redis 제거 (코드 리팩토링)
- E. VM 2대 분리

**Why this option**:
- 비용 최저 (월 ~18,000원)
- "2GB에 풀스택 + MLOps + 관측성 꾸겨넣기" 자체가 엔지니어링 스토리
- 실패 시 e2-medium 승격은 Terraform 한 줄 10분 작업
- 피크 대응은 일시 승격으로 커버 (런북 명시)

**Consequences**:
- Postgres, Redis, uvicorn 각각 세밀한 튜닝 필요
- 동시 30명 피크에서 p95 악화 허용
- OOM 발생 가능성 상시 → Grafana 알림 필수

**Revisit triggers**:
- OOM이 주당 1회 이상 발생
- p95가 500ms 상한을 2주 연속 초과
- 피크 트래픽이 상시화

---

## Decision 11: 크로스 OS = 로컬은 Mac/WSL2만 권장

**Context**: TODO 4번 2항목 "window ↔ mac 환경 차이와 한국어 이름 모델 경로 문제".

**Alternatives**:
- A. Windows 네이티브 완전 지원
- B. WSL2 사용 요구
- **C. 배포 성공 후 자동 해소에 의존 (로컬 Windows 개발은 비공식)**

**Why this option**:
- 본인 개발 환경은 Mac, 팀원도 Ubuntu로 전환 완료
- 배포되면 사용자는 브라우저로만 접근 → 로컬 빌드 불필요
- Windows 네이티브 지원은 공수 대비 가치 낮음

**Consequences**:
- Windows 팀원이 생기면 WSL2 사용 권장 (README 명시)
- `.editorconfig`와 `.gitattributes` (EOL LF 강제)는 기본 포함
- 경로 이슈는 GCS 모델 다운로드(Decision 6)로 자동 해결

**Revisit triggers**:
- Windows 네이티브 개발자가 합류

---

## Decision 12: 스테이징 환경 = 없음

**Context**: "staging → prod" 2단계 파이프라인은 표준이지만, 단일 인원/A~B 규모에서는 과투자.

**Alternatives**:
- A. 상시 스테이징 VM
- B. Ephemeral PR 환경 (PR당 임시 VM)
- **C. 없음. PR CI + 태그 릴리즈로 대체**

**Why this option**:
- VM 비용 × 2
- 단일 인원이 스테이징과 prod를 관리하는 부담
- PR CI에서 docker compose 헬스체크만 돌려도 "작동 여부"는 검증됨
- Phase D 태그 릴리즈 도입 후에는 `main`이 사실상 스테이징 역할

**Consequences**:
- 마이그레이션 사고가 prod에서 발견될 가능성
- 대응책: **additive-only 마이그레이션 원칙** 명시 (런북)
- 큰 리팩토링은 feature flag 활용

**Revisit triggers**:
- 팀 규모 > 3명
- 마이그레이션 사고 월 1회 초과

---

## Decision 13: 롤백 전략 = 이미지 태그 되감기 (환경변수 주입)

**Context**: 배포 사고 시 복구 방법이 정해져 있어야 함.

**Alternatives**:
- A. 수동 `docker run` 이전 태그
- **B. Compose 파일 이미지 태그를 환경변수로 → `BACKEND_TAG=v1.2.2` 변경 + 재시작**
- C. Helm / Argo Rollbacks (K8s 필요, 과투자)

**Why this option**:
- 가장 단순
- 이미지 불변성 보장 (같은 태그 = 같은 아티팩트)
- git 태그 = 이미지 태그 매핑으로 추적 가능

**Consequences**:
- DB 마이그레이션 롤백은 별도 이슈 → additive-only 원칙
- 태그 관리 실수 가능 → CI가 `:<git-sha>`와 `:latest` 동시 푸시, 릴리즈 시 `:v1.2.3` 추가

**Revisit triggers**:
- 롤백이 자주 발생
- 스키마 마이그레이션 사고가 여러 번 발생

---

## Decision 14: 게임 식별자 = ULID + slug + title 3-레이어

**Context**: 리플레이 UI에서 `game_id`로 게임을 선택하는데, 사람이 ID만 보고 어떤 게임인지 알아야 한다는 요구.

**Alternatives**:
- A. UUID만
- B. Slug만 (UUID 없이)
- **C. ULID (internal) + slug (human) + title (optional)**
- D. 순번 + 시맨틱 접미사

**Why this option**:
- ULID는 시간 정렬 가능 + 충돌 없음 + URL-safe
- Slug는 사람이 목록에서 스캔 가능 (`20260410-bot-seungmun-vs-ppo81k-8rky`)
- Title은 유저가 "내가 첨으로 이긴 날" 처럼 의미 부여 가능
- 닉네임 변경이 과거 slug에 영향 없음 (스냅샷)

**Consequences**:
- 스키마에 컬럼 3개 필요
- slug 생성 규칙과 handle 로마자 변환 로직 필요 (`korean-romanizer`)
- 자세한 내용은 [06_game_id_design.md](./06_game_id_design.md)

**Revisit triggers**:
- slug 충돌이 대시 폴백으로 해결 안 되는 수준
- 한글 유지 요구

---

## Decision 15: 게임 이벤트 저장 = Postgres `game_events` 테이블

**Context**: 리플레이 재생과 MLOps 분석의 데이터 소스. Postgres vs GCS JSONL.

**Alternatives**:
- A. Postgres `game_events` 테이블
- B. GCS JSONL 파일 (게임당 1 파일)
- C. 하이브리드 (Postgres 최근 + GCS 아카이브)

**Why this option**:
- 리플레이 재생이 인덱스 쿼리 한 방으로 빠름
- MLOps 집계 쿼리도 SQL로 직접
- 1년 누적 ~1,000만 행은 Postgres에 여전히 작음
- GCS는 백업 매체로만 활용

**Consequences**:
- DB 크기 증가 → 백업 크기 증가 (GCS 비용 미미)
- 아주 큰 이벤트(예: 게임 상태 스냅샷)는 JSONB로 저장
- 1년 이후 아카이빙 정책 재검토 필요 (Phase 10)

**Revisit triggers**:
- 이벤트 테이블이 1억 행 초과
- 쿼리 지연이 눈에 띄게 증가

---

## Decision 16: 리플레이 UI = Phase 7 (배포 이후 분리)

**Context**: TODO 3번 "로그 기반 리플레이 기능"이 배포 트랙에 병합됨.

**Alternatives**:
- A. 배포와 동시에 Phase 6에 포함
- **B. 배포 이후 Phase 7로 분리**

**Why this option**:
- Phase 6(MLOps 데이터 스키마) 가 있으면 Phase 7 재료가 이미 준비됨
- 배포 긴급성이 높으면 Phase 7은 연기 가능
- 독립적 개발/테스트가 가능

**Consequences**:
- 초기 배포 시점에는 "게임 목록만" 있고 재생은 없음
- 리플레이 UI는 프론트엔드 컴포넌트 재사용 (현재 게임 화면을 과거 상태 주입 모드로)

**Revisit triggers**:
- 없음 (이 결정은 일정 조정용)

---

## 결정을 내릴 수 있었던 정보 상태 (Snapshot)

이 결정들이 내려진 시점(2026-04-10)의 **지식 스냅샷**. 나중에 "이 결정이 더 이상 유효한가?"를 판단할 때 참조한다.

- 프로젝트는 Puerto Rico 보드게임 RL 에이전트 실험 플랫폼 (동아리 홍보 겸용)
- 팀원: 본인 1명 + PuCo_RL 팀 (코어 RL 담당)
- 예산: 월 3만원
- 개발 환경: Mac
- 배포 경험: 없음
- 팀 클라우드 컨벤션: GCP
- 현재 코드베이스: React Vite + FastAPI + Postgres 16 + Redis 7, Docker Compose 기반 dev/prod 분리
- 현재 모델: `PPO_PR_Local_20260405_205030_step_81920.pth` (PPO, step 81920)

이 중 하나라도 크게 변하면(예: 팀 5명으로 확대, 월 예산 10만원) 이 설계 전체의 재검토가 필요하다.
