# 📋 Castone Project: MLOps Audit & Observability Framework

본 문서는 프로젝트의 기술적 완결성을 증명하고, 발표를 위한 시각화 자료의 핵심 지표 및 데이터 검증 전략을 정리합니다.

## 1. 데이터 계보 및 상태 정렬 (Data Lineage & Step Alignment)
모델이 인식하는 게임 상태와 사용자가 보는 화면이 100% 일치함을 증명합니다.
- **검증 목표:** `Engine.raw_obs` ↔ `BotInputSnapshot` ↔ `Serializer.GameState` 간의 **Step ID 정합성**.
- **시각화 요소:**
    - **Step-Lock Sankey Diagram:** 엔진에서 발생한 하나의 스텝이 Backend를 거쳐 UI까지 전파되는 흐름과 지연 시간(Latency) 시각화.
    - **Data Comparison Table:** 특정 스텝에서의 모델 Input Tensor값과 UI 표시 수치(자원, 승점 등)를 병렬 배치하여 데이터 누락(Drift)이 없음을 입증.

## 2. 결정론적 재현성 (Determinism & Reproducibility)
"동일한 시드에서는 동일한 결과가 보장되는가?"를 입증하여 시스템의 신뢰성을 확보합니다.
- **검증 목표:** `Global Seed` → `Engine RNG` → `Agent RNG`로 이어지는 결정론적 시드 전파 체인 확인.
- **시각화 요소:**
    - **Replay Consistency Graph:** 동일 시드로 N번 재시뮬레이션 시, 액션 시퀀스(Action Sequence)가 100% 일치함을 보여주는 검증표.
    - **Seed-to-Board Trace:** 특정 시드 입력 시 생성되는 초기 보드(Plantation stack 등)의 고정된 상태 시각화.

## 3. 에이전트 행동 분석 및 추적 (Behavioral Traceability)
"에이전트가 왜 그 행동을 선택했는가?"에 대한 근거와 안전 장치를 시각화합니다.
- **검증 목표:** `Action Mask` 적용 전/후 확률 분포 및 `Phase ID`에 따른 에이전트 판단의 정합성.
- **시각화 요소:**
    - **Action Probabilities Heatmap:** 특정 국면(예: Mayor 페이즈)에서 봇이 고려한 모든 선택지의 확률값과 최종 선택 액션 강조.
    - **Invalid Action Defense Trace:** 모델이 Mask를 위반하는 출력을 낼 경우, Backend 레이어에서 차단하고 Fallback(Random)으로 전환되는 '방어 로직' 시각화.

## 4. 데이터 저장소 무결성 (Storage Integrity)
실시간 서비스 데이터와 학습용 로그 데이터가 동일한지 검증합니다.
- **검증 목표:** Redis(실시간 전파) ↔ PostgreSQL(이력 저장) ↔ JSONL(훈련 로그) 간의 레코드 수 및 필드 일치성.
- **시각화 요소:**
    - **Storage Sync Dashboard:** 실시간 액션이 세 곳의 저장소에 기록되기까지의 성공률 및 동기화 지연 시간 모니터링.
    - **Schema Drift Check:** 엔진 업데이트 시 기존 JSONL 로그 스키마와 현재 모델 Input 스펙 간의 충돌 여부 체크 결과 시각화.

## 5. 실시간 성능 및 모니터링 (Online Monitoring)
실제 서비스 중인 에이전트의 성능 지표를 실시간으로 추적합니다.
- **검증 목표:** 추론 지연 시간(Inference Latency), 에이전트 타입별 승률 및 유효 액션 비율.
- **시각화 요소:**
    - **Agent Performance Radar:** 에이전트별 평균 추론 속도, 승률, 게임당 획득 승점을 비교하는 레이더 차트.
    - **Winning Rate Drift:** 모델 업데이트 전후의 승률 변동 추이를 보여주는 시계열 그래프.

---

### **💡 발표 자료 구성 팁**
- **Contract Test 결과 활용:** Priority 2 단계에서 수행할 '계약 테스트(Contract Test)' 통과 결과(예: "1,000 스텝 무결성 통과")를 스크린샷으로 포함하여 신뢰도 강조.
- **Architecture Diagram:** 데이터가 저장되고 검증되는 전체 파이프라인(PostgreSQL, Redis, JSONL)의 흐름도를 시각화 자료의 시작점으로 활용.
