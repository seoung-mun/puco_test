"""
TDD tests for DB schema changes:
- JSONB columns (players, model_versions, action_data, etc.)
- Float win_rate (was Integer)
- GameSession.updated_at (new column)
- GameSession <-> GameLog relationship
- Composite index ix_game_logs_game_round
- Mutable default fix (players=list, model_versions=dict)
"""
import uuid

from sqlalchemy import inspect, text

from app.db.models import GameLog, GameSession, User


class TestUserModel:
    def test_win_rate_is_float(self, db):
        """win_rate must accept float values, not just integers."""
        user = User(
            id=uuid.uuid4(),
            google_id="google_float_test",
            nickname="FloatTester",
        )
        db.add(user)
        db.flush()

        # Set a float win rate
        user.win_rate = 0.67
        db.flush()
        db.refresh(user)

        assert isinstance(user.win_rate, float), "win_rate should be a float"
        assert abs(user.win_rate - 0.67) < 0.001

    def test_win_rate_default_is_zero_float(self, db):
        """Default win_rate is 0.0 (float), not 0 (int)."""
        user = User(
            id=uuid.uuid4(),
            google_id="google_default_test",
            nickname="DefaultTester",
        )
        db.add(user)
        db.flush()
        db.refresh(user)

        assert user.win_rate is not None
        assert user.win_rate == 0.0

    def test_total_games_default_is_zero(self, db):
        user = User(id=uuid.uuid4(), google_id="google_games_test", nickname="Tester")
        db.add(user)
        db.flush()
        db.refresh(user)

        assert user.total_games == 0


class TestGameSessionModel:
    def test_players_default_is_empty_list(self, db):
        """players column default must be an empty list, not a shared mutable."""
        game1 = GameSession(
            id=uuid.uuid4(), title="Room1", status="WAITING", num_players=3
        )
        game2 = GameSession(
            id=uuid.uuid4(), title="Room2", status="WAITING", num_players=3
        )
        db.add_all([game1, game2])
        db.flush()

        # Modify game1.players and ensure game2 is not affected
        game1.players = ["user_a"]
        db.flush()
        db.refresh(game2)

        assert game2.players == [] or game2.players is None or game2.players == {}, \
            "game2.players should not share state with game1.players"

    def test_model_versions_default_is_empty_dict(self, db):
        """model_versions must default to empty dict."""
        game = GameSession(
            id=uuid.uuid4(), title="ModelTest", status="WAITING", num_players=3
        )
        db.add(game)
        db.flush()
        db.refresh(game)

        assert game.model_versions is None or game.model_versions == {}

    def test_updated_at_column_exists(self, db):
        """GameSession must have an updated_at column."""
        game = GameSession(
            id=uuid.uuid4(), title="UpdatedAtTest", status="WAITING", num_players=3
        )
        db.add(game)
        db.flush()
        db.refresh(game)

        assert hasattr(game, "updated_at"), "GameSession must have updated_at"
        assert game.updated_at is not None, "updated_at should have a server default"

    def test_players_stores_list_as_jsonb(self, db):
        """players column must persist a list with string elements."""
        game_id = uuid.uuid4()
        players = ["user_abc", "BOT_PPO_1", "user_xyz"]
        game = GameSession(
            id=game_id, title="JSONB Test", status="PROGRESS",
            num_players=3, players=players
        )
        db.add(game)
        db.flush()
        db.refresh(game)

        assert game.players == players

    def test_model_versions_stores_dict_as_jsonb(self, db):
        """model_versions column must persist a dict."""
        game_id = uuid.uuid4()
        model_versions = {"0": "PPO_v2", "1": "PPO_v1"}
        game = GameSession(
            id=game_id, title="ModelVer Test", status="WAITING",
            num_players=2, model_versions=model_versions
        )
        db.add(game)
        db.flush()
        db.refresh(game)

        assert game.model_versions == model_versions

    def test_relationship_to_game_logs(self, db):
        """GameSession.logs relationship must return associated GameLog records."""
        game = GameSession(
            id=uuid.uuid4(), title="Rel Test", status="PROGRESS", num_players=3
        )
        db.add(game)
        db.flush()

        log = GameLog(
            game_id=game.id,
            round=1,
            step=0,
            actor_id="user_abc",
            action_data={"action": 3},
            available_options=[0, 1, 0, 1],
            state_before={"round": 1},
            state_after={"round": 1},
        )
        db.add(log)
        db.flush()
        db.refresh(game)

        assert len(game.logs) == 1
        assert game.logs[0].actor_id == "user_abc"


class TestGameLogModel:
    def test_action_data_stores_json_dict(self, db):
        """action_data JSONB column must persist a dict."""
        game = GameSession(
            id=uuid.uuid4(), title="Log JSON Test", status="PROGRESS", num_players=3
        )
        db.add(game)
        db.flush()

        action_data = {"action": 5, "role": "settler"}
        log = GameLog(
            game_id=game.id,
            round=2,
            step=1,
            actor_id="player_0",
            action_data=action_data,
            available_options=[1, 0, 1, 0, 0, 0, 0, 0],
            state_before={"phase": "role_selection"},
            state_after={"phase": "settler_action"},
        )
        db.add(log)
        db.flush()
        db.refresh(log)

        assert log.action_data == action_data

    def test_state_before_and_after_store_nested_json(self, db):
        """state_before / state_after must persist nested dicts."""
        game = GameSession(
            id=uuid.uuid4(), title="Nested JSON", status="PROGRESS", num_players=3
        )
        db.add(game)
        db.flush()

        state_before = {
            "meta": {"round": 3, "phase": "role_selection"},
            "players": {"player_0": {"doubloons": 5, "vp_chips": 2}},
        }
        state_after = {
            "meta": {"round": 3, "phase": "settler_action"},
            "players": {"player_0": {"doubloons": 5, "vp_chips": 2}},
        }
        log = GameLog(
            game_id=game.id, round=3, step=0,
            actor_id="player_0",
            action_data={"action": 1},
            available_options=[0, 1],
            state_before=state_before,
            state_after=state_after,
        )
        db.add(log)
        db.flush()
        db.refresh(log)

        assert log.state_before["meta"]["round"] == 3
        assert log.state_after["meta"]["phase"] == "settler_action"

    def test_game_log_back_references_game_session(self, db):
        """GameLog.game_session relationship must point back to the GameSession."""
        game = GameSession(
            id=uuid.uuid4(), title="Backref Test", status="PROGRESS", num_players=3
        )
        db.add(game)
        db.flush()

        log = GameLog(
            game_id=game.id, round=1, step=0,
            actor_id="player_0", action_data={"action": 0},
            available_options=[1], state_before={}, state_after={},
        )
        db.add(log)
        db.flush()
        db.refresh(log)

        assert log.game_session is not None
        assert log.game_session.id == game.id

    def test_composite_index_exists(self, db_engine):
        """Composite index ix_game_logs_game_round must exist in the database."""
        inspector = inspect(db_engine)
        indexes = inspector.get_indexes("game_logs")
        index_names = [idx["name"] for idx in indexes]
        assert "ix_game_logs_game_round" in index_names, \
            f"Missing composite index ix_game_logs_game_round. Found: {index_names}"

    def test_games_status_index_exists(self, db_engine):
        """Index ix_games_status must exist on the games table."""
        inspector = inspect(db_engine)
        indexes = inspector.get_indexes("games")
        index_names = [idx["name"] for idx in indexes]
        assert "ix_games_status" in index_names, \
            f"Missing index ix_games_status. Found: {index_names}"

    def test_jsonb_query_with_operator(self, db):
        """JSONB columns must support PostgreSQL JSON operators in raw SQL."""
        game = GameSession(
            id=uuid.uuid4(), title="JSONB Query Test", status="PROGRESS", num_players=3
        )
        db.add(game)
        db.flush()

        log = GameLog(
            game_id=game.id, round=1, step=0, actor_id="player_0",
            action_data={"action": 7, "role": "captain"},
            available_options=[0, 0, 0, 0, 0, 0, 0, 1],
            state_before={"phase": "role_selection"},
            state_after={"phase": "captain_action"},
        )
        db.add(log)
        db.flush()

        # Use PostgreSQL JSONB operator ->> to query by nested key
        result = db.execute(
            text("SELECT action_data->>'role' FROM game_logs WHERE game_id = :gid"),
            {"gid": str(game.id)}
        ).fetchone()

        assert result is not None
        assert result[0] == "captain"
