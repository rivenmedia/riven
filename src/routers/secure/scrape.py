import asyncio
import concurrent.futures
import threading
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Annotated, Any, Literal, Self

from fastapi import (
    APIRouter,
    Body,
    HTTPException,
    Query,
)
from fastapi.responses import StreamingResponse
from kink import di
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, model_validator
from RTN import ParsedData
from sqlalchemy.orm import Session

from program.db import db_functions
from program.db.db import db_session
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.state import States
from program.program import Program
from program.services.downloaders.models import (
    DebridFile,
    TorrentContainer,
    TorrentInfo,
)
from program.services.downloaders.shared import parse_filename
from program.types import Event
from program.utils.request import CircuitBreakerOpen
from program.utils.torrent import extract_infohash

from ..models.shared import MessageResponse


class Stream(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    infohash: str
    raw_title: str
    parsed_title: str
    parsed_data: ParsedData
    rank: int
    lev_ratio: float
    is_cached: bool = False
    resolution: str | None = None


class ScrapeStreamEvent(BaseModel):
    """Event model for SSE streaming scrape results."""

    event: Literal["start", "progress", "streams", "complete", "error"]
    service: str | None = None
    message: str | None = None
    streams: dict[str, Stream] | None = None
    total_streams: int = 0
    services_completed: int = 0
    total_services: int = 0




class ManualScrapeReponse(MessageResponse):
    magnet: str
    torrent_info: TorrentInfo
    # We return raw dicts because frontend expects parsed structure not exactly DebridFile
    # Each file dict now includes 'parsed_metadata'
    parsed_files: list[dict[str, Any]] = Field(default_factory=list)

class ManualData(BaseModel):
    file_id: int
    filename: str
    filesize: int
    download_url: str | None = None

class ManualSelectFile(BaseModel):
    filename: str
    filesize: int
    download_url: str | None = None

class ManualDownloadRequest(BaseModel):
    magnet: str
    items: dict[int, ManualSelectFile] = Field(description="Map of file_id to file info")
    item_id: int | None = None
    # For creating new items when item_id is None
    tmdb_id: str | None = None
    tvdb_id: str | None = None
    imdb_id: str | None = None
    media_type: Literal["movie", "tv", "mediaitem"] | None = None
    max_bitrate_override: int | None = Field(default=None, description="Max bitrate override in Mbps")


class ManualDownloadResponse(MessageResponse):
    download_type: Literal["cached", "uncached"]

router = APIRouter(prefix="/scrape", tags=["scrape"])


async def resolve_torrent_container(
    infohash: str,
    services: list,
    item_type: str = "movie",
    runtime: int | None = None,
    max_bitrate_override: int | None = None,
) -> tuple["TorrentContainer | None", str | None]:
    """
    Resolve a magnet infohash to a TorrentContainer using available downloader services.
    
    First tries instant availability check on each service.
    Falls back to adding/probing the torrent temporarily if not cached.
    
    Returns:
        Tuple of (container, error_message). If container is None, error_message explains why.
    """
    from program.services.downloaders.models import TorrentContainer, DebridFile
    from program.services.downloaders.models import InvalidDebridFileException, BitrateLimitExceededException
    
    # Try to find cached container from any service
    container = None
    last_error = None
    for svc in services:
        try:
            container = await asyncio.to_thread(
                svc.get_instant_availability, infohash, item_type, runtime, max_bitrate_override
            )
            if container and container.files:
                return container, None
        except BitrateLimitExceededException as e:
            last_error = str(e)
            logger.debug(f"Bitrate limit exceeded on {svc.key}: {e}")
            continue
        except InvalidDebridFileException as e:
            last_error = str(e)
            logger.debug(f"Invalid file on {svc.key}: {e}")
            continue
        except Exception as e:
            last_error = f"Service error: {str(e)}"
            logger.debug(f"Error on {svc.key}: {e}")
            continue

    # Fallback: probe torrent by adding temporarily
    if not container or not container.files:
        svc = services[0]
        try:
            tid = await asyncio.to_thread(svc.add_torrent, infohash)
            try:
                info = await asyncio.to_thread(svc.get_torrent_info, tid)
                if info and info.files:
                    valid_files = []
                    for f in info.files.values():
                        try:
                            df = DebridFile.create(
                                path=f.path, filename=f.filename,
                                filesize_bytes=f.bytes, filetype="movie", file_id=f.id
                            )
                            valid_files.append(df)
                        except (InvalidDebridFileException, BitrateLimitExceededException) as e:
                            logger.debug(f"Skipping file {f.filename}: {e}")
                            continue
                    
                    if valid_files:
                        container = TorrentContainer(
                            infohash=infohash,
                            files=valid_files,
                            torrent_id=tid
                        )
                    else:
                        last_error = "No valid video files found (all files filtered by bitrate or type)"
            finally:
                await asyncio.to_thread(svc.delete_torrent, tid)
        except Exception as e:
            logger.error(f"Magnet resolution error: {e}")
            return None, f"Unable to resolve magnet: {str(e)}"
    
    if container and container.files:
        return container, None
    
    return None, last_error or "No files found in torrent"


def get_media_item(
    session: Session,
    item_id: int | None = None,
    tmdb_id: str | None = None,
    tvdb_id: str | None = None,
    imdb_id: str | None = None,
    media_type: str | None = None,
    persist: bool = True,
) -> MediaItem:
    """
    Get or create a MediaItem based on provided IDs.

    Tries to fetch authentication item by item_id, then by external IDs.
    If not found, tries to fetch from indexer and create/merge into DB.
    
    Args:
        persist: If True, new items are saved to DB. If False, returns in-memory item
                 without persisting (useful for read-only scrape queries).
    """
    item = None

    # 1. Try by internal ID
    if item_id:
        item = db_functions.get_item_by_id(item_id, session=session)
        if item:
            return item

    # 2. Try by external IDs
    try:
        item = db_functions.get_item_by_external_id(
            tmdb_id=tmdb_id,
            tvdb_id=tvdb_id,
            imdb_id=imdb_id,
            session=session,
        )
        if item:
            return item
    except ValueError:
        pass

    # 3. Try to fetch from Indexer
    if services := di[Program].services:
        indexer = services.indexer
    else:
        raise HTTPException(status_code=412, detail="Services not initialized")

    prepared_item = None
    if tmdb_id and media_type == "movie":
        prepared_item = MediaItem(
            {
                "tmdb_id": tmdb_id,
                "requested_by": "riven",
                "requested_at": datetime.now(),
            }
        )
    elif media_type == "tv" and (tvdb_id or tmdb_id):
        params = {
            "requested_by": "riven",
            "requested_at": datetime.now(),
        }
        if tvdb_id:
            params["tvdb_id"] = tvdb_id
        if tmdb_id:
            params["tmdb_id"] = tmdb_id
            
        prepared_item = MediaItem(params)
    elif imdb_id:
        prepared_item = MediaItem(
            {
                "imdb_id": imdb_id,
                "tvdb_id": tvdb_id,
                "requested_by": "riven",
                "requested_at": datetime.now(),
            }
        )

    if prepared_item:
        try:
            if result := next(indexer.run(prepared_item), None):
                if result.media_items:
                    indexed = result.media_items[0]

                    # Check directly if item exists in DB by external IDs to avoid unique constraint error
                    try:
                        existing = db_functions.get_item_by_external_id(
                            tmdb_id=indexed.tmdb_id,
                            tvdb_id=indexed.tvdb_id,
                            imdb_id=indexed.imdb_id,
                            session=session,
                        )
                        if existing:
                            return existing
                    except ValueError:
                        pass

                    # Only persist to DB if persist=True
                    if persist:
                        item = session.merge(indexed)
                        session.commit()
                        session.refresh(item)
                        return item
                    else:
                        # Return in-memory item without persisting
                        return indexed
        except Exception as e:
            from program.apis.tmdb_api import TMDBConnectionError
            from program.apis.tvdb_api import TVDBConnectionError

            if isinstance(e, TVDBConnectionError):
                raise HTTPException(
                    status_code=503,
                    detail=f"TVDB Service Unavailable: {str(e)}",
                ) from e
            if isinstance(e, TMDBConnectionError):
                raise HTTPException(
                    status_code=503,
                    detail=f"TMDB Service Unavailable: {str(e)}",
                ) from e
            raise

    raise HTTPException(status_code=404, detail="Item not found")


def setup_scrape_request(
    session: Any,
    item_id: int | None = None,
    tmdb_id: str | None = None,
    tvdb_id: str | None = None,
    imdb_id: str | None = None,
    media_type: Literal["movie", "tv"] | None = None,
    persist: bool = True,
) -> tuple[MediaItem, list[MediaItem]]:
    """Helper to retrieve item and scrape targets.
    
    Args:
        persist: If True, new items are saved to DB. If False, returns in-memory item
                 without persisting (useful for read-only scrape queries).
    """

    item = get_media_item(
        session,
        item_id=item_id,
        tmdb_id=tmdb_id,
        tvdb_id=tvdb_id,
        imdb_id=imdb_id,
        media_type=media_type,
        persist=persist,
    )

    targets = [item]

    if isinstance(item, Show):
        # Pre-load/assign parent to avoid lazy load in threads causing DetachedInstanceError
        for season in item.seasons:
            season.parent = item

        targets.extend(item.seasons)

    return item, targets


async def execute_scrape(
    item: MediaItem,
    scraper: Any,
    targets: list[MediaItem],
    ranking_overrides: dict[str, Any] | None = None,
    relaxed: bool = False,
) -> AsyncGenerator[ScrapeStreamEvent, None]:
    """
    Execute scrape for multiple targets in parallel and yield events.
    """
    num_scrapers = len(scraper.initialized_services)
    total_targets = len(targets)
    total_services = num_scrapers * total_targets

    all_streams: dict[str, Stream] = {}
    all_streams_lock = threading.Lock()
    services_completed = 0
    services_completed_lock = threading.Lock()

    # Send start event
    yield ScrapeStreamEvent(
        event="start",
        message=f"Starting scrape for {item.log_string}",
        total_services=total_services,
    )

    event_queue: asyncio.Queue[ScrapeStreamEvent | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def process_target(target: MediaItem):
        nonlocal services_completed
        target_name = getattr(target, "log_string", str(target))

        try:
            for service_name, parsed_streams in scraper.scrape_streaming(
                target, relaxed=relaxed, overrides=ranking_overrides
            ):
                current_streams: dict[str, Stream] = {}

                with all_streams_lock:
                    # Update global streams - use streams directly from scrape_streaming
                    for infohash, stream in parsed_streams.items():
                        if infohash not in all_streams:
                            all_streams[infohash] = stream
                            current_streams[infohash] = stream

                    total_count = len(all_streams)

                with services_completed_lock:
                    services_completed += 1
                    current_completed = services_completed

                # Create event
                if current_streams:
                    event = ScrapeStreamEvent(
                        event="streams",
                        service=service_name,
                        message=f"{service_name} found {len(current_streams)} new streams for {target_name}",
                        streams=current_streams,
                        total_streams=total_count,
                        services_completed=current_completed,
                        total_services=total_services,
                    )
                else:
                    event = ScrapeStreamEvent(
                        event="progress",
                        service=service_name,
                        message=f"{service_name} completed for {target_name}",
                        total_streams=total_count,
                        services_completed=current_completed,
                        total_services=total_services,
                    )

                asyncio.run_coroutine_threadsafe(event_queue.put(event), loop)

        except CircuitBreakerOpen:
            logger.debug(
                f"Circuit breaker OPEN during scrape of {target_name}, skipping remaining services"
            )
            error_event = ScrapeStreamEvent(
                event="progress",
                message=f"Circuit breaker OPEN for {target_name}, skipping remaining services",
                services_completed=services_completed,
                total_services=total_services,
                streams={},
                total_streams=0,
                service="circuit_breaker",
            )
            asyncio.run_coroutine_threadsafe(event_queue.put(error_event), loop)

        except Exception as e:
            logger.error(f"Error scraping {target_name}: {e}")
            error_event = ScrapeStreamEvent(
                event="error",
                message=f"Error scraping {target_name}: {str(e)}",
                services_completed=services_completed,
                total_services=total_services,
            )
            asyncio.run_coroutine_threadsafe(event_queue.put(error_event), loop)

    def run_all_targets():
        # Limit concurrency for targets to avoid exploding threads (max 10 targets in parallel)
        max_workers = min(len(targets), 10)
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="ScrapeTarget_"
        ) as executor:
            futures = [executor.submit(process_target, target) for target in targets]
            concurrent.futures.wait(futures)

        # Signal completion
        asyncio.run_coroutine_threadsafe(event_queue.put(None), loop)

    # Start scraping in background thread
    wrapper_executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="ScrapeCoordinator_"
    )
    wrapper_executor.submit(run_all_targets)

    try:
        while True:
            try:
                event = await asyncio.wait_for(event_queue.get(), timeout=30.0)
                if event is None:
                    break
                yield event
            except asyncio.TimeoutError:
                pass
    finally:
        wrapper_executor.shutdown(wait=False)

    # Send final complete event
    yield ScrapeStreamEvent(
        event="complete",
        message=f"Scraping complete. Found {len(all_streams)} total streams.",
        streams=all_streams,
        total_streams=len(all_streams),
        services_completed=services_completed,
        total_services=total_services,
    )


def apply_custom_scrape_params(
    session: Session,
    item: MediaItem,
    custom_title: str | None,
    custom_imdb_id: str | None,
) -> None:
    """
    Apply custom scrape parameters to the item by detaching it from the session
    and modifying it in-memory. This prevents changes from being committed to the DB.
    """
    if not (custom_title or custom_imdb_id):
        return

    # 1. Expunge children if it's a Show
    if isinstance(item, Show):
        for s in item.seasons:
            for e in s.episodes:
                try:
                    session.expunge(e)
                except InvalidRequestError:
                    pass
            try:
                session.expunge(s)
            except InvalidRequestError:
                pass

    # 2. Expunge parents/grandparents if it's Season/Episode
    target_item = item
    if isinstance(item, Season):
        if item.parent:
            try:
                session.expunge(item.parent)
            except InvalidRequestError:
                pass
            target_item = item.parent
    elif isinstance(item, Episode):
        if item.parent and item.parent.parent:
            try:
                session.expunge(item.parent)
                session.expunge(item.parent.parent)
            except InvalidRequestError:
                pass
            target_item = item.parent.parent

    # 3. Expunge the item itself
    try:
        session.expunge(item)
    except InvalidRequestError:
        pass

    # 4. Apply changes
    if custom_title:
        target_item.title = custom_title
    if custom_imdb_id:
        target_item.imdb_id = custom_imdb_id




@router.get(
    "/scrape_stream",
    summary="Stream scraping results via SSE",
    operation_id="scrape_item_stream",
)
async def scrape_item_stream(
    item_id: Annotated[
        int | None,
        Query(description="The ID of the media item"),
    ] = None,
    tmdb_id: Annotated[
        str | None,
        Query(description="The TMDB ID of the media item"),
    ] = None,
    tvdb_id: Annotated[
        str | None,
        Query(description="The TVDB ID of the media item"),
    ] = None,
    imdb_id: Annotated[
        str | None,
        Query(description="The IMDB ID of the media item"),
    ] = None,
    media_type: Annotated[
        Literal["movie", "tv"] | None,
        Query(description="The media type"),
    ] = None,
    custom_title: Annotated[
        str | None,
        Query(description="Custom title to use for scraping"),
    ] = None,
    custom_imdb_id: Annotated[
        str | None,
        Query(description="Custom IMDB ID to use for scraping"),
    ] = None,
    ranking_overrides: Annotated[
        str | None,
        Query(description="JSON string of ranking overrides"),
    ] = None,
) -> StreamingResponse:
    """Stream scraping results via SSE."""

    if services := di[Program].services:
        scraper = services.scraping
    else:
        raise HTTPException(status_code=412, detail="Scraping services not initialized")

    async def sse_generator():
        with db_session() as session:
            item, targets = setup_scrape_request(
                session, item_id, tmdb_id, tvdb_id, imdb_id, media_type, persist=False
            )

            overrides: dict[str, Any] | None = None
            if ranking_overrides:
                try:
                    import json
                    overrides = json.loads(ranking_overrides)
                except Exception as e:
                    logger.error(f"Failed to parse ranking_overrides: {e}")

            apply_custom_scrape_params(session, item, custom_title, custom_imdb_id)

            async for event in execute_scrape(
                item, scraper, targets, ranking_overrides=overrides, relaxed=True
            ):
                yield f"data: {event.model_dump_json()}\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )





class AutoScrapeRequestPayload(BaseModel):
    item_id: Annotated[
        int | None,
        Field(
            default=None,
            description="The ID of the media item",
        ),
    ] = None

    max_bitrate_override: Annotated[
        int | None,
        Field(
            default=None,
            description="Override max bitrate in Mbps for this scrape",
        ),
    ] = None
    tmdb_id: Annotated[
        str | None,
        Field(
            default=None,
            description="The TMDB ID of the media item",
        ),
    ] = None
    tvdb_id: Annotated[
        str | None,
        Field(
            default=None,
            description="The TVDB ID of the media item",
        ),
    ] = None
    imdb_id: Annotated[
        str | None,
        Field(
            default=None,
            description="The IMDB ID of the media item",
        ),
    ] = None
    media_type: Annotated[
        Literal["movie", "tv"] | None,
        Field(
            default=None,
            description="The media type",
        ),
    ] = None
    ranking_overrides: Annotated[
        dict[str, Any] | None,
        Field(description="Ranking overrides for the media item"),
    ] = None

    @model_validator(mode="after")
    def check_at_least_one_id_provided(self) -> Self:
        if not any([self.item_id, self.tvdb_id, self.tmdb_id, self.imdb_id]):
            raise ValueError("At least one ID must be provided")

        return self


class SeasonScrapeRequest(BaseModel):
    tmdb_id: str | None = None
    tvdb_id: str | None = None
    imdb_id: str | None = None
    season_numbers: list[int]
    ranking_overrides: dict[str, Any] | None = None


async def perform_season_scrape(
    tmdb_id: str | None = None,
    tvdb_id: str | None = None,
    imdb_id: str | None = None,
    season_numbers: list[int] | None = None,
    ranking_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Helper to scrape specific seasons of a show.
    Used by both the /seasons endpoint and webhooks.
    """
    if season_numbers is None:
        season_numbers = []

    if not any([tmdb_id, tvdb_id, imdb_id]):
        logger.error("perform_season_scrape called without any IDs")
        return {}

    with db_session() as session:
        # Get or create the show
        try:
            item = get_media_item(
                session,
                tmdb_id=tmdb_id,
                tvdb_id=tvdb_id,
                imdb_id=imdb_id,
                media_type="tv",
                persist=True
            )
        except Exception as e:
            logger.error(f"Error resolving show: {e}")
            return {}

        if not isinstance(item, Show):
             logger.error(f"Item {item.log_string} is not a TV Show")
             return {}

        # Delegate logic to the model method to ensure consistency with standard state machine
        try:
            item.update_season_states(season_numbers)
        except Exception as e:
            logger.error(f"Failed to update season states for {item.log_string}: {e}")
            return {}

        session.commit()
        
        return {"triggered": season_numbers}


@router.post(
    "/seasons",
    summary="Scrape specific seasons",
    operation_id="scrape_seasons",
    response_model=MessageResponse,
)
async def scrape_seasons(
    payload: SeasonScrapeRequest,
) -> MessageResponse:
    """
    Scrape specific seasons of a show.
    """
    result = await perform_season_scrape(
        tmdb_id=payload.tmdb_id,
        tvdb_id=payload.tvdb_id,
        imdb_id=payload.imdb_id,
        season_numbers=payload.season_numbers,
        ranking_overrides=payload.ranking_overrides,
    )
    
    return MessageResponse(
        message=f"Triggered scrape for seasons: {result.get('triggered', [])}"
    )


@router.post(
    "/start_session",
    summary="Preview a manual scraping magnet",
    operation_id="start_manual_session",
    response_model=ManualScrapeReponse,
)
async def start_manual_session(
    magnet: str,
    max_bitrate_override: int | None = None,
    item_id: int | None = None,
    tmdb_id: str | None = None,
    tvdb_id: str | None = None,
    imdb_id: str | None = None,
    media_type: Literal["movie", "tv"] | None = None,
) -> ManualScrapeReponse:
    """
    Stateless preview of a magnet link.
    Returns torrent info and files without creating a server-side session.
    """
    infohash = extract_infohash(magnet)
    if not infohash:
        raise HTTPException(status_code=400, detail="Invalid magnet link")

    services = di[Program].services.downloader.initialized_services
    if not services:
        raise HTTPException(status_code=500, detail="No downloader services enabled")

    runtime = None
    with db_session() as session:
        if item := get_media_item(
            session,
            item_id=item_id,
            tmdb_id=tmdb_id,
            tvdb_id=tvdb_id,
            imdb_id=imdb_id,
            media_type=media_type,
        ):
            runtime = item.runtime

    # Resolve torrent container using shared helper
    item_type = item.type if item else "movie"
    container, error_msg = await resolve_torrent_container(
        infohash, services, item_type, runtime, max_bitrate_override
    )

    if not container or not container.files:
        raise HTTPException(status_code=404, detail=error_msg or "No files found in torrent")

    # Build response with parsed metadata
    parsed_files = [
        {
            "file_id": f.file_id,
            "filename": f.filename,
            "filesize": f.filesize,
            "parsed_metadata": parse_filename(f.filename).model_dump() if f.filename else None
        }
        for f in container.files
    ]

    return ManualScrapeReponse(
        message="Magnet resolved",
        magnet=magnet,
        torrent_info=TorrentInfo(
            id=container.torrent_id or infohash,
            infohash=infohash,
            name="Torrent",
            bytes=sum(f["filesize"] for f in parsed_files),
            original_title="Torrent"
        ),
        parsed_files=parsed_files
    )



def _create_stream_from_manual_selection(infohash: str, items: dict) -> "Stream":
    """Helper to create a Stream object from manually selected files."""
    from RTN import Torrent
    from program.services.downloaders.shared import parse_filename
    from program.media.stream import Stream

    files_list = list(items.values())
    main_file = max(files_list, key=lambda x: x.filesize) if files_list else None
    
    if not main_file:
            raise HTTPException(status_code=400, detail="No files selected")

    parsed_data = parse_filename(main_file.filename)
    
    torrent = Torrent(
        raw_title=main_file.filename,
        infohash=infohash,
        data=parsed_data,
        rank=0, 
        lev_ratio=1.0
    )

    return Stream(torrent)



@router.post(
    "/select_files",
    summary="Start download for manual scrape",
    operation_id="manual_select_files",
    response_model=ManualDownloadResponse,
)
async def manual_select_files(
    payload: ManualDownloadRequest,
) -> ManualDownloadResponse:
    """
    Stateless download start.
    Adds the magnet and selects the specified files using the best available service.
    """

    infohash = extract_infohash(payload.magnet)
    if not infohash:
        raise HTTPException(status_code=400, detail="Invalid magnet link")

    services = di[Program].services.downloader.initialized_services
    if not services:
        raise HTTPException(status_code=500, detail="No services available")

    # Use first available service
    svc = services[0]

    # State Machine Logic - handle both existing items and new items
    if payload.item_id or payload.tmdb_id or payload.tvdb_id or payload.imdb_id:
        with db_session() as session:
            from program.media.item import Movie, Show
            
            item = None
            
            # 1. Try to find or create item using standardized helper
            item = get_media_item(
                session,
                item_id=payload.item_id,
                tmdb_id=payload.tmdb_id,
                tvdb_id=payload.tvdb_id,
                imdb_id=payload.imdb_id,
                media_type=payload.media_type,
                persist=True
            )

            # 1. Parse Metadata for Stream and create object
            item_files = payload.items if payload.items else {}
            stream = _create_stream_from_manual_selection(infohash, item_files)
            
            try:
                # 3. Invoke Downloader Service
                downloader_svc = di[Program].services.downloader
                
                file_ids = list(payload.items.keys()) if payload.items else []
                
                # Start Manual Download (handles download initiation and attribute updates)
                success = await asyncio.to_thread(
                    downloader_svc.start_manual_download,
                    item,
                    stream,
                    svc,
                    file_ids,
                    payload.max_bitrate_override,
                )
                
                if success:
                     # For Shows, update season states based on selected files
                     if isinstance(item, Show):
                         try:
                             # Identify active seasons from selected files
                             active_seasons = set()
                             for f in payload.items.values():
                                 try:
                                     # We re-parse here as we need season info for all files, not just main
                                     p_data = parse_filename(f.filename)
                                     if p_data.seasons:
                                         active_seasons.update(p_data.seasons)
                                 except Exception:
                                     continue
                             
                             if active_seasons:
                                 logger.info(f"Manual scrape active seasons for {item.log_string}: {active_seasons}")
                                 item.update_season_states(list(active_seasons), emit_scraping_event=False)
                         except Exception as e:
                             logger.error(f"Failed to update season states for {item.log_string}: {e}")

                     session.commit()
                     # Emit event to trigger standard state machine (symlinker → updater)
                     di[Program].em.add_event(Event("Scraping", item_id=item.id))
                     return ManualDownloadResponse(message="Download started via standard pipeline", download_type="cached")
                else:
                     raise HTTPException(status_code=500, detail="Failed to start manual download")

            except Exception as e:
                logger.error(f"Failed to start standard download: {e}")
                raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/overseerr/requests",
    summary="Fetch Overseerr Requests",
    operation_id="fetch_overseerr_requests",
    response_model=MessageResponse,
)
async def overseerr_requests(
    filter: Annotated[
        Literal[
            "all",
            "approved",
            "available",
            "pending",
            "processing",
            "unavailable",
            "failed",
            "deleted",
            "completed",
        ]
        | None,
        Query(description="Filter for Overseerr requests"),
    ] = None,
    take: Annotated[
        int,
        Query(description="Number of requests to fetch"),
    ] = 100000,
) -> MessageResponse:
    """Get all overseerr requests and make sure they exist in the database"""

    from kink import di

    from program.db.db_functions import item_exists_by_any_id

    if services := di[Program].services:
        if not services.overseerr.enabled:
            raise HTTPException(
                status_code=412,
                detail="Overseerr service not enabled",
            )

        overseerr_api = services.overseerr.api
    else:
        raise HTTPException(
            status_code=412,
            detail="Overseerr service not initialized",
        )

    overseerr_media_requests = overseerr_api.get_media_requests(
        "overseerr",
        filter,
        take,
    )

    if not overseerr_media_requests:
        return MessageResponse(message="No new overseerr requests to process")

    with db_session() as session:
        overseerr_items = [
            item
            for item in overseerr_media_requests
            if not item_exists_by_any_id(
                tvdb_id=item.tvdb_id,
                tmdb_id=item.tmdb_id,
                session=session,
            )
        ]

        logger.info(f"Found {len(overseerr_items)} new overseerr requests")

        if overseerr_items:
            # Persist first, then enqueue
            persisted_items: list[MediaItem] = []

            for item in overseerr_items:
                persisted = session.merge(item)
                persisted_items.append(persisted)

            session.commit()

            from program.services.content.overseerr import Overseerr

            for persisted in persisted_items:
                di[Program].em.add_item(persisted, service=Overseerr.__class__.__name__)

            return MessageResponse(
                message=f"Submitted {len(overseerr_items)} overseerr requests to the queue"
            )

    return MessageResponse(message="No new overseerr requests to process")


@router.post(
    "/auto",
    summary="Auto scrape an item with resolution overrides",
    operation_id="auto_scrape_item",
    response_model=MessageResponse,
)
async def auto_scrape_item(
    body: Annotated[AutoScrapeRequestPayload, Body()],
) -> MessageResponse:
    """
    Auto scrape an item with specific resolution overrides.
    This performs a one-time scrape using the provided resolutions
    and triggers the downloader if new streams are found.
    """

    if services := di[Program].services:
        scraper = services.scraping
    else:
        raise HTTPException(status_code=412, detail="Services not initialized")

    item = None

    with db_session() as session:
        item = get_media_item(
            session,
            item_id=body.item_id,
            tmdb_id=body.tmdb_id,
            tvdb_id=body.tvdb_id,
            imdb_id=body.imdb_id,
            media_type=body.media_type,
        )

        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        if body.ranking_overrides:
            overrides_dict = {k: v for k, v in body.ranking_overrides.items() if v is not None}

        logger.info(f"Triggering auto scrape for {item.log_string}")

        # We consume the generator to ensure it runs
        # Scraping.run will update the item object with new streams and state
        list(scraper.run(item, overrides=overrides_dict, max_bitrate_override=body.max_bitrate_override))

        session.commit()

        # Check if any new streams were added (item state would be 'Scraped' if successful)
        if item.last_state == States.Scraped:
            # Emit event to trigger downloader
            di[Program].em.add_event(Event("Scraping", item_id=item.id))
            return MessageResponse(
                message=f"Auto scrape completed. New streams found for {item.log_string}."
            )

        return MessageResponse(
            message=f"Auto scrape completed for {item.log_string}. No new streams added."
        )


@router.get("/ping")
def ping():
    return {"pong": True}
