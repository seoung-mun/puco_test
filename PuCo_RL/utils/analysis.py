import os
import torch
import numpy as np
from collections import defaultdict
from typing import Dict, List, Tuple
from env.pr_env import PuertoRicoEnv
from agents.ppo_agent import Agent, HierarchicalAgent
from utils.env_wrappers import flatten_dict_observation, get_flattened_obs_dim
from configs.constants import Role, BuildingType

class GameAnalyzer:
    def __init__(self, model_path: str = None, num_players: int = 4, device: str = "cpu"):
        self.num_players = num_players
        self.device = device
        self.env = PuertoRicoEnv(num_players=num_players)
        
        # Load Agent
        obs_space = self.env.observation_space(self.env.possible_agents[0])["observation"]
        self.obs_dim = get_flattened_obs_dim(obs_space)
        self.action_dim = self.env.action_space(self.env.possible_agents[0]).n
        
        self.agent = Agent(obs_dim=self.obs_dim, action_dim=self.action_dim).to(device)
        
        if model_path and os.path.exists(model_path):
            checkpoint = torch.load(model_path, map_location=device)
            # Handle both full checkpoint dict and direct state_dict
            if "model_state_dict" in checkpoint:
                self.agent.load_state_dict(checkpoint["model_state_dict"])
            else:
                self.agent.load_state_dict(checkpoint)
            self.agent.eval()
            print(f"Loaded model from {model_path}")
        else:
            print("No model path provided or file not found. Using random initialized agent.")

    def run_simulation(self, num_games: int = 100) -> Dict:
        print(f"Starting simulation of {num_games} games...")
        stats = {
            "wins_by_seat": defaultdict(int),
            "scores": [],
            "game_lengths": [],
            "winning_buildings": defaultdict(int),
            "winning_strategies": {"shipping": 0, "building": 0, "balanced": 0},
            "first_role_picked": defaultdict(int) # Track opening moves
        }

        for game_idx in range(num_games):
            obs, _ = self.env.reset()
            done = False
            
            # Track game-specific data
            player_buildings = [[] for _ in range(self.num_players)]
            first_role = None
            
            while not done:
                # Get valid actions
                current_agent = self.env.agent_selection
                player_idx = int(current_agent.split("_")[1])
                
                observation = obs[current_agent]["observation"]
                mask = obs[current_agent]["action_mask"]
                
                # Check for opening move (Round 1, Turn 1)
                # In actual implementation, we'd need to check the phase/round from observation
                # For simplicity, we might just track the first role action taken.
                
                # Select Action
                if mask.sum() == 0:
                    action = None # Should not happen with valid mask, but for safety
                else:
                    # Prepare input
                    flat_obs = flatten_dict_observation(observation, self.env.observation_space(current_agent)["observation"])
                    obs_tensor = torch.Tensor(flat_obs).to(self.device).unsqueeze(0)
                    mask_tensor = torch.Tensor(mask).to(self.device).unsqueeze(0)
                    
                    with torch.no_grad():
                        action_tensor, _, _, _ = self.agent.get_action_and_value(obs_tensor, mask_tensor)
                        action = action_tensor.item()
                
                # Record strategy data (e.g., if action is building, record it)
                # Note: This requires mapping action ID to building ID. 
                # Assuming actions 16-38 are buildings based on README
                if 16 <= action <= 38:
                    building_id = action - 16
                    player_buildings[player_idx].append(building_id)

                obs, reward, termination, truncation, info = self.env.step(action)
                done = all(self.env.terminations.values())
                
                if done:
                    # Game Over - Collect Stats
                    final_scores = self.env.infos[self.env.agents[0]]["final_scores"] # [(score, shipping_vp, building_vp, bonus_vp), ...]
                    winner_idx = np.argmax([s[0] for s in final_scores])
                    
                    stats["wins_by_seat"][winner_idx] += 1
                    stats["scores"].append([s[0] for s in final_scores])
                    stats["game_lengths"].append(self.env.current_round) # Assuming env tracks rounds
                    
                    # Analyze Winner's Strategy
                    w_score, w_ship, w_build, w_bonus = final_scores[winner_idx]
                    
                    # Strategy Classification
                    total_vp = w_score
                    if w_ship / total_vp > 0.4:
                        stats["winning_strategies"]["shipping"] += 1
                    elif (w_build + w_bonus) / total_vp > 0.4:
                         stats["winning_strategies"]["building"] += 1
                    else:
                        stats["winning_strategies"]["balanced"] += 1
                        
                    # Winning Buildings
                    for b_id in player_buildings[winner_idx]:
                        try:
                            b_name = BuildingType(b_id).name
                            stats["winning_buildings"][b_name] += 1
                        except ValueError:
                            pass

            if (game_idx + 1) % 10 == 0:
                print(f"Completed {game_idx + 1}/{num_games} games")

        return stats

    def print_report(self, stats: Dict):
        num_games = sum(stats["wins_by_seat"].values())
        print("\n" + "="*40)
        print("      PUERTO RICO BALANCE ANALYSIS      ")
        print("="*40)
        print(f"Total Games Simulated: {num_games}")
        
        print("\n1. Seat Balance (Win Rate by Turn Order)")
        for seat in range(self.num_players):
            wins = stats["wins_by_seat"][seat]
            print(f"  Player {seat+1}: {wins} wins ({wins/num_games*100:.1f}%)")
            
        print("\n2. Strategy Effectiveness")
        for strategy, count in stats["winning_strategies"].items():
            print(f"  {strategy.capitalize()}: {count} wins ({count/num_games*100:.1f}%)")
            
        print("\n3. Top 5 Winning Buildings")
        sorted_buildings = sorted(stats["winning_buildings"].items(), key=lambda x: x[1], reverse=True)
        for b_name, count in sorted_buildings[:5]:
            print(f"  {b_name}: {count} times present in winning city")
            
        print("\n4. Score Distribution")
        avg_scores = np.mean(stats["scores"], axis=0)
        print(f"  Average Scores: {avg_scores}")
        print("="*40)

if __name__ == "__main__":
    # Example Usage
    analyzer = GameAnalyzer(model_path="models/ppo_checkpoint_update_50.pth", num_players=4)
    stats = analyzer.run_simulation(num_games=100) # Fast test
    analyzer.print_report(stats)
