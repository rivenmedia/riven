# tests/test_db_functions.py
from __future__ import annotations
import os

import pytest
from RTN import ParsedData, Torrent
from sqlalchemy import create_engine, text
from testcontainers.postgres import PostgresContainer

from program.db.db import db, run_migrations
from program.db.db_functions import (
    clear_streams,
    delete_media_item,
    get_item_by_external_id,
    get_items_by_ids,
    item_exists_by_any_id,
    set_stream_blacklisted,
)
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.stream import Stream, StreamBlacklistRelation, StreamRelation



@pytest.fixture(scope="session")
def test_container():
    # One container for the whole test session
    with PostgresContainer(
        "postgres:16.4-alpine3.20",
        username="postgres",
        password="postgres",
        dbname="riven",
    ) as pg:
        yield pg


@pytest.fixture(scope="session")
def db_engine(test_container):
    """
    One engine + one migrated schema for the whole test session.
    We also relax durability for speed (safe in tests).
    """
    url = test_container.get_connection_url()
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)

    # Make Alembic target this DB
    os.environ["DATABASE_URL"] = url

    # Run migrations ONCE (big win)
    run_migrations(database_url=url)

    # Build an engine for tests
    engine = create_engine(url, future=True, pool_pre_ping=True)

    # Speed knobs (commit is much cheaper now)
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text("SET synchronous_commit = OFF"))
        # Optional extras:
        # conn.execute(text("SET client_min_messages = WARNING"))
        # conn.execute(text("SET log_statement = 'none'"))

    # Rebind global db.* so app code uses this engine
    db.engine = engine
    db.Session.configure(bind=engine)

    yield engine

    engine.dispose()


@pytest.fixture(scope="function")
def test_scoped_db_session(db_engine):
    """
    Hand out a Session for each test. After each test, TRUNCATE all tables
    instead of dropping the schema / rerunning migrations. Very fast.
    """
    session = db.Session()
    try:
        yield session
    finally:
        session.close()
        # Fast cleanup: TRUNCATE everything, reset sequences
        with db_engine.connect() as conn:
            tables = conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).scalars().all()
            if tables:
                quoted = ", ".join(f'"public"."{t}"' for t in tables)
                conn.execute(text(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE"))
                conn.commit()



def _torrent(rt: str, ih: str, pt: str, rank=100, lev=0.9) -> Torrent:
    pd = ParsedData(parsed_title=pt, raw_title=rt)
    return Torrent(raw_title=rt, infohash=ih, data=pd, fetch=True, rank=rank, lev_ratio=lev)

def _movie(tmdb_id: str, imdb_id: str | None = None, title="Movie") -> Movie:
    return Movie({"title": title, "tmdb_id": tmdb_id, "imdb_id": imdb_id, "type": "movie"})

def _show_tree(tvdb: str, seasons: list[int], eps: int) -> tuple[Show, list[Season], list[Episode]]:
    show = Show({"title": "Show", "tvdb_id": tvdb, "type": "show"})
    all_s, all_e = [], []
    for s in seasons:
        season = Season({"number": s, "tvdb_id": f"{tvdb}-{s}", "type": "season"})
        season.parent = show
        season.parent_id = show.id
        all_s.append(season)
        for e in range(1, eps + 1):
            ep = Episode({"number": e, "tvdb_id": f"{tvdb}-{s}-{e}", "type": "episode"})
            ep.parent = season
            ep.parent_id = season.id
            all_e.append(ep)
    show.seasons = all_s
    for s in all_s:
        s.episodes = [e for e in all_e if e.parent_id == s.id]
    return show, all_s, all_e


# ------------------------------ Tests -------------------------------------- #

def test_clear_streams_when_none_exist(test_scoped_db_session):
    m = _movie("10001", "tt10001")
    test_scoped_db_session.add(m)
    test_scoped_db_session.commit()

    clear_streams(media_item_id=m.id)

    from sqlalchemy import select
    assert test_scoped_db_session.execute(select(StreamRelation).where(StreamRelation.parent_id == m.id)).scalar_one_or_none() is None
    assert test_scoped_db_session.execute(select(StreamBlacklistRelation).where(StreamBlacklistRelation.media_item_id == m.id)).scalar_one_or_none() is None


def test_add_multiple_streams_then_clear_streams(test_scoped_db_session):
    from sqlalchemy import select, func
    
    m = _movie("10002", "tt10002")
    s1 = Stream(_torrent("Example.Movie.2020.1080p", "997592a005d9c162391803c615975676738d6a11", "Example Movie"))
    s2 = Stream(_torrent("Example.Movie.2020.720p",  "c24046b60d764b2b58dce6fbb676bcd3cfcd257e", "Example Movie"))
    test_scoped_db_session.add_all([m, s1, s2])
    test_scoped_db_session.commit()

    test_scoped_db_session.add_all([
        StreamRelation(parent_id=m.id, child_id=s1.id),
        StreamRelation(parent_id=m.id, child_id=s2.id),
    ])
    test_scoped_db_session.commit()

    clear_streams(media_item_id=m.id)

    assert test_scoped_db_session.execute(select(func.count()).select_from(StreamRelation).where(StreamRelation.parent_id == m.id)).scalar() == 0
    assert test_scoped_db_session.execute(select(func.count()).select_from(StreamBlacklistRelation).where(StreamBlacklistRelation.media_item_id == m.id)).scalar() == 0
    # clear_streams only drops associations, not Stream rows
    assert test_scoped_db_session.execute(select(func.count()).select_from(Stream).where(Stream.id.in_([s1.id, s2.id]))).scalar() == 2


def test_blacklist_and_unblacklist_stream(test_scoped_db_session):
    from sqlalchemy import select, func
    
    m = _movie("10003", "tt10003")
    s = Stream(_torrent("Example.Movie.2021.1080p", "997592a005d9c162391803c615975676738d6a12", "Example Movie"))
    test_scoped_db_session.add_all([m, s])
    test_scoped_db_session.commit()

    test_scoped_db_session.add(StreamRelation(parent_id=m.id, child_id=s.id))
    test_scoped_db_session.commit()

    changed = set_stream_blacklisted(m, s, blacklisted=True)
    assert changed is True
    assert test_scoped_db_session.execute(select(func.count()).select_from(StreamRelation).where(StreamRelation.parent_id == m.id, StreamRelation.child_id == s.id)).scalar() == 0
    assert test_scoped_db_session.execute(select(func.count()).select_from(StreamBlacklistRelation).where(StreamBlacklistRelation.media_item_id == m.id, StreamBlacklistRelation.stream_id == s.id)).scalar() == 1

    changed_back = set_stream_blacklisted(m, s, blacklisted=False)
    assert changed_back is True
    assert test_scoped_db_session.execute(select(func.count()).select_from(StreamBlacklistRelation).where(StreamBlacklistRelation.media_item_id == m.id, StreamBlacklistRelation.stream_id == s.id)).scalar() == 0
    assert test_scoped_db_session.execute(select(func.count()).select_from(StreamRelation).where(StreamRelation.parent_id == m.id, StreamRelation.child_id == s.id)).scalar() == 1


def test_delete_movie_cascades_and_deletes_orphan_streams(test_scoped_db_session):
    from sqlalchemy import select, func
    
    m = _movie("10004", "tt10004")
    s = Stream(_torrent("Movie", "abcdabcdabcdabcdabcdabcdabcdabcdabcdabcd", "Movie"))
    test_scoped_db_session.add_all([m, s])
    test_scoped_db_session.commit()

    test_scoped_db_session.add(StreamRelation(parent_id=m.id, child_id=s.id))
    test_scoped_db_session.commit()

    assert test_scoped_db_session.execute(select(func.count()).select_from(Stream).where(Stream.id == s.id)).scalar() == 1

    delete_media_item(m)

    # item + associations are gone
    assert test_scoped_db_session.execute(select(func.count()).select_from(MediaItem).where(MediaItem.id == m.id)).scalar() == 0
    assert test_scoped_db_session.execute(select(func.count()).select_from(StreamRelation).where(StreamRelation.parent_id == m.id)).scalar() == 0
    # stream was orphaned -> purged
    assert test_scoped_db_session.execute(select(func.count()).select_from(Stream).where(Stream.id == s.id)).scalar() == 0


def test_delete_show_cascades_and_deletes_orphan_streams(test_scoped_db_session):
    from sqlalchemy import select, func
    
    show, seasons, eps = _show_tree("20001", [1], 2)
    s = Stream(_torrent("Show.S01E01", "abcd1234abcd1234abcd1234abcd1234abcd1234", "Show"))
    test_scoped_db_session.add_all([show] + seasons + eps + [s])
    test_scoped_db_session.commit()

    test_scoped_db_session.add(StreamRelation(parent_id=show.id, child_id=s.id))
    test_scoped_db_session.commit()

    delete_media_item(show)

    # hierarchy + associations are gone
    assert test_scoped_db_session.execute(select(func.count()).select_from(Show).where(Show.id == show.id)).scalar() == 0
    assert test_scoped_db_session.execute(select(func.count()).select_from(Season).where(Season.parent_id == show.id)).scalar() == 0
    # orphan stream purged
    assert test_scoped_db_session.execute(select(func.count()).select_from(Stream).where(Stream.id == s.id)).scalar() == 0


def test_delete_one_of_two_items_sharing_stream_does_not_delete_stream(test_scoped_db_session):
    from sqlalchemy import select, func
    
    m1 = _movie("30010", "tt30010")
    m2 = _movie("30011", "tt30011")
    s = Stream(_torrent("Shared", "feedfacefeedfacefeedfacefeedfacefeedface", "Shared"))
    test_scoped_db_session.add_all([m1, m2, s])
    test_scoped_db_session.commit()

    test_scoped_db_session.add_all([
        StreamRelation(parent_id=m1.id, child_id=s.id),
        StreamRelation(parent_id=m2.id, child_id=s.id),
    ])
    test_scoped_db_session.commit()

    delete_media_item(m1)

    # still referenced by m2, so stream remains
    assert test_scoped_db_session.execute(select(func.count()).select_from(MediaItem).where(MediaItem.id == m1.id)).scalar() == 0
    assert test_scoped_db_session.execute(select(func.count()).select_from(StreamRelation).where(StreamRelation.parent_id == m1.id)).scalar() == 0
    assert test_scoped_db_session.execute(select(func.count()).select_from(Stream).where(Stream.id == s.id)).scalar() == 1

    delete_media_item(m2)
    # now orphaned -> purged
    assert test_scoped_db_session.execute(select(func.count()).select_from(Stream).where(Stream.id == s.id)).scalar() == 0


def test_get_media_items_by_ids_success(test_scoped_db_session):
    show, seasons, eps = _show_tree("20002", [1], 2)
    mov = _movie("30001", "tt30001", title="Test Movie")
    test_scoped_db_session.add_all([show] + seasons + eps + [mov])
    test_scoped_db_session.commit()

    ids = [show.id, seasons[0].id, eps[0].id, eps[1].id, mov.id]
    items = get_items_by_ids(ids)

    assert len(items) == 5
    assert any(isinstance(x, Show) and x.id == show.id for x in items)
    assert any(isinstance(x, Season) and x.id == seasons[0].id for x in items)
    assert any(isinstance(x, Episode) and x.id == eps[0].id for x in items)
    assert any(isinstance(x, Episode) and x.id == eps[1].id for x in items)
    assert any(isinstance(x, Movie) and x.id == mov.id for x in items)


def test_item_exists_by_any_id_paths(test_scoped_db_session):
    mov = _movie("30002", "tt30002", title="Exists Check")
    test_scoped_db_session.add(mov)
    test_scoped_db_session.commit()

    assert item_exists_by_any_id(item_id=mov.id, tvdb_id=None, tmdb_id=None, imdb_id=None, session=test_scoped_db_session)
    assert item_exists_by_any_id(item_id=None, tvdb_id=None, tmdb_id=30002, imdb_id=None, session=test_scoped_db_session)
    assert item_exists_by_any_id(item_id=None, tvdb_id=None, tmdb_id=None, imdb_id="tt30002", session=test_scoped_db_session)

def test_item_exists_by_any_id_negative(test_scoped_db_session):
    assert not item_exists_by_any_id(item_id="non_existent", tvdb_id=None, tmdb_id=None, imdb_id=None, session=test_scoped_db_session)

def test_get_item_by_external_id_edge_cases(test_scoped_db_session):
    with pytest.raises(ValueError, match="At least one external ID must be provided"):
        get_item_by_external_id(session=test_scoped_db_session)

    assert get_item_by_external_id(imdb_id="tt99999999", session=test_scoped_db_session) is None

    mov = _movie("30003", "tt30003", title="External ID")
    test_scoped_db_session.add(mov)
    test_scoped_db_session.commit()

    found = get_item_by_external_id(imdb_id="tt30003", session=test_scoped_db_session)
    assert found is not None and found.id == mov.id

    delete_media_item(mov)
