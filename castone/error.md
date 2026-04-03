# 남은 할일



1. 봇전 수정
    - 현재는 전부 random 봇 3개로만 되어 있는데 이걸 봇전을 만들 때, 봇의 종류를 지정할 수 있게 수정하기
    - ws 문제가 또 발생할 수 있으므로 주의
    - 서로 같은 봇이 셀프 플레이 방식으로 게임을 진행하는 걸 볼 수도 있어야함
        - 새로운 기능을 추가하기 보다는 봇을 고를 때 똑같은 종류의 봇 3개를 고를 수 있게

2. 봇이 받는 데이터가 적합한 데이터 인지
    - 현재 봇의 input 데이터가 정말로 ui상에서 보이는 게임의 데이터인지 검증하는 로직의 유무를 모르겠음
    - 있다면 그걸 테스트 후, 보고서화, 없다면 설계 보고서 작성
    - 통신 에러가 발생할 수도 있고, 수많은 엣지케이스가 발생할건데 이러한 상황들에서 어떤 식으로 대응하는지

3. 게임 데이터 저장 로그
    - /Users/seoungmun/Documents/agent_dev/castest/castone/PuCo_RL/logs/replay/replay_seed42_1775006136.json
    - 위의 파일처럼 저런 형태로 로그가 로컬이나 postgresql에 저장되게
        - db에 저장된다면 그걸 확인하는 방법도 보고서로
    - redis의 역할을 정확하게 정의하고, 이 플젝에서 그게 어떤 역할들을 수행할 수 있는지


4. 게임이 종료 조건을 맞아 종료되었을 때 상태 확인
    - 어떤 식으로 Ui에 보이고, 그게 ux에 어떤 도움이 되는지


        - 1,2,3등을 보이고, ui/ux 부분에서 적당히 괜찮게 수정
5. 훈련된 모델 추가

    - /Users/seoungmun/Documents/agent_dev/castest/castone/PuCo_RL/models/PPO_PR_Server_20260401_214532_step_99942400.pth
    - 위의 파일 같은 모델들이 계속 추가될 예정이고, 
    - /Users/seoungmun/Documents/agent_dev/castest/castone/PuCo_RL/train/train_ppo_selfplay_server.py 
    - 이 파일의 결과로 나온 가중치로도 학습될 예정
    - input은 안바뀔거 같지만, 잠재함수는 앞으로도 수정할 예정