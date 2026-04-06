"""
API-level edge case tests for all game phases.

Covers:
  - Auth: no JWT → 401, expired JWT → 401
  - IDOR: user not in game → 403
  - No active engine (game not started) → 400
  - Missing action_index in payload → 400
  - Out-of-range action index → 400
  - Masked action (mask=0) rejected → 400
  - Wrong player's turn → 400
  - Valid role selection → 200 (enters a specific phase)
  - Phase-specific valid action → 200

Action mapping (from pr_env.py):
  0-7:    Role selection (Role enum 0-7)
  8-13:   Settler - face-up plantation (index 0-5)
  14:     Settler - quarry
  15:     Pass
  16-38:  Builder - build building (BuildingType 0-22)
  39-43:  Trader - sell good (Good 0-4)
  44-58:  Captain - load ship (ship_idx*5 + good_type + 44)
  59-63:  Captain - load via Wharf (Good 0-4)
  64-68:  Captain Store - keep good (Good 0-4)
  69-72:  Mayor - place colonists
  93-97:  Craftsman - privilege good (Good 0-4)
  105:    Hacienda pass
  106-110:Captain Store Warehouse
"""
import uuid
from datetime import timedelta, datetime, timezone

import jwt as pyjwt
import pytest

from app.core.security import create_access_token, SECRET_KEY, ALGORITHM
from app.db.models import User, GameSession
from app.services.game_service import GameService


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_user(db, nickname="TestUser"):
    user_id = uuid.uuid4()
    user = User(id=user_id, google_id=f"gid_{uuid.uuid4().hex}", nickname=nickname)
    db.add(user)
    db.flush()
    return user


def _make_game(db, players):
    game = GameSession(
        id=uuid.uuid4(),
        title="Edge Case Room",
        status="WAITING",
        num_players=len(players),
        players=players,
        host_id=players[0],
    )
    db.add(game)
    db.flush()
    return game


def _make_human_game(db, prefix="Player", count=3):
    users = [_make_user(db, f"{prefix}{idx}") for idx in range(count)]
    game = _make_game(db, [str(user.id) for user in users])
    return game, users


def _bearer(user_id):
    return {"Authorization": f"Bearer {create_access_token(subject=str(user_id))}"}


def _start(client, game_id, headers):
    res = client.post(f"/api/puco/game/{game_id}/start", headers=headers)
    assert res.status_code == 200, res.json()
    return res.json()


def _action(client, game_id, action_index, headers):
    return client.post(
        f"/api/puco/game/{game_id}/action",
        json={"payload": {"action_index": action_index}},
        headers=headers,
    )


def _first_valid(action_mask):
    return next(i for i, v in enumerate(action_mask) if v == 1)


def _first_invalid(action_mask):
    """Return first masked-off action (mask==0) that isn't out-of-range."""
    return next(i for i, v in enumerate(action_mask) if v == 0)


def _active_player_idx(payload):
    return int(payload["state"]["meta"]["active_player"].split("_")[1])


def _active_user(users, payload):
    return users[_active_player_idx(payload)]


def _start_human_turn(client, game, users):
    start_res = _start(client, game.id, _bearer(users[0].id))
    return start_res, _active_user(users, start_res)


# ---------------------------------------------------------------------------
# AUTH EDGE CASES
# ---------------------------------------------------------------------------

class TestAuthEdgeCases:
    def test_no_jwt_returns_401(self, client):
        game_id = uuid.uuid4()
        res = client.post(
            f"/api/puco/game/{game_id}/action",
            json={"payload": {"action_index": 0}},
        )
        assert res.status_code == 401

    def test_expired_jwt_returns_401(self, client):
        expire = datetime.now(timezone.utc) - timedelta(minutes=10)
        token = pyjwt.encode(
            {"exp": expire, "sub": str(uuid.uuid4())}, SECRET_KEY, algorithm=ALGORITHM
        )
        res = client.post(
            f"/api/puco/game/{uuid.uuid4()}/action",
            json={"payload": {"action_index": 0}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 401

    def test_start_no_jwt_returns_401(self, client):
        res = client.post(f"/api/puco/game/{uuid.uuid4()}/start")
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# IDOR EDGE CASES
# ---------------------------------------------------------------------------

class TestIDOREdgeCases:
    def test_start_user_not_in_game_returns_403(self, client, db):
        owner = _make_user(db, "Owner")
        outsider = _make_user(db, "Outsider")
        game = _make_game(db, [str(owner.id), "BOT_random", "BOT_random"])

        res = client.post(
            f"/api/puco/game/{game.id}/start",
            headers=_bearer(outsider.id),
        )
        assert res.status_code == 403

    def test_action_user_not_in_game_returns_403(self, client, db):
        owner = _make_user(db, "Owner2")
        outsider = _make_user(db, "Outsider2")
        game = _make_game(db, [str(owner.id), "BOT_random", "BOT_random"])

        _start(client, game.id, _bearer(owner.id))

        res = _action(client, game.id, 0, _bearer(outsider.id))
        assert res.status_code == 403

    def test_nonexistent_game_returns_404(self, client, db):
        user = _make_user(db, "Ghost")
        res = client.post(
            f"/api/puco/game/{uuid.uuid4()}/start",
            headers=_bearer(user.id),
        )
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# VALIDATION EDGE CASES (before phase matters)
# ---------------------------------------------------------------------------

class TestPayloadValidation:
    def test_missing_action_index_returns_400(self, client, db):
        game, users = _make_human_game(db, "PayloadMissing")
        _, current_user = _start_human_turn(client, game, users)

        res = client.post(
            f"/api/puco/game/{game.id}/action",
            json={"payload": {}},
            headers=_bearer(current_user.id),
        )
        assert res.status_code == 400
        assert "action_index" in res.json()["detail"].lower()

    def test_no_engine_returns_400(self, client, db):
        """Action on a game that was never started should 400."""
        user = _make_user(db)
        game = _make_game(db, [str(user.id), "BOT_random", "BOT_random"])
        # Skip start — no engine in active_engines

        res = _action(client, game.id, 0, _bearer(user.id))
        assert res.status_code == 400

    def test_out_of_range_action_returns_400(self, client, db):
        game, users = _make_human_game(db, "PayloadRange")
        _, current_user = _start_human_turn(client, game, users)

        # Action space is 0-199; 999 is out of range
        res = _action(client, game.id, 999, _bearer(current_user.id))
        assert res.status_code == 400

    def test_masked_action_rejected_returns_400(self, client, db):
        """An action with mask=0 must be rejected."""
        game, users = _make_human_game(db, "PayloadMasked")
        start_res, current_user = _start_human_turn(client, game, users)

        invalid_idx = _first_invalid(start_res["action_mask"])
        res = _action(client, game.id, invalid_idx, _bearer(current_user.id))
        assert res.status_code == 400

    def test_negative_action_index_returns_400(self, client, db):
        game, users = _make_human_game(db, "PayloadNegative")
        _, current_user = _start_human_turn(client, game, users)

        res = _action(client, game.id, -1, _bearer(current_user.id))
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# ROLE SELECTION PHASE
# ---------------------------------------------------------------------------

class TestRoleSelectionPhase:
    def test_valid_role_selection_returns_200(self, client, db):
        game, users = _make_human_game(db, "RoleSelection")
        start_res, current_user = _start_human_turn(client, game, users)

        # Game starts at role selection; valid actions are 0-7 (role picks)
        valid_role = _first_valid(start_res["action_mask"])
        assert valid_role <= 7, "First turn should be role selection"
        res = _action(client, game.id, valid_role, _bearer(current_user.id))
        assert res.status_code == 200
        assert res.json()["status"] == "success"

    def test_all_roles_are_selectable_at_start(self, client, db):
        """At game start the mask has at least one role bit set."""
        game, users = _make_human_game(db, "RoleMask")
        start_res, _ = _start_human_turn(client, game, users)
        mask = start_res["action_mask"]
        role_bits = mask[:8]
        assert sum(role_bits) >= 1


# ---------------------------------------------------------------------------
# SETTLER PHASE
# ---------------------------------------------------------------------------

class TestSettlerPhase:
    """
    Select Settler role (action 0) → enter Settler phase.
    In Settler phase: actions 8-14 place tiles, 15 passes.
    """

    def _enter_settler(self, client, game, users):
        """Start game on the active human turn, select Settler role, return response and actor."""
        start_res, current_user = _start_human_turn(client, game, users)
        mask = start_res["action_mask"]
        # Role.SETTLER == 0
        if mask[0] == 0:
            pytest.skip("Settler role not available (may be taken or not in this setup)")
        return _action(client, game.id, 0, _bearer(current_user.id)), current_user

    def test_settler_role_select_enters_phase(self, client, db):
        game, users = _make_human_game(db, "SettlerEnter")
        res, _ = self._enter_settler(client, game, users)
        assert res.status_code == 200
        mask = res.json()["action_mask"]
        # Should have some plantation or quarry actions (8-14) or pass (15) enabled
        settler_bits = mask[8:16]
        assert sum(settler_bits) >= 1, "Settler phase should have valid actions 8-15"

    def test_settler_pass_blocked_while_regular_pick_exists(self, client, db):
        users = [_make_user(db, f"SettlerPass{i}") for i in range(3)]
        game = _make_game(db, [str(user.id) for user in users])
        start_res = _start(client, game.id, _bearer(users[0].id))
        current_idx = int(start_res["state"]["meta"]["active_player"].split("_")[1])
        current_user = users[current_idx]
        if start_res["action_mask"][0] == 0:
            pytest.skip("Settler role not available for the current role picker")

        res = _action(client, game.id, 0, _bearer(current_user.id))
        assert res.status_code == 200

        mask = res.json()["action_mask"]
        assert any(mask[i] == 1 for i in range(8, 15)), "Settler phase should offer a regular pick"
        assert mask[15] == 0, "Pass must be blocked while a regular settler pick exists"

        res2 = _action(client, game.id, 15, _bearer(current_user.id))
        assert res2.status_code == 400

    def test_settler_masked_action_blocked(self, client, db):
        """Builder actions (16-38) must be blocked during Settler phase."""
        game, users = _make_human_game(db, "SettlerMasked")
        res, _ = self._enter_settler(client, game, users)
        assert res.status_code == 200
        mask = res.json()["action_mask"]
        # Builder action 16 (SMALL_INDIGO_PLANT) should be 0 during Settler phase
        assert mask[16] == 0, "Builder action must be blocked in Settler phase"

    def test_settler_valid_plantation_action(self, client, db):
        game, users = _make_human_game(db, "SettlerPlantation")
        res, current_user = self._enter_settler(client, game, users)
        assert res.status_code == 200

        mask = res.json()["action_mask"]
        # Pick first valid action in settler range (8-15)
        settler_valid = next(
            (i for i in range(8, 16) if mask[i] == 1), None
        )
        if settler_valid is None:
            pytest.skip("No valid settler action available")

        res2 = _action(client, game.id, settler_valid, _bearer(current_user.id))
        assert res2.status_code == 200

    def test_out_of_range_action_in_settler_phase_blocked(self, client, db):
        game, users = _make_human_game(db, "SettlerOutOfRange")
        res, current_user = self._enter_settler(client, game, users)
        assert res.status_code == 200

        res2 = _action(client, game.id, 999, _bearer(current_user.id))
        assert res2.status_code == 400


# ---------------------------------------------------------------------------
# BUILDER PHASE
# ---------------------------------------------------------------------------

class TestBuilderPhase:
    """
    Select Builder role (action 2) → enter Builder phase.
    In Builder phase: actions 16-38 build buildings.
    """

    def _enter_builder(self, client, game, users):
        start_res, current_user = _start_human_turn(client, game, users)
        mask = start_res["action_mask"]
        # Role.BUILDER == 2
        if mask[2] == 0:
            pytest.skip("Builder role not available")
        return _action(client, game.id, 2, _bearer(current_user.id)), current_user

    def test_builder_role_select_enters_phase(self, client, db):
        game, users = _make_human_game(db, "BuilderEnter")
        res, _ = self._enter_builder(client, game, users)
        assert res.status_code == 200
        mask = res.json()["action_mask"]
        builder_bits = mask[16:39]
        assert sum(builder_bits) >= 1, "Builder phase must have valid build actions"

    def test_builder_masked_action_blocked(self, client, db):
        """Settler actions (8-14) must be blocked during Builder phase."""
        game, users = _make_human_game(db, "BuilderMasked")
        res, _ = self._enter_builder(client, game, users)
        assert res.status_code == 200
        mask = res.json()["action_mask"]
        settler_bits = mask[8:15]
        assert sum(settler_bits) == 0, "Settler actions must be blocked in Builder phase"

    def test_builder_valid_build_action(self, client, db):
        game, users = _make_human_game(db, "BuilderAction")
        res, current_user = self._enter_builder(client, game, users)
        assert res.status_code == 200

        mask = res.json()["action_mask"]
        builder_valid = next((i for i in range(16, 39) if mask[i] == 1), None)
        if builder_valid is None:
            pytest.skip("No valid builder action")

        res2 = _action(client, game.id, builder_valid, _bearer(current_user.id))
        assert res2.status_code == 200

    def test_builder_cannot_build_unaffordable_building(self, client, db):
        """
        Player starts with 3 doubloons (3-player game).
        Large violet buildings cost 10 — should be masked off.
        Actions 34-38 map to BuildingType 18-22 (cost 10).
        """
        game, users = _make_human_game(db, "BuilderAffordable")
        res, _ = self._enter_builder(client, game, users)
        assert res.status_code == 200
        mask = res.json()["action_mask"]
        # Large violet buildings: BuildingType 18-22 → actions 34-38
        large_violet_bits = mask[34:39]
        assert sum(large_violet_bits) == 0, "Unaffordable buildings must be masked"


# ---------------------------------------------------------------------------
# TRADER PHASE
# ---------------------------------------------------------------------------

class TestTraderPhase:
    """
    Select Trader role (action 4) → enter Trader phase.
    Trader phase: actions 39-43 sell goods (Good 0-4).
    At game start, players have no goods → only pass (action 15) is valid.
    """

    def _enter_trader(self, client, game, users):
        start_res, current_user = _start_human_turn(client, game, users)
        mask = start_res["action_mask"]
        # Role.TRADER == 4
        if mask[4] == 0:
            pytest.skip("Trader role not available")
        return _action(client, game.id, 4, _bearer(current_user.id)), current_user

    def test_trader_role_select_enters_phase(self, client, db):
        game, users = _make_human_game(db, "TraderEnter")
        res, _ = self._enter_trader(client, game, users)
        assert res.status_code == 200

    def test_trader_cannot_sell_without_goods(self, client, db):
        """
        At game start players have no goods.
        Sell actions 39-43 must all be masked off.
        Pass (15) should be available.
        """
        game, users = _make_human_game(db, "TraderNoGoods")
        res, _ = self._enter_trader(client, game, users)
        assert res.status_code == 200
        mask = res.json()["action_mask"]
        sell_bits = mask[39:44]
        assert sum(sell_bits) == 0, "Cannot sell without goods"
        assert mask[15] == 1, "Pass must be available when no goods to sell"

    def test_trader_sell_action_rejected_when_masked(self, client, db):
        game, users = _make_human_game(db, "TraderMaskedSell")
        res, current_user = self._enter_trader(client, game, users)
        assert res.status_code == 200
        # Try to sell corn (action 41, Good.CORN=2) without any goods
        res2 = _action(client, game.id, 41, _bearer(current_user.id))
        assert res2.status_code == 400

    def test_trader_pass_accepted(self, client, db):
        game, users = _make_human_game(db, "TraderPass")
        res, current_user = self._enter_trader(client, game, users)
        assert res.status_code == 200
        mask = res.json()["action_mask"]
        if mask[15] != 1:
            pytest.skip("Pass not available in trader phase")
        res2 = _action(client, game.id, 15, _bearer(current_user.id))
        assert res2.status_code == 200


# ---------------------------------------------------------------------------
# CAPTAIN PHASE
# ---------------------------------------------------------------------------

class TestCaptainPhase:
    """
    Select Captain role (action 5) → enter Captain phase.
    Captain actions: 44-58 load ships, 59-63 wharf, 15 pass.
    At game start, players have no goods → pass (action 15) should be valid.
    """

    def _enter_captain(self, client, game, users):
        start_res, current_user = _start_human_turn(client, game, users)
        mask = start_res["action_mask"]
        # Role.CAPTAIN == 5
        if mask[5] == 0:
            pytest.skip("Captain role not available")
        return _action(client, game.id, 5, _bearer(current_user.id)), current_user

    def test_captain_role_select_enters_phase(self, client, db):
        game, users = _make_human_game(db, "CaptainEnter")
        res, _ = self._enter_captain(client, game, users)
        assert res.status_code == 200

    def test_captain_cannot_load_without_goods(self, client, db):
        """No goods → load actions 44-58 must be masked."""
        game, users = _make_human_game(db, "CaptainNoGoods")
        res, _ = self._enter_captain(client, game, users)
        assert res.status_code == 200
        mask = res.json()["action_mask"]
        load_bits = mask[44:59]
        assert sum(load_bits) == 0, "Cannot load without goods"

    def test_captain_wharf_actions_blocked_without_goods(self, client, db):
        game, users = _make_human_game(db, "CaptainWharf")
        res, _ = self._enter_captain(client, game, users)
        assert res.status_code == 200
        mask = res.json()["action_mask"]
        wharf_bits = mask[59:64]
        assert sum(wharf_bits) == 0, "Wharf actions blocked without goods"

    def test_captain_load_masked_action_blocked(self, client, db):
        game, users = _make_human_game(db, "CaptainMaskedLoad")
        res, current_user = self._enter_captain(client, game, users)
        assert res.status_code == 200
        # Try to load coffee (action 44) without having any coffee
        res2 = _action(client, game.id, 44, _bearer(current_user.id))
        assert res2.status_code == 400

    def test_captain_pass_accepted_when_no_goods(self, client, db):
        game, users = _make_human_game(db, "CaptainPass")
        res, current_user = self._enter_captain(client, game, users)
        assert res.status_code == 200
        mask = res.json()["action_mask"]
        if mask[15] != 1:
            pytest.skip("Pass not available in captain phase")
        res2 = _action(client, game.id, 15, _bearer(current_user.id))
        assert res2.status_code == 200


# ---------------------------------------------------------------------------
# MAYOR PHASE
# ---------------------------------------------------------------------------

class TestMayorPhase:
    """
    Select Mayor role (action 1) → enter Mayor phase.
    Mayor actions: 69-72 place colonists.
    """

    def _enter_mayor(self, client, game, users):
        start_res, current_user = _start_human_turn(client, game, users)
        mask = start_res["action_mask"]
        # Role.MAYOR == 1
        if mask[1] == 0:
            pytest.skip("Mayor role not available")
        return _action(client, game.id, 1, _bearer(current_user.id)), current_user

    def test_mayor_role_select_enters_phase(self, client, db):
        game, users = _make_human_game(db, "MayorEnter")
        res, _ = self._enter_mayor(client, game, users)
        assert res.status_code == 200

    def test_mayor_has_colonist_placement_actions(self, client, db):
        game, users = _make_human_game(db, "MayorActions")
        res, _ = self._enter_mayor(client, game, users)
        assert res.status_code == 200
        mask = res.json()["action_mask"]
        mayor_bits = mask[69:73]
        assert sum(mayor_bits) >= 1, "Mayor phase must have colonist placement actions"

    def test_mayor_valid_colonist_placement(self, client, db):
        game, users = _make_human_game(db, "MayorPlacement")
        res, current_user = self._enter_mayor(client, game, users)
        assert res.status_code == 200
        mask = res.json()["action_mask"]
        mayor_valid = next((i for i in range(69, 73) if mask[i] == 1), None)
        if mayor_valid is None:
            pytest.skip("No mayor placement action available")
        res2 = _action(client, game.id, mayor_valid, _bearer(current_user.id))
        assert res2.status_code == 200

    def test_mayor_settler_actions_blocked(self, client, db):
        """Settler actions (8-14) must be blocked during Mayor phase."""
        game, users = _make_human_game(db, "MayorSettlerMask")
        res, _ = self._enter_mayor(client, game, users)
        assert res.status_code == 200
        mask = res.json()["action_mask"]
        settler_bits = mask[8:15]
        assert sum(settler_bits) == 0, "Settler actions must be blocked in Mayor phase"

    def test_mayor_builder_actions_blocked(self, client, db):
        """Builder actions (16-38) must be blocked during Mayor phase."""
        game, users = _make_human_game(db, "MayorBuilderMask")
        res, _ = self._enter_mayor(client, game, users)
        assert res.status_code == 200
        mask = res.json()["action_mask"]
        builder_bits = mask[16:39]
        assert sum(builder_bits) == 0, "Builder actions must be blocked in Mayor phase"


# ---------------------------------------------------------------------------
# WRONG TURN / SEQUENCE EDGE CASES
# ---------------------------------------------------------------------------

class TestWrongTurnEdgeCases:
    def test_second_user_cannot_act_on_first_users_turn(self, client, db):
        """
        With 3-player game (user0, user1, user2):
        After game start, the current player is the governor.
        The non-current human must get 400 when trying to act.

        Governor is random, so we inspect `global_state.current_player` from the
        start response to determine who the current player is, then have the
        OTHER human try to act.
        """
        user0 = _make_user(db, "Player0")
        user1 = _make_user(db, "Player1")
        user2 = _make_user(db, "Player2")
        game = _make_game(db, [str(user0.id), str(user1.id), str(user2.id)])

        start_res = _start(client, game.id, _bearer(user0.id))
        current_player_idx = int(start_res["state"]["meta"]["active_player"].split("_")[1])

        # Map player index → user
        players = [user0, user1, user2]
        current_user = players[current_player_idx]
        # Pick any other human player
        other_users = [u for u in players if u.id != current_user.id]
        wrong_user = other_users[0]

        valid = _first_valid(start_res["action_mask"])
        res = _action(client, game.id, valid, _bearer(wrong_user.id))
        assert res.status_code == 400
        assert "turn" in res.json()["detail"].lower()

    def test_correct_user_can_act_on_their_turn(self, client, db):
        """The current (governor) player can act on their turn."""
        user0 = _make_user(db, "RightPlayer0")
        user1 = _make_user(db, "RightPlayer1")
        user2 = _make_user(db, "RightPlayer2")
        game = _make_game(db, [str(user0.id), str(user1.id), str(user2.id)])

        start_res = _start(client, game.id, _bearer(user0.id))
        current_player_idx = int(start_res["state"]["meta"]["active_player"].split("_")[1])
        players = [user0, user1, user2]
        current_user = players[current_player_idx]

        valid = _first_valid(start_res["action_mask"])
        res = _action(client, game.id, valid, _bearer(current_user.id))
        assert res.status_code == 200


# ---------------------------------------------------------------------------
# CONSECUTIVE ACTIONS
# ---------------------------------------------------------------------------

class TestConsecutiveActions:
    def test_two_consecutive_valid_actions(self, client, db):
        """
        1. user selects a role.
        2. user performs the phase action.
        Both should return 200.
        """
        game, users = _make_human_game(db, "Consecutive")
        start_res, current_user = _start_human_turn(client, game, users)

        # Step 1: select first valid role
        role_mask = start_res["action_mask"]
        role_action = _first_valid(role_mask)
        res1 = _action(client, game.id, role_action, _bearer(current_user.id))
        assert res1.status_code == 200

        # Step 2: perform first valid phase action
        phase_mask = res1.json()["action_mask"]
        phase_action = _first_valid(phase_mask)
        res2 = _action(client, game.id, phase_action, _bearer(current_user.id))
        assert res2.status_code == 200

    def test_cannot_replay_already_consumed_action(self, client, db):
        """
        After a valid action is processed the state changes.
        Repeating the same action index may now be masked — should 400.
        """
        game, users = _make_human_game(db, "Replay")
        start_res, current_user = _start_human_turn(client, game, users)

        role_action = _first_valid(start_res["action_mask"])
        res1 = _action(client, game.id, role_action, _bearer(current_user.id))
        assert res1.status_code == 200

        # Attempt to resend the same role-selection action (now stale)
        # If still valid in the new phase, pick an action we know is now invalid
        phase_mask = res1.json()["action_mask"]
        if phase_mask[role_action] == 0:
            # The old role action is now masked → should 400
            res2 = _action(client, game.id, role_action, _bearer(current_user.id))
            assert res2.status_code == 400
        # else: the action might still be valid in the new state — skip
