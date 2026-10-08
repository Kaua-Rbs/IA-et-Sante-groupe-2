from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from api.config import settings


def _make_engine(url: str):
    if not url.startswith("sqlite"):
        return create_engine(url)
    # In-memory SQLite (tests) must share a single connection across threads
    if url in ("sqlite://", "sqlite:///:memory:"):
        return create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    return create_engine(url, connect_args={"check_same_thread": False})


engine = _make_engine(settings.DATABASE_URL)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def utcnow() -> datetime:
    """Return current UTC time as a naive datetime (SQLite compatibility)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
