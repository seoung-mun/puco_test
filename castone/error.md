
# 현재 발생중인 에러

1. 현재 게임방 내에서 봇(사람 플레이어x)가 액션을 하고 있지 않아 이 에러 상황 체크
puco_backend   | strict=True load failed for /PuCo_RL/models/ppo_agent_update_100.pth: Error(s) in loading state_dict for Agent:
puco_backend   |        Missing key(s) in state_dict: "embed.0.weight", "embed.0.bias", "embed.1.weight", "embed.1.bias", "shared_trunk.0.net.0.weight", "shared_trunk.0.net.0.bias", "shared_trunk.0.net.1.weight", "shared_trunk.0.net.1.bias", "shared_trunk.0.net.3.weight", "shared_trunk.0.net.3.bias", "shared_trunk.1.net.0.weight", "shared_trunk.1.net.0.bias", "shared_trunk.1.net.1.weight", "shared_trunk.1.net.1.bias", "shared_trunk.1.net.3.weight", "shared_trunk.1.net.3.bias", "shared_trunk.2.net.0.weight", "shared_trunk.2.net.0.bias", "shared_trunk.2.net.1.weight", "shared_trunk.2.net.1.bias", "shared_trunk.2.net.3.weight", "shared_trunk.2.net.3.bias", "actor_head.0.weight", "actor_head.0.bias", "actor_head.1.weight", "actor_head.1.bias", "actor_head.3.weight", "actor_head.3.bias", "critic_head.0.weight", "critic_head.0.bias", "critic_head.1.weight", "critic_head.1.bias", "critic_head.3.weight", "critic_head.3.bias". 
puco_backend   |        Unexpected key(s) in state_dict: "critic.0.weight", "critic.0.bias", "critic.2.weight", "critic.2.bias", "critic.4.weight", "critic.4.bias", "actor.0.weight", "actor.0.bias", "actor.2.weight", "actor.2.bias", "actor.4.weight", "actor.4.bias".  — retrying strict=False. Check MODEL_TYPE matches the checkpoint architecture.

2. 봇의 작동 속도를 사람이 볼 수 있게 해줘
    예를 들면 텀을 어느정도(대충 2~4초?) 두어서 사람이 봇이 어떤 선택을 하는지 실시간으로 볼 수 있게
3. 


# 앞으로 할 일

1. MLops 부분 파이프라인 점검
    - 현재 서빙/훈련 환경 불일치
    - pydantic 라이브러리를 사용해서 프론트/백에서 보낸 데이터가 정확하게 db/model에 전달되는지 검증하는 로직 필요
    - 멀티 에이전트 환경 + 다중 플레이어(사람) 환경에서 과연 현재 파이프라인이 명확하게 작동할까
        - 예를 들어 똑같은 모델이 서로 다른 게임방에서 동시에 결과를 요구한다면? 
    - 모델 평가를 위해 따로 커스텀된 평가 지표를 제안할 예정
        - 이를 위해 mlflow 연동 고려
    - 재학습 관련하여 현재 학교 GPU 빌리는 중, 차후 파이프라인 완성 예정
    - 완전 자동화는 시간적 여유가 많으므로 일단 나중에 현재는 환경 불일치와 검증 로직만 하면 될듯

2. db/로그 확인 방법 정리 
    - 현재 DB/게임 로그를 확인하고, 유저 정보를 확인 하는 작업이 아직 부진함
    - 확인하는 명령어 및 방법들을 .sh 파일에 정리하여 그 파일을 실행시키면 볼 수 있게
    - postgreSQL에 명확하게 저장이 되는가
        - 플레이어가 액션을 끝냈을 때 저장이 된다고 했는데 그게 정말인지 체크하고
        - 실제로 저장된 값들이 진짜 게임의 값인지 아니면 그냥 초기 데이터 값이 계속해서 저장되는지 확인
    - redis에는 어떤 데이터들이 저장되고 그걸 제어하는 방법은? 

3. 멀티 플레이어 환경에서 에러 발생 확인
    - 현재 테스트는 개발자 혼자인 상황에서 테스트한 거라 멀티 환경에서는 어떻게 될지 모름
    - 인간 플레이어가 다수일때 어떤 현상들이 발생하고 어떤 에러가 발생하는지
    - 통신 에러가 발생했을 때 이를 어떻게 대처하는지
    - 배포된 서버에서 용량을 초과하거나 그런 위험이 있을 때 어떻게 대처하는지
    - 몇번 더 코드를 고치거나 할텐데 그때마다 서버를 다운시켜야하는지 아니면 서버 올린 상태로 코드만 교체할 수 있는지
        - 이 부분은 너무 많은 비용이 들면 생각을 해보는걸로(어짜피 이 웹은 연구용이라 에이전트의 개발 및 게임 밸런스 검증이 더 중요)
    
    - 그 외에도 다양한 문제들이 있겠지만 일단 생각나는것은 이거


