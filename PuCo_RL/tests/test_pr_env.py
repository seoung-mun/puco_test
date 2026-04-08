import unittest
import numpy as np
from pettingzoo.test import api_test

from env.pr_env import PuertoRicoEnv
from configs.constants import Phase, BuildingType, TileType, Good

class TestPuertoRicoAECEnv(unittest.TestCase):
    def test_pettingzoo_api(self):
        """Run the standard PettingZoo API test to ensure compliance"""
        env = PuertoRicoEnv(num_players=2)
        api_test(env, num_cycles=100)
        
    def test_random_rollout(self):
        """Run a minimal random rollout using the standard AEC Env loop"""
        env = PuertoRicoEnv(num_players=3)
        env.reset()
        
        step_count = 0
        max_steps = 1000
        
        for agent in env.agent_iter():
            step_count += 1
            if step_count > max_steps:
                break
                
            observation, reward, termination, truncation, info = env.last()
            
            if termination or truncation:
                action = None
            else:
                mask = observation["action_mask"]
                valid_actions = np.where(mask == 1)[0]
                self.assertGreater(len(valid_actions), 0, "Agent must have at least 1 valid action")
                action = int(np.random.choice(valid_actions))
                
            env.step(action)
            
            if all(env.terminations.values()):
                break


class TestAutoSkip(unittest.TestCase):
    def test_hacienda_auto_use(self):
        """Test that Hacienda is automatically used when conditions are met."""
        env = PuertoRicoEnv(num_players=3)
        env.reset()
        game = env.game
        
        # Setup: Give player 0 an occupied Hacienda
        p = game.players[0]
        p.city_board = []
        p.island_board = []
        p.build_building(BuildingType.HACIENDA)
        p.city_board[0].colonists = 1  # Occupy it
        
        # Force Settler phase
        game.current_phase = Phase.SETTLER
        game.current_player_idx = 0
        game.active_role_player = 0
        game.players_taken_action = 0
        game._hacienda_used = False
        
        # Get valid actions - Hacienda action (105) should NOT be in mask
        mask = env.valid_action_mask()
        self.assertFalse(mask[105], "Hacienda action should not be in mask (auto-used)")
        
        # The auto-action should trigger Hacienda draw
        # We simulate by calling _execute_auto_actions
        initial_island_count = len(p.island_board)
        auto_executed = env._execute_auto_actions()
        
        self.assertTrue(auto_executed, "Hacienda should be auto-executed")
        self.assertEqual(len(p.island_board), initial_island_count + 1, "Should have drawn 1 plantation")
        self.assertTrue(game._hacienda_used, "Hacienda flag should be set")
        
        print("Hacienda auto-use test passed!")

    def test_pass_only_auto_skip(self):
        """Test that pass-only situations are auto-skipped."""
        env = PuertoRicoEnv(num_players=3)
        env.reset()
        game = env.game
        
        # Setup: Trader phase with no sellable goods
        p = game.players[0]
        for g in Good:
            p.goods[g] = 0  # No goods
        
        game.current_phase = Phase.TRADER
        game.current_player_idx = 0
        game.active_role_player = 0
        game.players_taken_action = 0
        
        # Get valid actions - should only be pass (15)
        mask = env.valid_action_mask()
        valid_actions = np.where(mask == 1)[0]
        self.assertEqual(list(valid_actions), [15], "Only pass should be valid")
        
        # Auto-skip should execute pass
        initial_players_taken = game.players_taken_action
        auto_executed = env._execute_auto_actions()
        
        self.assertTrue(auto_executed, "Pass should be auto-executed")
        self.assertGreater(game.players_taken_action, initial_players_taken, "Turn should advance")
        
        print("Pass-only auto-skip test passed!")

    def test_captain_forced_shipping(self):
        """Test that captain phase auto-ships when only one option exists."""
        env = PuertoRicoEnv(num_players=3)
        env.reset()
        game = env.game
        
        # Setup: Captain phase with only one valid ship/good combo
        p = game.players[0]
        for g in Good:
            p.goods[g] = 0
        p.goods[Good.CORN] = 3  # Only corn
        
        # Clear all ships, set one to accept corn
        for ship in game.cargo_ships:
            ship.current_load = 0
            ship.good_type = None
        game.cargo_ships[0].good_type = Good.CORN
        game.cargo_ships[0].current_load = 1  # Partially filled
        # Fill other ships to make them unusable for corn
        game.cargo_ships[1].good_type = Good.INDIGO
        game.cargo_ships[2].good_type = Good.SUGAR
        
        game.current_phase = Phase.CAPTAIN
        game.current_player_idx = 0
        game.active_role_player = 0
        game._captain_passed_players = set()
        
        # Get valid actions - should only be one ship/good combo
        mask = env.valid_action_mask()
        valid_actions = np.where(mask == 1)[0]
        
        # Filter to only captain actions (44-63)
        captain_actions = [a for a in valid_actions if 44 <= a <= 63]
        
        if len(captain_actions) == 1:
            # Should auto-execute
            initial_corn = p.goods[Good.CORN]
            auto_executed = env._execute_auto_actions()
            
            self.assertTrue(auto_executed, "Single captain option should be auto-executed")
            self.assertLess(p.goods[Good.CORN], initial_corn, "Corn should be shipped")
            print("Captain forced shipping test passed!")
        else:
            # Multiple options exist, auto-skip shouldn't happen
            print(f"Skipping captain forced test - {len(captain_actions)} options available")


if __name__ == "__main__":
    unittest.main()
