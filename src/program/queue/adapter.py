from __future__ import annotations

from typing import Any

from program.media.item import MediaItem
from program.queue.models import ContentQueueEntry, QueueEntry
from program.types import Event


def emitted_by_name(emitted_by: object) -> str:
    if isinstance(emitted_by, str):
        return emitted_by
    return emitted_by.__class__.__name__


def event_to_entry(event: Event) -> QueueEntry | None:
    if not event.item_id:
        return None
    return QueueEntry(
        item_id=int(event.item_id),
        item_state=event.item_state,
        run_at=event.run_at,
        queued_at=event.queued_at,
        emitted_by=emitted_by_name(event.emitted_by),
        overrides=event.overrides,
    )


def event_to_content_entry(event: Event) -> ContentQueueEntry | None:
    if event.item_id or not event.content_item:
        return None
    return ContentQueueEntry(
        content_item=event.content_item,
        run_at=event.run_at,
        queued_at=event.queued_at,
        emitted_by=emitted_by_name(event.emitted_by),
        overrides=event.overrides,
    )


def entry_to_event(entry: QueueEntry, emitted_by: Any = None) -> Event:
    from program.types import Event

    emitter = emitted_by if emitted_by is not None else entry.emitted_by
    return Event(
        emitted_by=emitter,
        item_id=entry.item_id,
        run_at=entry.run_at,
        queued_at=entry.queued_at,
        item_state=entry.item_state,
        overrides=entry.overrides,
    )


def content_entry_to_event(entry: ContentQueueEntry) -> Event:
    from program.types import Event

    return Event(
        emitted_by=entry.emitted_by,
        content_item=entry.content_item,
        run_at=entry.run_at,
        queued_at=entry.queued_at,
        overrides=entry.overrides,
    )
