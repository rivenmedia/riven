# tests/conftest.py
from __future__ import annotations

from collections.abc import Iterator
from typing import Final
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session, sessionmaker
from testcontainers.postgres import PostgresContainer

from program.db.db import run_migrations
from program.utils.logging import setup_logger

# Setup logger for tests to ensure custom log levels are available
setup_logger("DEBUG")


@pytest.fixture(scope="session")
def pg_engine() -> Iterator[Engine]:
    """
    Session-scoped real Postgres engine via Testcontainers.
    - Starts a disposable postgres:16-alpine
    - Runs Alembic migrations ONCE
    - Returns a reusable Engine for the whole session
    """
    image: Final = "postgres:16-alpine"
    with PostgresContainer(image) as pg:
        # Example: postgresql+psycopg2://test:test@0.0.0.0:XXXXX/test
        url = pg.get_connection_url()
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
        
        # Override settings manager database URL for migrations
        from program.settings.manager import settings_manager
        settings_manager.settings.database.host = url

        # Run migrations
        run_migrations(database_url=url)
        
        # Create engine
        engine = create_engine(url, future=True, pool_pre_ping=True)
        yield engine
        engine.dispose()


@pytest.fixture()
def pg_session(pg_engine: Engine) -> Iterator[Session]:
    """
    Test-scoped SQLAlchemy Session with SAVEPOINT-based isolation.
    - Each test runs inside a transaction.
    - If your app code commits, we reset to a SAVEPOINT so isolation still holds.
    """
    # Configure global db instance to use our test engine
    from program.db.db import db
    original_engine = db.engine
    original_session = db.Session
    
    db.engine = pg_engine
    db.Session.configure(bind=pg_engine)
    
    connection: Connection = pg_engine.connect()
    outer_tx = connection.begin()
    SessionLocal = sessionmaker(
        bind=connection,
        expire_on_commit=False,
        autoflush=False,
        future=True,
    )
    session: Session = SessionLocal()

    # Start first SAVEPOINT so app-side commits don't escape our test boundary
    nested_tx = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(_sess: Session, trans) -> None:  # type: ignore[no-redef]
        # When the SAVEPOINT ends (commit/rollback), re-open a new one.
        nonlocal nested_tx
        if trans.nested and not connection.closed:
            nested_tx = connection.begin_nested()

    try:
        yield session
    finally:
        try:
            session.close()
            outer_tx.rollback()
            connection.close()
        except Exception:
            # Connection may have been terminated by hard_reset_database() or similar
            # Just dispose of the engine to clean up any remaining connections
            try:
                pg_engine.dispose()
            except Exception:
                pass  # Ignore cleanup errors
        
        # Restore original db configuration
        db.engine = original_engine
        db.Session = original_session


@pytest.fixture()
def mock_db_session() -> Session:
    """
    Create a mocked database session for unit tests that don't need real DB.
    """
    mock_session = MagicMock(spec=Session)
    mock_session.execute.return_value.scalar_one_or_none.return_value = None
    mock_session.execute.return_value.scalars.return_value.all.return_value = []
    mock_session.execute.return_value.unique.return_value.scalars.return_value.all.return_value = []
    mock_session.query.return_value.filter_by.return_value.first.return_value = None
    mock_session.query.return_value.filter.return_value.count.return_value = 0
    mock_session.add = MagicMock()
    mock_session.add_all = MagicMock()
    mock_session.commit = MagicMock()
    mock_session.rollback = MagicMock()
    mock_session.close = MagicMock()
    mock_session.is_active = True
    
    return mock_session


@pytest.fixture()
def test_scoped_db_session(pg_engine: Engine) -> Iterator[Session]:
    """
    Test-scoped SQLAlchemy Session for tests that need a clean session.
    This is an alias for pg_session to maintain compatibility with existing tests.
    """
    # Configure global db instance to use our test engine
    from program.db.db import db
    original_engine = db.engine
    original_session = db.Session
    
    db.engine = pg_engine
    db.Session.configure(bind=pg_engine)
    
    connection: Connection = pg_engine.connect()
    outer_tx = connection.begin()
    SessionLocal = sessionmaker(
        bind=connection,
        expire_on_commit=False,
        autoflush=False,
        future=True,
    )
    session: Session = SessionLocal()

    # Start first SAVEPOINT so app-side commits don't escape our test boundary
    nested_tx = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(_sess: Session, trans) -> None:  # type: ignore[no-redef]
        # When the SAVEPOINT ends (commit/rollback), re-open a new one.
        nonlocal nested_tx
        if trans.nested and not connection.closed:
            nested_tx = connection.begin_nested()

    try:
        yield session
    finally:
        try:
            session.close()
            outer_tx.rollback()
            connection.close()
        except Exception:
            # Connection may have been terminated by hard_reset_database() or similar
            # Just dispose of the engine to clean up any remaining connections
            try:
                pg_engine.dispose()
            except Exception:
                pass  # Ignore cleanup errors
        
        # Restore original db configuration
        db.engine = original_engine
        db.Session = original_session