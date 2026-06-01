"""Shared pytest fixtures — SQLite schema via SQLAlchemy metadata (no Postgres container)."""

from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from program.db import db
from program.db.base_model import get_base_metadata


@pytest.fixture(scope="session")
def db_engine(tmp_path_factory: pytest.TempPathFactory) -> Generator[Engine, None, None]:
    """One SQLite file + schema for the whole test session."""

    db_path = tmp_path_factory.mktemp("riven_sqlite") / "riven_test.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(
        url,
        future=True,
        connect_args={"check_same_thread": False},
    )
    get_base_metadata().create_all(engine)
    db.engine = engine
    db.Session.configure(bind=engine)

    yield engine

    engine.dispose()


def _truncate_all_tables(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys = OFF"))
        for table in reversed(get_base_metadata().sorted_tables):
            conn.execute(text(f'DELETE FROM "{table.name}"'))
        conn.execute(text("PRAGMA foreign_keys = ON"))


@pytest.fixture
def test_scoped_db_session(db_engine: Engine) -> Generator[Session, None, None]:
    """Per-test session; tables are cleared after each test."""

    session = db.Session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        _truncate_all_tables(db_engine)


@contextmanager
def _test_db_session(test_scoped_db_session: Session) -> Iterator[Session]:
    yield test_scoped_db_session


@pytest.fixture
def use_test_database(
    test_scoped_db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> Session:
    """
    Route program.db.db.db_session to the SQLite test session.

    Use via @pytest.mark.usefixtures("use_test_database") on modules that hit the DB.
    """

    @contextmanager
    def _session() -> Iterator[Session]:
        yield test_scoped_db_session

    monkeypatch.setattr("program.db.db.db_session", _session)
    monkeypatch.setattr("program.managers.event_manager.db_session", _session)
    return test_scoped_db_session


def seed_movie(
    session: Session,
    item_id: int,
    *,
    last_state: Any = None,
    imdb_id: str | None = None,
) -> None:
    from program.media.item import Movie
    from program.media.state import States

    movie = Movie(
        {
            "title": f"Item {item_id}",
            "imdb_id": imdb_id or f"tt{item_id:07d}",
            "requested_by": "pytest",
            "type": "movie",
        }
    )
    movie.id = item_id
    if last_state is not None:
        movie.last_state = last_state
    else:
        movie.last_state = States.Requested
    session.add(movie)
    session.commit()


@pytest.fixture
def seed_common_queue_items(
    use_test_database: Session, test_scoped_db_session: Session
) -> None:
    """IDs used by event-manager queue tests."""

    from program.media.state import States

    seed_movie(test_scoped_db_session, 10, last_state=States.Scraped)
    seed_movie(test_scoped_db_session, 11, last_state=States.Downloaded)
    seed_movie(test_scoped_db_session, 12, last_state=States.Indexed)
    seed_movie(test_scoped_db_session, 42, last_state=States.Scraped)
    seed_movie(test_scoped_db_session, 5, last_state=States.Failed)
