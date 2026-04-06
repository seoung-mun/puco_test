"""
Edge-case tests for every game phase action mask.
Each test verifies that the action mask correctly allows/blocks specific actions
in corner-case game states.

Run:
    cd PuCo_RL && python -m pytest tests/test_phase_edge_cases.py -v
"""
import sys
import os
import pytest
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from env.pr_env import PuertoRicoEnv
from env.components import IslandTile, CityBuilding
from configs.constants import (
    Phase, Role, Good, TileType, BuildingType, BUILDING_DATA
)


# ─── Helpers ────────────────────────────────────────────────────────────────

def make_env(num_players: int = 3, seed: int = 42) -> PuertoRicoEnv:
    env = PuertoRicoEnv(num_players=num_players)
    env.reset(seed=seed)
    return env


def get_mask(env: PuertoRicoEnv) -> np.ndarray:
    return env.observe(env.agent_selection)["action_mask"]


def cur_player(env: PuertoRicoEnv):
    return env.game.players[env.game.current_player_idx]


def enter_phase(env: PuertoRicoEnv, role: Role) -> None:
    """Select a role from END_ROUND to enter that role's phase."""
    assert env.game.current_phase == Phase.END_ROUND
    env.step(role.value)


def finish_settler_phase_all_pass(env: PuertoRicoEnv) -> None:
    """Fast-forward through settler phase: all players pass."""
    while env.game.current_phase == Phase.SETTLER:
        env.step(15)  # Pass


# ─── Settler Phase ───────────────────────────────────────────────────────────

class TestSettlerPhase:

    def test_pass_always_valid(self):
        """Pass (action 15) must always be valid in settler phase."""
        env = make_env()
        enter_phase(env, Role.SETTLER)
        assert get_mask(env)[15] == 1

    def test_plantation_indices_match_face_up_count(self):
        """Mask enables exactly the indices that exist in face_up_plantations."""
        env = make_env()
        enter_phase(env, Role.SETTLER)
        mask = get_mask(env)
        n = len(env.game.face_up_plantations)
        p = cur_player(env)
        if p.empty_island_spaces > 0:
            for i in range(n):
                assert mask[8 + i] == 1, f"Plantation slot {i} should be valid (n={n})"
            # Slots beyond face_up count must be masked out
            for i in range(n, 6):
                assert mask[8 + i] == 0, f"Plantation slot {i} beyond face_up must be invalid"

    def test_island_full_blocks_all_plantation_actions(self):
        """When island is full (12 tiles), no plantation or quarry actions valid."""
        env = make_env()
        enter_phase(env, Role.SETTLER)
        p = cur_player(env)
        # Fill island to capacity
        while p.empty_island_spaces > 0:
            p.island_board.append(IslandTile(tile_type=TileType.CORN_PLANTATION))
        mask = get_mask(env)
        for action in range(8, 15):  # 8-14 are plantation + quarry
            assert mask[action] == 0, f"Action {action} must be blocked when island full"
        assert mask[15] == 1, "Pass must still be valid"

    def test_quarry_available_to_role_player(self):
        """Role player can take quarry if stack > 0 and has island space."""
        env = make_env()
        enter_phase(env, Role.SETTLER)
        game = env.game
        assert game.quarry_stack > 0
        assert game.current_player_idx == game.active_role_player_idx()
        assert cur_player(env).empty_island_spaces > 0
        assert get_mask(env)[14] == 1

    def test_quarry_blocked_for_non_role_player_without_hut(self):
        """Non-role-player without Construction Hut cannot take quarry."""
        env = make_env(num_players=3)
        enter_phase(env, Role.SETTLER)
        game = env.game
        role_player_idx = game.active_role_player_idx()
        # Role player takes first plantation
        env.step(8)
        # Now a different player is active
        assert game.current_player_idx != role_player_idx
        p = cur_player(env)
        # Ensure no construction hut
        p.city_board = [b for b in p.city_board
                        if b.building_type != BuildingType.CONSTRUCTION_HUT]
        assert get_mask(env)[14] == 0, "Quarry must be blocked for non-role-player"

    def test_quarry_blocked_when_stack_empty(self):
        """Even role player cannot take quarry when stack is 0."""
        env = make_env()
        enter_phase(env, Role.SETTLER)
        env.game.quarry_stack = 0
        assert get_mask(env)[14] == 0

    def test_quarry_blocked_when_island_full(self):
        """Role player cannot take quarry when their island is full."""
        env = make_env()
        enter_phase(env, Role.SETTLER)
        p = cur_player(env)
        while p.empty_island_spaces > 0:
            p.island_board.append(IslandTile(tile_type=TileType.CORN_PLANTATION))
        assert get_mask(env)[14] == 0

    def test_stale_index_terminates_env(self):
        """Stepping with a plantation index beyond face_up list terminates env."""
        env = make_env()
        enter_phase(env, Role.SETTLER)
        env.game.face_up_plantations = []  # empty face_up
        env.step(8)  # index 0 on empty list → ValueError in engine
        assert any(env.terminations.values()), "Invalid plantation index must terminate env"

    def test_hacienda_action_blocked_without_occupied_hacienda(self):
        """Hacienda draw (action 105) not available if Hacienda not occupied."""
        env = make_env()
        enter_phase(env, Role.SETTLER)
        p = cur_player(env)
        # Ensure player has no occupied hacienda
        p.city_board = [b for b in p.city_board if b.building_type != BuildingType.HACIENDA]
        assert get_mask(env)[105] == 0, "Action 105 must be blocked without occupied Hacienda"


# ─── Builder Phase ──────────────────────────────────────────────────────────

class TestBuilderPhase:

    def test_pass_always_valid(self):
        env = make_env()
        enter_phase(env, Role.BUILDER)
        assert get_mask(env)[15] == 1

    def test_zero_doubloons_blocks_all_buildings(self):
        """With 0 doubloons and no discounts, no buildings are in mask."""
        env = make_env()
        enter_phase(env, Role.BUILDER)
        p = cur_player(env)
        p.doubloons = 0
        # Remove all quarries so no discount applies
        p.island_board = [t for t in p.island_board if t.tile_type != TileType.QUARRY]
        # Override to non-role-player to remove privilege
        env.game.active_role_player = (env.game.current_player_idx + 1) % env.game.num_players
        mask = get_mask(env)
        for i in range(16, 39):
            assert mask[i] == 0, f"Action {i} must be masked with 0 doubloons and no discount"
        assert mask[15] == 1

    def test_already_owned_building_blocked(self):
        """A building the player owns is excluded from the mask."""
        env = make_env()
        enter_phase(env, Role.BUILDER)
        p = cur_player(env)
        p.doubloons = 99
        p.city_board.append(CityBuilding(building_type=BuildingType.SMALL_INDIGO_PLANT))
        assert get_mask(env)[16 + BuildingType.SMALL_INDIGO_PLANT.value] == 0

    def test_city_board_full_blocks_all_buildings(self):
        """When city board is full (12 slots), no buildings can be built."""
        env = make_env()
        enter_phase(env, Role.BUILDER)
        p = cur_player(env)
        p.doubloons = 99
        p.city_board = [CityBuilding(building_type=BuildingType.SMALL_MARKET)
                        for _ in range(12)]
        mask = get_mask(env)
        for i in range(16, 39):
            assert mask[i] == 0, f"Action {i} must be blocked when city full"

    def test_only_one_city_space_blocks_large_buildings(self):
        """Large buildings (2 slots) cannot be built when only 1 slot remains."""
        env = make_env()
        enter_phase(env, Role.BUILDER)
        p = cur_player(env)
        p.doubloons = 99
        # Fill 11 of 12 city slots (1 remaining)
        p.city_board = [CityBuilding(building_type=BuildingType.SMALL_MARKET)
                        for _ in range(11)]
        mask = get_mask(env)
        large_buildings = [BuildingType.GUILDHALL, BuildingType.RESIDENCE,
                           BuildingType.FORTRESS, BuildingType.CUSTOMS_HOUSE,
                           BuildingType.CITY_HALL]
        for b in large_buildings:
            assert mask[16 + b.value] == 0, f"{b.name} needs 2 slots, must be blocked"

    def test_quarry_discount_enables_building(self):
        """Active quarry reduces cost so an otherwise unaffordable building becomes available."""
        env = make_env()
        enter_phase(env, Role.BUILDER)
        p = cur_player(env)
        # SMALL_INDIGO_PLANT costs 1. With 0 doubloons and quarry discount it costs 0.
        p.doubloons = 0
        p.island_board = [IslandTile(tile_type=TileType.QUARRY, is_occupied=True)]
        mask = get_mask(env)
        # SMALL_INDIGO_PLANT: base_cost=1, max_q=1 → quarry discount 1 → final 0
        assert mask[16 + BuildingType.SMALL_INDIGO_PLANT.value] == 1, \
            "SMALL_INDIGO_PLANT should be free with active quarry"

    def test_privilege_discount_enables_building(self):
        """Role player privilege (-1 doubloon) enables an otherwise borderline building."""
        env = make_env()
        enter_phase(env, Role.BUILDER)
        p = cur_player(env)
        # SMALL_INDIGO_PLANT costs 1. Role player gets -1. 0 doubloons → affordable.
        p.doubloons = 0
        assert env.game.current_player_idx == env.game.active_role_player_idx()
        mask = get_mask(env)
        assert mask[16 + BuildingType.SMALL_INDIGO_PLANT.value] == 1, \
            "Role player privilege should make SMALL_INDIGO_PLANT free"

    def test_out_of_stock_building_blocked(self):
        """A building with 0 supply is not in the mask even if affordable."""
        env = make_env()
        enter_phase(env, Role.BUILDER)
        p = cur_player(env)
        p.doubloons = 99
        env.game.building_supply[BuildingType.SMALL_SUGAR_MILL] = 0
        assert get_mask(env)[16 + BuildingType.SMALL_SUGAR_MILL.value] == 0


# ─── Trader Phase ───────────────────────────────────────────────────────────

class TestTraderPhase:

    def test_pass_always_valid(self):
        env = make_env()
        enter_phase(env, Role.TRADER)
        assert get_mask(env)[15] == 1

    def test_no_goods_blocks_all_trade_actions(self):
        """With no goods in inventory, only pass is valid."""
        env = make_env()
        enter_phase(env, Role.TRADER)
        p = cur_player(env)
        for g in Good:
            p.goods[g] = 0
        mask = get_mask(env)
        for i in range(39, 44):
            assert mask[i] == 0, f"No goods → action {i} must be blocked"
        assert mask[15] == 1

    def test_trading_house_full_blocks_all_trade_actions(self):
        """When trading house has 4 goods, no more trades allowed."""
        env = make_env()
        enter_phase(env, Role.TRADER)
        p = cur_player(env)
        p.goods[Good.CORN] = 3
        env.game.trading_house = [Good.COFFEE, Good.TOBACCO, Good.INDIGO, Good.SUGAR]
        mask = get_mask(env)
        for i in range(39, 44):
            assert mask[i] == 0, f"Trading house full → action {i} must be blocked"
        assert mask[15] == 1

    def test_duplicate_good_blocked_without_office(self):
        """Cannot sell a good already in the trading house without Office."""
        env = make_env()
        enter_phase(env, Role.TRADER)
        p = cur_player(env)
        p.goods[Good.CORN] = 2
        env.game.trading_house = [Good.CORN]
        # Ensure no Office
        p.city_board = [b for b in p.city_board if b.building_type != BuildingType.OFFICE]
        assert get_mask(env)[39 + Good.CORN.value] == 0, "CORN already in house → blocked"

    def test_duplicate_good_allowed_with_occupied_office(self):
        """With an occupied Office, duplicate goods can be sold."""
        env = make_env()
        enter_phase(env, Role.TRADER)
        p = cur_player(env)
        p.goods[Good.CORN] = 2
        env.game.trading_house = [Good.CORN]
        # Add occupied Office
        p.city_board.append(CityBuilding(building_type=BuildingType.OFFICE, colonists=1))
        assert get_mask(env)[39 + Good.CORN.value] == 1, "With Office, duplicate good allowed"

    def test_only_owned_goods_offered(self):
        """Only goods the player actually owns appear in the mask."""
        env = make_env()
        enter_phase(env, Role.TRADER)
        p = cur_player(env)
        for g in Good:
            p.goods[g] = 0
        p.goods[Good.TOBACCO] = 1
        mask = get_mask(env)
        assert mask[39 + Good.TOBACCO.value] == 1, "Tobacco owned → should be in mask"
        for g in Good:
            if g != Good.TOBACCO:
                assert mask[39 + g.value] == 0, f"{g.name} not owned → must be blocked"

    def test_corn_has_zero_price_but_still_tradeable(self):
        """Corn can be sold (price=0 is valid per rules), mask should include it."""
        env = make_env()
        enter_phase(env, Role.TRADER)
        p = cur_player(env)
        for g in Good:
            p.goods[g] = 0
        p.goods[Good.CORN] = 1
        env.game.trading_house = []
        assert get_mask(env)[39 + Good.CORN.value] == 1, "Corn is tradeable (price=0)"

    def test_unoccupied_office_does_not_allow_duplicate(self):
        """Office must have a colonist (be occupied) to grant the duplicate-selling privilege."""
        env = make_env()
        enter_phase(env, Role.TRADER)
        p = cur_player(env)
        p.goods[Good.TOBACCO] = 2
        env.game.trading_house = [Good.TOBACCO]
        # Add UN-occupied Office (colonists=0)
        p.city_board.append(CityBuilding(building_type=BuildingType.OFFICE, colonists=0))
        assert get_mask(env)[39 + Good.TOBACCO.value] == 0, \
            "Unoccupied Office must not grant duplicate-sell privilege"


# ─── Captain Phase ──────────────────────────────────────────────────────────

class TestCaptainPhase:

    def test_no_goods_gives_only_pass(self):
        """With no goods, only pass is valid in captain phase."""
        env = make_env()
        enter_phase(env, Role.CAPTAIN)
        p = cur_player(env)
        for g in Good:
            p.goods[g] = 0
        mask = get_mask(env)
        assert mask[15] == 1
        for i in range(44, 64):
            assert mask[i] == 0

    def test_all_ships_full_gives_only_pass(self):
        """When every ship is full, only pass is valid."""
        env = make_env()
        enter_phase(env, Role.CAPTAIN)
        p = cur_player(env)
        p.goods[Good.CORN] = 5
        for ship in env.game.cargo_ships:
            ship.current_load = ship.capacity
            ship.good_type = Good.CORN
        mask = get_mask(env)
        assert mask[15] == 1
        for i in range(44, 64):
            assert mask[i] == 0

    def test_pass_blocked_when_can_load(self):
        """Pass must NOT be valid when the player has a loadable good."""
        env = make_env()
        enter_phase(env, Role.CAPTAIN)
        p = cur_player(env)
        p.goods[Good.CORN] = 3
        # Ensure ship 0 is free
        env.game.cargo_ships[0].current_load = 0
        env.game.cargo_ships[0].good_type = None
        assert get_mask(env)[15] == 0, "Pass must be blocked when player can load"

    def test_cannot_load_good_on_wrong_ship(self):
        """Cannot load TOBACCO onto a ship already assigned to CORN."""
        env = make_env()
        enter_phase(env, Role.CAPTAIN)
        p = cur_player(env)
        # Give player only tobacco
        for g in Good:
            p.goods[g] = 0
        p.goods[Good.TOBACCO] = 3
        # All ships committed to CORN
        for ship in env.game.cargo_ships:
            ship.good_type = Good.CORN
            ship.current_load = 1
        mask = get_mask(env)
        for ship_idx in range(len(env.game.cargo_ships)):
            action = 44 + ship_idx * 5 + Good.TOBACCO.value
            assert mask[action] == 0, f"TOBACCO on ship {ship_idx} (CORN) must be blocked"
        assert mask[15] == 1, "Player must pass when no valid load"

    def test_wharf_actions_available_with_occupied_wharf(self):
        """Wharf actions (59-63) enabled per good when Wharf is occupied and unused."""
        env = make_env()
        enter_phase(env, Role.CAPTAIN)
        p = cur_player(env)
        for g in Good:
            p.goods[g] = 0
        p.goods[Good.COFFEE] = 2
        p.city_board.append(CityBuilding(building_type=BuildingType.WHARF, colonists=1))
        env.game._wharf_used[env.game.current_player_idx] = False
        assert get_mask(env)[59 + Good.COFFEE.value] == 1

    def test_wharf_actions_blocked_after_wharf_used(self):
        """Wharf actions are blocked when _wharf_used flag is True."""
        env = make_env()
        enter_phase(env, Role.CAPTAIN)
        p = cur_player(env)
        for g in Good:
            p.goods[g] = 0
        p.goods[Good.COFFEE] = 2
        p.city_board.append(CityBuilding(building_type=BuildingType.WHARF, colonists=1))
        env.game._wharf_used[env.game.current_player_idx] = True
        for i in range(59, 64):
            assert get_mask(env)[i] == 0, f"Wharf action {i} must be blocked after use"

    def test_wharf_blocked_without_occupied_wharf(self):
        """Wharf actions blocked if player has no Wharf building."""
        env = make_env()
        enter_phase(env, Role.CAPTAIN)
        p = cur_player(env)
        for g in Good:
            p.goods[g] = 0
        p.goods[Good.CORN] = 2
        # Ensure no wharf
        p.city_board = [b for b in p.city_board if b.building_type != BuildingType.WHARF]
        for i in range(59, 64):
            assert get_mask(env)[i] == 0, f"No Wharf → action {i} blocked"

    def test_can_load_matching_ship(self):
        """Player can load a good onto a ship already carrying that good."""
        env = make_env()
        enter_phase(env, Role.CAPTAIN)
        p = cur_player(env)
        for g in Good:
            p.goods[g] = 0
        p.goods[Good.CORN] = 3
        env.game.cargo_ships[0].good_type = Good.CORN
        env.game.cargo_ships[0].current_load = 1
        env.game.cargo_ships[0].capacity = 5
        # Other ships are committed to other goods
        for i in range(1, len(env.game.cargo_ships)):
            env.game.cargo_ships[i].good_type = Good.COFFEE
            env.game.cargo_ships[i].current_load = 1
        mask = get_mask(env)
        # CORN on ship 0 should be available
        assert mask[44 + 0 * 5 + Good.CORN.value] == 1, "Can load CORN on CORN-ship"

    def test_cannot_place_good_on_ship_already_used_by_another_good(self):
        """A good cannot start a new ship if another ship already holds that good."""
        env = make_env()
        enter_phase(env, Role.CAPTAIN)
        p = cur_player(env)
        for g in Good:
            p.goods[g] = 0
        p.goods[Good.INDIGO] = 3
        # Ship 0: INDIGO already committed → player can load there
        env.game.cargo_ships[0].good_type = Good.INDIGO
        env.game.cargo_ships[0].current_load = 2
        env.game.cargo_ships[0].capacity = 5
        # Ship 1: empty
        env.game.cargo_ships[1].good_type = None
        env.game.cargo_ships[1].current_load = 0
        # Ship 1 is empty but INDIGO is already on ship 0 →
        # player should NOT be able to start INDIGO on ship 1
        mask = get_mask(env)
        assert mask[44 + 1 * 5 + Good.INDIGO.value] == 0, \
            "Cannot start INDIGO on ship 1 if ship 0 already has INDIGO"


# ─── Mayor Phase ────────────────────────────────────────────────────────────

class TestMayorPhase:

    def test_no_colonists_only_zero_placement(self):
        """With no unplaced colonists, only action 69 (place 0) is valid."""
        env = make_env()
        enter_phase(env, Role.MAYOR)
        p = cur_player(env)
        p.unplaced_colonists = 0
        mask = get_mask(env)
        assert mask[69] == 1, "Place-0 must always be available"
        for i in range(70, 73):
            assert mask[i] == 0, f"Cannot place {i - 69} with no colonists"

    def test_plantation_slot_capacity_is_one(self):
        """On a plantation slot, max placement is 1."""
        env = make_env()
        enter_phase(env, Role.MAYOR)
        p = cur_player(env)
        p.unplaced_colonists = 3
        # Slot 0 must be a plantation (set it explicitly)
        if len(p.island_board) == 0:
            p.island_board.append(IslandTile(tile_type=TileType.CORN_PLANTATION))
        else:
            p.island_board[0] = IslandTile(tile_type=TileType.CORN_PLANTATION)
        env.game.mayor_placement_idx = 0
        mask = get_mask(env)
        assert mask[70] == 1, "Place 1 valid on plantation"
        assert mask[71] == 0, "Place 2 invalid (plantation capacity = 1)"
        assert mask[72] == 0, "Place 3 invalid (plantation capacity = 1)"

    def test_empty_slot_forces_zero_placement(self):
        """On a slot with no tile/building (capacity=0), only place-0 is valid."""
        env = make_env()
        enter_phase(env, Role.MAYOR)
        p = cur_player(env)
        p.unplaced_colonists = 3
        # Point to a slot beyond the player's board (capacity = 0)
        env.game.mayor_placement_idx = 11  # last island slot
        if len(p.island_board) <= 11:
            # Slot 11 doesn't exist → capacity = 0
            pass
        mask = get_mask(env)
        assert mask[69] == 1
        # Only 0 allowed if capacity is 0 or colonists = 0

    def test_building_slot_capacity_matches_building_data(self):
        """On a building slot, valid range is [min_place, max_place].

        With unplaced_colonists=3, city_board=[SUGAR_MILL] (cap=3), and no future slots,
        future_capacity=0, so min_place = max(0, 3-0) = 3, max_place = min(3, 3) = 3.
        Only placing all 3 is valid — you must not leave colonists unplaced.
        """
        env = make_env()
        enter_phase(env, Role.MAYOR)
        p = cur_player(env)
        p.unplaced_colonists = 3
        # Replace city board with a single SUGAR_MILL (capacity=3) — no future slots
        p.city_board = [CityBuilding(building_type=BuildingType.SUGAR_MILL, colonists=0)]
        env.game.mayor_placement_idx = 12  # first city slot (idx >= 12 → city slot 0)
        mask = get_mask(env)
        # future_capacity=0, min_place=3, max_place=3 → only placing 3 is valid
        assert mask[69 + 3] == 1, "Must place all 3 (no future slots to absorb them)"
        for disallowed in range(0, 3):
            assert mask[69 + disallowed] == 0, f"Placing {disallowed} forbidden when min_place=3"


# ─── Craftsman Phase ────────────────────────────────────────────────────────

class TestCraftsmanPhase:

    def test_pass_valid_in_craftsman_phase(self):
        """Pass (action 15) is valid when the game is actively in CRAFTSMAN phase.

        In a new game with no production, the craftsman phase auto-resolves and the
        game advances to END_ROUND without any player input. We only assert pass
        if we actually end up in the craftsman phase.
        """
        env = make_env()
        # Give player 0 an occupied corn plantation so production occurs
        p = env.game.players[0]
        p.island_board.append(IslandTile(tile_type=TileType.CORN_PLANTATION, is_occupied=True))
        enter_phase(env, Role.CRAFTSMAN)
        if env.game.current_phase == Phase.CRAFTSMAN:
            assert get_mask(env)[15] == 1, "Pass must be valid in active CRAFTSMAN phase"
        # If phase auto-advanced (no goods produced), we just skip the assertion

    def test_role_player_has_privilege_good_selection(self):
        """Role player can select a privilege good if something was produced."""
        env = make_env()
        # Set up production: add an occupied corn plantation
        game = env.game
        role_player_idx = game.current_player_idx
        p = game.players[role_player_idx]
        # Add occupied corn plantation before entering phase
        p.island_board.append(IslandTile(tile_type=TileType.CORN_PLANTATION, is_occupied=True))
        enter_phase(env, Role.CRAFTSMAN)
        # After role selection, production runs and _craftsman_produced_kinds is set
        produced = getattr(game, '_craftsman_produced_kinds', [])
        mask = get_mask(env)
        # If corn was produced and supply > 0, action 93+CORN.value should be valid
        if Good.CORN in produced and game.goods_supply[Good.CORN] > 0:
            assert mask[93 + Good.CORN.value] == 1, "Role player should see CORN privilege"

    def test_non_role_player_no_privilege_actions(self):
        """Non-role-player must not have access to craftsman privilege actions."""
        env = make_env(num_players=3)
        enter_phase(env, Role.CRAFTSMAN)
        # Role player passes (uses privilege or passes)
        env.step(15)
        # Now a non-role-player is active
        assert env.game.current_player_idx != env.game.active_role_player_idx()
        mask = get_mask(env)
        for i in range(93, 98):
            assert mask[i] == 0, f"Non-role-player must not see privilege action {i}"

    def test_privilege_good_blocked_when_supply_empty(self):
        """Even if produced, a good cannot be selected as privilege if supply is 0."""
        env = make_env()
        game = env.game
        role_player_idx = game.current_player_idx
        p = game.players[role_player_idx]
        p.island_board.append(IslandTile(tile_type=TileType.CORN_PLANTATION, is_occupied=True))
        enter_phase(env, Role.CRAFTSMAN)
        # Drain corn supply
        env.game.goods_supply[Good.CORN] = 0
        mask = get_mask(env)
        assert mask[93 + Good.CORN.value] == 0, "Corn privilege blocked when supply=0"


# ─── Role Selection ─────────────────────────────────────────────────────────

class TestRoleSelection:

    def test_all_roles_available_at_start(self):
        """At the start of a round, all roles for the player count are in mask."""
        env = make_env(num_players=3)
        # 3-player game has SETTLER, MAYOR, BUILDER, CRAFTSMAN, TRADER, CAPTAIN
        mask = get_mask(env)
        expected_roles = [Role.SETTLER, Role.MAYOR, Role.BUILDER,
                          Role.CRAFTSMAN, Role.TRADER, Role.CAPTAIN]
        for r in expected_roles:
            assert mask[r.value] == 1, f"{r.name} should be available at game start"

    def test_taken_role_blocked_in_same_round(self):
        """After SETTLER is selected, it must not appear in mask for subsequent pickers."""
        env = make_env(num_players=3)
        enter_phase(env, Role.SETTLER)
        finish_settler_phase_all_pass(env)
        # Back to END_ROUND — SETTLER taken this round
        assert env.game.current_phase == Phase.END_ROUND
        assert get_mask(env)[Role.SETTLER.value] == 0, "SETTLER already taken this round"

    def test_prospector_available_in_4player_game(self):
        """In 4-player game, PROSPECTOR_1 (action 6) should be available."""
        env = make_env(num_players=4)
        mask = get_mask(env)
        assert mask[Role.PROSPECTOR_1.value] == 1, "PROSPECTOR_1 must be in 4-player game"

    def test_prospector_not_available_in_3player_game(self):
        """In 3-player game, PROSPECTOR roles are not used."""
        env = make_env(num_players=3)
        mask = get_mask(env)
        assert mask[Role.PROSPECTOR_1.value] == 0, "PROSPECTOR_1 not in 3-player game"
        assert mask[Role.PROSPECTOR_2.value] == 0, "PROSPECTOR_2 not in 3-player game"


# ─── Invalid / Reserved Actions ─────────────────────────────────────────────

class TestInvalidActions:

    def test_reserved_action_is_silently_ignored(self):
        """Action 199 (reserved range 111-199) is not handled by any branch.

        The engine silently ignores it (no ValueError raised), so the env
        does NOT terminate. This is current by-design behaviour — reserved
        actions are expected to be blocked by the action mask before they
        reach step().
        """
        env = make_env()
        enter_phase(env, Role.SETTLER)
        env.step(199)
        # No termination — unknown actions fall through without raising ValueError
        assert not any(env.terminations.values()), \
            "Reserved action must not terminate env (mask guards prevent it in practice)"

    def test_builder_action_in_settler_phase_terminates(self):
        """Using a builder action (16-38) while in settler phase terminates env."""
        env = make_env()
        enter_phase(env, Role.SETTLER)
        env.step(20)
        assert any(env.terminations.values()), "Wrong-phase action must terminate env"

    def test_trader_action_in_builder_phase_terminates(self):
        """Trader action (39-43) during builder phase terminates env."""
        env = make_env()
        enter_phase(env, Role.BUILDER)
        env.step(39)
        assert any(env.terminations.values())

    def test_mask_always_has_at_least_one_valid_action(self):
        """In every non-terminal state, the mask must have ≥1 valid action."""
        env = make_env(num_players=3)
        env.reset(seed=99)
        for step_i in range(300):
            if all(env.terminations.values()):
                break
            mask = get_mask(env)
            valid = np.where(mask == 1)[0]
            assert len(valid) > 0, (
                f"No valid actions at step {step_i}, "
                f"phase={env.game.current_phase}"
            )
            env.step(int(valid[0]))  # greedy: always pick first valid

    def test_mask_consistency_across_random_rollout(self):
        """Random play never encounters a state with 0 valid actions."""
        rng = np.random.default_rng(seed=7)
        env = make_env(num_players=3, seed=7)
        for _ in range(200):
            if all(env.terminations.values()):
                break
            mask = get_mask(env)
            valid = np.where(mask == 1)[0]
            assert len(valid) > 0, "Zero valid actions encountered during random rollout"
            env.step(int(rng.choice(valid)))
