"""Database setup: SQLite file at ./data/app.db relative to the backend dir."""

import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .paths import BACKEND_DIR

DB_PATH = Path(os.environ.get("APP_DB_PATH", BACKEND_DIR / "data" / "app.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{DB_PATH.as_posix()}", connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def utcnow() -> datetime:
    """Naive UTC. SQLite stores no offset whatever the column type says, so the
    storage contract is "always UTC, never stamped" and the offset is put back
    at the API edge (ExampleOut in main.py)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Example(Base):
    __tablename__ = "examples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ai: Mapped[str] = mapped_column(Text, nullable=False)
    human: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class DirectionCache(Base):
    __tablename__ = "meta"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    unit_json: Mapped[str] = mapped_column(Text, nullable=False)


class MapCache(Base):
    """The computed map payload (scores + 2D layout), keyed by everything it
    was computed from (scoring.map_key) — any library change, and any change
    to how the payload is built, recomputes it."""

    __tablename__ = "map_cache"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)


def init_db() -> None:
    Base.metadata.create_all(engine)
