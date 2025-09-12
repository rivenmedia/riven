# program/db/stream_operations.py
from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Iterator, Optional, Tuple

from sqlalchemy import delete, insert
from sqlalchemy.orm import Session

from .db import db

if TYPE_CHECKING:
    from program.media.item import MediaItem
    from program.media.stream import Stream


@contextmanager
def _maybe_session(session: Optional[Session]) -> Iterator[Tuple[Session, bool]]:
    """
    Yield a (session, owns_session) pair.

    If `session` is None, create a new db.Session() and close it on exit.
    Otherwise, yield the caller-provided session and do not close it.
    """
    if session is not None:
        yield session, False
        return
    _s = db.Session()
    try:
        yield _s, True
    finally:
        _s.close()


def clear_streams(
    *,
    media_item_id: str,
    session: Optional[Session] = None,
) -> None:
    """
    Remove ALL stream relations and blacklists for a media item in one transaction.
    """
    from program.media.stream import StreamBlacklistRelation, StreamRelation
    
    with _maybe_session(session) as (_s, _owns):
        _s.execute(delete(StreamRelation).where(StreamRelation.parent_id == media_item_id))
        _s.execute(delete(StreamBlacklistRelation).where(StreamBlacklistRelation.media_item_id == media_item_id))
        _s.commit()


def set_stream_blacklisted(
    item: "MediaItem",
    stream: "Stream",
    *,
    blacklisted: bool,
    session: Optional[Session] = None,
) -> bool:
    """
    Toggle blacklist state for a (item, stream) pair atomically.
    Returns True if a change was applied.
    """
    from program.media.stream import StreamBlacklistRelation, StreamRelation
    
    with _maybe_session(session) as (_s, _owns):
        m_item = _s.merge(item)

        if blacklisted:
            # If the stream is currently linked, remove the link and add a blacklist row.
            linked = _s.query(
                _s.query(StreamRelation)
                .filter(
                    StreamRelation.parent_id == m_item.id,
                    StreamRelation.child_id == stream.id,
                )
                .exists()
            ).scalar()

            if not linked:
                return False

            _s.execute(
                delete(StreamRelation).where(
                    StreamRelation.parent_id == m_item.id,
                    StreamRelation.child_id == stream.id,
                )
            )
            _s.execute(
                insert(StreamBlacklistRelation).values(
                    media_item_id=m_item.id, stream_id=stream.id
                )
            )

        else:
            # If the stream is blacklisted, remove blacklist and restore link.
            bl = _s.query(
                _s.query(StreamBlacklistRelation)
                .filter(
                    StreamBlacklistRelation.media_item_id == m_item.id,
                    StreamBlacklistRelation.stream_id == stream.id,
                )
                .exists()
            ).scalar()

            if not bl:
                return False

            _s.execute(
                delete(StreamBlacklistRelation).where(
                    StreamBlacklistRelation.media_item_id == m_item.id,
                    StreamBlacklistRelation.stream_id == stream.id,
                )
            )
            _s.execute(
                insert(StreamRelation).values(parent_id=m_item.id, child_id=stream.id)
            )

        m_item.store_state()
        _s.commit()
        return True
