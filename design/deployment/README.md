# Castone 배포 / 운영 / MLOps 설계 문서

**작성일**: 2026-04-10
**상태**: 설계 완료, 구현 대기
**범위**: TODO.md 4번 트랙(배포/운영) + 3번 트랙(리플레이/로그 재설계)를 병합한 통합 설계
**목표**: RL 기반 Puerto Rico AI 실험 플랫폼을 GCP에 배포하고, 모델 성능 추적·게임 밸런스 검증을 위한 MLOps 파이프라인을 구축한다

---

## 이 설계의 정체성

> **이 프로젝트는 웹 서비스가 아니라 RL 실험 플랫폼이다.**
> 웹은 "봇과 사람이 대전하면서 RL 재학습용 데이터와 밸런스 검증 데이터를 수집하는 수단"이다.
> 따라서 배포 트랙은 단순 웹 배포가 아니라 **추론 측(inference-side) MLOps 파이프라인 배포**다.

---

## 문서 구성

각 문서는 독립적으로 읽을 수 있도록 작성되었다. 번호는 읽는 순서의 권장이며, 필요한 문서만 발췌해서 읽어도 무방하다.

| # | 파일 | 다루는 내용 | 대상 독자 |
|---|---|---|---|
| 00 | [executive_summary.md](./00_executive_summary.md) | 1페이지 요약. 무엇을 / 왜 / 얼마에 / 언제까지 | 모두 |
| 01 | [project_identity.md](./01_project_identity.md) | MLOps 플랫폼으로서의 프로젝트 정체성, 1차/2차 목표, Non-goals | 리뷰어, 면접관 |
| 02 | [non_functional_requirements.md](./02_non_functional_requirements.md) | 성능·가용성·보안·RPO/RTO 등 측정 가능한 NFR | 운영자, 리뷰어 |
| 03 | [decision_log.md](./03_decision_log.md) | 16개 아키텍처 결정의 근거와 대안 | 리뷰어, 후임 개발자 |
| 04 | [architecture.md](./04_architecture.md) | 시스템 구성도(텍스트), 컴포넌트, 데이터 흐름 | 개발자 |
| 05 | [data_model.md](./05_data_model.md) | Postgres 스키마, GCS 레이아웃, 모델 메타데이터 | 개발자 |
| 06 | [game_id_design.md](./06_game_id_design.md) | ULID + slug + title 3-레이어 식별자 설계 | 개발자 |
| 07 | [mlops_pipeline.md](./07_mlops_pipeline.md) | 메트릭·대시보드·모델 승격 게이트 | 개발자, 데이터 엔지니어 |
| 08 | [phase_roadmap.md](./08_phase_roadmap.md) | Phase 0~8 구현 순서와 공수 추정 | 구현자(본인) |
| 09 | [terraform_resources.md](./09_terraform_resources.md) | Terraform 파일 구조와 리소스 목록 | 구현자 |
| 10 | [github_actions.md](./10_github_actions.md) | CI/CD 워크플로 스켈레톤 | 구현자 |
| 11 | [docker_rightsizing.md](./11_docker_rightsizing.md) | `docker-compose.prod.yml` 2GB RAM 라이트사이징 | 구현자 |
| 12 | [runbook.md](./12_runbook.md) | 배포·롤백·백업 복원·모델 교체·시크릿 회전 절차 | 운영자 |
| 13 | [cost_model.md](./13_cost_model.md) | 월 비용 산정, 가드레일, 비용 튀는 시나리오 | 본인, 리뷰어 |
| 14 | [risk_register.md](./14_risk_register.md) | 식별된 리스크와 완화책 | 리뷰어 |
| 15 | [portfolio_readme_checklist.md](./15_portfolio_readme_checklist.md) | 포폴 README에 써야 할 어필 포인트 체크리스트 | 본인 |

---

## 빠른 읽기 경로

**"30초 안에 이 설계를 이해하고 싶다"** → [00_executive_summary.md](./00_executive_summary.md)

**"왜 이런 결정을 했는지 궁금하다"** → [03_decision_log.md](./03_decision_log.md)

**"당장 뭐부터 시작할지 알고 싶다"** → [08_phase_roadmap.md](./08_phase_roadmap.md) Phase 0

**"포트폴리오에 뭘 써야 하나"** → [15_portfolio_readme_checklist.md](./15_portfolio_readme_checklist.md)

**"비용이 걱정된다"** → [13_cost_model.md](./13_cost_model.md)

---

## 상태 표기 규칙

이 문서들 내부에서 사용하는 상태 마커:

- ✅ 결정됨 / 확정
- 🚧 구현 예정 (Phase 명시)
- ⚠️ 주의 필요 / 리스크
- 🚨 반드시 먼저 처리 (블로커)
- 💡 선택적 / 여력 있을 때
- 🏆 포트폴리오 하이라이트 포인트

---

## 설계 주체 및 변경 이력

| 일자 | 변경 | 주체 |
|---|---|---|
| 2026-04-10 | 초안 작성. 브레인스토밍 13라운드 합의 기반 | Seoung-mun + Claude (brainstorming session) |

변경이 발생하면 **해당 문서 상단에 이력 추가** 하고, 영향받는 다른 문서에 크로스 참조를 남긴다.

---

## 관련 외부 문서

- 프로젝트 루트 [`TODO.md`](../../TODO.md) — 이 설계가 다루는 작업 목록
- [`design/2026-04-08_engine_cutover_task_breakdown.md`](../2026-04-08_engine_cutover_task_breakdown.md) — 엔진 컷오버 트랙 (병렬 진행)
- [`contract.md`](../../contract.md) — 프로젝트 계약/협업 규칙
- [`.env.example`](../../.env.example) — 현재 환경변수 스키마
