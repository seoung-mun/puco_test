"""Contract tests for ``ConnectionManager._broadcast`` resilience.

Covers Task 2 §1.2 Step 3 of
``docs/superpowers/plans/2026-05-05-error-log-stabilization.md``:

- Concurrent send via ``asyncio.gather(..., return_exceptions=True)`` so a
  single slow / dead socket cannot stall the rest of the room.
- Dead-socket harvesting: failures must be removed from
  ``active_connections`` and ``_conn_ids``.
- When the entire room becomes dead in a single broadcast, the ``game_id``
  entry must be popped so the Redis listener can exit.
- The Redis listener must keep running until the room has truly zero
  active sockets (we cover the contract by exercising the broadcast cleanup
  that the listener observes).
"""

import json
from unittest.mock import AsyncMock

import pytest

from app.services.ws_manager import ConnectionManager


def _make_socket() -> AsyncMock:
    """Build a minimal fake websocket whose ``send_text`` we can mock."""
    sock = AsyncMock()
    sock.send_text = AsyncMock()
    return sock


@pytest.mark.asyncio
async def test_broadcast_concurrent_happy_path_no_drops(caplog):
    """All sockets succeed → all called once, none harvested, no error log."""
    mgr = ConnectionManager()
    game_id = "g-happy"
    s1, s2, s3 = _make_socket(), _make_socket(), _make_socket()
    mgr.active_connections[game_id] = {s1, s2, s3}
    for s in (s1, s2, s3):
        mgr._get_connection_id(s)  # populate _conn_ids

    payload = json.dumps({"type": "PING"})
    with caplog.at_level("WARNING"):
        await mgr._broadcast(game_id, payload)

    s1.send_text.assert_awaited_once_with(payload)
    s2.send_text.assert_awaited_once_with(payload)
    s3.send_text.assert_awaited_once_with(payload)
    # No harvesting happened.
    assert mgr.active_connections[game_id] == {s1, s2, s3}
    assert all(id(s) in mgr._conn_ids for s in (s1, s2, s3))
    # No ws_broadcast_error log emitted.
    error_records = [r for r in caplog.records if "ws_broadcast_error" in r.getMessage()]
    assert error_records == []
    # Start/end log contract preserved.
    msgs = [r.getMessage() for r in caplog.records]
    assert any("ws_broadcast_start" in m for m in msgs)
    assert any("ws_broadcast_end" in m for m in msgs)


@pytest.mark.asyncio
async def test_broadcast_dead_socket_harvested_others_still_delivered(caplog):
    """The middle socket raises → other two still receive the message;
    dead socket is removed from active_connections AND _conn_ids."""
    mgr = ConnectionManager()
    game_id = "g-mixed"
    s_ok1 = _make_socket()
    s_dead = _make_socket()
    s_dead.send_text.side_effect = RuntimeError("boom")
    s_ok2 = _make_socket()

    # Use a list to keep a deterministic order, then build the set.
    mgr.active_connections[game_id] = {s_ok1, s_dead, s_ok2}
    for s in (s_ok1, s_dead, s_ok2):
        mgr._get_connection_id(s)

    payload = json.dumps({"type": "STATE_UPDATE"})
    with caplog.at_level("WARNING"):
        await mgr._broadcast(game_id, payload)

    # gather did NOT short-circuit — the two healthy sockets still got called.
    s_ok1.send_text.assert_awaited_once_with(payload)
    s_ok2.send_text.assert_awaited_once_with(payload)
    s_dead.send_text.assert_awaited_once_with(payload)

    # Dead socket is gone, healthy ones remain, set length is 2.
    assert mgr.active_connections[game_id] == {s_ok1, s_ok2}
    assert len(mgr.active_connections[game_id]) == 2
    assert id(s_dead) not in mgr._conn_ids
    assert id(s_ok1) in mgr._conn_ids
    assert id(s_ok2) in mgr._conn_ids

    # ws_broadcast_error log was emitted with exc_info attached.
    error_records = [r for r in caplog.records if "ws_broadcast_error" in r.getMessage()]
    assert len(error_records) == 1
    err = error_records[0]
    assert err.exc_info is not None
    # exc_info[1] is the exception instance.
    assert isinstance(err.exc_info[1], RuntimeError)

    # ws_broadcast_harvested summary line emitted with dropped_count=1.
    harvest_records = [
        r for r in caplog.records if "ws_broadcast_harvested" in r.getMessage()
    ]
    assert len(harvest_records) == 1
    assert "dropped_count=1" in harvest_records[0].getMessage()


@pytest.mark.asyncio
async def test_broadcast_all_sockets_dead_drops_room_entry(caplog):
    """Every socket raises → game_id removed from active_connections entirely
    so the Redis listener will exit on its next iteration."""
    mgr = ConnectionManager()
    game_id = "g-allgone"
    sockets = []
    for _ in range(3):
        s = _make_socket()
        s.send_text.side_effect = RuntimeError("dead")
        sockets.append(s)
    mgr.active_connections[game_id] = set(sockets)
    for s in sockets:
        mgr._get_connection_id(s)

    payload = json.dumps({"type": "BROADCAST"})
    with caplog.at_level("WARNING"):
        await mgr._broadcast(game_id, payload)

    assert game_id not in mgr.active_connections
    for s in sockets:
        assert id(s) not in mgr._conn_ids
    # Three errors + one harvested summary line.
    error_records = [r for r in caplog.records if "ws_broadcast_error" in r.getMessage()]
    assert len(error_records) == 3
    harvest_records = [
        r for r in caplog.records if "ws_broadcast_harvested" in r.getMessage()
    ]
    assert len(harvest_records) == 1
    assert "dropped_count=3" in harvest_records[0].getMessage()


@pytest.mark.asyncio
async def test_broadcast_on_empty_set_removes_game_id():
    """An empty set for a game_id (e.g. from a prior failed broadcast) must
    cause _broadcast to remove the key so the listener can exit."""
    mgr = ConnectionManager()
    game_id = "g-empty"
    mgr.active_connections[game_id] = set()

    await mgr._broadcast(game_id, json.dumps({"type": "X"}))

    assert game_id not in mgr.active_connections


@pytest.mark.asyncio
async def test_broadcast_clears_player_connections_for_dead_socket():
    """Best-effort: a dead socket also gets pruned from player_connections."""
    mgr = ConnectionManager()
    game_id = "g-player"
    s_ok = _make_socket()
    s_dead = _make_socket()
    s_dead.send_text.side_effect = RuntimeError("boom")
    mgr.active_connections[game_id] = {s_ok, s_dead}
    mgr._get_connection_id(s_ok)
    mgr._get_connection_id(s_dead)
    mgr.player_connections[game_id] = {"player-ok": s_ok, "player-dead": s_dead}

    await mgr._broadcast(game_id, json.dumps({"type": "PING"}))

    # Healthy player still tracked, dead one harvested.
    assert mgr.player_connections[game_id] == {"player-ok": s_ok}
    assert mgr.active_connections[game_id] == {s_ok}


@pytest.mark.asyncio
async def test_broadcast_missing_game_id_is_noop():
    """Broadcasting to an unknown game_id must not raise and must not create
    state."""
    mgr = ConnectionManager()
    await mgr._broadcast("nope", json.dumps({"type": "X"}))
    assert "nope" not in mgr.active_connections
