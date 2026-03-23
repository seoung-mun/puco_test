# 프로젝트 TODO 및 우선순위 

> `docs/next_steps_report.md`의 분석 타이틀(MLOps, Security, AWS, Docker)을 바탕으로 기존 TODO를 구체화하고 우선순위를 재정렬했습니다.

## ✅ 완료된 항목 (Done)
- [x] **데이터베이스 생성 및 URL 연결** (기존 TODO 1)
  - Redis, PostgreSQL 각각의 데이터베이스 연결 및 설정 완료
  - PostgreSQL 스키마 및 Alembic 마이그레이션 적용 완료
- [ ] **구글 인증 (OAuth) 구현** (기존 TODO 2)

  - SMTP 인증 이메일 주소 삽입(.env)
  - 
  - JWT 발급 및 닉네임 설정, 관련 API 구현 완료
  - JWT 인증 기본 보안 강화 (SECRET_KEY 필수화)

---

## 🚀 Phase 1. 배포 준비 및 핵심 보안 (Immediate/High Priority)
배포 전에 필수적으로 반영되어야 할 인프라 경량화 및 치명적 보안/무결성 이슈를 해결합니다. (`@backend-security-coder`, `@docker-expert`)

- [ ] **도커 경량화 및 최적화** (기존 TODO 4)
  - `requirements.api.txt` / `requirements.train.txt` 분리 (학습 환경 분리)
  - `.dockerignore` 생성
  - Dockerfile 멀티스테이지 빌드 구현 및 `HEALTHCHECK` 추가
  - `entrypoint.sh` 스크립트 분리 및 프로덕션 환경의 `--reload` 제거
- [ ] **엔드포인트 방어 및 한도 설정** (기존 TODO 2, 3 고도화)
  - `slowapi`를 적용하여 전 API 엔드포인트 대상 Rate Limiting 적용 (브루트포스/DoS 방어)
- [ ] **보안 및 감사 로깅**
  - PII 분리 원칙을 적용한 사용자 인증 이벤트 감사 로그(Auth Audit Log) 테이블 및 마이그레이션 생성
- [ ] **강화학습 데이터 무결성 검증 추가**
  - `ml_logger.py`에 PPO 학습 데이터 무결성 및 구조 검증 로직 추가 (필수 속성, action 유효 범위 검사 등) 구현

---

## 🛠 Phase 2. MLOps 파이프라인 기반 구축 및 인증 고도화 (Medium Priority)
학습/서빙 환경을 분리하고 모델 결과 및 버전을 안전하고 체계적으로 관리하는 환경을 조성합니다. (`@mlops-engineer`, `@backend-security-coder`)

- [ ] **접근 통제 및 세션 관리 고도화**
  - Redis Blocklist 기반 JWT 토큰 즉시 무효화 (Revocation) 처리 로직 구축
  - 로그아웃 엔드포인트 및 GDPR 준수용 사용자 데이터 익명화(회원 탈퇴 처리) 엔드포인트 작성
- [ ] **ML 실험 추적 및 실험 환경 구성**
  - 로컬 `docker-compose`에 MLflow 서버 서비스 추가
  - `PuCo_RL` 학습 코드 내 MLflow 로깅 매크로 통합 (`log_params`, `log_metrics`, 등)
- [ ] **ML 모델 아티팩트 버전 관리**
  - DVC 등을 통한 모델 가중치 파일(`.pth`) 소스 분리 및 의존성 버전 관리 설정

---

## ☁️ Phase 3. 클라우드 인프라 (AWS) 배포 구현 (Medium-Long Term Priority)
클라우드 프로덕션 런타임 보안 및 서비스 확장을 위한 클라우드 환경으로 앱을 배포합니다. (`@aws-serverless`)

- [ ] **AWS IaC 프로비저닝 구축 (Terraform 권장)**
  - 기초 네트워크(VPC), DB(RDS PostgreSQL), 인메모리(ElastiCache Redis) 환경 프로비저닝
- [ ] **CI/CD 오토메이션**
  - GitHub Actions 파이프라인 작성 (테스트 러너 → ECR 이미지 빌드 및 푸시 자동화)
- [ ] **컨테이너 서빙 및 엣지 로드 밸런싱**
  - AWS ECS Fargate 클러스터 생성 및 Task / Service 정의 (무중단 배포 전략 포함)
  - AWS CloudFront 배포 및 WAF를 엮어서 어플리케이션 레이어 보호 구축
- [ ] **가시성 및 모니터링**
  - AWS CloudWatch 연동: 알람(ECS 리소스, 5xx 에러, RDS 연결 등) 및 커스텀 게임 서버 메트릭 대시보드 구축

---

## 🤖 Phase 4. 시스템 자동화 및 RLOps 완성 (Long Term Priority)
AI 에이전트 성능 유지를 위한 자동화된 학습 인프라 파이프라인을 완성합니다. (`@mlops-engineer`, `@aws-serverless`)

- [ ] **강화학습 데이터 백업 자동화**
  - `game_logs` 및 JSONL 파일 데이터를 AWS S3로 이중 업로드하도록 로거 파이프라인 연동
- [ ] **모델 자동 재학습 (Retraining) 파이프라인**
  - 데이터 임계점 도달(예: 로그 N건 이상)에 따른 재학습 파이프라인 자동 트리거 구현 (AWS EventBridge/SQS 활용)
  - 학습 전용 리소스 프로비저닝 배포 (AWS Batch 또는 ECS Task 활용)
- [ ] **운영 무중단 핫-리로딩**
  - 신규 PPO 모델 아티팩트 승격 후 서버 재시작 없는 핫 리로드(Hot-Reload) API 엔드포인트 구축
