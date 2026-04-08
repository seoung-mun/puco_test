import unittest
from env.engine import PuertoRicoGame
from env.pr_env import PuertoRicoEnv
from configs.constants import (
    Phase, Role, BuildingType, TileType, BUILDING_DATA, 
    MayorStrategy, Good
)

class TestMayorStrategy(unittest.TestCase):
    def test_mayor_strategy_captain_focus(self):
        """Test Captain Focus strategy prioritizes shipping buildings."""
        env = PuertoRicoEnv(num_players=3)
        env.reset()
        game = env.game
        
        # Setup player 0 with specific buildings
        p = game.players[0]
        p.city_board = []
        p.island_board = []
        
        # Add buildings: Wharf (captain), Factory (trade), Small Indigo (production)
        p.build_building(BuildingType.WHARF)
        p.build_building(BuildingType.FACTORY)
        p.build_building(BuildingType.SMALL_INDIGO_PLANT)
        
        # Add plantations
        p.place_plantation(TileType.INDIGO_PLANTATION)
        p.place_plantation(TileType.CORN_PLANTATION)
        
        # Give colonists
        p.unplaced_colonists = 3
        
        # Force Mayor phase
        game.current_phase = Phase.MAYOR
        game.current_player_idx = 0
        game.active_role_player = 0
        game.players_taken_action = 0
        
        # Execute Captain Focus strategy
        game.action_mayor_strategy(0, MayorStrategy.CAPTAIN_FOCUS)
        
        # Wharf should be filled first (captain priority)
        wharf_filled = any(b.building_type == BuildingType.WHARF and b.colonists > 0 
                         for b in p.city_board)
        self.assertTrue(wharf_filled, "Wharf should be prioritized in Captain Focus")
        
        print("Captain Focus strategy test passed!")

    def test_mayor_strategy_trade_factory_focus(self):
        """Test Trade/Factory Focus strategy prioritizes trading buildings."""
        env = PuertoRicoEnv(num_players=3)
        env.reset()
        game = env.game
        
        # Setup player 0
        p = game.players[0]
        p.city_board = []
        p.island_board = []
        
        # Add buildings
        p.build_building(BuildingType.HARBOR)  # Captain related
        p.build_building(BuildingType.OFFICE)  # Trade related
        p.build_building(BuildingType.SMALL_SUGAR_MILL)
        
        p.place_plantation(TileType.SUGAR_PLANTATION)
        
        p.unplaced_colonists = 2
        
        game.current_phase = Phase.MAYOR
        game.current_player_idx = 0
        game.active_role_player = 0
        game.players_taken_action = 0
        
        game.action_mayor_strategy(0, MayorStrategy.TRADE_FACTORY_FOCUS)
        
        # Office should be filled (trade priority)
        office_filled = any(b.building_type == BuildingType.OFFICE and b.colonists > 0 
                          for b in p.city_board)
        self.assertTrue(office_filled, "Office should be prioritized in Trade Focus")
        
        print("Trade/Factory Focus strategy test passed!")

    def test_mayor_strategy_building_focus(self):
        """Test Building Focus strategy prioritizes infrastructure buildings."""
        env = PuertoRicoEnv(num_players=3)
        env.reset()
        game = env.game
        
        p = game.players[0]
        p.city_board = []
        p.island_board = []
        
        # Add buildings
        p.build_building(BuildingType.UNIVERSITY)  # Building focus
        p.build_building(BuildingType.HARBOR)      # Captain related
        p.build_building(BuildingType.SMALL_INDIGO_PLANT)
        
        p.place_plantation(TileType.INDIGO_PLANTATION)
        
        p.unplaced_colonists = 2
        
        game.current_phase = Phase.MAYOR
        game.current_player_idx = 0
        game.active_role_player = 0
        game.players_taken_action = 0
        
        game.action_mayor_strategy(0, MayorStrategy.BUILDING_FOCUS)
        
        # University should be filled (building priority)
        univ_filled = any(b.building_type == BuildingType.UNIVERSITY and b.colonists > 0 
                        for b in p.city_board)
        self.assertTrue(univ_filled, "University should be prioritized in Building Focus")
        
        print("Building Focus strategy test passed!")

    def test_mayor_strategy_large_vp_priority(self):
        """Test that large VP buildings are always filled first."""
        env = PuertoRicoEnv(num_players=3)
        env.reset()
        game = env.game
        
        p = game.players[0]
        p.city_board = []
        p.island_board = []
        
        # Add Guild Hall (large VP) and Wharf
        p.build_building(BuildingType.GUILDHALL)
        p.build_building(BuildingType.WHARF)
        
        p.unplaced_colonists = 1  # Only 1 colonist
        
        game.current_phase = Phase.MAYOR
        game.current_player_idx = 0
        game.active_role_player = 0
        game.players_taken_action = 0
        
        # Even with Captain Focus, Guild Hall should be filled first
        game.action_mayor_strategy(0, MayorStrategy.CAPTAIN_FOCUS)
        
        guildhall_filled = any(b.building_type == BuildingType.GUILDHALL and b.colonists > 0 
                              for b in p.city_board)
        wharf_filled = any(b.building_type == BuildingType.WHARF and b.colonists > 0 
                          for b in p.city_board)
        
        self.assertTrue(guildhall_filled, "Guild Hall should be filled first")
        self.assertFalse(wharf_filled, "Wharf should not be filled (no colonists left)")
        
        print("Large VP priority test passed!")

    def test_mayor_strategy_production_pairs(self):
        """Test production pair logic - fill min(farms, building capacity) for production."""
        env = PuertoRicoEnv(num_players=3)
        env.reset()
        game = env.game
        
        p = game.players[0]
        p.city_board = []
        p.island_board = []
        
        # 2 Indigo farms, but only 1 capacity building
        p.place_plantation(TileType.INDIGO_PLANTATION)
        p.place_plantation(TileType.INDIGO_PLANTATION)
        p.build_building(BuildingType.SMALL_INDIGO_PLANT)  # Capacity 1
        
        p.unplaced_colonists = 5
        
        game.current_phase = Phase.MAYOR
        game.current_player_idx = 0
        game.active_role_player = 0
        game.players_taken_action = 0
        
        game.action_mayor_strategy(0, MayorStrategy.CAPTAIN_FOCUS)
        
        # Production pairs: min(2 farms, 1 building capacity) = 1
        # So 1 farm + 1 building for production = 2 colonists used
        building_colonists = sum(b.colonists for b in p.city_board 
                                if b.building_type == BuildingType.SMALL_INDIGO_PLANT)
        self.assertEqual(building_colonists, 1, "Should fill building to capacity")
        
        # Remaining colonists (3) should fill remaining slots (1 more farm available)
        # Total occupied farms = 2 (1 for production + 1 leftover)
        occupied_farms = sum(1 for t in p.island_board 
                            if t.tile_type == TileType.INDIGO_PLANTATION and t.is_occupied)
        self.assertEqual(occupied_farms, 2, "Remaining colonists fill other farms")
        
        # 5 - 1 (building) - 2 (farms) = 2 colonists unplaced (no more slots)
        self.assertEqual(p.unplaced_colonists, 2, "2 colonists unplaced (no more slots)")
        
        print("Production pairs test passed!")

    def test_mayor_strategy_corn_only_farm(self):
        """Test corn plantations are filled without needing buildings."""
        env = PuertoRicoEnv(num_players=3)
        env.reset()
        game = env.game
        
        p = game.players[0]
        p.city_board = []
        p.island_board = []
        
        p.place_plantation(TileType.CORN_PLANTATION)
        p.place_plantation(TileType.CORN_PLANTATION)
        
        p.unplaced_colonists = 2
        
        game.current_phase = Phase.MAYOR
        game.current_player_idx = 0
        game.active_role_player = 0
        game.players_taken_action = 0
        
        game.action_mayor_strategy(0, MayorStrategy.CAPTAIN_FOCUS)
        
        occupied_corn = sum(1 for t in p.island_board 
                           if t.tile_type == TileType.CORN_PLANTATION and t.is_occupied)
        
        self.assertEqual(occupied_corn, 2, "Both corn farms should be occupied")
        
        print("Corn farm test passed!")

    def test_mayor_action_mask(self):
        """Test that all 3 strategies are always available in Mayor phase."""
        env = PuertoRicoEnv(num_players=3)
        env.reset()
        game = env.game
        
        game.current_phase = Phase.MAYOR
        game.current_player_idx = 0
        
        mask = env.valid_action_mask()
        
        self.assertTrue(mask[69], "CAPTAIN_FOCUS (69) should be valid")
        self.assertTrue(mask[70], "TRADE_FACTORY_FOCUS (70) should be valid")
        self.assertTrue(mask[71], "BUILDING_FOCUS (71) should be valid")
        self.assertFalse(mask[72], "Action 72 should NOT be valid (old system)")
        
        print("Action mask test passed!")

    def test_mayor_phase_turn_advance(self):
        """Test that turn advances correctly after strategy selection."""
        env = PuertoRicoEnv(num_players=3)
        env.reset()
        game = env.game
        
        # Setup
        game.current_phase = Phase.MAYOR
        game.current_player_idx = 0
        game.active_role_player = 0
        game.players_taken_action = 0
        
        for p in game.players:
            p.recall_all_colonists()
        
        # Player 0 selects strategy
        game.action_mayor_strategy(0, MayorStrategy.CAPTAIN_FOCUS)
        
        # Should advance to player 1
        self.assertEqual(game.current_player_idx, 1, "Turn should advance to player 1")
        self.assertEqual(game.players_taken_action, 1)
        
        print("Turn advance test passed!")

if __name__ == '__main__':
    unittest.main()

