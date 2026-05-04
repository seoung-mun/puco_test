import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
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
    host_id = Column(String, nullable=True, index=True)
    game_seed = Column(BigInteger, nullable=True)
    governor_idx = Column(Integer, nullable=True)
    engine_compat_version = Column(Integer, nullable=True)
    state_revision = Column(Integer, nullable=False, server_default="0", default=0)
    recovery_blocked_reason = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    logs = relationship("GameLog", back_populates="game_session")
    replay = relationship("Replay", back_populates="game_session", uselist=False)


class GameLog(Base):
    __tablename__ = "game_logs"
    __table_args__ = (
        Index("ix_game_logs_game_round", "game_id", "round"),
        Index(
            "ux_game_logs_game_intent",
            "game_id",
            "action_intent_id",
            unique=True,
            postgresql_where=text("action_intent_id IS NOT NULL"),
        ),
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
    revision = Column(Integer, nullable=True)
    action_intent_id = Column(String(64), nullable=True)
    phase_before = Column(String(32), nullable=True)
    active_player_before = Column(String(16), nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    game_session = relationship("GameSession", back_populates="logs")


class Replay(Base):
    __tablename__ = "replays"

    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id"), primary_key=True)
    payload = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    game_session = relationship("GameSession", back_populates="replay")
