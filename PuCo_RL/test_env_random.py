from env.pr_env import PuertoRicoEnv
import numpy as np
from collections import Counter

env = PuertoRicoEnv(num_players=3, max_game_steps=2000)
num_games = 100
error_counter = Counter()

for _ in range(num_games):
    env.reset()
    while True:
        agent = env.agent_selection
        obs, reward, term, trunc, info = env.last()
        
        if term or trunc:
            if 'error' in info:
                error_counter[info['error']] += 1
            break
            
        mask = obs['action_mask']
        valid_actions = np.where(mask == 1)[0]
        
        # Random agent
        if len(valid_actions) > 0:
            action = np.random.choice(valid_actions)
        else:
            break
            
        env.step(action)

print("Error causes:")
for err, cnt in error_counter.items():
    print(f"- {cnt} times: {err}")
