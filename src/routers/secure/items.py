import os

from collections.abc import Callable, Sequence
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal, Self
from fastapi import APIRouter, Body, HTTPException, Path, status, Query
from kink import di
from loguru import logger
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, object_session

from program.db import db_functions
from program.db.db import db_session
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.state import States
from program.types import Event
from program.program import Program
from program.media.models import MediaMetadata

from ..models.shared import IdListPayload, MessageResponse


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


def handle_ids(ids: Sequence[str | int]) -> list[int]:
    try:
        id_list = [int(id) for id in ids]

        if not id_list:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No item ID provided",
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
    program: Program,
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
        if isinstance(item, Episode):
            season = session.get(Season, item.parent_id)

            if season:
                MediaItem.store_state(season)
                show = session.get(Show, season.parent_id)

                if show:
                    MediaItem.store_state(show)
        elif isinstance(item, Season):
            show = session.get(Show, item.parent_id)

            if show:
                MediaItem.store_state(show)
    except Exception as e:
        logger.warning(f"Failed to update parent state(s) for item {item.id}: {e}")


class StateResponse(BaseModel):
    success: Annotated[
        bool,
        Field(description="Boolean signifying whether the request was successful"),
    ]
    states: Annotated[
        list[str],
        Field(description="The list of states"),
    ]


@router.get(
    "/states",
    operation_id="get_states",
    response_model=StateResponse,
)
async def get_states() -> StateResponse:
    return StateResponse(states=[state._name_ for state in States], success=True)


class ItemsResponse(BaseModel):
    success: Annotated[
        bool,
        Field(description="Boolean signifying whether the request was successful"),
    ]
    items: Annotated[
        list[dict[str, Any]],
        Field(description="The list of media items"),
    ]
    page: Annotated[
        int,
        Field(description="Current page number"),
    ]
    limit: Annotated[
        int,
        Field(description="Number of items per page"),
    ]
    total_items: Annotated[
        int,
        Field(description="Total number of items"),
    ]
    total_pages: Annotated[
        int,
        Field(description="Total number of pages"),
    ]


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
    limit: Annotated[
        int,
        Query(
            description="Number of items per page",
            ge=1,
        ),
    ] = 50,
    page: Annotated[
        int,
        Query(
            description="Page number",
            ge=1,
        ),
    ] = 1,
    type: Annotated[
        list[MediaTypeEnum] | None,
        Query(description="Filter by media type(s)"),
    ] = None,
    states: Annotated[
        list[States | StatesFilter] | None,
        Query(description="Filter by state(s)"),
    ] = None,
    sort: Annotated[
        list[SortOrderEnum] | None,
        Query(
            description="Sort order(s). Multiple sorts allowed but only one per type (title or date)"
        ),
    ] = None,
    search: Annotated[
        str | None,
        Query(
            description="Search by title or IMDB/TVDB/TMDB ID",
            min_length=1,
        ),
    ] = None,
    extended: Annotated[
        bool,
        Query(description="Include extended item details"),
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
        media_types = {t.value for t in type}

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

    # Validation moved, sorting logic delayed
    if sort:
        # Verify we don't have multiple sorts of the same type
        sort_types = set[str]()

        for sort_criterion in sort:
            sort_type = sort_criterion.sort_type

            if sort_type in sort_types:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Multiple {sort_type} sort criteria provided. Only one sort per type is allowed.",
                )

            sort_types.add(sort_type)

    with db_session() as session:
        total_items = session.execute(
            select(func.count()).select_from(query.subquery())
        ).scalar_one()

        if count_only:
            items = []
        else:
            if sort:
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

    with db_session() as session:
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


class AddMediaItemPayload(BaseModel):
    tmdb_ids: Annotated[
        list[str] | None,
        Field(
            default=None,
            description="Comma-separated list of TMDB IDs",
        ),
    ]
    tvdb_ids: Annotated[
        list[str] | None,
        Field(
            default=None,
            description="Comma-separated list of TVDB IDs",
        ),
    ]
    media_type: Annotated[
        Literal["movie", "tv"],
        Field(description="Media type"),
    ]


@router.post(
    "/add",
    summary="Add Media Items",
    description="""
        Add media items with bases on TMDB ID or TVDB ID,
        you can add multiple IDs by comma separating them.
    """,
    operation_id="add_items",
    response_model=MessageResponse,
)
async def add_items(
    payload: Annotated[
        AddMediaItemPayload,
        Body(description="Add media items payload"),
    ],
) -> MessageResponse:
    if not payload.tmdb_ids and not payload.tvdb_ids:
        raise HTTPException(status_code=400, detail="No ID(s) provided")

    all_tmdb_ids = (
        [id.strip() for id in payload.tmdb_ids if id]
        if payload.tmdb_ids and payload.media_type == "movie"
        else None
    )

    all_tvdb_ids = (
        [id.strip() for id in payload.tvdb_ids if id]
        if payload.tvdb_ids and payload.media_type == "tv"
        else None
    )

    added_count = 0
    items = list[MediaItem]()

    with db_session() as session:
        if all_tmdb_ids:
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

        if all_tvdb_ids:
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
                di[Program].em.add_item(item)
                added_count += 1

    return MessageResponse(message=f"Added {added_count} item(s) to the queue")


@router.get(
    "/{id}",
    summary="Get Media Item by ID",
    description="Fetch a single media item by item ID",
    operation_id="get_item",
)
async def get_item(
    id: Annotated[
        str,
        Path(
            description="""
                The ID of the media item. For 'item' type, use the numeric item ID;
                for 'movie' or 'tv' types, use the TMDB or TVDB ID respectively.
            """,
        ),
    ],
    media_type: Annotated[
        Literal["movie", "tv", "item"],
        Query(description="The type of media item"),
    ],
    extended: Annotated[
        bool,
        Query(description="Whether to include extended information"),
    ] = False,
) -> dict[str, Any]:
    if not id:
        raise HTTPException(status_code=400, detail="No ID or media type provided")

    with db_session() as session:
        match media_type:
            case "movie":
                # needs to be a string
                query = select(MediaItem).where(
                    MediaItem.tmdb_id == id,
                )
            case "tv":
                # needs to be a string
                query = select(MediaItem).where(
                    MediaItem.tvdb_id == id,
                )
            case "item":
                # needs to be an integer
                _id = int(id)
                query = select(MediaItem).where(
                    MediaItem.id == _id,
                )

        try:
            item = session.execute(query).unique().scalar_one_or_none()

            if not item:
                raise HTTPException(status_code=404, detail="Item not found")

            if extended:
                return item.to_extended_dict()

            return item.to_dict()
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


class ResetResponse(MessageResponse):
    ids: list[int]


@router.post(
    "/reset",
    summary="Reset Media Items",
    description="Reset media items with bases on item IDs",
    operation_id="reset_items",
    response_model=ResetResponse,
)
async def reset_items(
    payload: Annotated[
        IdListPayload,
        Body(description="Reset items payload"),
    ],
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

    parsed_ids = handle_ids(payload.ids)

    services = di[Program].services

    assert services, "Program services not initialized"

    # Get updater service for media server refresh
    updater = services.updater

    try:
        # Load items using ORM
        with db_session() as session:
            items = (
                session.execute(select(MediaItem).where(MediaItem.id.in_(parsed_ids)))
                .scalars()
                .all()
            )

            for media_item in items:
                try:
                    # Gather all refresh paths before reset (entry may appear at multiple VFS paths)
                    refresh_paths = list[str]()

                    media_entry = media_item.media_entry

                    if updater and media_entry:
                        vfs_paths = media_entry.get_all_vfs_paths()

                        for vfs_path in vfs_paths:
                            abs_path = os.path.join(
                                updater.library_path, vfs_path.lstrip("/")
                            )

                            if isinstance(media_item, Movie):
                                refresh_path = os.path.dirname(
                                    os.path.dirname(abs_path)
                                )
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
                        di[Program],
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
                    logger.error(
                        f"Failed to reset item with id {media_item.id}: {str(e)}"
                    )
                    continue
                except Exception as e:
                    logger.error(
                        f"Unexpected error while resetting item with id {media_item.id}: {str(e)}"
                    )
                    continue
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return ResetResponse(
        message=f"Reset items with id {parsed_ids}",
        ids=parsed_ids,
    )


class RetryResponse(MessageResponse):
    ids: Annotated[
        Sequence[int],
        Field(description="The IDs to retry", min_length=1),
    ]


@router.post(
    "/retry",
    summary="Retry Media Items",
    description="Retry media items with bases on item IDs",
    operation_id="retry_items",
    response_model=RetryResponse,
)
async def retry_items(
    payload: Annotated[
        IdListPayload,
        Body(description="Retry items payload"),
    ],
) -> RetryResponse:
    """Re-add items to the queue"""

    parsed_ids = handle_ids(payload.ids)

    with db_session() as session:
        for id in parsed_ids:
            try:
                # Load item using ORM
                item = session.get(MediaItem, id)

                if item:

                    def mutation(i: MediaItem, s: Session):
                        i.scraped_at = None
                        i.scraped_times = 1

                    apply_item_mutation(
                        program=di[Program],
                        session=session,
                        item=item,
                        mutation_fn=mutation,
                        bubble_parents=True,
                    )

                    session.commit()

                    di[Program].em.add_event(Event("RetryItem", id))
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
                )

    return RetryResponse(
        message=f"Retried items with ids {parsed_ids}",
        ids=parsed_ids,
    )


@router.post(
    "/retry_library",
    summary="Retry Library Items",
    description="Retry items in the library that failed to download",
    operation_id="retry_library_items",
    response_model=RetryResponse,
)
async def retry_library_items() -> RetryResponse:
    item_ids = db_functions.retry_library()

    for item_id in item_ids:
        di[Program].em.add_event(
            Event(
                emitted_by="RetryLibrary",
                item_id=item_id,
            )
        )

    return RetryResponse(
        message=f"Retried {len(item_ids)} items",
        ids=item_ids,
    )


class RemoveResponse(BaseModel):
    message: str
    ids: Annotated[
        list[int],
        Field(description="The IDs to remove"),
    ]


@router.delete(
    "/remove",
    summary="Remove Media Items",
    description="Remove media items based on item IDs",
    operation_id="remove_item",
    response_model=RemoveResponse,
)
async def remove_item(
    payload: Annotated[
        IdListPayload,
        Body(description="Remove items payload"),
    ],
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

    parsed_ids = handle_ids(payload.ids)

    if not parsed_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No IDs provided"
        )

    services = di[Program].services

    assert services, "Program services not initialized"

    # Get services
    overseerr = services.overseerr
    updater = services.updater
    removed_ids = list[int]()

    with db_session() as session:
        for item_id in parsed_ids:
            # Load item using ORM
            item = session.get(MediaItem, item_id)

            if not item:
                logger.warning(f"Item {item_id} not found, skipping")
                continue

            # Only allow movies and shows to be removed
            if not isinstance(item, (Movie, Show)):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Only movies and shows can be removed. Item {item_id} is a {item.type}",
                )

            logger.debug(f"Removing item with ID {item.id}")

            # 1. Cancel active jobs (EventManager cancels children too)
            di[Program].em.cancel_job(item.id)

            # 2. Gather all refresh paths before deletion (entry may appear at multiple VFS paths)
            refresh_paths = list[str]()

            if updater and item.filesystem_entry:
                if media_entry := item.media_entry:
                    for vfs_path in media_entry.get_all_vfs_paths():
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
                            abs_path = os.path.join(
                                updater.library_path, vfs_path.lstrip("/")
                            )

                        if isinstance(item, Movie):
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
                    overseerr.api.delete_request(item.overseerr_id)

                    logger.debug(
                        f"Deleted Overseerr request {item.overseerr_id} for {item.id}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to delete Overseerr request {item.overseerr_id}: {e}"
                    )

            # 4. Remove from VFS
            if services.filesystem.riven_vfs:
                services.filesystem.riven_vfs.remove(item)

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

    return RemoveResponse(
        message=f"Removed items with ids {removed_ids}",
        ids=removed_ids,
    )


class StreamsResponse(MessageResponse):
    streams: Annotated[
        list[dict[str, Any]],
        Field(description="The list of streams"),
    ]
    blacklisted_streams: Annotated[
        list[dict[str, Any]],
        Field(description="The list of blacklisted streams"),
    ]


@router.get(
    "/{item_id}/streams",
    summary="Get Media Item Streams",
    description="Get streams for a media item",
    operation_id="get_item_streams",
    response_model=StreamsResponse,
)
async def get_item_streams(
    item_id: Annotated[
        int,
        Path(description="The ID of the media item", ge=1),
    ],
) -> StreamsResponse:
    with db_session() as session:
        item = (
            session.execute(select(MediaItem).where(MediaItem.id == item_id))
            .unique()
            .scalar_one_or_none()
        )

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
        )

    return StreamsResponse(
        message=f"Retrieved streams for item {item_id}",
        streams=[stream.to_dict() for stream in item.streams],
        blacklisted_streams=[stream.to_dict() for stream in item.blacklisted_streams],
    )


@router.post(
    "/{item_id}/streams/{stream_id}/blacklist",
    summary="Blacklist Media Item Stream",
    description="Blacklist a stream for a media item",
    operation_id="blacklist_item_stream",
    response_model=MessageResponse,
)
async def blacklist_stream(
    item_id: Annotated[
        int,
        Path(
            description="The ID of the media item",
            ge=1,
        ),
    ],
    stream_id: Annotated[
        int,
        Path(
            description="The ID of the stream",
            ge=1,
        ),
    ],
) -> MessageResponse:
    with db_session() as session:
        item = (
            session.execute(select(MediaItem).where(MediaItem.id == item_id))
            .unique()
            .scalar_one_or_none()
        )

        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Item not found",
            )

        stream = next(
            (stream for stream in item.streams if stream.id == stream_id), None
        )

        if not stream:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Stream not found",
            )

        def mutation(i: MediaItem, s: Session):
            i.blacklist_stream(stream)

        apply_item_mutation(
            di[Program],
            session,
            item,
            mutation,
            bubble_parents=True,
        )

        session.commit()

        return MessageResponse(
            message=f"Blacklisted stream {stream_id} for item {item_id}",
        )


@router.post(
    "/{item_id}/streams/{stream_id}/unblacklist",
    summary="Unblacklist Media Item Stream",
    description="Unblacklist a stream for a media item",
    operation_id="unblacklist_item_stream",
    response_model=MessageResponse,
)
async def unblacklist_stream(
    item_id: Annotated[
        int,
        Path(
            description="The ID of the media item",
            ge=1,
        ),
    ],
    stream_id: Annotated[
        int,
        Path(
            description="The ID of the stream",
            ge=1,
        ),
    ],
) -> MessageResponse:
    with db_session() as db:
        item = (
            db.execute(select(MediaItem).where(MediaItem.id == item_id))
            .unique()
            .scalar_one_or_none()
        )

        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
            )

        stream = next(
            (stream for stream in item.blacklisted_streams if stream.id == stream_id),
            None,
        )

        if not stream:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Stream not found"
            )

        def mutation(i: MediaItem, s: Session):
            i.unblacklist_stream(stream)

        apply_item_mutation(di[Program], db, item, mutation, bubble_parents=True)

        db.commit()

        return MessageResponse(
            message=f"Unblacklisted stream {stream_id} for item {item_id}",
        )


@router.post(
    path="/{item_id}/streams/reset",
    summary="Reset Media Item Streams",
    description="Reset all streams for a media item",
    operation_id="reset_item_streams",
    response_model=MessageResponse,
)
async def reset_item_streams(
    item_id: Annotated[
        int,
        Path(
            description="The ID of the media item",
            ge=1,
        ),
    ],
) -> MessageResponse:
    with db_session() as session:
        item = (
            session.execute(select(MediaItem).where(MediaItem.id == item_id))
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
            i.active_stream = None

        apply_item_mutation(
            di[Program],
            session,
            item,
            mutation,
            bubble_parents=True,
        )

        session.commit()

        return MessageResponse(
            message=f"Successfully reset streams for item {item_id}",
        )


class PauseResponse(MessageResponse):
    ids: Annotated[
        list[int],
        Field(description="The IDs to pause", min_length=1),
    ]


@router.post(
    "/pause",
    summary="Pause Media Items",
    description="Pause media items based on item IDs",
    operation_id="pause_items",
    response_model=PauseResponse,
)
async def pause_items(
    payload: Annotated[
        IdListPayload,
        Body(description="Pause items payload"),
    ],
) -> PauseResponse:
    """Pause items and their children from being processed"""

    parsed_ids = handle_ids(payload.ids)

    try:
        with db_session() as session:
            # Load items using ORM
            items = (
                session.execute(select(MediaItem).where(MediaItem.id.in_(parsed_ids)))
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
                        di[Program].em.cancel_job(id)
                        di[Program].em.remove_id_from_queues(id)

                    if media_item.last_state not in [
                        States.Paused,
                        States.Failed,
                        States.Completed,
                    ]:

                        def mutation(i: MediaItem, s: Session):
                            i.store_state(States.Paused)

                        apply_item_mutation(
                            di[Program],
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

    return PauseResponse(
        message="Successfully paused items.",
        ids=parsed_ids,
    )


@router.post(
    "/unpause",
    summary="Unpause Media Items",
    description="Unpause media items based on item IDs",
    operation_id="unpause_items",
    response_model=PauseResponse,
)
async def unpause_items(
    payload: Annotated[
        IdListPayload,
        Body(description="Unpause items payload"),
    ],
) -> PauseResponse:
    """Unpause items and their children to resume processing"""

    parsed_ids = handle_ids(payload.ids)

    try:
        with db_session() as session:
            # Load items using ORM
            items = (
                session.execute(select(MediaItem).where(MediaItem.id.in_(parsed_ids)))
                .scalars()
                .all()
            )

            for media_item in items:
                try:
                    if media_item.last_state == States.Paused:

                        def mutation(i: MediaItem, s: Session):
                            i.store_state(States.Requested)

                        apply_item_mutation(
                            di[Program],
                            session,
                            media_item,
                            mutation,
                            bubble_parents=True,
                        )

                        session.commit()

                        di[Program].em.add_event(Event("RetryItem", media_item.id))

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

    return PauseResponse(
        message="Successfully unpaused items.",
        ids=parsed_ids,
    )


class ReindexPayload(BaseModel):
    item_id: Annotated[
        int | None,
        Field(
            default=None,
            description="The ID of the media item",
        ),
    ]
    tvdb_id: Annotated[
        str | None,
        Field(
            default=None,
            description="The TVDB ID of the media item",
        ),
    ]
    tmdb_id: Annotated[
        str | None,
        Field(
            default=None,
            description="The TMDB ID of the media item",
        ),
    ]
    imdb_id: Annotated[
        str | None,
        Field(
            default=None,
            description="The IMDB ID of the media item",
        ),
    ]

    @model_validator(mode="after")
    def check_at_least_one_id_provided(self) -> Self:
        if not any([self.item_id, self.tvdb_id, self.tmdb_id, self.imdb_id]):
            raise ValueError("At least one ID must be provided")

        return self


@router.post(
    path="/reindex",
    summary="Reindex item to pick up new season & episode releases.",
    description="""
        Submits an item to be re-indexed through the indexer to manually fix shows that don't have release dates.
        Only works for movies and shows. Requires item id as a parameter.
    """,
    operation_id="composite_reindexer",
    response_model=MessageResponse,
)
async def reindex_item(
    payload: Annotated[
        ReindexPayload,
        Body(description="Reindex item payload"),
    ],
) -> MessageResponse:
    """Reindex item through Composite Indexer manually"""

    with db_session() as session:
        # Load item using ORM based on provided ID
        item: MediaItem | None = None

        if payload.item_id:
            item = session.get(MediaItem, payload.item_id)
        elif payload.tvdb_id:
            item = session.execute(
                select(MediaItem).where(MediaItem.tvdb_id == payload.tvdb_id)
            ).scalar_one_or_none()
        elif payload.tmdb_id:
            item = session.execute(
                select(MediaItem).where(MediaItem.tmdb_id == payload.tmdb_id)
            ).scalar_one_or_none()
        elif payload.imdb_id:
            item = session.execute(
                select(MediaItem).where(MediaItem.imdb_id == payload.imdb_id)
            ).scalar_one_or_none()

        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
            )

        if not isinstance(item, Movie | Show):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Item must be a movie or show",
            )

        try:
            services = di[Program].services

            assert services, "Services not initialized"

            indexer_service = services.indexer

            def mutation(i: MediaItem, s: Session):
                # Reset indexed_at to trigger reindexing
                i.indexed_at = None

                # Run the indexer within the session context
                runner_result = next(indexer_service.run(i, log_msg=True))

                if not runner_result.media_items:
                    raise ValueError(
                        "Failed to reindex item - no data returned from indexer"
                    )

                # Merge the reindexed item back into the session
                # Use no_autoflush to prevent SQLAlchemy from trying to flush
                # the new Season/Episode objects before the merge is complete
                with s.no_autoflush:
                    s.merge(runner_result.media_items[0])

            apply_item_mutation(
                program=di[Program],
                session=session,
                item=item,
                mutation_fn=mutation,
                bubble_parents=True,
            )

            logger.info(f"Successfully re-indexed {item.log_string}")

            di[Program].em.add_event(Event("RetryItem", item.id))

            return MessageResponse(message=f"Successfully re-indexed {item.log_string}")
        except Exception as e:
            logger.error(f"Failed to re-index {item.log_string}: {str(e)}")

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to re-index item: {str(e)}",
            )


class ItemAliasesResponse(BaseModel):
    aliases: Annotated[
        dict[str, list[str]] | None,
        Field(description="The item aliases"),
    ]


@router.get(
    "/{item_id}/aliases",
    summary="Get Media Item Aliases",
    description="Get aliases for a media item",
    operation_id="get_item_aliases",
    response_model=ItemAliasesResponse,
)
async def get_item_aliases(
    item_id: Annotated[
        int,
        Path(
            description="The ID of the media item",
            ge=1,
        ),
    ],
) -> ItemAliasesResponse:
    """Get aliases for a media item"""

    with db_session() as session:
        item = (
            session.execute(select(MediaItem).where(MediaItem.id == item_id))
            .unique()
            .scalar_one_or_none()
        )

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
        )

    return ItemAliasesResponse(aliases=item.aliases)


@router.get(
    "/{item_id}/metadata",
    summary="Get Media Item Metadata",
    description="Get metadata for a media item using item ID",
    operation_id="get_item_metadata",
    response_model=MediaMetadata,
)
async def get_item_metadata(
    item_id: Annotated[
        int,
        Path(
            description="The ID of the media item",
            ge=1,
        ),
    ],
) -> MediaMetadata:
    """Get all metadata for a media item using item ID"""

    with db_session() as session:
        item = (
            session.execute(select(MediaItem).where(MediaItem.id == item_id))
            .unique()
            .scalar_one_or_none()
        )

        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
            )

        media_entry = item.media_entry

        if not media_entry or not media_entry.media_metadata:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No metadata available for this item",
            )

        return media_entry.media_metadata
