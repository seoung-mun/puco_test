import uuid

from sqlalchemy import Column, Integer, Float, String, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    google_id = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=True)
    nickname = Column(String, unique=True, nullable=True)  # None until user completes setup
    total_games = Column(Integer, server_default="0", default=0)
    win_rate = Column(Float, server_default="0.0", default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class GameSession(Base):
    __tablename__ = "games"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String)
    status = Column(String, index=True)  # WAITING, PROGRESS, FINISHED
    num_players = Column(Integer, default=3)
    is_private = Column(Boolean, default=False, nullable=False)
    password = Column(String(4), nullable=True)
    players = Column(JSONB, default=list)
    model_versions = Column(JSONB, default=dict)
    winner_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    logs = relationship("GameLog", back_populates="game_session")


class GameLog(Base):
    __tablename__ = "game_logs"
    __table_args__ = (
        Index("ix_game_logs_game_round", "game_id", "round"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id"), index=True)
    round = Column(Integer, index=True)
    step = Column(Integer)
    actor_id = Column(String)
    action_data = Column(JSONB)
    available_options = Column(JSONB)
    state_before = Column(JSONB)
    state_after = Column(JSONB)
    state_summary = Column(JSONB, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    game_session = relationship("GameSession", back_populates="logs")
