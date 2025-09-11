import asyncio
from datetime import datetime
import os
from typing import List, Literal, Optional

import Levenshtein
from fastapi import APIRouter, Depends, HTTPException, Request, status
from RTN import parse_media_file
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from program.db import db_functions
from program.db.db import db, get_db
from program.media.item import MediaItem
from program.media.state import States
from program.services.indexers import CompositeIndexer
from program.services.content import Overseerr
from program.services.filesystem import FilesystemService
from program.types import Event
from program.settings.manager import settings_manager

from ..models.shared import MessageResponse

router = APIRouter(
    prefix="/items",
    tags=["items"],
    responses={404: {"description": "Not found"}},
)


def handle_ids(ids: str) -> list[str]:
    ids = [str(id) for id in ids.split(",")] if "," in ids else [str(ids)]
    if not ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No item ID provided")
    return ids


class StateResponse(BaseModel):
    success: bool
    states: list[str]


@router.get("/states", operation_id="get_states")
async def get_states() -> StateResponse:
    return {
        "success": True,
        "states": [state for state in States],
    }


class ItemsResponse(BaseModel):
    success: bool
    items: list[dict]
    page: int
    limit: int
    total_items: int
    total_pages: int


@router.get(
    "",
    summary="Retrieve Media Items",
    description="Fetch media items with optional filters and pagination",
    operation_id="get_items",
)
async def get_items(
    _: Request,
    limit: Optional[int] = 50,
    page: Optional[int] = 1,
    type: Optional[str] = None,
    states: Optional[str] = None,
    sort: Optional[
        Literal["date_desc", "date_asc", "title_asc", "title_desc"]
    ] = "date_desc",
    search: Optional[str] = None,
    extended: Optional[bool] = False,
    is_anime: Optional[bool] = False,
) -> ItemsResponse:
    if page < 1:
        raise HTTPException(status_code=400, detail="Page number must be 1 or greater.")

    if limit < 1:
        raise HTTPException(status_code=400, detail="Limit must be 1 or greater.")

    query = select(MediaItem)

    if search:
        search_lower = search.lower()
        if search_lower.startswith("tt"):
            query = query.where(MediaItem.imdb_id == search_lower)
        else:
            query = query.where(
                (func.lower(MediaItem.title).like(f"%{search_lower}%"))
                | (func.lower(MediaItem.imdb_id).like(f"%{search_lower}%"))
            )

    if states:
        states = states.split(",")
        filter_states = []
        for state in states:
            filter_lower = state.lower()
            for state_enum in States:
                if Levenshtein.ratio(filter_lower, state_enum.name.lower()) >= 0.82:
                    filter_states.append(state_enum)
                    break
        if 'All' not in states:
            if len(filter_states) == len(states):
                query = query.where(MediaItem.last_state.in_(filter_states))
            else:
                valid_states = [state_enum.name for state_enum in States]
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid filter states: {states}. Valid states are: {valid_states}",
                )

    if type:
        if "," in type:
            types = type.split(",")
            for type in types:
                if type not in ["movie", "show", "season", "episode", "anime"]:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid type: {type}. Valid types are: ['movie', 'show', 'season', 'episode', 'anime']",
                    )
        else:
            types = [type]
        if "anime" in types:
            types = [type for type in types if type != "anime"]
            query = query.where(
                or_(
                    and_(
                        MediaItem.type.in_(["movie", "show"]),
                        MediaItem.is_anime == True,
                    ),
                    MediaItem.type.in_(types),
                )
            )
        else:
            query = query.where(MediaItem.type.in_(types))

    if is_anime:
        query = query.where(MediaItem.is_anime is True)

    if sort and not search:
        sort_lower = sort.lower()
        if sort_lower == "title_asc":
            query = query.order_by(MediaItem.title.asc())
        elif sort_lower == "title_desc":
            query = query.order_by(MediaItem.title.desc())
        elif sort_lower == "date_asc":
            query = query.order_by(MediaItem.requested_at.asc())
        elif sort_lower == "date_desc":
            query = query.order_by(MediaItem.requested_at.desc())
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid sort: {sort}. Valid sorts are: ['title_asc', 'title_desc', 'date_asc', 'date_desc']",
            )

    with db.Session() as session:
        total_items = session.execute(
            select(func.count()).select_from(query.subquery())
        ).scalar_one()
        items = (
            session.execute(query.offset((page - 1) * limit).limit(limit))
            .unique()
            .scalars()
            .all()
        )

        total_pages = (total_items + limit - 1) // limit

        return {
            "success": True,
            "items": [
                item.to_extended_dict() if extended else item.to_dict()
                for item in items
            ],
            "page": page,
            "limit": limit,
            "total_items": total_items,
            "total_pages": total_pages,
        }


@router.post(
    "/add",
    summary="Add Media Items",
    description="Add media items with bases on TMDB ID or TVDB ID",
    operation_id="add_items",
)
async def add_items(request: Request, tmdb_ids: Optional[str] = None, tvdb_ids: Optional[str] = None, media_type: Optional[Literal["movie", "tv"]] = None) -> MessageResponse:
    if (not tmdb_ids and not tvdb_ids) or not media_type:
        raise HTTPException(status_code=400, detail="No ID(s) or media type provided")

    if tmdb_ids:
        all_tmdb_ids = [id.strip() for id in tmdb_ids.split(",")] if "," in tmdb_ids else [tmdb_ids.strip()]
        all_tmdb_ids = [id for id in all_tmdb_ids if id]
    else:
        all_tmdb_ids = []

    if tvdb_ids:
        all_tvdb_ids = [id.strip() for id in tvdb_ids.split(",")] if "," in tvdb_ids else [tvdb_ids.strip()]
        all_tvdb_ids = [id for id in all_tvdb_ids if id]
    else:
        all_tvdb_ids = []

    added_count = 0
    items = []

    with db.Session() as session:
        for id in all_tmdb_ids:
            if media_type == "movie" and not db_functions.item_exists_by_any_id(tmdb_id=id):
                item = MediaItem({"tmdb_id": id, "requested_by": "riven", "requested_at": datetime.now()})
                if item:
                    items.append(item)
            else:
                logger.debug(f"Item with TMDB ID {id} already exists")

        for id in all_tvdb_ids:
            if media_type == "tv" and not db_functions.item_exists_by_any_id(tvdb_id=id):
                item = MediaItem({"tvdb_id": id, "requested_by": "riven", "requested_at": datetime.now()})
                if item:
                    items.append(item)
            else:
                logger.debug(f"Item with TVDB ID {id} already exists")

        if items:
            for item in items:
                request.app.program.em.add_item(item)
                added_count += 1

    return {"message": f"Added {added_count} item(s) to the queue", "tmdb_ids": all_tmdb_ids, "tvdb_ids": all_tvdb_ids}

@router.get(
    "/{id}",
    summary="Retrieve Media Item",
    description="Fetch a single media item by TMDB ID or TVDB ID",
    operation_id="get_item",
)
async def get_item(_: Request, id: str = None, media_type: Literal["movie", "tv"] = None, with_streams: Optional[bool] = False) -> dict:
    if not id or not media_type:
        raise HTTPException(status_code=400, detail="No ID or media type provided")

    with db.Session() as session:
        if media_type == "movie":
            query = select(MediaItem).where(
                MediaItem.tmdb_id == id,
                MediaItem.type.in_(["movie"])
            )
        elif media_type == "tv":
            query = select(MediaItem).where(
                MediaItem.tvdb_id == id,
                MediaItem.type.in_(["show"])
            )
        else:
            raise HTTPException(status_code=400, detail="Invalid media type")

        try:
            item = session.execute(query).unique().scalar_one_or_none()
            if item:
                return item.to_extended_dict(with_streams=with_streams)
            else:
                raise HTTPException(status_code=404, detail="Item not found")
        except Exception as e:
            # Handle multiple results
            if "Multiple rows were found when one or none was required" in str(e):
                items = session.execute(query).unique().scalars().all()
                duplicate_ids = {item.id for item in items}
                logger.debug(f"Multiple items found with ID {id}: {duplicate_ids}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Multiple items found with ID {id}: {duplicate_ids}"
                )
            logger.error(f"Error fetching item with ID {id}: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e)) from e

@router.get(
    "/imdb/{imdb_ids}",
    summary="Retrieve Media Items By IMDb IDs",
    description="Fetch media items by IMDb IDs",
    operation_id="get_items_by_imdb_ids",
)
async def get_items_by_imdb_ids(request: Request, imdb_ids: str) -> list[dict]:
    ids = imdb_ids.split(",")
    with db.Session() as session:
        items = []
        for id in ids:
            item = (
                session.execute(select(MediaItem).where(MediaItem.imdb_id == id).where(MediaItem.type.in_(["movie", "show"])))
                .unique()
                .scalar_one()
            )
            if item:
                items.append(item)
        return [item.to_extended_dict() for item in items]


class ResetResponse(BaseModel):
    message: str
    ids: list[str]


@router.post(
    "/reset",
    summary="Reset Media Items",
    description="Reset media items with bases on item IDs",
    operation_id="reset_items",
)
async def reset_items(request: Request, ids: str) -> ResetResponse:
    ids = handle_ids(ids)
    try:
        for media_item in db_functions.get_items_by_ids(ids):
            try:
                request.app.program.em.cancel_job(media_item.id)
                active_hash = media_item.active_stream.get("infohash", None)
                active_stream = next((stream for stream in media_item.streams if stream.infohash == active_hash), None)
                db_functions.clear_streams(media_item)
                db_functions.reset_media_item(media_item)
                if active_stream:
                    # lets blacklist the active stream so it doesnt get used again
                    db_functions.blacklist_stream(media_item, active_stream)
                    logger.debug(f"Blacklisted stream {active_hash} for item {media_item.log_string}")
            except ValueError as e:
                logger.error(f"Failed to reset item with id {media_item.id}: {str(e)}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error while resetting item with id {media_item.id}: {str(e)}")
                continue
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"message": f"Reset items with id {ids}", "ids": ids}


class RetryResponse(BaseModel):
    message: str
    ids: list[str]


@router.post(
    "/retry",
    summary="Retry Media Items",
    description="Retry media items with bases on item IDs",
    operation_id="retry_items",
)
async def retry_items(request: Request, ids: str) -> RetryResponse:
    """Re-add items to the queue"""
    ids = handle_ids(ids)
    for id in ids:
        try:
            item = db_functions.get_item_by_id(id)
            if item:
                with db.Session() as session:
                    item.scraped_at = None
                    item.scraped_times = 1
                    session.merge(item)
                    session.commit()
                request.app.program.em.add_event(Event("RetryItem", id))
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    return {"message": f"Retried items with ids {ids}", "ids": ids}


@router.post(
    "/retry_library",
    summary="Retry Library Items",
    description="Retry items in the library that failed to download",
    operation_id="retry_library_items",
)
async def retry_library_items(request: Request) -> RetryResponse:
    with db.Session() as session:
        item_ids = db_functions.retry_library(session)
        for item_id in item_ids:
            request.app.program.em.add_event(Event(emitted_by="RetryLibrary", item_id=item_id))
    return {"message": f"Retried {len(item_ids)} items", "ids": item_ids}


class UpdateOngoingResponse(BaseModel):
    message: str
    updated_items: list[dict]


@router.post(
    "/update_ongoing",
    summary="Update Ongoing Items",
    description="Update state for ongoing and unreleased items",
    operation_id="update_ongoing_items",
)
async def update_ongoing_items(request: Request) -> UpdateOngoingResponse:
    with db.Session() as session:
        updated_items = db_functions.update_ongoing(session)
        for item_id, previous_state, new_state in updated_items:
            request.app.program.em.add_event(Event(emitted_by="UpdateOngoing", item_id=item_id))
    return {
        "message": f"Updated {len(updated_items)} items",
        "updated_items": [
            {"item_id": item_id, "previous_state": previous_state, "new_state": new_state}
            for item_id, previous_state, new_state in updated_items
        ]
    }




class RemoveResponse(BaseModel):
    message: str
    ids: list[str]


@router.delete(
    "/remove",
    summary="Remove Media Items",
    description="Remove media items based on item IDs",
    operation_id="remove_item",
    response_model=RemoveResponse,  # keep if you already use this
)
async def remove_item(request: Request, ids: str) -> RemoveResponse:
    """
    Remove one or more media items by their IDs.

    This uses ON DELETE CASCADE, so deleting the root MediaItem row also removes:
      - joined-table rows (Movie/Show/Season/Episode),
      - hierarchy children (Season/Episode via parent_id),
      - Subtitle rows (Subtitle.parent_id → MediaItem.id),
      - StreamRelation / StreamBlacklistRelation rows.

    We explicitly avoid pre-deleting seasons/episodes or clearing stream links—
    that work is delegated to the database for speed and consistency.
    """
    ids: List[str] = handle_ids(ids)
    if not ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No IDs provided")
    media_items: list[MediaItem] = db_functions.get_items_by_ids(ids, ["movie", "show"])
    if not media_items or not all(isinstance(item, MediaItem) for item in media_items):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item(s) not found")
    for item in media_items:
        if not item or not isinstance(item, MediaItem):
            continue
        logger.debug(f"Removing item with ID {item.id}")
        request.app.program.em.cancel_job(item.id)  # this will cancel the item and all its children
        await asyncio.sleep(0.2)  # Ensure cancellation is processed

        # Remove VFS entries recursively before DB deletions
        filesystem_service = request.app.program.services.get(FilesystemService)
        filesystem_service.delete_item_files_by_id(item.id)
        if item.type == "show":
            for season in item.seasons:
                for episode in season.episodes:
                    db_functions.delete_media_item_by_id(episode.id)
                db_functions.delete_media_item_by_id(season.id)
        db_functions.clear_streams_by_id(item.id)

        if item.overseerr_id:
            overseerr: Overseerr = request.app.program.services.get(Overseerr)
            if overseerr:
                overseerr.delete_request(item.overseerr_id)
                logger.debug(f"Deleted request from Overseerr with ID {item.overseerr_id}")

    # Load items (allow any concrete type; callers may pass show/movie/season/episode)
    items: List[MediaItem] = db_functions.get_items_by_ids(ids)
    found_ids = {it.id for it in items}
    missing = [i for i in ids if i not in found_ids]
    if missing:
        # Keep existing behavior: all must exist, otherwise 404
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item(s) not found: {missing}",
        )

    # Cancel active jobs first (your EventManager cancels children too)
    for item in items:
        logger.debug(f"Canceling jobs for {item.id}")
        request.app.program.em.cancel_job(item.id)

    # Give the scheduler a tick to process cancellations (non-blocking)
    await asyncio.sleep(0.2)

    # Side-effects outside the DB (symlinks, Overseerr) before deleting rows
    overseerr: Overseerr | None = request.app.program.services.get(Overseerr)

    for item in items:
        if item.overseerr_id and overseerr:
            try:
                overseerr.delete_request(item.overseerr_id)
                logger.debug(f"Deleted Overseerr request {item.overseerr_id} for {item.id}")
            except Exception as e:
                logger.warning(f"Failed to delete Overseerr request {item.overseerr_id} for {item.id}: {e}")

    # Single responsibility: remove root MediaItem(s); cascades handle the rest
    for item in items:
        logger.debug(f"Deleting item {item.id} via cascade")
        ok = db_functions.delete_media_item_by_id(item.id)
        if not ok:
            # If one fails, continue deleting the rest but report a 500 afterward
            logger.error(f"Failed to delete item {item.id}")

    logger.info(f"Successfully removed items: {ids}")
    return {"message": f"Removed items with ids {ids}", "ids": ids}

@router.get(
    "/{item_id}/streams"
)
async def get_item_streams(_: Request, item_id: str, db: Session = Depends(get_db)):
    item: MediaItem = (
        db.execute(
            select(MediaItem)
            .where(MediaItem.id == item_id)
        )
        .unique()
        .scalar_one_or_none()
    )

    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    return {
        "message": f"Retrieved streams for item {item_id}",
        "streams": item.streams,
        "blacklisted_streams": item.blacklisted_streams
    }

@router.post(
    "/{item_id}/streams/{stream_id}/blacklist"
)
async def blacklist_stream(_: Request, item_id: str, stream_id: int, db: Session = Depends(get_db)):
    item: MediaItem = (
        db.execute(
            select(MediaItem)
            .where(MediaItem.id == item_id)
        )
        .unique()
        .scalar_one_or_none()
    )
    stream = next((stream for stream in item.streams if stream.id == stream_id), None)

    if not item or not stream:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item or stream not found")

    db_functions.set_stream_blacklisted(item, stream, blacklisted=True, session=db)

    return {
        "message": f"Blacklisted stream {stream_id} for item {item_id}",
    }

@router.post(
    "/{item_id}/streams/{stream_id}/unblacklist"
)
async def unblacklist_stream(_: Request, item_id: str, stream_id: int, db: Session = Depends(get_db)):
    item: MediaItem = (
        db.execute(
            select(MediaItem)
            .where(MediaItem.id == item_id)
        )
        .unique()
        .scalar_one_or_none()
    )

    stream = next((stream for stream in item.blacklisted_streams if stream.id == stream_id), None)

    if not item or not stream:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item or stream not found")

    db_functions.set_stream_blacklisted(item, stream, blacklisted=False, session=db)

    return {
        "message": f"Unblacklisted stream {stream_id} for item {item_id}",
    }

@router.post(
    "/{item_id}/streams/reset",
    summary="Reset Media Item Streams",
    description="Reset all streams for a media item",
    operation_id="reset_item_streams",
)
async def reset_item_streams(_: Request, item_id: str, db: Session = Depends(get_db)):
    item: MediaItem = (
        db.execute(
            select(MediaItem)
            .where(MediaItem.id == item_id)
        )
        .unique()
        .scalar_one_or_none()
    )

    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    db_functions.clear_streams(item)

    return {
        "message": f"Successfully reset streams for item {item_id}",
    }

class PauseResponse(BaseModel):
    message: str
    ids: list[str]

@router.post(
    "/pause",
    summary="Pause Media Items",
    description="Pause media items based on item IDs",
    operation_id="pause_items",
)
async def pause_items(request: Request, ids: str) -> PauseResponse:
    """Pause items and their children from being processed"""
    ids = handle_ids(ids)
    try:
        with db.Session() as session:
            for media_item in db_functions.get_items_by_ids(ids):
                try:
                    item_id, related_ids = db_functions.get_item_ids(session, media_item.id)
                    all_ids = [item_id] + related_ids

                    for id in all_ids:
                        request.app.program.em.cancel_job(id)
                        request.app.program.em.remove_id_from_queues(id)

                    if media_item.last_state not in [States.Paused, States.Failed, States.Completed]:
                        media_item.store_state(States.Paused)
                        session.merge(media_item)
                        session.commit()

                    logger.info(f"Successfully paused items.")
                except Exception as e:
                    logger.error(f"Failed to pause {media_item.log_string}: {str(e)}")
                    continue
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {"message": "Successfully paused items.", "ids": ids}

@router.post(
    "/unpause",
    summary="Unpause Media Items",
    description="Unpause media items based on item IDs",
    operation_id="unpause_items",
)
async def unpause_items(request: Request, ids: str) -> PauseResponse:
    """Unpause items and their children to resume processing"""
    ids = handle_ids(ids)
    try:
        with db.Session() as session:
            for media_item in db_functions.get_items_by_ids(ids):
                try:
                    if media_item.last_state == States.Paused:
                        media_item.store_state(States.Requested)
                        session.merge(media_item)
                        session.commit()
                        request.app.program.em.add_event(Event("RetryItem", media_item.id))
                        logger.info(f"Successfully unpaused {media_item.log_string}")
                    else:
                        logger.debug(f"Skipping unpause for {media_item.log_string} - not in paused state")
                except Exception as e:
                    logger.error(f"Failed to unpause {media_item.log_string}: {str(e)}")
                    continue
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"message": f"Successfully unpaused items.", "ids": ids}

class ReindexResponse(BaseModel):
    message: str

@router.post(
    "/reindex",
    summary="Reindex item with Composite Indexer to pick up new season & episode releases.",
    description="Submits an item to be re-indexed through the indexer to manually fix shows that don't have release dates. Only works for movies and shows. Requires item id as a parameter.",
    operation_id="composite_reindexer"
)
async def reindex_item(request: Request, item_id: Optional[str] = None, imdb_id: Optional[str] = None) -> ReindexResponse:
    """Reindex item through Composite Indexer manually"""
    if item_id:
        item: MediaItem = db_functions.get_item_by_id(item_id)
    elif imdb_id:
        item: MediaItem = db_functions.get_item_by_external_id(imdb_id=imdb_id)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Item id or imdb id is required")

    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    if item.type not in ("movie", "show"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Item must be a movie or show")

    try:
        c_indexer = request.app.program.all_services[CompositeIndexer]
        item.indexed_at = None
        reindexed_item = next(c_indexer.run(item, log_msg=True))
        
        if reindexed_item:
            with db.Session() as session:
                session.merge(reindexed_item)
                session.commit()
            
            logger.info(f"Successfully reindexed {item.log_string}")
            request.app.program.em.add_event(Event("RetryItem", item.id))
            return ReindexResponse(message=f"Successfully reindexed {item.log_string}")
        else:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to reindex item - no data returned from Composite Indexer")

    except Exception as e:
        logger.error(f"Failed to reindex {item.log_string}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to reindex item: {str(e)}")

class FfprobeResponse(BaseModel):
    message: str
    data: dict

@router.post(
    "/ffprobe",
    summary="Parse Media File",
    description="Parse a media file",
    operation_id="ffprobe_media_files",
)
async def ffprobe_symlinks(request: Request, id: str) -> FfprobeResponse:
    """Parse all symlinks from item. Requires ffmpeg to be installed."""
    item: MediaItem = db_functions.get_item_by_id(id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    data = {}
    try:
        if item.type in ("movie", "episode"):
            if item.filesystem_path:
                data[item.id] = parse_media_file(item.filesystem_path)

        elif item.type == "show":
            for season in item.seasons:
                for episode in season.episodes:
                    if episode.filesystem_path:
                        data[episode.id] = parse_media_file(episode.filesystem_path)

        elif item.type == "season":
            for episode in item.episodes:
                if episode.filesystem_path:
                    data[episode.id] = parse_media_file(episode.filesystem_path)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    if data:
        return FfprobeResponse(message=f"Successfully parsed media files for item {id}", data=data)
    return FfprobeResponse(message=f"No media files found for item {id}", data={})
