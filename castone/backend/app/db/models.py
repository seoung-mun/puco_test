from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey, UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import uuid

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    google_id = Column(String, unique=True, index=True)
    nickname = Column(String)
    total_games = Column(Integer, default=0)
    win_rate = Column(Integer, default=0)

class GameSession(Base):
    __tablename__ = "games"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String)
    status = Column(String)  # WAITING, PROGRESS, FINISHED
    num_players = Column(Integer)
    players = Column(JSON, default=[]) # Array of user_ids or bot identifiers
    model_versions = Column(JSON, default={}) # e.g. {"player_idx": "PPO_v2"}
    winner_id = Column(String, nullable=True) # User ID or bot identifier
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class GameLog(Base):
    __tablename__ = "game_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id"), index=True)
    round = Column(Integer, index=True)  # Partition Key in production
    step = Column(Integer)
    actor_id = Column(String)
    action_data = Column(JSON)
    available_options = Column(JSON)
    state_before = Column(JSON)
    state_after = Column(JSON)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
