"""
Session Manager — in-memory singleton that tracks the current game session.
Supports single-player and multiplayer modes.
"""
import threading
import secrets
import time
from typing import Optional, List, Dict, Any
from dataclasses import dataclass


@dataclass
class LobbyPlayerInfo:
    name: str
    player_id: Optional[str]
    is_host: bool
    is_spectator: bool
    is_bot: bool
    connected: bool
    bot_type: str = "random"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "player_id": self.player_id,
            "is_host": self.is_host,
            "is_spectator": self.is_spectator,
            "is_bot": self.is_bot,
            "connected": self.connected,
        }


class SessionManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init()
        return cls._instance

    def _init(self):
        # Stable session ID for WebSocket channel routing
        import uuid
        self.session_id: str = str(uuid.uuid4())

        # Game engine (EngineWrapper instance)
        self.game = None

        # Session mode
        self.mode: str = "idle"          # "idle" | "single" | "multiplayer"
        self.game_exists: bool = False
        self.game_over: bool = False

        # Player info (index-aligned)
        self.player_names: List[str] = []   # display names
        self.bot_players: Dict[int, str] = {}  # player_idx -> bot_type ("random" | "ppo")

        # Round counter (incremented at each _end_round)
        self.round: int = 1

        # History log (last 50 actions)
        self.history: List[Dict[str, Any]] = []

        # Bot thinking flag (set True while bot is computing)
        self.bot_thinking: bool = False

        # Multiplayer lobby
        self.lobby_key: Optional[str] = None
        self.lobby_players: List[LobbyPlayerInfo] = []
        self.host_name: Optional[str] = None
        self.lobby_status: Optional[str] = None   # "waiting" | "playing"

        # Heartbeat tracking: name -> last_seen timestamp
        self._heartbeats: Dict[str, float] = {}

    def reset(self):
        self._init()

    # ------------------------------------------------------------------ #
    #  Properties                                                          #
    # ------------------------------------------------------------------ #

    @property
    def num_players(self) -> int:
        return len(self.player_names)

    @property
    def server_info(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "game_exists": self.game_exists,
            "lobby_status": self.lobby_status,
            "players": [p.to_dict() for p in self.lobby_players] if self.lobby_players else None,
            "host": self.host_name,
        }

    # ------------------------------------------------------------------ #
    #  History                                                             #
    # ------------------------------------------------------------------ #

    def add_history(self, action: str, params: Dict[str, object]):
        self.history.append({
            "ts": int(time.time() * 1000),
            "action": action,
            "params": params,
        })
        if len(self.history) > 50:
            self.history = self.history[-50:]

    # ------------------------------------------------------------------ #
    #  Single-player setup                                                 #
    # ------------------------------------------------------------------ #

    def init_single(self, player_names: List[str], bot_map: Dict[int, str]):
        """Set up a single-player session (must call start_game separately)."""
        self.reset()
        self.mode = "single"
        self.player_names = list(player_names)
        self.bot_players = dict(bot_map)

    def start_game(self):
        """Initialise the EngineWrapper with the current player count."""
        from app.engine_wrapper.wrapper import create_game_engine
        self.game = create_game_engine(num_players=self.num_players)
        self.game_exists = True
        self.game_over = False
        self.round = 1
        self.history = []
        if self.mode == "multiplayer":
            self.lobby_status = "playing"

    # ------------------------------------------------------------------ #
    #  Multiplayer lobby                                                   #
    # ------------------------------------------------------------------ #

    def init_multiplayer(self, host_name: str) -> str:
        self.reset()
        self.mode = "multiplayer"
        self.lobby_status = "waiting"
        self.host_name = host_name
        self.lobby_key = secrets.token_urlsafe(6)

        self.lobby_players = [
            LobbyPlayerInfo(
                name=host_name,
                player_id=None,
                is_host=True,
                is_spectator=False,
                is_bot=False,
                connected=True,
            )
        ]
        return self.lobby_key

    def lobby_join(self, key: str, name: str) -> bool:
        if key != self.lobby_key:
            return False
        if any(p.name == name for p in self.lobby_players):
            return True   # already joined
        self.lobby_players.append(
            LobbyPlayerInfo(
                name=name,
                player_id=None,
                is_host=False,
                is_spectator=False,
                is_bot=False,
                connected=True,
            )
        )
        return True

    def lobby_add_bot(self, key: str, host_name: str, bot_name: str, bot_type: str) -> bool:
        if key != self.lobby_key or host_name != self.host_name:
            return False
        self.lobby_players.append(
            LobbyPlayerInfo(
                name=bot_name,
                player_id=None,
                is_host=False,
                is_spectator=False,
                is_bot=True,
                connected=True,
                bot_type=bot_type,
            )
        )
        return True

    def lobby_remove_bot(self, key: str, host_name: str, bot_name: str) -> bool:
        if key != self.lobby_key or host_name != self.host_name:
            return False
        self.lobby_players = [p for p in self.lobby_players if p.name != bot_name]
        return True

    def lobby_start(self, key: str, name: str):
        """Convert lobby players into the game's player_names + bot_players."""
        if key != self.lobby_key:
            raise ValueError("Invalid key")
        self.player_names = [p.name for p in self.lobby_players if not p.is_spectator]
        self.bot_players = {
            i: p.bot_type
            for i, p in enumerate(self.lobby_players)
            if p.is_bot and not p.is_spectator
        }
        self.start_game()

    # ------------------------------------------------------------------ #
    #  Heartbeat                                                           #
    # ------------------------------------------------------------------ #

    def heartbeat(self, key: str, name: str):
        self._heartbeats[name] = time.time()


# Module-level singleton
session = SessionManager()
