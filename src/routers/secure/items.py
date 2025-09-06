import asyncio
from datetime import datetime
import os
from typing import Literal, Optional

import Levenshtein
from fastapi import APIRouter, Depends, HTTPException, Request, status
from RTN import parse_media_file
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session

from program.db import db_functions
from program.db.db import db, get_db
from program.media.item import MediaItem
from program.media.state import States
from program.services.content import Overseerr

from program.symlink import Symlinker
from program.types import Event
from program.services.libraries.symlink import fix_broken_symlinks
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
    description="Add media items with bases on imdb IDs",
    operation_id="add_items",
)
async def add_items(request: Request, imdb_ids: str = None) -> MessageResponse:
    if not imdb_ids:
        raise HTTPException(status_code=400, detail="No IMDb ID(s) provided")

    ids = imdb_ids.split(",")

    valid_ids = []
    for id in ids:
        if not id.startswith("tt"):
            logger.warning(f"Invalid IMDb ID {id}, skipping")
        else:
            valid_ids.append(id)

    if not valid_ids:
        raise HTTPException(status_code=400, detail="No valid IMDb ID(s) provided")

    with db.Session() as _:
        for id in valid_ids:
            item = MediaItem(
                {"imdb_id": id, "requested_by": "riven", "requested_at": datetime.now()}
            )
            request.app.program.em.add_item(item)

    return {"message": f"Added {len(valid_ids)} item(s) to the queue"}

@router.get(
    "/{id}",
    summary="Retrieve Media Item",
    description="Fetch a single media item by ID",
    operation_id="get_item",
)
async def get_item(_: Request, id: str, use_tmdb_id: Optional[bool] = False) -> dict:
    with db.Session() as session:
        query = select(MediaItem)
        if use_tmdb_id:
            query = query.where(MediaItem.tmdb_id == id).where(MediaItem.type.in_(["movie", "show"]))
        else:
            query = query.where(MediaItem.id == id)
        try:
            item = session.execute(query).unique().scalar_one_or_none()
            if item:
                return item.to_extended_dict(with_streams=False)
            raise NoResultFound
        except NoResultFound:
            raise HTTPException(status_code=404, detail="Item not found")
        except Exception as e:
            if "Multiple rows were found when one or none was required" in str(e):
                duplicate_ids = set()
                items = session.execute(query).unique().scalars().all()
                for item in items:
                    duplicate_ids.add(item.id)
                logger.debug(f"Multiple items found with ID {id}: {duplicate_ids}")
            else:
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

class RepairSymlinksResponse(BaseModel):
    message: str

@router.post(
    "/repair_symlinks",
    summary="Repair Broken Symlinks",
    description="Repair broken symlinks in the library. Optionally, provide a directory path to only scan that directory.",
    operation_id="repair_symlinks",
)
async def repair_symlinks(request: Request, directory: Optional[str] = None) -> RepairSymlinksResponse:
    library_path = settings_manager.settings.symlink.library_path
    rclone_path = settings_manager.settings.symlink.rclone_path

    if directory:
        specific_directory = os.path.join(library_path, directory)
        if not os.path.isdir(specific_directory):
            raise HTTPException(status_code=400, detail=f"Directory {specific_directory} does not exist.")
    else:
        specific_directory = None

    fix_broken_symlinks(library_path, rclone_path, specific_directory=specific_directory)

    return {"message": "Symlink repair process completed."}


class RemoveResponse(BaseModel):
    message: str
    ids: list[str]


@router.delete(
    "/remove",
    summary="Remove Media Items",
    description="Remove media items based on item IDs",
    operation_id="remove_item",
)
async def remove_item(request: Request, ids: str) -> RemoveResponse:
    ids: list[str] = handle_ids(ids)
    try:
        media_items: list[MediaItem] = db_functions.get_items_by_ids(ids, ["movie", "show"])
        if not media_items or not all(isinstance(item, MediaItem) for item in media_items):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item(s) not found")
        for item in media_items:
            if not item or not isinstance(item, MediaItem):
                continue
            logger.debug(f"Removing item with ID {item.id}")
            request.app.program.em.cancel_job(item.id)  # this will cancel the item and all its children
            await asyncio.sleep(0.2)  # Ensure cancellation is processed
            if item.type == "show":
                for season in item.seasons:
                    for episode in season.episodes:
                        db_functions.delete_media_item_by_id(episode.id)
                    db_functions.delete_media_item_by_id(season.id)
            db_functions.clear_streams_by_id(item.id)

            symlink_service = request.app.program.services.get(Symlinker)
            if symlink_service:
                symlink_service.delete_item_symlinks_by_id(item.id)

            if item.overseerr_id:
                overseerr: Overseerr = request.app.program.services.get(Overseerr)
                if overseerr:
                    overseerr.delete_request(item.overseerr_id)
                    logger.debug(f"Deleted request from Overseerr with ID {item.overseerr_id}")

            logger.debug(f"Deleting item from database with ID {item.id}")
            db_functions.delete_media_item_by_id(item.id)
            logger.info(f"Successfully removed item with ID {item.id}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

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

    db_functions.blacklist_stream(item, stream, db)

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

    db_functions.unblacklist_stream(item, stream, db)

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

# class ReindexResponse(BaseModel):
#     message: str

# @router.post(
#     "/reindex",
#     summary="Reindex item with Trakt Indexer to pick up new season & episode releases.",
#     description="Submits an item to be re-indexed through the indexer to manually fix shows that don't have release dates. Only works for movies and shows. Requires item id as a parameter.",
#     operation_id="trakt_reindexer"
# )
# async def reindex_item(request: Request, item_id: Optional[str] = None, imdb_id: Optional[str] = None) -> ReindexResponse:
#     """Reindex item through Trakt manually"""
#     if item_id:
#         item: MediaItem = db_functions.get_item_by_id(item_id)
#     elif imdb_id:
#         item: MediaItem = db_functions.get_item_by_external_id(imdb_id=imdb_id)
#     else:
#         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Item id or imdb id is required")

#     if not item:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

#     if item.type not in ("movie", "show"):
#         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Item must be a movie or show")

#     try:
#         trakt_indexer = request.app.program.all_services[TraktIndexer]
#         item.indexed_at = None
#         reindexed_item = next(trakt_indexer.run(item, log_msg=True))
        
#         if reindexed_item:
#             with db.Session() as session:
#                 session.merge(reindexed_item)
#                 session.commit()
            
#             logger.info(f"Successfully reindexed {item.log_string}")
#             request.app.program.em.add_event(Event("RetryItem", item.id))
#             return ReindexResponse(message=f"Successfully reindexed {item.log_string}")
#         else:
#             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to reindex item - no data returned from Trakt")

#     except Exception as e:
#         logger.error(f"Failed to reindex {item.log_string}: {str(e)}")
#         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to reindex item: {str(e)}")

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
            if item.symlink_path:
                data[item.id] = parse_media_file(item.symlink_path)

        elif item.type == "show":
            for season in item.seasons:
                for episode in season.episodes:
                    if episode.symlink_path:
                        data[episode.id] = parse_media_file(episode.symlink_path)

        elif item.type == "season":
            for episode in item.episodes:
                if episode.symlink_path:
                    data[episode.id] = parse_media_file(episode.symlink_path)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    if data:
        return FfprobeResponse(message=f"Successfully parsed media files for item {id}", data=data)
    return FfprobeResponse(message=f"No media files found for item {id}", data={})
