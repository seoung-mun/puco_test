# Room Management Design Spec
**Date:** 2026-03-30
**Status:** Approved

---

## Problem Statement

The lobby (WAITING state) currently has no presence tracking, no host concept, no auto-cleanup, and several bugs. This spec defines a complete room lifecycle management system.

---

## Requirements

1. If a room has no human players, delete it automatically.
2. The room creator is the host. If the host leaves and other human players exist, transfer host to the next human player.
3. If the host leaves and no human players remain, delete the room.
4. Closing the browser tab counts as leaving the room (detected via WebSocket disconnect).
5. Navigating back to the room list counts as leaving the room (explicit leave call).
6. A user who is already the host of a WAITING room cannot create another room.
7. **Bug fix:** Game start button incorrectly disabled when room has 1 human + 2 bots or 2 humans + 1 bot.
8. **Bug fix:** Private room join UI shows "session key" (UUID) instead of prompting for the 4-digit password. Fix to always use 4-digit password.
9. **Bug fix:** Lobby screen exposes the session key (UUID) to the host. Remove this display.
10. **Post-implementation:** Verify all frontend–backend endpoint connections are correctly wired.

---

## Approach

**Lobby WebSocket + `host_id` DB column**

- Add `host_id` VARCHAR column to `games` table via Alembic migration.
- New WebSocket endpoint `/api/puco/ws/lobby/{room_id}` handles lobby presence separately from the in-game WebSocket (`/api/puco/ws/{game_id}`).
- New REST endpoint `POST /api/puco/rooms/{room_id}/leave` for explicit leave (navigating away).
- WS disconnect and explicit leave share the same leave logic.

---

## DB Changes

### Migration

```sql
ALTER TABLE games ADD COLUMN host_id VARCHAR NOT NULL DEFAULT '';
```

- Backfill: `UPDATE games SET host_id = players[0] WHERE status = 'WAITING' AND host_id = ''`
- Model: add `host_id: str` to `GameSession` SQLAlchemy model.

---

## Backend

### New: Lobby WebSocket

**Endpoint:** `WS /api/puco/ws/lobby/{room_id}`

**Auth:** First message must be `{ "token": "<JWT>" }` (same pattern as game WS).

**Connection flow:**
1. Accept WS connection.
2. Wait for auth message (5s timeout), verify JWT.
3. Verify user is in `room.players`.
4. Register connection in `LobbyConnectionManager`.
5. Broadcast `LOBBY_STATE` to all connected lobby members.
6. Listen for disconnect; on disconnect run `_handle_leave(room_id, player_id)`.

**Message types (server → client):**

```json
// Full state on join
{ "type": "LOBBY_STATE", "players": [LobbyPlayerInfo], "host_id": "uuid" }

// Incremental update on any change
{ "type": "LOBBY_UPDATE", "players": [LobbyPlayerInfo], "host_id": "uuid" }

// Room was deleted (no humans left)
{ "type": "ROOM_DELETED" }
```

### New: Leave Endpoint

**Endpoint:** `POST /api/puco/rooms/{room_id}/leave`
**Auth:** JWT required.

Calls the same `_handle_leave(room_id, player_id)` logic as the WS disconnect handler.

### Shared Leave Logic (`_handle_leave`)

```
1. Remove player from room.players (DB).
2. Count remaining human players.
3. If 0 humans remain → DELETE room from DB, broadcast ROOM_DELETED, done.
4. If player was host:
     a. Find next human player in room.players.
     b. UPDATE room.host_id = next_human.
5. Broadcast LOBBY_UPDATE with new player list and host_id.
```

### Modified: Room Creation Endpoint

`POST /api/puco/rooms/` — add host uniqueness check:

```python
existing = db.query(GameSession).filter(
    GameSession.host_id == str(current_user.id),
    GameSession.status == "WAITING"
).first()
if existing:
    raise HTTPException(409, "이미 방장인 방이 있습니다")
```

On success: `room.host_id = str(current_user.id)`.

### LobbyConnectionManager (new service)

Tracks `Dict[room_id, Dict[player_id, WebSocket]]`. Separate from the game `ConnectionManager` to avoid entangling lobby and game state.

---

## Frontend

### App.tsx

- On create/join room success: connect Lobby WS (`/api/puco/ws/lobby/{roomId}`).
- On WS `LOBBY_STATE` / `LOBBY_UPDATE`: update `lobbyPlayers` state (replaces the current local-only state management).
- On WS `ROOM_DELETED`: navigate back to room list, show toast.
- On navigate back to room list (`onBack`): call `POST /rooms/{roomId}/leave`, then close WS.
- Remove `sessionKeyDisplay` state and all related prop passing.

### LobbyScreen.tsx

- Remove the session key yellow box (lines 67–77).
- No other structural changes needed; `players` prop now comes from WS state.

### RoomListScreen.tsx (private room join)

- Replace any "session key" label with "비밀번호 (4자리 숫자)".
- Ensure `doJoin` sends `{ password }` (already correct in backend; verify UI label only).

### Bug Fix: handleAddBot in App.tsx (line 552)

```typescript
// Before (bug: missing is_bot)
{ name: `Bot (${data.bot_type})`, role: 'player', player_id: `BOT_${data.bot_type}` }

// After
{ name: `Bot (${data.bot_type})`, player_id: `BOT_${data.bot_type}`, is_bot: true, connected: true }
```

---

## Endpoint Connection Verification (Post-Implementation)

After all changes are implemented, verify the following connection matrix:

| Frontend call | Backend endpoint | Verified? |
|---|---|---|
| Create room | `POST /api/puco/rooms/` | ☐ |
| List rooms | `GET /api/puco/rooms/` | ☐ |
| Join room (public) | `POST /api/puco/rooms/{id}/join` | ☐ |
| Join room (private, 4-digit pw) | `POST /api/puco/rooms/{id}/join` + `{ password }` | ☐ |
| Leave room | `POST /api/puco/rooms/{id}/leave` | ☐ |
| Lobby WS connect | `WS /api/puco/ws/lobby/{id}` | ☐ |
| Add bot | `POST /api/puco/game/{id}/add-bot` | ☐ |
| Remove bot | `DELETE /api/puco/game/{id}/bots/{slot}` | ☐ |
| Start game | `POST /api/puco/game/{id}/start` | ☐ |
| Game WS | `WS /api/puco/ws/{id}` | ☐ |

---

## Out of Scope

- Rate limiting on room creation.
- Spectator mode.
- Room name editing after creation.
- Mid-game room management (game WS disconnect logic is unchanged).
