import os
from datetime import datetime
from enum import Enum
from typing import Annotated, Callable, List, Literal, Optional, Set, Union

import Levenshtein
from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, object_session

from program.db import db_functions
from program.db.db import db, get_db
from program.media.item import MediaItem, Season, Show
from program.media.state import States
from program.services.content import Overseerr
from program.services.filesystem.filesystem_service import FilesystemService
from program.services.updaters import Updater
from program.types import Event

from ..models.shared import MessageResponse


class MediaTypeEnum(str, Enum):
    MOVIE = "movie"
    SHOW = "show"
    SEASON = "season"
    EPISODE = "episode"
    ANIME = "anime"


class SortOrderEnum(str, Enum):
    TITLE_ASC = "title_asc"
    TITLE_DESC = "title_desc"
    DATE_ASC = "date_asc"
    DATE_DESC = "date_desc"

    @property
    def sort_type(self) -> str:
        return "title" if self.value.startswith("title") else "date"


router = APIRouter(
    prefix="/items",
    tags=["items"],
    responses={404: {"description": "Not found"}},
)


def handle_ids(ids: str) -> list[int]:
    try:
        id_list = [int(id) for id in ids.split(",")] if "," in ids else [int(ids)]
        if not id_list:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="No item ID provided"
            )
        return id_list
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid item ID(s) provided",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing item ID(s): {str(e)}",
        ) from e


# Convenience helper to mutate an item and update states consistently
def apply_item_mutation(
    program,
    session: Session,
    item: MediaItem,
    mutation_fn: "Callable[[MediaItem, Session], None]",
    bubble_parents: bool = True,
) -> None:
    """Cancel jobs, apply mutation, then update item and ancestor states.
    - Uses base MediaItem.store_state to avoid recursive child updates for seasons/shows.
    - Caller is responsible for session.commit().
    """
    try:
        program.em.cancel_job(item.id)
    except Exception:
        logger.debug(f"No active job to cancel for item {getattr(item, 'id', None)}")

    # Ensure attached instance
    if object_session(item) is not session:
        item = session.merge(item)

    # Apply mutation
    mutation_fn(item, session)

    # Update self state (non-recursive)
    try:
        MediaItem.store_state(item)
    except Exception as e:
        logger.warning(f"Failed to store state for {item.id}: {e}")

    if not bubble_parents:
        return

    # Update parent states (non-recursive)
    try:
        if item.type == "episode":
            season = session.get(Season, getattr(item, "parent_id", None))
            if season:
                MediaItem.store_state(season)
                show = session.get(Show, getattr(season, "parent_id", None))
                if show:
                    MediaItem.store_state(show)
        elif item.type == "season":
            show = session.get(Show, getattr(item, "parent_id", None))
            if show:
                MediaItem.store_state(show)
    except Exception as e:
        logger.warning(f"Failed to update parent state(s) for item {item.id}: {e}")


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


class StatesFilter(str, Enum):
    All = "All"


@router.get(
    "",
    summary="Search Media Items",
    description="Fetch media items with optional filters and pagination",
    operation_id="get_items",
    response_model=ItemsResponse,
)
async def get_items(
    _: Request,
    limit: Annotated[int, Query(gt=0, description="Number of items per page")] = 50,
    page: Annotated[int, Query(gt=0, description="Page number")] = 1,
    type: Annotated[
        Optional[List[MediaTypeEnum]], Query(description="Filter by media type(s)")
    ] = None,
    states: Annotated[
        Optional[List[Union[States, StatesFilter]]],
        Query(description="Filter by state(s)"),
    ] = None,
    sort: Annotated[
        Optional[List[SortOrderEnum]],
        Query(
            description="Sort order(s). Multiple sorts allowed but only one per type (title or date)"
        ),
    ] = None,
    search: Annotated[
        Optional[str],
        Query(min_length=1, description="Search by title or IMDB/TVDB/TMDB ID"),
    ] = None,
    extended: Annotated[
        bool, Query(description="Include extended item details")
    ] = False,
) -> ItemsResponse:
    query = select(MediaItem)

    if search:
        search_lower = search.lower()
        if search_lower.startswith("tt"):
            query = query.where(MediaItem.imdb_id == search_lower)
        elif search_lower.startswith("tmdb_"):
            tmdb_id = search_lower.replace("tmdb_", "")
            query = query.where(MediaItem.tmdb_id == tmdb_id)
        elif search_lower.startswith("tvdb_"):
            tvdb_id = search_lower.replace("tvdb_", "")
            query = query.where(MediaItem.tvdb_id == tvdb_id)
        else:
            query = query.where(func.lower(MediaItem.title).like(f"%{search_lower}%"))

    if states and StatesFilter.All not in states:
        query = query.where(
            MediaItem.last_state.in_([s for s in states if isinstance(s, States)])
        )

    if type:
        media_types: Set[str] = {t.value for t in type}

        if MediaTypeEnum.ANIME in type:
            media_types.remove(MediaTypeEnum.ANIME.value)

            if not media_types:
                query = query.where(MediaItem.is_anime == True)
            else:
                query = query.where(
                    and_(
                        MediaItem.type.in_(
                            media_types if media_types else ["movie", "show"]
                        ),
                        MediaItem.is_anime == True,
                    )
                )

        elif media_types:
            query = query.where(MediaItem.type.in_(media_types))

    if sort:
        # Verify we don't have multiple sorts of the same type
        sort_types = set()
        for sort_criterion in sort:
            sort_type = sort_criterion.sort_type
            if sort_type in sort_types:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Multiple {sort_type} sort criteria provided. Only one sort per type is allowed.",
                )
            sort_types.add(sort_type)

        for sort_criterion in sort:
            if sort_criterion == SortOrderEnum.TITLE_ASC:
                query = query.order_by(MediaItem.title.asc())
            elif sort_criterion == SortOrderEnum.TITLE_DESC:
                query = query.order_by(MediaItem.title.desc())
            elif sort_criterion == SortOrderEnum.DATE_ASC:
                query = query.order_by(MediaItem.requested_at.asc())
            elif sort_criterion == SortOrderEnum.DATE_DESC:
                query = query.order_by(MediaItem.requested_at.desc())

    else:
        query = query.order_by(MediaItem.requested_at.desc())

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

        return ItemsResponse(
            success=True,
            items=[
                item.to_extended_dict() if extended else item.to_dict()
                for item in items
            ],
            page=page,
            limit=limit,
            total_items=total_items,
            total_pages=total_pages,
        )


@router.post(
    "/add",
    summary="Add Media Items",
    description="""Add media items with bases on TMDB ID or TVDB ID,
                   you can add multiple IDs by comma separating them.""",
    operation_id="add_items",
)
async def add_items(
    request: Request,
    tmdb_ids: Optional[str] = None,
    tvdb_ids: Optional[str] = None,
    media_type: Optional[Literal["movie", "tv"]] = None,
) -> MessageResponse:
    if not tmdb_ids and not tvdb_ids:
        raise HTTPException(status_code=400, detail="No ID(s) provided")

    all_tmdb_ids = []
    all_tvdb_ids = []

    if tmdb_ids and media_type == "movie":
        all_tmdb_ids = (
            [id.strip() for id in tmdb_ids.split(",")]
            if "," in tmdb_ids
            else [tmdb_ids.strip()]
        )
        all_tmdb_ids = [id for id in all_tmdb_ids if id]

    if tvdb_ids and media_type == "tv":
        all_tvdb_ids = (
            [id.strip() for id in tvdb_ids.split(",")]
            if "," in tvdb_ids
            else [tvdb_ids.strip()]
        )
        all_tvdb_ids = [id for id in all_tvdb_ids if id]

    added_count = 0
    items = []

    with db.Session() as session:
        if media_type == "movie" and tmdb_ids:
            for id in all_tmdb_ids:
                # Check if item exists using ORM
                existing = session.execute(
                    select(MediaItem).where(MediaItem.tmdb_id == id)
                ).scalar_one_or_none()

                if not existing:
                    item = MediaItem(
                        {
                            "tmdb_id": id,
                            "requested_by": "riven",
                            "requested_at": datetime.now(),
                        }
                    )
                    if item:
                        items.append(item)
                else:
                    logger.debug(f"Item with TMDB ID {id} already exists")

        if media_type == "tv" and tvdb_ids:
            for id in all_tvdb_ids:
                # Check if item exists using ORM
                existing = session.execute(
                    select(MediaItem).where(MediaItem.tvdb_id == id)
                ).scalar_one_or_none()

                if not existing:
                    item = MediaItem(
                        {
                            "tvdb_id": id,
                            "requested_by": "riven",
                            "requested_at": datetime.now(),
                        }
                    )
                    if item:
                        items.append(item)
                else:
                    logger.debug(f"Item with TVDB ID {id} already exists")

        if items:
            for item in items:
                request.app.program.em.add_item(item)
                added_count += 1

    return {"message": f"Added {added_count} item(s) to the queue"}


@router.get(
    "/{id}",
    summary="Get Media Item by ID",
    description="Fetch a single media item by TMDB ID, TVDB ID or item ID. TMDB and TVDB IDs are strings, item ID is an integer.",
    operation_id="get_item",
)
async def get_item(
    _: Request,
    id: str = None,
    media_type: Literal["movie", "tv", "item"] = None,
    extended: Optional[bool] = False,
) -> dict:
    if not id:
        raise HTTPException(status_code=400, detail="No ID or media type provided")

    with db.Session() as session:
        if media_type == "movie":
            # needs to be a string
            query = select(MediaItem).where(
                MediaItem.tmdb_id == id,
            )
        elif media_type == "tv":
            # needs to be a string
            query = select(MediaItem).where(
                MediaItem.tvdb_id == id,
            )
        elif media_type == "item":
            # needs to be an integer
            _id = int(id)
            query = select(MediaItem).where(
                MediaItem.id == _id,
            )
        else:
            raise HTTPException(status_code=400, detail="Invalid media type")

        try:
            item: MediaItem = session.execute(query).unique().scalar_one_or_none()
            if item:
                if extended:
                    return item.to_extended_dict()
                return item.to_dict()
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
                    detail=f"Multiple items found with ID {id}: {duplicate_ids}",
                )
            logger.error(f"Error fetching item with ID {id}: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e)) from e


class ResetResponse(BaseModel):
    message: str
    ids: list[int]


@router.post(
    "/reset",
    summary="Reset Media Items",
    description="Reset media items with bases on item IDs",
    operation_id="reset_items",
)
async def reset_items(
    request: Request, ids: str, session: Session = Depends(get_db)
) -> ResetResponse:
    """
    Reset the specified media items to their initial state and trigger a media-server library refresh when applicable.

    Parameters:
        request (Request): FastAPI request object used to access application services.
        ids (str): Comma-separated list of item IDs (e.g., "1,2,3") to reset.

    Returns:
        ResetResponse: Dictionary with a human-readable message and the list of processed item IDs:
            - message (str): Summary of the performed reset.
            - ids (list[int]): The numeric IDs that were processed.

    Raises:
        HTTPException: Raised with status 400 when the provided `ids` string cannot be parsed into valid IDs.
    """
    ids: list[int] = handle_ids(ids)

    # Get updater service for media server refresh
    updater: Updater | None = request.app.program.services.get(Updater)

    try:
        # Load items using ORM
        items = (
            session.execute(select(MediaItem).where(MediaItem.id.in_(ids)))
            .scalars()
            .all()
        )

        for media_item in items:
            try:
                # Gather all refresh paths before reset (entry may appear at multiple VFS paths)
                refresh_paths = []
                if updater and media_item.filesystem_entry:
                    vfs_paths = media_item.filesystem_entry.get_all_vfs_paths()
                    for vfs_path in vfs_paths:
                        abs_path = os.path.join(
                            updater.library_path, vfs_path.lstrip("/")
                        )
                        if media_item.type == "movie":
                            refresh_path = os.path.dirname(os.path.dirname(abs_path))
                        else:  # show
                            refresh_path = os.path.dirname(
                                os.path.dirname(os.path.dirname(abs_path))
                            )
                        if refresh_path not in refresh_paths:
                            refresh_paths.append(refresh_path)

                def mutation(i: MediaItem, s: Session):
                    """
                    Blacklist the MediaItem's currently active stream and reset the item's state.

                    Parameters:
                        i (MediaItem): The item to mutate.
                        s (Session): Database session (provided for caller context; not used directly here).
                    """
                    i.blacklist_active_stream()
                    i.reset()

                apply_item_mutation(
                    request.app.program,
                    session,
                    media_item,
                    mutation,
                    bubble_parents=True,
                )
                session.commit()

                # Trigger media server refresh for all paths where this item appeared
                if updater and updater.initialized:
                    for refresh_path in refresh_paths:
                        updater.refresh_path(refresh_path)
                        logger.debug(
                            f"Triggered media server refresh for {refresh_path}"
                        )

            except ValueError as e:
                logger.error(f"Failed to reset item with id {media_item.id}: {str(e)}")
                continue
            except Exception as e:
                logger.error(
                    f"Unexpected error while resetting item with id {media_item.id}: {str(e)}"
                )
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
async def retry_items(request: Request, ids: str) -> RetryResponse:
    """Re-add items to the queue"""
    ids: list[int] = handle_ids(ids)

    with db.Session() as session:
        for id in ids:
            try:
                # Load item using ORM
                item = session.get(MediaItem, id)
                if item:

                    def mutation(i: MediaItem, s: Session):
                        i.scraped_at = None
                        i.scraped_times = 1

                    apply_item_mutation(
                        request.app.program,
                        session,
                        item,
                        mutation,
                        bubble_parents=True,
                    )
                    session.commit()
                    request.app.program.em.add_event(Event("RetryItem", id))
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
                )

    return {"message": f"Retried items with ids {ids}", "ids": ids}


@router.post(
    "/retry_library",
    summary="Retry Library Items",
    description="Retry items in the library that failed to download",
    operation_id="retry_library_items",
)
async def retry_library_items(request: Request) -> RetryResponse:
    item_ids = db_functions.retry_library()
    for item_id in item_ids:
        request.app.program.em.add_event(
            Event(emitted_by="RetryLibrary", item_id=item_id)
        )
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
            request.app.program.em.add_event(
                Event(emitted_by="UpdateOngoing", item_id=item_id)
            )
    return {
        "message": f"Updated {len(updated_items)} items",
        "updated_items": [
            {
                "item_id": item_id,
                "previous_state": previous_state,
                "new_state": new_state,
            }
            for item_id, previous_state, new_state in updated_items
        ],
    }


# TODO: reimplement later
# class UpdateNewReleasesResponse(BaseModel):
#     message: str
#     updated_items: list[dict]

# @router.post(
#     "/update_new_releases",
#     summary="Update New Releases",
#     description="Update state for new releases",
#     operation_id="update_new_releases_items",
# )
# async def update_new_releases_items(request: Request, update_type: Literal["series", "seasons", "episodes"] = "episodes", hours: Optional[int] = 24) -> UpdateNewReleasesResponse:
#     with db.Session() as session:
#         updated_items = db_functions.update_new_releases(session, update_type=update_type, hours=hours)
#         for item_id in updated_items:
#             request.app.program.em.add_event(Event(emitted_by="UpdateNewReleases", item_id=item_id))
#         if updated_items:
#             logger.log("API", f"Successfully updated {len(updated_items)} items")
#         else:
#             logger.log("API", "No items required state updates")
#     return {"message": f"Updated {len(updated_items)} items", "updated_items": updated_items}


class RemoveResponse(BaseModel):
    message: str
    ids: list[int]


@router.delete(
    "/remove",
    summary="Remove Media Items",
    description="Remove media items based on item IDs",
    operation_id="remove_item",
    response_model=RemoveResponse,  # keep if you already use this
)
async def remove_item(
    request: Request, ids: str, session: Session = Depends(get_db)
) -> RemoveResponse:
    """
    Remove one or more media items identified by their IDs.

    Deletes the MediaItem rows and their related data (joined-table rows, hierarchical children, subtitles, and stream relations) and coordinates related side effects: cancels active jobs for the item, deletes an associated Overseerr request when present, and triggers a media server library refresh for the item's library path when an Updater service is available and initialized.

    Parameters:
        request (Request): FastAPI request object (used to access application services).
        ids (str): Comma-separated string of one or more numeric item IDs.

    Returns:
        dict: Response containing a human-readable message and the list of removed item IDs, e.g. {"message": "...", "ids": [1,2]}.

    Raises:
        HTTPException: If no IDs are provided or if an item type is not removable (only "movie" and "show" are allowed).
    """
    ids: list[int] = handle_ids(ids)
    if not ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No IDs provided"
        )

    # Get services
    overseerr: Overseerr | None = request.app.program.services.get(Overseerr)
    updater: Updater | None = request.app.program.services.get(Updater)

    removed_ids = []

    for item_id in ids:
        # Load item using ORM
        item: MediaItem = session.get(MediaItem, item_id)
        if not item:
            logger.warning(f"Item {item_id} not found, skipping")
            continue

        # Only allow movies and shows to be removed
        if item.type not in ("movie", "show"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Only movies and shows can be removed. Item {item_id} is a {item.type}",
            )

        logger.debug(f"Removing item with ID {item.id}")

        # 1. Cancel active jobs (EventManager cancels children too)
        request.app.program.em.cancel_job(item.id)

        # 2. Gather all refresh paths before deletion (entry may appear at multiple VFS paths)
        refresh_paths = []
        if updater and item.filesystem_entry:
            vfs_paths = item.filesystem_entry.get_all_vfs_paths()
            for vfs_path in vfs_paths:
                # Check if VFS path is already absolute (filesystem path)
                # VFS paths are normally VFS-relative (e.g., /movies/...) but could be
                # absolute filesystem paths in some configurations
                if os.path.isabs(vfs_path) and not vfs_path.startswith(
                    str(updater.library_path)
                ):
                    # VFS path is absolute but not under library_path - use as-is
                    abs_path = vfs_path
                elif os.path.isabs(vfs_path) and vfs_path.startswith(
                    str(updater.library_path)
                ):
                    # VFS path is already an absolute path under library_path - use as-is
                    abs_path = vfs_path
                else:
                    # VFS path is VFS-relative - join with library_path
                    abs_path = os.path.join(updater.library_path, vfs_path.lstrip("/"))

                if item.type == "movie":
                    refresh_path = os.path.dirname(os.path.dirname(abs_path))
                else:  # show
                    refresh_path = os.path.dirname(
                        os.path.dirname(os.path.dirname(abs_path))
                    )
                if refresh_path not in refresh_paths:
                    refresh_paths.append(refresh_path)

        # 3. Delete from Overseerr
        if item.overseerr_id and overseerr:
            try:
                overseerr.delete_request(item.overseerr_id)
                logger.debug(
                    f"Deleted Overseerr request {item.overseerr_id} for {item.id}"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to delete Overseerr request {item.overseerr_id}: {e}"
                )

        # 4. Remove from VFS
        filesystem_service = request.app.program.services.get(FilesystemService)
        if filesystem_service and filesystem_service.riven_vfs:
            filesystem_service.riven_vfs.remove(item)

        # 5. Delete from database using ORM
        session.delete(item)
        session.commit()
        removed_ids.append(item_id)
        logger.debug(f"Deleted item {item_id} from database")

        # 6. Trigger media server refresh for all paths where this item appeared
        if updater and updater.initialized:
            for refresh_path in refresh_paths:
                updater.refresh_path(refresh_path)
                logger.debug(f"Triggered media server refresh for {refresh_path}")

    logger.info(f"Successfully removed items: {removed_ids}")
    return {"message": f"Removed items with ids {removed_ids}", "ids": removed_ids}


@router.get("/{item_id}/streams")
async def get_item_streams(_: Request, item_id: int, db: Session = Depends(get_db)):
    item: MediaItem = (
        db.execute(select(MediaItem).where(MediaItem.id == item_id))
        .unique()
        .scalar_one_or_none()
    )

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
        )

    return {
        "message": f"Retrieved streams for item {item_id}",
        "streams": [stream.to_dict() for stream in item.streams],
        "blacklisted_streams": [
            stream.to_dict() for stream in item.blacklisted_streams
        ],
    }


@router.post("/{item_id}/streams/{stream_id}/blacklist")
async def blacklist_stream(
    request: Request, item_id: int, stream_id: int, db: Session = Depends(get_db)
):
    item: MediaItem = (
        db.execute(select(MediaItem).where(MediaItem.id == item_id))
        .unique()
        .scalar_one_or_none()
    )
    stream = next((stream for stream in item.streams if stream.id == stream_id), None)

    if not item or not stream:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item or stream not found"
        )

    def mutation(i: MediaItem, s: Session):
        i.blacklist_stream(stream)

    apply_item_mutation(request.app.program, db, item, mutation, bubble_parents=True)
    db.commit()

    return {
        "message": f"Blacklisted stream {stream_id} for item {item_id}",
    }


@router.post("/{item_id}/streams/{stream_id}/unblacklist")
async def unblacklist_stream(
    request: Request, item_id: int, stream_id: int, db: Session = Depends(get_db)
):
    item: MediaItem = (
        db.execute(select(MediaItem).where(MediaItem.id == item_id))
        .unique()
        .scalar_one_or_none()
    )

    stream = next(
        (stream for stream in item.blacklisted_streams if stream.id == stream_id), None
    )

    if not item or not stream:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item or stream not found"
        )

    def mutation(i: MediaItem, s: Session):
        i.unblacklist_stream(stream)

    apply_item_mutation(request.app.program, db, item, mutation, bubble_parents=True)
    db.commit()

    return {
        "message": f"Unblacklisted stream {stream_id} for item {item_id}",
    }


@router.post(
    "/{item_id}/streams/reset",
    summary="Reset Media Item Streams",
    description="Reset all streams for a media item",
    operation_id="reset_item_streams",
)
async def reset_item_streams(
    request: Request, item_id: int, db: Session = Depends(get_db)
):
    item: MediaItem = (
        db.execute(select(MediaItem).where(MediaItem.id == item_id))
        .unique()
        .scalar_one_or_none()
    )

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
        )

    def mutation(i: MediaItem, s: Session):
        i.streams.clear()
        i.blacklisted_streams.clear()
        i.active_stream = {}

    apply_item_mutation(request.app.program, db, item, mutation, bubble_parents=True)
    db.commit()

    return {
        "message": f"Successfully reset streams for item {item_id}",
    }


class PauseResponse(BaseModel):
    message: str
    ids: list[int]


@router.post(
    "/pause",
    summary="Pause Media Items",
    description="Pause media items based on item IDs",
    operation_id="pause_items",
)
async def pause_items(request: Request, ids: str) -> PauseResponse:
    """Pause items and their children from being processed"""
    ids: list[int] = handle_ids(ids)
    try:
        with db.Session() as session:
            # Load items using ORM
            items = (
                session.execute(select(MediaItem).where(MediaItem.id.in_(ids)))
                .scalars()
                .all()
            )

            for media_item in items:
                try:
                    item_id, related_ids = db_functions.get_item_ids(
                        session, media_item.id
                    )
                    all_ids = [item_id] + related_ids

                    # Cancel all related jobs
                    for id in all_ids:
                        request.app.program.em.cancel_job(id)
                        request.app.program.em.remove_id_from_queues(id)

                    if media_item.last_state not in [
                        States.Paused,
                        States.Failed,
                        States.Completed,
                    ]:

                        def mutation(i: MediaItem, s: Session):
                            i.store_state(States.Paused)

                        apply_item_mutation(
                            request.app.program,
                            session,
                            media_item,
                            mutation,
                            bubble_parents=False,
                        )
                        session.commit()

                    logger.info("Successfully paused items.")
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
    ids: list[int] = handle_ids(ids)
    try:
        with db.Session() as session:
            # Load items using ORM
            items = (
                session.execute(select(MediaItem).where(MediaItem.id.in_(ids)))
                .scalars()
                .all()
            )

            for media_item in items:
                try:
                    if media_item.last_state == States.Paused:

                        def mutation(i: MediaItem, s: Session):
                            i.store_state(States.Requested)

                        apply_item_mutation(
                            request.app.program,
                            session,
                            media_item,
                            mutation,
                            bubble_parents=True,
                        )
                        session.commit()
                        request.app.program.em.add_event(
                            Event("RetryItem", media_item.id)
                        )
                        logger.info(f"Successfully unpaused {media_item.log_string}")
                    else:
                        logger.debug(
                            f"Skipping unpause for {media_item.log_string} - not in paused state"
                        )
                except Exception as e:
                    logger.error(f"Failed to unpause {media_item.log_string}: {str(e)}")
                    continue
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"message": "Successfully unpaused items.", "ids": ids}


class ReindexResponse(BaseModel):
    message: str


@router.post(
    "/reindex",
    summary="Reindex item to pick up new season & episode releases.",
    description="Submits an item to be re-indexed through the indexer to manually fix shows that don't have release dates. Only works for movies and shows. Requires item id as a parameter.",
    operation_id="composite_reindexer",
)
async def reindex_item(
    request: Request,
    item_id: Optional[int] = None,
    tvdb_id: Optional[str] = None,
    tmdb_id: Optional[str] = None,
    imdb_id: Optional[str] = None,
) -> ReindexResponse:
    """Reindex item through Composite Indexer manually"""

    with db.Session() as session:
        # Load item using ORM based on provided ID
        item: MediaItem = None
        if item_id:
            item = session.get(MediaItem, item_id)
        elif tvdb_id:
            item = session.execute(
                select(MediaItem).where(MediaItem.tvdb_id == tvdb_id)
            ).scalar_one_or_none()
        elif tmdb_id:
            item = session.execute(
                select(MediaItem).where(MediaItem.tmdb_id == tmdb_id)
            ).scalar_one_or_none()
        elif imdb_id:
            item = session.execute(
                select(MediaItem).where(MediaItem.imdb_id == imdb_id)
            ).scalar_one_or_none()
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Item id or external id is required",
            )

        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
            )

        if item.type not in ("movie", "show"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Item must be a movie or show",
            )

        try:
            from program.services.indexers import IndexerService

            c_indexer = request.app.program.all_services[IndexerService]

            def mutation(i: MediaItem, s: Session):
                # Reset indexed_at to trigger reindexing
                i.indexed_at = None

                # Run the indexer within the session context
                reindexed_item = next(c_indexer.run(i, log_msg=True))

                if not reindexed_item:
                    raise ValueError(
                        "Failed to reindex item - no data returned from indexer"
                    )

                # Merge the reindexed item back into the session
                # Use no_autoflush to prevent SQLAlchemy from trying to flush
                # the new Season/Episode objects before the merge is complete
                with s.no_autoflush:
                    s.merge(reindexed_item)

            apply_item_mutation(
                request.app.program, session, item, mutation, bubble_parents=True
            )

            logger.info(f"Successfully reindexed {item.log_string}")
            request.app.program.em.add_event(Event("RetryItem", item.id))
            return ReindexResponse(message=f"Successfully reindexed {item.log_string}")
        except Exception as e:
            logger.error(f"Failed to reindex {item.log_string}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to reindex item: {str(e)}",
            )


class ItemAliasesResponse(BaseModel):
    aliases: dict[str, list[str]]


@router.get(
    "/{item_id}/aliases",
    summary="Get Media Item Aliases",
    description="Get aliases for a media item",
    operation_id="get_item_aliases",
)
async def get_item_aliases(
    _: Request, item_id: int, db: Session = Depends(get_db)
) -> ItemAliasesResponse:
    """Get aliases for a media item"""
    item: MediaItem = (
        db.execute(select(MediaItem).where(MediaItem.id == item_id))
        .unique()
        .scalar_one_or_none()
    )

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
        )

    aliases = item.aliases or {}
    return ItemAliasesResponse(aliases=aliases)
