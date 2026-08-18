import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory = None


def default_database_url():
    local_db = Path(__file__).with_name("shiptrack.db")
    return os.getenv("DATABASE_URL", f"sqlite:///{local_db}")


def configure_database(database_url=None):
    global _engine, _session_factory
    url = database_url or default_database_url()
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    _engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
    _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def init_db():
    if _engine is None:
        configure_database()
    Base.metadata.create_all(_engine)


def get_session():
    if _session_factory is None:
        configure_database()
    return _session_factory()
