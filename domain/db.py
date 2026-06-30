"""Database engine and session factory."""

from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from domain.paths import ROOT

DEFAULT_DB_PATH = ROOT / "data" / "portfolio.db"


class Base(DeclarativeBase):
    pass


def database_url() -> str:
    return os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")


def _sqlite_connect_args(url: str) -> dict[str, bool]:
    return {"check_same_thread": False} if url.startswith("sqlite") else {}


engine = create_engine(
    database_url(),
    connect_args=_sqlite_connect_args(database_url()),
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def configure_engine(url: str | None = None) -> None:
    """Rebind engine (for tests)."""
    global engine, SessionLocal
    engine.dispose()
    target = url or database_url()
    engine = create_engine(target, connect_args=_sqlite_connect_args(target))
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    from domain import models  # noqa: F401

    DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)


def get_session() -> Session:
    return SessionLocal()


def session_scope() -> Generator[Session, None, None]:
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
