from sqlalchemy import text
from app.db.models import GameLog

def test_game_action_integration(client, db):
    # 1. Setup: Create a room and start game
    room_data = {
        "title": "Test Battle Room",
        "agent_count": 1,
        "max_players": 3
    }
    create_res = client.post("/api/v1/rooms/", json=room_data)
    assert create_res.status_code == 200
    game_id = create_res.json()["id"]

    # Start the game to initialize engine
    start_res = client.post(f"/api/v1/game/{game_id}/start")
    assert start_res.status_code == 200

    # 2. Execution: Call /action endpoint
    # Puerto Rico engine initially expects a role selection (action 0-7)
    action_data = {
        "game_id": game_id,
        "action_type": "DISCRETE",
        "payload": {"action_index": 0} # Select Settler role
    }
    
    response = client.post(f"/api/v1/game/{game_id}/action", json=action_data)
    
    # Checkpoint 1: HTTP 200 Response
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    # 3. Verification: DB game_logs count
    # Checkpoint 2: New record in game_logs
    log_count = db.query(GameLog).filter(GameLog.game_id == game_id).count()
    assert log_count == 1

    # 4. Verification: SQL query for action_mask structure
    # Checkpoint 3: JSONB field structure (available_options)
    sql = text("SELECT available_options FROM game_logs WHERE game_id = :game_id ORDER BY timestamp DESC LIMIT 1")
    result = db.execute(sql, {"game_id": game_id}).fetchone()
    
    assert result is not None
    action_mask = result[0]
    
    # Verification of data structure: Should be a list (action mask)
    assert isinstance(action_mask, list)
    assert len(action_mask) > 0
    # Every element should be 0 or 1
    assert all(x in [0, 1] for x in action_mask)
    
    print(f"Verified Action Mask Length: {len(action_mask)}")
