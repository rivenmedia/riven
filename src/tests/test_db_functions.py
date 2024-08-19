import pytest

from RTN import Torrent, ParsedData
from testcontainers.postgres import PostgresContainer

from program.db.db import db, run_migrations
from program import MediaItem
from program.media.stream import Stream, StreamRelation, StreamBlacklistRelation
from program.db.db_functions import reset_streams, blacklist_stream


@pytest.fixture(scope="session")
def test_container():
    with PostgresContainer("postgres:16.4-alpine3.20", username="postgres", password="postgres", dbname="riven", port=5432).with_bind_ports(5432, 5432) as postgres:
        yield postgres
@pytest.fixture(scope="function")
def test_scoped_db_session(test_container):
    run_migrations()
    session = db.Session()
    yield session
    session.close()
    db.drop_all()

def test_reset_streams_for_mediaitem_with_no_streams(test_scoped_db_session):
    media_item = MediaItem({"name":"MediaItem with No Streams"})
    media_item.item_id = "tt123456"
    test_scoped_db_session.add(media_item)
    test_scoped_db_session.commit()

    reset_streams(media_item)

    assert test_scoped_db_session.query(StreamRelation).filter_by(parent_id=media_item._id).count() == 0
    assert test_scoped_db_session.query(StreamBlacklistRelation).filter_by(media_item_id=media_item._id).count() == 0


def test_add_new_mediaitem_with_multiple_streams_and_reset_streams(test_scoped_db_session):
    media_item = MediaItem({"name":"New MediaItem"})
    media_item.item_id = "tt123456"
    stream1 = Stream(Torrent(
        raw_title="Example.Movie.2020.1080p.BluRay.x264-Example",
        infohash="997592a005d9c162391803c615975676738d6a11",
        data=ParsedData(parsed_title='Example Movie'),
        fetch=True,
        rank=150,
        lev_ratio=0.9
    ))
    stream2 = Stream(Torrent(
        raw_title="Example.Movie.2020.1080p.BluRay.x264-Example",
        infohash="c24046b60d764b2b58dce6fbb676bcd3cfcd257e",
        data=ParsedData(parsed_title='Example Movie'),
        fetch=True,
        rank=150,
        lev_ratio=0.8
    ))
    test_scoped_db_session.add(media_item)
    test_scoped_db_session.add(stream1)
    test_scoped_db_session.add(stream2)
    test_scoped_db_session.commit()

    stream_relation1 = StreamRelation(parent_id=media_item._id, child_id=stream1._id)
    stream_relation2 = StreamRelation(parent_id=media_item._id, child_id=stream2._id)
    test_scoped_db_session.add(stream_relation1)
    test_scoped_db_session.add(stream_relation2)
    test_scoped_db_session.commit()

    reset_streams(media_item)

    assert test_scoped_db_session.query(StreamRelation).filter_by(parent_id=media_item._id).count() == 0
    assert test_scoped_db_session.query(StreamBlacklistRelation).filter_by(media_item_id=media_item._id).count() == 0

def test_blacklists_active_stream(test_scoped_db_session):
    media_item = MediaItem({"name":"New MediaItem"})
    media_item.item_id = "tt123456"
    stream = Stream(Torrent(
        raw_title="Example.Movie.2020.1080p.BluRay.x264-Example",
        infohash="997592a005d9c162391803c615975676738d6a11",
        data=ParsedData(parsed_title='Example Movie'),
        fetch=True,
        rank=150,
        lev_ratio=0.9
    ))
    test_scoped_db_session.add(media_item)
    test_scoped_db_session.add(stream)
    test_scoped_db_session.commit()
    stream_relation = StreamRelation(parent_id=media_item._id, child_id=stream._id)
    test_scoped_db_session.add(stream_relation)
    test_scoped_db_session.commit()

    blacklist_stream(media_item, stream)

    assert test_scoped_db_session.query(StreamBlacklistRelation).filter_by(media_item_id=media_item._id, stream_id=stream._id).count() == 1

def test_successfully_resets_streams(test_scoped_db_session):
    media_item = MediaItem({"name":"New MediaItem"})
    media_item.item_id = "tt123456"
     
    stream1 = Stream(Torrent(
        raw_title="Example.Movie.2020.1080p.BluRay.x264-Example",
        infohash="997592a005d9c162391803c615975676738d6a11",
        data=ParsedData(parsed_title='Example Movie'),
        fetch=True,
        rank=150,
        lev_ratio=0.9
    ))

    stream2 = Stream(Torrent(
        raw_title="Example.Movie.2020.1080p.BluRay.x264-Example",
        infohash="c24046b60d764b2b58dce6fbb676bcd3cfcd257e",
        data=ParsedData(parsed_title='Example Movie'),
        fetch=True,
        rank=150,
        lev_ratio=0.8
    ))
    
    test_scoped_db_session.add(media_item)
    test_scoped_db_session.add(stream1)
    test_scoped_db_session.add(stream2)
    test_scoped_db_session.commit()

    stream_relation1 = StreamRelation(parent_id=media_item._id, child_id=stream1._id)
    stream_relation2 = StreamRelation(parent_id=media_item._id, child_id=stream2._id)
    test_scoped_db_session.add(stream_relation1)
    test_scoped_db_session.add(stream_relation2)
    test_scoped_db_session.commit()

    reset_streams(media_item)

    assert test_scoped_db_session.query(StreamRelation).filter_by(parent_id=media_item._id).count() == 0
    assert test_scoped_db_session.query(StreamBlacklistRelation).filter_by(media_item_id=media_item._id).count() == 0