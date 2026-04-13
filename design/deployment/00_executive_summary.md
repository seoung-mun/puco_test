# 00. Executive Summary

**1페이지 요약.** 이 문서 하나만 읽으면 전체 배포 트랙의 뼈대를 이해할 수 있어야 한다.

---

## 무엇을 만드는가

GCP 단일 VM 위에 **Castone (Puerto Rico AI 실험 플랫폼)** 을 배포한다. 단순 웹 배포가 아니라:

1. **웹 서비스**: React SPA + FastAPI + Postgres + Redis, Cloudflare Tunnel 뒤에 HTTPS
2. **모델 레지스트리**: GCS 기반, 사람이 읽을 수 있는 short_code로 식별
3. **추론 측 MLOps**: 모든 게임에 model_id 태깅, Prometheus 메트릭, Grafana 대시보드 (모델별 승률, 역할 선택 분포, 건물 구매 빈도 등)
4. **모델 승격 게이트 (Phase 8)**: 새 candidate 모델이 업로드되면 eval tournament 자동 실행, 승률 기준 통과 시 자동 promotion
5. **리플레이 시스템**: 게임 목록에서 `game_id`를 클릭하면 턴별 재생 UI로 관전
6. **IaC**: Terraform으로 VM·네트워크·IAM·Secret Manager·GCS·Cloudflare Tunnel 전부 코드화

이 전부가 **월 3만원 이하** 비용으로 운영 가능하다.

---

## 왜 만드는가

1. **1차 목표**: Puerto Rico를 잘 플레이하는 RL 에이전트를 개선하고, 그 에이전트로 게임 밸런스를 데이터 기반으로 검증
2. **2차 목표**: 과동아리 홍보 채널 + 포트폴리오 어필
3. **부수 효과**: 실제 인간 대전 데이터가 RL 재학습 소스로 축적됨

---

## 누구를 위해 만드는가

| 유저 그룹 | 규모 | 역할 |
|---|---|---|
| **동아리원** | 5~30명 | 봇/PvP 대전, 데이터 제공 |
| **면접관·채용 리뷰어** | 미정 | 포트폴리오 URL 방문, README 리뷰 |
| **RL 팀** | 1~2명 | 새 모델 GCS 업로드 |
| **운영자(본인)** | 1명 | 배포·관측·사고 대응 전담 |

---

## 핵심 제약

- 💰 **월 3만원 이하** (피크 시 허용)
- 🖐 **배포 초심자** (상세 런북 필수, 단순 패턴 선호)
- 🚫 **PuCo_RL 폴더 수정 금지** (팀 분리)
- 💾 **e2-small 2GB RAM** 하드 제약
- ⏰ 동아리 홍보 시점 전에 최소 배포 성공 필요

---

## Non-Goals (명시적으로 안 하는 것)

- 고가용성(HA) / 다중 리전
- 관리형 DB(RDS/Cloud SQL)
- Kubernetes/ECS/Cloud Run
- 상시 스테이징 환경
- Windows 네이티브 로컬 개발 지원
- 상용 SLA / 24x7 온콜
- 훈련 측(training-side) MLOps (W&B/MLflow 통합 — PuCo_RL 수정 금지 제약)

---

## 아키텍처 한눈에 보기

```
[유저 브라우저]
      │  HTTPS
      ▼
[Cloudflare Edge] ── TLS 종단, DDoS 방어
      │  Cloudflare Tunnel (cloudflared)
      ▼
┌─────────────────────────────────────────────┐
│ GCP VM (e2-small, Seoul, 2GB RAM)           │
│                                             │
│ ┌──────────┐  ┌──────────┐  ┌─────────────┐ │
│ │ frontend │  │ backend  │  │ cloudflared │ │
│ │  (nginx) │  │ (FastAPI │  │  (tunnel)   │ │
│ └────┬─────┘  │ +PuCo_RL)│  └─────────────┘ │
│      │        └────┬─────┘                  │
│      │             │                        │
│      │  ┌──────────┴──────────┐             │
│      │  ▼                     ▼             │
│      │ ┌─────────┐      ┌───────┐           │
│      │ │postgres │      │ redis │           │
│      │ └─────────┘      └───────┘           │
│      │                                      │
│ ┌────┴────────┐  ┌──────────────┐           │
│ │  promtail   │  │ node-exporter│           │
│ └────┬────────┘  └─────┬────────┘           │
└──────┼──────────────────┼───────────────────┘
       │                  │
       ▼                  ▼
  [Grafana Cloud Free]  (metrics, logs, dashboards)
       ▲
       │ 외부 푸시 알림
  [UptimeRobot] ── /health 5분 폴링

[GCS Buckets]
 ├─ castone-models/      (모델 .pth + metadata.json)
 ├─ castone-backups/     (pg_dump 일 1회)
 └─ castone-tfstate/     (Terraform state)

[GitHub] ── Actions: 빌드 → GHCR 푸시 → VM에 SSH로 배포 트리거
    ▲
    │ OIDC (키 파일 없음, Workload Identity Federation)
    ▼
[GCP IAM]
```

---

## 얼마나 걸리는가

| 단계 | 누적 시간 | 결과물 |
|---|---|---|
| Phase 0~5: 최소 배포 성공 | 20~30시간 | HTTPS 도메인으로 웹 접속 가능 |
| Phase 6: MLOps C 최소 | +8~14시간 | 모델 성능 대시보드 작동 |
| Phase 7: 리플레이 UI | +8~12시간 | `game_id` 클릭 → 재생 |
| Phase 8: MLOps D 델타 | +6~10시간 | 자동 모델 승격 게이트 |
| **합계** | **~42~66시간** | 전체 시스템 완성 |

주 5일 × 하루 2시간 기준 **약 5~6주**, 주말 집중 작업 기준 **약 3~4주**.

---

## 얼마가 드는가

| 구간 | 월 비용 |
|---|---|
| 첫 90일 (GCP $300 크레딧 중) | **약 1,200원/월** |
| 정상 운영 | **약 26,000~28,000원/월** |
| 피크 홍보 달 | **약 30,000원/월** |

3만원/월 상한선 준수. 상세는 [13_cost_model.md](./13_cost_model.md).

---

## 가장 큰 리스크 Top 3

1. **GCP Billing Alert 미설정 → 과금 폭탄** (SSH 오픈 + 채굴 해킹 시나리오 포함)
2. **2GB RAM 라이트사이징 실패 → OOM kill 반복** (Phase 5 중요성)
3. **게임 이벤트 스키마 1차 확정 실패 → Phase 6 이후 대규모 재작업** (설계서 [05_data_model.md](./05_data_model.md) 신중히 확정)

---

## 포트폴리오 어필 포인트 (요약)

- 🏆 **"2GB VM에 풀스택 + MLOps + 관측성을 꾸겨넣기"** 자체가 엔지니어링 스토리
- 🏆 **"모델 승격 게이트를 CI/CD 파이프라인으로 구현"** — MLOps 엔지니어 포지션 어필
- 🏆 **"Workload Identity Federation으로 키 파일 없는 배포"** — 보안 어필
- 🏆 **"게임 밸런스를 데이터 기반으로 검증하는 대시보드"** — 프로젝트 본연의 목적과 일치

상세는 [15_portfolio_readme_checklist.md](./15_portfolio_readme_checklist.md).
