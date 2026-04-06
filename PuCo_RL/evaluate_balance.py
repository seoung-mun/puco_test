import argparse
import os
from utils.analysis import GameAnalyzer

def main():
    parser = argparse.ArgumentParser(description="Puerto Rico RL Balance Analysis")
    parser.add_argument("--model_path", type=str, default="models/ppo_checkpoint_update_50.pth",
                        help="Path to the trained PPO model checkpoint")
    parser.add_argument("--num_games", type=int, default=100,
                        help="Number of games to simulate")
    parser.add_argument("--num_players", type=int, default=4,
                        help="Number of players (3-5)")
    parser.add_argument("--device", type=str, default="cpu",
                        help="Device to run inference on (cpu/cuda)")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.model_path):
        print(f"Warning: Model path {args.model_path} does not exist. Running with random agent.")
        args.model_path = None

    analyzer = GameAnalyzer(
        model_path=args.model_path,
        num_players=args.num_players,
        device=args.device
    )
    
    stats = analyzer.run_simulation(num_games=args.num_games)
    analyzer.print_report(stats)

if __name__ == "__main__":
    main()
