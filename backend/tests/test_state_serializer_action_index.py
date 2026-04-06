"""
TDD: StateSerializer action_index 포함 검증

Channel API 전환을 위해 serialize_game_state() / serialize_game_state_from_engine()가
프론트엔드에서 action_index를 바로 쓸 수 있도록 각 interactive 요소에 action_index를 포함해야 한다.

Action space (action_translator.py 참고):
  0-7:    select_role (Role enum value)
  8-13:   settle_plantation (face-up index 0-5)
  14:     settle_quarry
  15:     pass
  16-38:  build (BuildingType value + 16)
  39-43:  sell (Good value + 39)
  44-58:  load_ship
  59-63:  load_wharf
  64-68:  store_windrose
  69-80:  mayor_island (slot index 0-11)
  81-92:  mayor_city (slot index 0-11)
  93-97:  craftsman_priv
  105:    hacienda_draw
  106-110: store_warehouse
"""
import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_action_index.db")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../PuCo_RL")))

import pytest

from app.engine_wrapper.wrapper import create_game_engine
from app.services.state_serializer import serialize_game_state_from_engine


# ================================================================== #
#  Helper                                                              #
# ================================================================== #

@pytest.fixture
def engine():
    return create_game_engine(num_players=3)


@pytest.fixture
def state(engine):
    return serialize_game_state_from_engine(
        engine=engine,
        player_names=["Alice", "Bot1", "Bot2"],
        game_id="test-game-id",
        bot_players={1: "random", 2: "random"},
    )


# ================================================================== #
#  Feature 1: meta 에 pass_action_index 포함                          #
# ================================================================== #

class TestMetaPassActionIndex:

    def test_meta_has_pass_action_index(self, state):
        """meta에 pass_action_index=15가 있어야 한다."""
        assert "pass_action_index" in state["meta"], (
            f"meta에 pass_action_index 없음. 키 목록: {list(state['meta'].keys())}"
        )
        assert state["meta"]["pass_action_index"] == 15

    def test_meta_has_hacienda_action_index(self, state):
        """meta에 hacienda_action_index=105가 있어야 한다."""
        assert "hacienda_action_index" in state["meta"]
        assert state["meta"]["hacienda_action_index"] == 105


# ================================================================== #
#  Feature 2: common_board.roles에 action_index 포함                  #
# ================================================================== #

class TestRolesActionIndex:

    def test_available_roles_have_action_index(self, state):
        """common_board.roles의 available role(taken_by=None)에 action_index가 있어야 한다."""
        roles = state["common_board"]["roles"]
        assert len(roles) > 0, "roles가 비어있음"

        for role_name, role_data in roles.items():
            if role_data.get("taken_by") is None:
                assert "action_index" in role_data, (
                    f"available role '{role_name}'에 action_index 없음. 키: {list(role_data.keys())}"
                )

    def test_settler_role_action_index_is_correct(self, state):
        """settler 역할의 action_index는 0이어야 한다 (Role.SETTLER.value == 0)."""
        from configs.constants import Role
        roles = state["common_board"]["roles"]
        if "settler" in roles and roles["settler"].get("taken_by") is None:
            assert roles["settler"]["action_index"] == Role.SETTLER.value, (
                f"settler action_index 오류: {roles['settler'].get('action_index')}"
            )

    def test_role_action_index_is_integer(self, state):
        """action_index는 정수여야 한다."""
        roles = state["common_board"]["roles"]
        for role_name, role_data in roles.items():
            if "action_index" in role_data:
                assert isinstance(role_data["action_index"], int), (
                    f"roles[{role_name}].action_index가 int가 아님: {type(role_data['action_index'])}"
                )

    def test_role_action_index_in_valid_range(self, state):
        """role action_index는 0-7 범위여야 한다."""
        roles = state["common_board"]["roles"]
        for role_name, role_data in roles.items():
            if "action_index" in role_data:
                ai = role_data["action_index"]
                assert 0 <= ai <= 7, (
                    f"roles[{role_name}].action_index={ai} 범위 벗어남 (0-7)"
                )


# ================================================================== #
#  Feature 3: face_up plantations에 action_index 포함                 #
# ================================================================== #

class TestPlantationsActionIndex:

    def test_face_up_plantations_have_action_index(self, state):
        """available_plantations.face_up 각 항목이 action_index를 포함해야 한다.

        현재: ["corn", "indigo", ...]
        변경: [{"type": "corn", "action_index": 8}, ...]
        """
        face_up = state["common_board"]["available_plantations"]["face_up"]
        assert len(face_up) > 0, "face_up plantations가 비어있음"

        for i, item in enumerate(face_up):
            assert isinstance(item, dict), (
                f"face_up[{i}]가 str이 아닌 dict여야 함: {item!r}"
            )
            assert "type" in item, f"face_up[{i}]에 'type' 없음"
            assert "action_index" in item, f"face_up[{i}]에 'action_index' 없음"

    def test_face_up_plantation_action_index_range(self, state):
        """면-up plantation action_index는 8-13 범위여야 한다."""
        face_up = state["common_board"]["available_plantations"]["face_up"]
        for i, item in enumerate(face_up):
            if isinstance(item, dict) and "action_index" in item:
                ai = item["action_index"]
                assert 8 <= ai <= 13, (
                    f"face_up[{i}].action_index={ai} 범위 벗어남 (8-13)"
                )

    def test_face_up_plantation_action_index_matches_position(self, state):
        """i번째 face-up plantation의 action_index는 8+i이어야 한다."""
        face_up = state["common_board"]["available_plantations"]["face_up"]
        for i, item in enumerate(face_up):
            if isinstance(item, dict) and "action_index" in item:
                assert item["action_index"] == 8 + i, (
                    f"face_up[{i}].action_index={item['action_index']}, 기대값={8+i}"
                )

    def test_quarry_action_index_is_14(self, state):
        """quarry tile의 action_index는 14여야 한다."""
        face_up = state["common_board"]["available_plantations"]["face_up"]
        for item in face_up:
            if isinstance(item, dict) and item.get("type") == "quarry":
                assert item["action_index"] == 14, (
                    f"quarry action_index={item['action_index']}, 기대값=14"
                )


# ================================================================== #
#  Feature 4: available_buildings에 action_index 포함                 #
# ================================================================== #

class TestBuildingsActionIndex:

    def test_available_buildings_have_action_index(self, state):
        """available_buildings 각 항목에 action_index가 있어야 한다."""
        buildings = state["common_board"]["available_buildings"]
        if not buildings:
            pytest.skip("available_buildings가 비어있음 (게임 시작 직후엔 있어야 함)")

        for bname, bdata in buildings.items():
            assert "action_index" in bdata, (
                f"available_buildings[{bname}]에 action_index 없음. 키: {list(bdata.keys())}"
            )

    def test_available_buildings_action_index_range(self, state):
        """building action_index는 16-38 범위여야 한다."""
        buildings = state["common_board"]["available_buildings"]
        for bname, bdata in buildings.items():
            if "action_index" in bdata:
                ai = bdata["action_index"]
                assert 16 <= ai <= 38, (
                    f"buildings[{bname}].action_index={ai} 범위 벗어남 (16-38)"
                )

    def test_small_indigo_plant_action_index(self, state):
        """small_indigo_plant의 action_index는 16 (BuildingType.SMALL_INDIGO_PLANT.value=0, 16+0=16)."""
        buildings = state["common_board"]["available_buildings"]
        if "small_indigo_plant" in buildings:
            ai = buildings["small_indigo_plant"]["action_index"]
            assert ai == 16, f"small_indigo_plant action_index={ai}, 기대=16"


# ================================================================== #
#  Feature 5: serialize_game_state_from_engine 기본 구조               #
# ================================================================== #

class TestSerializeFromEngine:

    def test_returns_meta_key(self, state):
        """반환값에 meta 키가 있어야 한다."""
        assert "meta" in state

    def test_returns_common_board_key(self, state):
        """반환값에 common_board 키가 있어야 한다."""
        assert "common_board" in state

    def test_returns_players_key(self, state):
        """반환값에 players 키가 있어야 한다."""
        assert "players" in state

    def test_player_names_reflected(self, state):
        """player_names가 players에 반영되어야 한다."""
        players = state["players"]
        names = [players[f"player_{i}"]["display_name"] for i in range(3)]
        assert names == ["Alice", "Bot1", "Bot2"]

    def test_bot_players_in_state(self, state):
        """bot_players 정보가 상태에 포함되어야 한다."""
        assert "bot_players" in state
        bp = state["bot_players"]
        assert bp.get("player_1") == "random"
        assert bp.get("player_2") == "random"

    def test_action_mask_key_in_state(self, state):
        """action_mask가 상태에 포함되어야 한다."""
        assert "action_mask" in state
        mask = state["action_mask"]
        assert isinstance(mask, list)
        assert len(mask) > 0
        assert all(v in (0, 1) for v in mask)
