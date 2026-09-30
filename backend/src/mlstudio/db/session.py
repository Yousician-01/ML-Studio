from collections.abc import Iterator
from pathlib import Path
from sqlite3 import Connection

from fastapi import Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import ConnectionPoolEntry

from mlstudio.core.config import Settings


def create_database_engine(settings: Settings) -> Engine:
    url = settings.resolved_database_url
    settings.home.mkdir(parents=True, exist_ok=True)
    Path(str(url.database)).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection: Connection, _record: ConnectionPoolEntry) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session
