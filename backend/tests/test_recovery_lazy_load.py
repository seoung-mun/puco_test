"""Spec Section 8.2: lazy per-game recovery behavior."""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.security import create_access_token
from app.db.models import GameLog, GameSession, User
from app.services.game_service import EngineLoadResult
from app.services.canonical_action import _describe_action
from app.services.game_service import GameService


class _SessionContext:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, exc_type, exc, tb):
        return False


def _session_local_factory(db):
    def _factory():
        return _SessionContext(db)

    return _factory


def _make_started_game_with_actions(db, action_count: int = 2):
    users = []
    for idx in range(3):
        user = User(
            id=uuid.uuid4(),
            google_id=f"lazy_recovery_gid_{idx}_{uuid.uuid4().hex}",
            nickname=f"LazyRecovery{idx}",
        )
        db.add(user)
        users.append(user)
    db.flush()

    room = GameSession(
        id=uuid.uuid4(),
        title="Lazy Recovery Room",
        status="WAITING",
        num_players=3,
        players=[str(user.id) for user in users],
        host_id=str(users[0].id),
    )
    db.add(room)
    db.commit()

    service = GameService(db)
    service.start_game(room.id)

    for _ in range(action_count):
        engine = GameService.active_engines[room.id]
        action_mask = engine.get_action_mask()
        action_index = next(idx for idx, valid in enumerate(action_mask) if valid)
        actor_id = str(users[engine.env.game.current_player_idx].id)
        decoded = _describe_action(action_index, state={})
        service.process_action(
            room.id,
            actor_id,
            action_index,
            canonical_id=decoded["canonical_id"] if decoded else None,
        )

    return room.id, users


@pytest.mark.asyncio
async def test_lazy_recovery_reloads_evicted_engine_from_journal(db):
    game_id, _users = _make_started_game_with_actions(db, action_count=3)
    GameService.active_engines.pop(game_id, None)
    GameService._engine_revision.pop(game_id, None)

    expected_game = db.query(GameSession).filter(GameSession.id == game_id).first()
    expected_logs = db.query(GameLog).filter(GameLog.game_id == game_id).count()

    service = GameService(db)
    result = await service.ensure_engine_loaded(game_id)

    assert result.state == "ready"
    assert result.state_revision == expected_game.state_revision
    assert expected_logs == expected_game.state_revision
    assert game_id in GameService.active_engines
    assert GameService._engine_revision[game_id] == expected_game.state_revision


def test_lazy_recovery_on_action_endpoint_after_engine_eviction(client, db):
    game_id, users = _make_started_game_with_actions(db, action_count=2)
    engine = GameService.active_engines[game_id]
    action_mask = engine.get_action_mask()
    action_index = next(idx for idx, valid in enumerate(action_mask) if valid)
    actor_id = str(users[engine.env.game.current_player_idx].id)
    headers = {"Authorization": f"Bearer {create_access_token(subject=actor_id)}"}

    GameService.active_engines.pop(game_id, None)
    GameService._engine_revision.pop(game_id, None)

    response = client.post(
        f"/api/puco/game/{game_id}/action",
        json={"payload": {"action_index": action_index}},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "success"
    assert game_id in GameService.active_engines

    row = db.query(GameSession).filter(GameSession.id == game_id).first()
    assert row is not None
    assert GameService._engine_revision[game_id] == row.state_revision


@pytest.mark.asyncio
async def test_lazy_recovery_on_ws_connect_emits_state_update_once(monkeypatch, db):
    from app.api.channel import ws as ws_module

    game_id = uuid.uuid4()
    player = User(
        id=uuid.uuid4(),
        google_id=f"ws_lazy_gid_{uuid.uuid4().hex}",
        nickname="WsRecoveryPlayer",
    )
    db.add(player)
    db.flush()
    room = GameSession(
        id=game_id,
        title="WS Recovery Room",
        status="PROGRESS",
        num_players=3,
        players=[str(player.id), "BOT_random", "BOT_random"],
        host_id=str(player.id),
    )
    db.add(room)
    db.flush()

    websocket = MagicMock()
    websocket.accept = AsyncMock()
    websocket.receive_json = AsyncMock(
        return_value={"token": create_access_token(subject=str(player.id))}
    )
    websocket.receive_text = AsyncMock(side_effect=ws_module.WebSocketDisconnect(code=1000))
    websocket.send_json = AsyncMock()
    websocket.close = AsyncMock()

    connect_mock = AsyncMock()
    disconnect_mock = AsyncMock()
    monkeypatch.setattr(ws_module, "SessionLocal", _session_local_factory(db))
    monkeypatch.setattr(ws_module.manager, "connect", connect_mock)
    monkeypatch.setattr(ws_module.manager, "disconnect", disconnect_mock)
    monkeypatch.setattr(
        ws_module.GameService,
        "ensure_engine_loaded",
        AsyncMock(return_value=EngineLoadResult(state="ready", state_revision=3)),
    )
    monkeypatch.setattr(
        ws_module.GameService,
        "_fetch_or_build_rich_state",
        AsyncMock(return_value={"meta": {"game_id": str(game_id)}, "action_mask": [1, 0, 1]}),
    )

    await ws_module.websocket_endpoint(websocket, str(game_id))

    sent_messages = [call.args[0] for call in websocket.send_json.await_args_list]
    assert sent_messages[0] == {"type": "auth_ok", "player_id": str(player.id)}
    state_updates = [msg for msg in sent_messages if msg.get("type") == "STATE_UPDATE"]
    assert len(state_updates) == 1
    assert state_updates[0]["data"]["meta"]["game_id"] == str(game_id)
    connect_mock.assert_awaited_once_with(str(game_id), websocket, player_id=str(player.id))
    disconnect_mock.assert_awaited_once_with(str(game_id), websocket, player_id=str(player.id))


@pytest.mark.asyncio
async def test_concurrent_recovery_runs_replay_only_once(db, monkeypatch):
    game_id, _users = _make_started_game_with_actions(db, action_count=3)
    GameService.active_engines.pop(game_id, None)
    GameService._engine_revision.pop(game_id, None)
    GameService._recovery_locks.pop(game_id, None)

    service = GameService(db)
    call_count = 0
    original = service._recover_with_db

    def wrapped_recover(sync_db, sync_game_id):
        nonlocal call_count
        call_count += 1
        return original(sync_db, sync_game_id)

    monkeypatch.setattr(service, "_recover_with_db", wrapped_recover)

    results = await asyncio.gather(
        *(service.ensure_engine_loaded(game_id) for _ in range(10))
    )

    assert all(result.state == "ready" for result in results)
    assert call_count == 1
