import asyncio
from datetime import datetime
from typing import Literal, Optional

import Levenshtein
from RTN import Torrent
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.exc import NoResultFound

from controllers.models.shared import MessageResponse
from fastapi import APIRouter, HTTPException, Request
from program.content import Overseerr
from program.db.db import db
from program.db.db_functions import (
    clear_streams,
    clear_streams_by_id,
    delete_media_item_by_id,
    get_media_items_by_ids,
    get_parent_ids,
    reset_media_item,
)
from program.media.item import MediaItem
from program.media.state import States
from program.symlink import Symlinker
from program.downloaders import Downloader, get_needed_media
from program.media.stream import Stream
from program.scrapers.shared import rtn
from program.types import Event
from pydantic import BaseModel
from RTN import Torrent
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import NoResultFound
from utils.logger import logger

router = APIRouter(
    prefix="/items",
    tags=["items"],
    responses={404: {"description": "Not found"}},
)


def handle_ids(ids: str) -> list[int]:
    if isinstance(ids, int):
        ids = [ids]
    else:
        ids = [int(id) for id in ids.split(",")] if "," in ids else [int(ids)]
    if not ids:
        raise HTTPException(status_code=400, detail="No item ID provided")
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
async def get_item(_: Request, id: int, use_tmdb_id: Optional[bool] = False) -> dict:
    with db.Session() as session:
        try:
            query = select(MediaItem)
            if use_tmdb_id:
                query = query.where(MediaItem.tmdb_id == str(id))
            else:
                query = query.where(MediaItem._id == id)
            item = session.execute(query).unique().scalar_one()
        except NoResultFound:
            raise HTTPException(status_code=404, detail="Item not found")
        return item.to_extended_dict(with_streams=False)


@router.get(
    "/{imdb_ids}",
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
                session.execute(select(MediaItem).where(MediaItem.imdb_id == id))
                .unique()
                .scalar_one()
            )
            if item:
                items.append(item)
        return [item.to_extended_dict() for item in items]


class ResetResponse(BaseModel):
    message: str
    ids: list[int]


@router.post(
    "/reset",
    summary="Reset Media Items",
    description="Reset media items with bases on item IDs",
    operation_id="reset_items",
)
async def reset_items(request: Request, ids: int) -> ResetResponse:
    ids = handle_ids(ids)
    try:
        media_items_generator = get_media_items_by_ids(ids)
        for media_item in media_items_generator:
            try:
                request.app.program.em.cancel_job(media_item._id)
                clear_streams(media_item)
                reset_media_item(media_item)
            except ValueError as e:
                logger.error(f"Failed to reset item with id {media_item._id}: {str(e)}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error while resetting item with id {media_item._id}: {str(e)}")
                continue
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"message": f"Reset items with id {ids}", "ids": ids}


class RetryResponse(BaseModel):
    message: str
    ids: list[int]


@router.post(
    "/retry",
    summary="Retry Media Items",
    description="Retry media items with bases on item IDs",
    operation_id="retry_items",
)
async def retry_items(request: Request, ids: int) -> RetryResponse:
    ids = handle_ids(ids)
    try:
        media_items_generator = get_media_items_by_ids(ids)
        for media_item in media_items_generator:
            request.app.program.em.cancel_job(media_item._id)
            await asyncio.sleep(0.1)  # Ensure cancellation is processed
            request.app.program.em.add_item(media_item)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"message": f"Retried items with ids {ids}", "ids": ids}


class RemoveResponse(BaseModel):
    message: str
    ids: list[int]


@router.delete(
    "/remove",
    summary="Remove Media Items",
    description="Remove media items based on item IDs",
    operation_id="remove_item",
)
async def remove_item(request: Request, ids: str) -> RemoveResponse:
    ids: list[int] = handle_ids(ids)
    try:
        media_items: list[int] = get_parent_ids(ids)
        if not media_items:
            return HTTPException(status_code=404, detail="Item(s) not found")

        for item_id in media_items:
            logger.debug(f"Removing item with ID {item_id}")
            request.app.program.em.cancel_job(item_id)
            await asyncio.sleep(0.2)  # Ensure cancellation is processed
            clear_streams_by_id(item_id)

            symlink_service = request.app.program.services.get(Symlinker)
            if symlink_service:
                symlink_service.delete_item_symlinks_by_id(item_id)

            with db.Session() as session:
                requested_id = session.execute(select(MediaItem.requested_id).where(MediaItem._id == item_id)).scalar_one()
                if requested_id:
                    logger.debug(f"Deleting request from Overseerr with ID {requested_id}")
                    Overseerr.delete_request(requested_id)

            logger.debug(f"Deleting item from database with ID {item_id}")
            delete_media_item_by_id(item_id)
            logger.info(f"Successfully removed item with ID {item_id}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"message": f"Removed items with ids {ids}", "ids": ids}


class SetTorrentRDResponse(BaseModel):
    message: str
    item_id: int
    torrent_id: str


@router.post(
    "/{id}/set_torrent_rd_magnet",
    name="Set torrent RD magnet",
    description="Set a torrent for a media item using a magnet link.",
    operation_id="set_torrent_rd_magnet",
)
def add_torrent(request: Request, id: int, magnet: str) -> SetTorrentRDResponse:
    torrent_id = ""
    downloader: Downloader = request.app.program.services.get(Downloader)
    try:
        torrent_id = downloader.add_torrent_magnet(magnet)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to add torrent.") from None

    return set_torrent_rd(request, id, torrent_id)


def reset_item_to_scraped(item: MediaItem):
    item.last_state = States.Scraped
    item.symlinked = False
    item.symlink_path = None
    item.symlinked_at = None
    item.scraped_at = datetime.now()
    item.scraped_times = 1
    item.symlinked_times = 0
    item.update_folder = None
    item.file = None
    item.folder = None


def create_stream(hash, torrent_info):
    try:
        torrent: Torrent = rtn.rank(
            raw_title=torrent_info["filename"], infohash=hash, remove_trash=False
        )
        return Stream(torrent)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to rank torrent: {e}"
        ) from e


@router.post(
    "/{id}/set_torrent_rd",
    description="Set a torrent for a media item using RD torrent ID.",
)
def set_torrent_rd(request: Request, id: int, torrent_id: str) -> SetTorrentRDResponse:
    downloader: Downloader = request.app.program.services.get(Downloader)
    with db.Session() as session:
        item: MediaItem = (
            session.execute(
                select(MediaItem)
                .where(MediaItem._id == id)
                .outerjoin(MediaItem.streams)
            )
            .unique()
            .scalar_one_or_none()
        )

        if item is None:
            raise HTTPException(status_code=404, detail="Item not found")

        fetched_torrent_info = downloader.get_torrent_info(torrent_id)

        stream = (
            session.execute(
                select(Stream).where(Stream.infohash == fetched_torrent_info["hash"])
            )
            .scalars()
            .first()
        )
        hash = fetched_torrent_info["hash"]

        # Create stream if it doesn't exist
        if stream is None:
            stream = create_stream(hash, fetched_torrent_info)
            item.streams.append(stream)

        # check if the stream exists in the item
        stream_exists_in_item = next(
            (stream for stream in item.streams if stream.infohash == hash), None
        )
        if stream_exists_in_item is None:
            item.streams.append(stream)

        reset_item_to_scraped(item)

        # reset episodes if it's a season
        if item.type == "season":
            logger.debug(f"Resetting episodes for {item.title}")
            for episode in item.episodes:
                reset_item_to_scraped(episode)

        needed_media = get_needed_media(item)
        cached_streams = downloader.get_cached_streams([hash], needed_media)

        if len(cached_streams) == 0:
            session.rollback()
            raise HTTPException(
                status_code=400,
                detail=f"No cached torrents found for {item.log_string}",
            )

        item.active_stream = cached_streams[0]
        try:
            downloader.download(item, item.active_stream)
        except Exception as e:
            logger.error(f"Failed to download {item.log_string}: {e}")
            if item.active_stream.get("infohash", None):
                downloader._delete_and_reset_active_stream(item)
            session.rollback()
            raise HTTPException(
                status_code=500, detail=f"Failed to download {item.log_string}: {e}"
            ) from e

        session.commit()

        request.app.program.em.add_event(Event("Symlinker", item._))

        return {
            "success": True,
            "message": f"Set torrent for {item.title} to {torrent_id}",
            "item_id": item._id,
            "torrent_id": torrent_id,
        }


# These require downloaders to be refactored

# @router.get("/cached")
# async def manual_scrape(request: Request, ids: str):
#     scraper = request.app.program.services.get(Scraping)
#     downloader = request.app.program.services.get(Downloader).service
#     if downloader.__class__.__name__ not in ["RealDebridDownloader", "TorBoxDownloader"]:
#         raise HTTPException(status_code=400, detail="Only Real-Debrid is supported for manual scraping currently")
#     ids = [int(id) for id in ids.split(",")] if "," in ids else [int(ids)]
#     if not ids:
#         raise HTTPException(status_code=400, detail="No item ID provided")
#     with db.Session() as session:
#         items = []
#         return_dict = {}
#         for id in ids:
#             items.append(session.execute(select(MediaItem).where(MediaItem._id == id)).unique().scalar_one())
#     if any(item for item in items if item.type in ["Season", "Episode"]):
#         raise HTTPException(status_code=400, detail="Only shows and movies can be manually scraped currently")
#     for item in items:
#         new_item = item.__class__({})
#         # new_item.parent = item.parent
#         new_item.copy(item)
#         new_item.copy_other_media_attr(item)
#         scraped_results = scraper.scrape(new_item, log=False)
#         cached_hashes = downloader.get_cached_hashes(new_item, scraped_results)
#         for hash, stream in scraped_results.items():
#             return_dict[hash] = {"cached": hash in cached_hashes, "name": stream.raw_title}
#         return {"success": True, "data": return_dict}

# @router.post("/download")
# async def download(request: Request, id: str, hash: str):
#     downloader = request.app.program.services.get(Downloader).service
#     with db.Session() as session:
#         item = session.execute(select(MediaItem).where(MediaItem._id == id)).unique().scalar_one()
#         item.reset(True)
#         downloader.download_cached(item, hash)
#         request.app.program.add_to_queue(item)
#         return {"success": True, "message": f"Downloading {item.title} with hash {hash}"}
