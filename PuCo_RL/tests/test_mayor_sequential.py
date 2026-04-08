import unittest
from env.engine import PuertoRicoGame
from env.pr_env import PuertoRicoEnv
from configs.constants import Phase, Role, BuildingType, TileType, BUILDING_DATA

class TestMayorSequential(unittest.TestCase):
    def test_mayor_sequential_placement(self):
        # Setup
        env = PuertoRicoEnv(num_players=3)
        env.reset()
        game = env.game
        
        # Manually force Mayor Phase
        game.current_phase = Phase.MAYOR
        game.current_player_idx = 0
        game.active_role_player = 0
        game.players_taken_action = 0
        game.players[0].unplaced_colonists = 3 # Player has 3 colonists
        
        # Give some buildings
        game.players[0].city_board = []
        game.players[0].build_building(BuildingType.SMALL_INDIGO_PLANT) # Cap 1, slot 12
        game.players[0].build_building(BuildingType.SMALL_MARKET) # Cap 1, slot 13
        # Setup island
        game.players[0].island_board = []
        game.players[0].place_plantation(TileType.CORN_PLANTATION) # Slot 0
        game.players[0].place_plantation(TileType.INDIGO_PLANTATION) # Slot 1
        
        # Init placement — should skip to slot 0 (first valid: Corn)
        game._init_mayor_placement(0)
        self.assertEqual(game.mayor_placement_idx, 0)
        
        # --- Slot 0: Corn (Capacity 1) ---
        # Player has 3 col. Future cap: Indigo(1) + SmIndigo(1) + SmMarket(1) = 3
        # min_place = max(0, 3-3) = 0. max_place = min(1, 3) = 1.
        mask = env.valid_action_mask()
        self.assertTrue(mask[72]) # 0
        self.assertTrue(mask[73]) # 1
        
        # Agent chooses 0
        game.action_mayor_place(0, 0)
        # Should skip empty island slots 2-11 → land on slot 1 (Indigo)
        self.assertEqual(game.mayor_placement_idx, 1)
        self.assertEqual(game.players[0].unplaced_colonists, 3)
        self.assertFalse(game.players[0].island_board[0].is_occupied)

        # --- Slot 1: Indigo (Capacity 1) ---
        # Player has 3 col. Future cap: SmIndigo(1) + SmMarket(1) = 2.
        # min_place = max(0, 3-2) = 1. max_place = 1.
        # MUST place 1.
        mask = env.valid_action_mask()
        self.assertFalse(mask[72]) # 0 invalid
        self.assertTrue(mask[73])  # 1 valid
        
        # Agent chooses 1
        game.action_mayor_place(0, 1)
        # Should skip empty island slots 2-11 → land on slot 12 (Small Indigo Plant)
        self.assertEqual(game.mayor_placement_idx, 12)
        self.assertEqual(game.players[0].unplaced_colonists, 2)
        self.assertTrue(game.players[0].island_board[1].is_occupied)
        
        # --- Slot 12: Small Indigo (Capacity 1) ---
        # Player has 2 col. Future cap: SmMarket(1).
        # min_place = max(0, 2-1) = 1. max_place = 1.
        mask = env.valid_action_mask()
        self.assertFalse(mask[72]) # 0 invalid
        self.assertTrue(mask[73])  # 1 valid
        game.action_mayor_place(0, 1)
        self.assertEqual(game.players[0].unplaced_colonists, 1)
        self.assertEqual(game.players[0].city_board[0].colonists, 1)
        # Should land on slot 13 (Small Market)
        self.assertEqual(game.mayor_placement_idx, 13)
        
        # --- Slot 13: Small Market (Capacity 1) ---
        # Player has 1 col. Future cap: 0.
        # min_place = max(0, 1-0) = 1. max_place = 1.
        mask = env.valid_action_mask()
        self.assertFalse(mask[72]) # 0 invalid
        self.assertTrue(mask[73])  # 1 valid
        game.action_mayor_place(0, 1)
        self.assertEqual(game.players[0].unplaced_colonists, 0)
        self.assertEqual(game.players[0].city_board[1].colonists, 1)
        
        # After placing last colonist → remaining slots auto-skipped (0 colonists left)
        # → mayor_placement_idx = 24 → _advance_phase_turn called
        # Players 1 & 2 have 0 colonists → auto-complete → phase advances past Mayor
        self.assertNotEqual(game.current_phase, Phase.MAYOR)
        
        print("TestMayorSequential Passed!")

if __name__ == '__main__':
    unittest.main()

