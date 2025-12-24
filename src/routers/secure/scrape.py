import asyncio
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
import concurrent.futures
import threading
from typing import Annotated, Any, Literal, Self
from uuid import uuid4

from RTN import ParsedData, Torrent
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    HTTPException,
    Path,
    Query,
)
from fastapi.responses import StreamingResponse
from kink import di
from loguru import logger
from PTT import parse_title  # pyright: ignore[reportUnknownVariableType]
from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator
from sqlalchemy.orm import object_session, Session
from sqlalchemy.exc import InvalidRequestError

from program.db import db_functions
from program.db.db import db_session
from program.media.item import Episode, MediaItem, Season, Show
from program.media.stream import Stream as ItemStream
from program.services.downloaders import Downloader
from program.services.downloaders.models import (
    DebridFile,
    TorrentContainer,
    TorrentInfo,
    FilesizeLimitExceededException,
)
from program.services.downloaders.shared import (
    DownloaderBase,
    parse_filename,
    resolve_download_url,
)
from program.services.scrapers.shared import rtn
from program.types import Event
from program.utils.torrent import extract_infohash
from program.program import Program
from program.media.models import ActiveStream
from program.media.state import States
from program.services.scrapers.models import RankingOverrides
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


class ScrapeItemResponse(MessageResponse):
    streams: dict[str, Stream]


class StartSessionResponse(MessageResponse):
    session_id: str
    torrent_id: str | int
    torrent_info: TorrentInfo
    containers: TorrentContainer | None
    expires_at: str


class SelectFilesResponse(MessageResponse):
    download_type: Literal["cached", "uncached"]


class Container(RootModel[dict[str, DebridFile]]):
    """
    Root model for container mapping file IDs to file information.

    Example:
    {
        "4": {
            "filename": "show.s01e01.mkv",
            "filesize": 30791392598
        },
        "5": {
            "filename": "show.s01e02.mkv",
            "filesize": 25573181861
        }
    }
    """

    root: dict[str, DebridFile]


class ShowFileData(RootModel[dict[int, dict[int, DebridFile]]]):
    """
    Root model for show file data that maps seasons to episodes to file data.

    Example:
    {
        1: {  # Season 1
            1: {"filename": "path/to/s01e01.mkv"},  # Episode 1
            2: {"filename": "path/to/s01e02.mkv"}   # Episode 2
        },
        2: {  # Season 2
            1: {"filename": "path/to/s02e01.mkv"}   # Episode 1
        }
    }
    """

    root: dict[int, dict[int, DebridFile]]


class ScrapingSession:
    def __init__(
        self,
        id: str,
        item_id: int,
        media_type: Literal["movie", "tv"] | None = None,
        imdb_id: str | None = None,
        tmdb_id: str | None = None,
        tvdb_id: str | None = None,
        magnet: str | None = None,
        service: DownloaderBase | None = None,
    ):
        self.id = id
        self.item_id = item_id
        self.media_type = media_type
        self.imdb_id = imdb_id
        self.tmdb_id = tmdb_id
        self.tvdb_id = tvdb_id
        self.magnet = magnet
        self.service = service
        self.torrent_id: int | str | None = None
        self.torrent_info: TorrentInfo | None = None
        self.containers: TorrentContainer | None = None
        self.selected_files: dict[str, dict[str, str | int]] | None = None
        self.created_at: datetime = datetime.now()
        self.expires_at: datetime = datetime.now() + timedelta(minutes=5)


class ScrapingSessionManager:
    def __init__(self):
        self.sessions = dict[str, ScrapingSession]()
        self.downloader: Downloader | None = None

    def set_downloader(self, downloader: Downloader):
        """Set the downloader for the session manager"""
        self.downloader = downloader

    def create_session(
        self,
        item_id: int,
        magnet: str,
        media_type: Literal["movie", "tv"] | None = None,
        imdb_id: str | None = None,
        tmdb_id: str | None = None,
        tvdb_id: str | None = None,
        service: DownloaderBase | None = None,
    ) -> ScrapingSession:
        """Create a new scraping session"""
        session_id = str(uuid4())
        session = ScrapingSession(
            session_id,
            item_id,
            media_type,
            imdb_id,
            tmdb_id,
            tvdb_id,
            magnet,
            service,
        )
        self.sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> ScrapingSession | None:
        """Get a scraping session by ID"""

        session = self.sessions.get(session_id)

        if not session:
            return None

        if datetime.now() > session.expires_at:
            self.abort_session(session_id)
            return None

        return session

    def update_session(self, session_id: str, **kwargs: Any) -> ScrapingSession | None:
        """Update a scraping session"""

        session = self.get_session(session_id)

        if not session:
            return None

        for key, value in kwargs.items():
            if hasattr(session, key):
                setattr(session, key, value)

        return session

    def abort_session(self, session_id: str):
        """Abort a scraping session"""

        session = self.sessions.pop(session_id, None)

        if session and session.torrent_id and self.downloader:
            try:
                self.downloader.delete_torrent(session.torrent_id)
                logger.debug(f"Deleted torrent for aborted session {session_id}")
            except Exception as e:
                logger.error(f"Failed to delete torrent for session {session_id}: {e}")

        if session:
            logger.debug(f"Aborted session {session_id} for item {session.item_id}")

    def complete_session(self, session_id: str):
        """Complete a scraping session"""

        session = self.get_session(session_id)
        if not session:
            return

        logger.debug(f"Completing session {session_id} for item {session.item_id}")
        self.sessions.pop(session_id)

    def cleanup_expired(self, background_tasks: BackgroundTasks):
        """Cleanup expired scraping sessions"""

        current_time = datetime.now()
        expired = [
            session_id
            for session_id, session in self.sessions.items()
            if current_time > session.expires_at
        ]
        for session_id in expired:
            background_tasks.add_task(self.abort_session, session_id)


scraping_session_manager = ScrapingSessionManager()

router = APIRouter(prefix="/scrape", tags=["scrape"])


def initialize_downloader(downloader: Downloader):
    """Initialize downloader if not already set"""

    if not scraping_session_manager.downloader:
        scraping_session_manager.set_downloader(downloader)


def get_media_item(
    session: Session,
    item_id: int | None = None,
    tmdb_id: str | None = None,
    tvdb_id: str | None = None,
    imdb_id: str | None = None,
    media_type: str | None = None,
) -> MediaItem:
    """
    Get or create a MediaItem based on provided IDs.

    Tries to fetch authentication item by item_id, then by external IDs.
    If not found, tries to fetch from indexer and create/merge into DB.
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
    elif tvdb_id and media_type == "tv":
        prepared_item = MediaItem(
            {
                "tvdb_id": tvdb_id,
                "requested_by": "riven",
                "requested_at": datetime.now(),
            }
        )
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

                item = session.merge(indexed)
                session.commit()
                session.refresh(item)
                return item

    raise HTTPException(status_code=404, detail="Item not found")


def setup_scrape_request(
    session: Any,
    item_id: int | None,
    tmdb_id: str | None,
    tvdb_id: str | None,
    imdb_id: str | None,
    media_type: Literal["movie", "tv"] | None,
) -> tuple[MediaItem, list[MediaItem]]:
    """Helper to retrieve item and scrape targets."""

    item = get_media_item(
        session,
        item_id=item_id,
        tmdb_id=tmdb_id,
        tvdb_id=tvdb_id,
        imdb_id=imdb_id,
        media_type=media_type,
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
    ranking_overrides: RankingOverrides | None = None,
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
                target, ranking_overrides=ranking_overrides, manual=True
            ):
                current_streams = dict[str, Stream]()

                with all_streams_lock:
                    # Update global streams
                    for infohash, stream in parsed_streams.items():
                        if infohash not in all_streams:
                            s = Stream(
                                infohash=stream.infohash,
                                raw_title=stream.raw_title,
                                parsed_title=stream.parsed_title,
                                parsed_data=stream.parsed_data,
                                rank=stream.rank,
                                lev_ratio=stream.lev_ratio,
                                resolution=stream.resolution,
                            )
                            all_streams[infohash] = s
                            current_streams[infohash] = s

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
        if item.parent and item.parent.parent:
             target_item = item.parent.parent

    # 3. Expunge the item itself
    try:
        session.expunge(item)
    except InvalidRequestError:
        pass

    # 4. Apply changes (only if target_item is found/valid)
    if target_item:
        if custom_title:
            target_item.title = custom_title
        if custom_imdb_id:
            target_item.imdb_id = custom_imdb_id


@router.get(
    "/scrape",
    summary="Get streams for an item",
    operation_id="scrape_item",
    response_model=ScrapeItemResponse,
)
@router.post(
    "/scrape",
    response_model=ScrapeItemResponse,
)
async def scrape_item(
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
) -> ScrapeItemResponse:
    """Get streams for an item by any supported ID (item_id, tmdb_id, tvdb_id, imdb_id)"""

    if services := di[Program].services:
        scraper = services.scraping
    else:
        raise HTTPException(status_code=412, detail="Scraping services not initialized")

    with db_session() as session:
        item, targets = setup_scrape_request(
            session, item_id, tmdb_id, tvdb_id, imdb_id, media_type
        )

        apply_custom_scrape_params(session, item, custom_title, custom_imdb_id)

        all_streams = dict[str, Stream]()

        async for event in execute_scrape(item, scraper, targets):
            if event.streams:
                all_streams.update(event.streams)

        return ScrapeItemResponse(
            message=f"Manually scraped streams for item {item.log_string}",
            streams=all_streams,
        )


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
) -> StreamingResponse:
    """Stream scraping results via SSE."""

    if services := di[Program].services:
        scraper = services.scraping
    else:
        raise HTTPException(status_code=412, detail="Scraping services not initialized")

    async def sse_generator():
        with db_session() as session:
            item, targets = setup_scrape_request(
                session, item_id, tmdb_id, tvdb_id, imdb_id, media_type
            )

            apply_custom_scrape_params(session, item, custom_title, custom_imdb_id)

            async for event in execute_scrape(item, scraper, targets):
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


class ScrapeSeasonsRequest(BaseModel):
    tvdb_id: str | None = None
    tmdb_id: str | None = None
    imdb_id: str | None = None
    season_numbers: list[int]


class AutoScrapeRequestPayload(BaseModel):
    item_id: Annotated[
        int | None,
        Field(
            default=None,
            description="The ID of the media item",
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
        RankingOverrides | None,
        Field(description="Ranking overrides for the media item"),
    ] = None

    @model_validator(mode="after")
    def check_at_least_one_id_provided(self) -> Self:
        if not any([self.item_id, self.tvdb_id, self.tmdb_id, self.imdb_id]):
            raise ValueError("At least one ID must be provided")

        return self


def _scrape_worker(item_id: int) -> dict[str, Stream]:
    """Worker function to run scraper in a separate thread/session."""
    
    if services := di[Program].services:
        scraper = services.scraping
    else:
        return {}

    with db_session() as session:
        item = session.get(MediaItem, item_id)
        if not item:
            return {}
            
        # Fail-safe: Ensure item is not paused in this session before scraping
        if item.last_state == States.Paused:
            logger.debug(f"Worker found item {item.id} still Paused. Forcing Unpause.")
            item.store_state(States.Unknown)

        # Run the scraper (this updates the item and its relationships)
        # We iterate to consume the generator
        logger.debug(f"Worker processing item {item.id}. Initial State: {item.last_state}")
        for _ in scraper.run(item):
            pass
        
        # Refresh the item and streams relationship to ensure is_scraped() works correctly
        session.refresh(item, attribute_names=["streams", "blacklisted_streams"])

        # Force state update to reflect new streams
        previous_state, new_state = item.store_state()
        
        logger.debug(f"Worker scraped item {item.id}. Streams: {len(item.streams)}, Previous: {previous_state}, New: {new_state}, is_scraped: {item.is_scraped()}")
            
        session.commit()
        session.refresh(item)
        
        logger.debug(f"Worker committed item {item.id}. Final State: {item.last_state}")

        # Trigger downstream processing (Downloading) by adding an event
        # We emit as 'Scraping' service so EventManager sees it as completing that step
        program = di[Program]
        if hasattr(program, "em") and program.em:
            program.em.add_event(
                Event(
                    emitted_by=services.scraping,
                    item_id=item.id,
                )
            )
        
        # Convert found streams to Pydantic models for return
        streams: dict[str, Stream] = {}
        for s in item.streams:
            if s not in item.blacklisted_streams:
                try:
                    # Reconstruct ParsedData since it's not persisted
                    if not hasattr(s, "parsed_data"):
                        torrent = rtn.rank(
                            raw_title=s.raw_title,
                            infohash=s.infohash,
                            correct_title=item.top_title,
                        )
                        s.parsed_data = torrent.data

                    pyd_s = Stream.model_validate(s)
                    streams[pyd_s.infohash] = pyd_s
                except Exception as e:
                    logger.error(f"Failed to convert stream: {e}")
                    
        return streams


async def perform_season_scrape(
    tmdb_id: str | None = None,
    tvdb_id: str | None = None,
    imdb_id: str | None = None,
    season_numbers: list[int] | None = None,
) -> dict[str, Stream]:
    """Helper to perform season scraping with state management."""

    if season_numbers is None:
        season_numbers = []
    
    if not di[Program].services:
        raise HTTPException(status_code=412, detail="Scraping services not initialized")
    
    target_ids: list[int] = []
    
    with db_session() as session:
        # Get the show item
        item = get_media_item(
            session,
            tmdb_id=tmdb_id,
            tvdb_id=tvdb_id,
            imdb_id=imdb_id,
            media_type="tv",
        )

        if not isinstance(item, Show):
            raise HTTPException(
                status_code=400,
                detail=f"Item found is not a Show, it is {type(item).__name__}",
            )
        
        # Check and unpause parent Show if needed so child seasons aren't blocked
        if item.last_state == States.Paused:
            logger.debug(f"Unpausing parent Show {item.title} (ID: {item.id}) to allow season scrape")
            item.store_state(States.Unknown)

        # Pre-load/assign parent to avoid lazy load in threads
        seasons = item.seasons 
        for season in seasons:
            season.parent = item
            
            if season.number in season_numbers:
                logger.debug(f"Processing requested season {season.number} (ID: {season.id}). Current State: {season.last_state}")
                # If specifically requested, ensure it's not paused
                if season.last_state == States.Paused:
                    logger.debug(f"Unpausing season {season.number}")
                    season.store_state(States.Unknown) # Reset state to allow scraping
                target_ids.append(season.id)
            else:
                # If not requested, pause it
                if season.last_state != States.Paused:
                    logger.debug(f"Pausing unrequested season {season.number}")
                    season.store_state(States.Paused)
        
        session.commit() # Save state changes
        logger.debug("Committed state changes in perform_season_scrape")

    if not target_ids:
        return {}

    # Run scraping in parallel threads to ensure persistence via separate sessions
    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor(thread_name_prefix="SeasonScrapeWorker_") as executor:
        tasks = [
            loop.run_in_executor(executor, _scrape_worker, tid)
            for tid in target_ids
        ]
        results = await asyncio.gather(*tasks)
        
    all_streams = dict[str, Stream]()
    for res in results:
        all_streams.update(res)
            
    return all_streams


@router.post(
    "/seasons",
    summary="Scrape specific seasons of a show",
    operation_id="scrape_seasons",
    response_model=ScrapeItemResponse,
)
async def scrape_seasons(
    payload: ScrapeSeasonsRequest = Body(...),
) -> ScrapeItemResponse:
    """Scrape specific seasons of a show and pause unselected ones."""

    all_streams = await perform_season_scrape(
        tmdb_id=payload.tmdb_id,
        tvdb_id=payload.tvdb_id,
        imdb_id=payload.imdb_id,
        season_numbers=payload.season_numbers,
    )

    return ScrapeItemResponse(
        message="Scraping specific seasons",
        streams=all_streams,
    )


@router.post(
    "/scrape_stream/auto",
    summary="Stream auto scraping results via SSE",
    operation_id="auto_scrape_item_stream",
)
async def auto_scrape_item_stream(
    body: Annotated[AutoScrapeRequestPayload, Body()],
) -> StreamingResponse:
    """Stream auto scraping results via SSE."""

    if services := di[Program].services:
        scraper = services.scraping
    else:
        raise HTTPException(status_code=412, detail="Scraping services not initialized")

    async def sse_generator():
        with db_session() as session:
            item, targets = setup_scrape_request(
                session,
                body.item_id,
                body.tmdb_id,
                body.tvdb_id,
                body.imdb_id,
                body.media_type,
            )

            async for event in execute_scrape(
                item, scraper, targets, ranking_overrides=body.ranking_overrides
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


@router.post(
    "/start_session",
    summary="Start a manual scraping session",
    operation_id="start_manual_session",
    response_model=StartSessionResponse,
)
async def start_manual_session(
    background_tasks: BackgroundTasks,
    magnet: str,
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
    disable_filesize_check: Annotated[
        bool,
        Query(description="Disable filesize check"),
    ] = False,
) -> StartSessionResponse:
    scraping_session_manager.cleanup_expired(background_tasks)

    info_hash = extract_infohash(magnet)

    if not info_hash:
        raise HTTPException(status_code=400, detail="Invalid magnet URI")

    if services := di[Program].services:
        downloader = services.downloader
    else:
        raise HTTPException(status_code=412, detail="Required services not initialized")

    initialize_downloader(downloader)

    item = None

    with db_session() as session:
        item = get_media_item(
            session,
            item_id=item_id,
            tmdb_id=tmdb_id,
            tvdb_id=tvdb_id,
            imdb_id=imdb_id,
            media_type=media_type,
        )

    if item.type == "mediaitem":
        raise HTTPException(status_code=500, detail="Incorrect item type found")

    container = None
    used_service = None
    filesize_error = False

    for service in downloader.initialized_services:
        try:
            if container := service.get_instant_availability(
                info_hash, item.type, limit_filesize=not disable_filesize_check
            ):
                if container.cached:
                    used_service = service
                    break
        except FilesizeLimitExceededException:
            filesize_error = True
            continue

    if not container or not container.cached:
        if filesize_error:
            raise HTTPException(status_code=400, detail="File size above set limit")
        raise HTTPException(
            status_code=400, detail="Torrent is not cached, please try another stream"
        )

    if not used_service:
        raise HTTPException(
            status_code=500,
            detail="Downloader service not initialized",
        )

    session = scraping_session_manager.create_session(
        item.id,
        info_hash,
        media_type=media_type,
        imdb_id=imdb_id,
        tmdb_id=tmdb_id,
        tvdb_id=tvdb_id,
        service=used_service,
    )

    logger.debug(f"Created session {session.id} with item ID: {session.item_id}")

    try:
        torrent_id = used_service.add_torrent(info_hash)
        torrent_info = used_service.get_torrent_info(torrent_id)
        scraping_session_manager.update_session(
            session_id=session.id,
            torrent_id=torrent_id,
            torrent_info=torrent_info,
            containers=container,
        )
    except Exception as e:
        background_tasks.add_task(scraping_session_manager.abort_session, session.id)
        raise HTTPException(status_code=500, detail=str(e))

    return StartSessionResponse(
        message="Started manual scraping session",
        session_id=session.id,
        torrent_id=torrent_id,
        torrent_info=torrent_info,
        containers=container,
        expires_at=session.expires_at.isoformat(),
    )


@router.post(
    "/select_files/{session_id}",
    summary="Select files for torrent id, for this to be instant it requires files to be one of /manual/instant_availability response containers",
    operation_id="manual_select",
    response_model=SelectFilesResponse,
)
def manual_select_files(
    session_id: Annotated[
        str,
        Path(
            description="Identifier of the scraping session containing item and torrent context."
        ),
    ],
    files: Annotated[
        Container,
        Body(description="The files to select"),
    ],
) -> SelectFilesResponse:
    if services := di[Program].services:
        downloader = services.downloader
    else:
        raise HTTPException(status_code=412, detail="Required services not initialized")

    session = scraping_session_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    if not session.torrent_id:
        scraping_session_manager.abort_session(session_id)

        raise HTTPException(status_code=500, detail="No torrent ID found")

    download_type = "uncached"

    if files.model_dump() in session.containers:
        download_type = "cached"

    try:
        downloader.select_files(
            session.torrent_id,
            [int(file_id) for file_id in files.root.keys()],
            service=session.service,
        )

        session.selected_files = files.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return SelectFilesResponse(
        message=f"Selected files for {session.item_id}",
        download_type=download_type,
    )


@router.post(
    "/update_attributes/{session_id}",
    summary="Match container files to item",
    operation_id="manual_update_attributes",
    response_model=MessageResponse,
)
async def manual_update_attributes(
    session_id: Annotated[
        str,
        Path(
            description="Identifier of the scraping session containing item and torrent context."
        ),
    ],
    data: Annotated[
        DebridFile | ShowFileData,
        Body(
            description="File metadata for a single movie (`DebridFile`) or a mapping of seasons/episodes to file metadata (`ShowFileData`) for TV content."
        ),
    ],
) -> MessageResponse:
    """
    Apply selected file attributes from a scraping session to the referenced media item(s).

    Locate the media item referenced by the given scraping session, create or reuse a staging FilesystemEntry for the provided file data, attach the file as the item's active stream (or attach to matching episodes for TV items), persist the changes to the database, and enqueue post-processing events for affected items.

    Parameters:
        session_id (str): Identifier of the scraping session containing item and torrent context.
        data (DebridFile | ShowFileData): File metadata for a single movie (`DebridFile`) or a mapping of seasons/episodes to file metadata (`ShowFileData`) for TV content.

    Returns:
        dict: A message indicating which item(s) were updated, including the item's log string.

    Raises:
        HTTPException: 404 if the session or target item cannot be found; 500 if the session lacks an associated item ID.
    """

    scraping_session = scraping_session_manager.get_session(session_id)
    log_string = None

    if not scraping_session:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    if not scraping_session.item_id:
        scraping_session_manager.abort_session(session_id)
        raise HTTPException(status_code=500, detail="No item ID found")

    item = None
    item_ids_to_submit = None

    with db_session() as session:
        item = get_media_item(
            session,
            item_id=scraping_session.item_id,
            tmdb_id=scraping_session.tmdb_id,
            tvdb_id=scraping_session.tvdb_id,
            imdb_id=scraping_session.imdb_id,
            media_type=scraping_session.media_type,
        )

        item = session.merge(item)
        item_ids_to_submit = set[int]()
        updated_episode_ids = set[int]()

        if isinstance(data, DebridFile):
            _update_item_fs_entry(
                session,
                updated_episode_ids,
                item_ids_to_submit,
                scraping_session,
                item,
                data,
            )
        else:
            for season_number, episodes in data.root.items():
                for episode_number, episode_data in episodes.items():
                    if isinstance(item, Show) or isinstance(item, Season):
                        show = item if isinstance(item, Show) else item.parent
                        if episode := show.get_absolute_episode(
                            episode_number, season_number
                        ):
                            _update_item_fs_entry(
                                session,
                                updated_episode_ids,
                                item_ids_to_submit,
                                scraping_session,
                                episode,
                                episode_data,
                            )
                        else:
                            logger.error(
                                f"Failed to find episode {episode_number} in season {season_number} for {item.log_string}"
                            )
                    elif isinstance(item, Episode):
                        if (
                            season_number == item.parent.number
                            and episode_number == item.number
                        ):
                            _update_item_fs_entry(
                                session,
                                updated_episode_ids,
                                item_ids_to_submit,
                                scraping_session,
                                item,
                                episode_data,
                            )

        # Set unselected episodes to paused
        if isinstance(item, Show):
            logger.debug(
                f"Checking {len(item.seasons)} seasons for unselected episodes to pause"
            )
            for season in item.seasons:
                logger.debug(
                    f"Season {season.number} has {len(season.episodes)} episodes"
                )
                for episode in season.episodes:
                    if episode.id not in updated_episode_ids:
                        if episode.state in [
                            States.Completed,
                            States.Symlinked,
                            States.Downloaded,
                        ]:
                            continue

                        episode.store_state(States.Paused)
                        session.merge(episode)
                        logger.debug(
                            f"Paused episode {episode.log_string} (ID: {episode.id})"
                        )
        elif isinstance(item, Season):
            logger.debug(
                f"Checking {len(item.episodes)} episodes in season {item.number} to pause"
            )
            for episode in item.episodes:
                if episode.id not in updated_episode_ids:
                    if episode.state in [
                        States.Completed,
                        States.Symlinked,
                        States.Downloaded,
                    ]:
                        continue

                    episode.store_state(States.Paused)
                    session.merge(episode)
                    logger.debug(
                        f"Paused episode {episode.log_string} (ID: {episode.id})"
                    )

        item.store_state()

        log_string = item.log_string

        session.merge(item)
        session.commit()

        # Sync VFS to reflect any deleted/updated entries
        # Must happen AFTER commit so the database reflects the changes
        if services := di[Program].services:
            filesystem_service = services.filesystem
        else:
            raise HTTPException(
                status_code=412, detail="Filesystem service not initialized"
            )

        if filesystem_service and filesystem_service.riven_vfs:
            filesystem_service.riven_vfs.sync(item)
            logger.debug("VFS synced after manual scraping update")

        if item_ids_to_submit:
            for item_id in item_ids_to_submit:
                di[Program].em.add_event(Event("ManualAPI", item_id))

        return MessageResponse(message=f"Updated given data to {log_string}")


def _update_item_fs_entry(
    session: Session,
    updated_episode_ids: set[int],
    item_ids_to_submit: set[int],
    scraping_session: ScrapingSession,
    item: MediaItem,
    data: DebridFile,
):
    """
    Prepare and attach a filesystem entry and stream to a MediaItem based on a selected DebridFile within a scraping session.

    Cancels any running processing job for the item and resets its state; ensures there is a staging FilesystemEntry for the given file (reusing an existing entry or creating a provisional one and persisting it), clears the item's existing filesystem_entries and links the staging entry, sets the item's active_stream to the session magnet and torrent id, appends a ranked ItemStream derived from the session, and records the item's id in the module-level item_ids_to_submit set.

    Parameters:
        item (MediaItem): The media item to update; will be merged into the active DB session as needed.
        data (DebridFile): Selected file metadata (filename, filesize, optional download_url) used to create or locate the staging entry.
    """

    di[Program].em.cancel_job(item.id)

    if item.last_state == States.Paused:
        item.last_state = States.Unknown

    item.reset()

    # Ensure a staging MediaEntry exists and is linked
    from program.media.media_entry import MediaEntry
    from program.media.models import MediaMetadata

    fs_entry = None

    if item.media_entry and data.filename:
        fs_entry = item.media_entry
        # Update source metadata on existing entry
        fs_entry.original_filename = data.filename
    else:
        # Create a provisional VIRTUAL entry (download_url/provider may be filled by downloader later)
        provider = scraping_session.service.key if scraping_session.service else None

        # Get torrent ID from scraping session
        torrent_id = (
            scraping_session.torrent_info.id if scraping_session.torrent_info else None
        )

        download_url = data.download_url

        # If download_url is missing, try to refresh torrent info to get it
        if not download_url and torrent_id and scraping_session.service:
            logger.debug(
                f"Refreshing torrent info for {torrent_id} to resolve download_url"
            )

            if new_url := resolve_download_url(
                scraping_session.service, torrent_id, data.filename
            ):
                download_url = new_url
                logger.debug(
                    f"Resolved download_url for {data.filename}: {download_url}"
                )
                data.download_url = download_url
                # Recursively call with updated file
                _update_item_fs_entry(
                    session,
                    updated_episode_ids,
                    item_ids_to_submit,
                    scraping_session,
                    item,
                    data,
                )
                return
            else:
                logger.warning(
                    f"Failed to resolve download_url for {data.filename}"
                )

        # Parse filename to create metadata
        media_metadata = None
        try:
            if data.filename:
                file_data = parse_filename(data.filename)
                media_metadata = MediaMetadata.from_parsed_data(
                    parsed_data=file_data,
                    filename=data.filename,
                )
        except Exception as e:
            logger.warning(
                f"Failed to parse filename '{data.filename}' for metadata: {e}"
            )
        # Create a provisional VIRTUAL entry (download_url/provider may be filled by downloader later)
        fs_entry = MediaEntry.create_placeholder_entry(
            original_filename=data.filename,
            download_url=download_url,
            provider=provider,
            provider_download_id=str(torrent_id) if torrent_id else None,
            file_size=data.filesize,
            media_metadata=media_metadata,
        )

        session.add(fs_entry)
        session.commit()
        session.refresh(fs_entry)

    # Link MediaItem to FilesystemEntry
    # Clear existing entries and add the new one
    item.filesystem_entries.clear()
    item.filesystem_entries.append(fs_entry)
    item = session.merge(item)

    assert scraping_session
    assert scraping_session.magnet
    assert scraping_session.torrent_info

    item.active_stream = ActiveStream(
        infohash=scraping_session.magnet,
        id=scraping_session.torrent_info.id,
    )

    torrent = rtn.rank(
        scraping_session.torrent_info.name,
        scraping_session.magnet,
    )

    # Ensure the item is properly attached to the session before adding streams
    # This prevents SQLAlchemy warnings about detached objects
    if object_session(item) is not session:
        item = session.merge(item)

    item.streams.append(ItemStream(torrent=torrent))
    item_ids_to_submit.add(item.id)

    if isinstance(item, Episode):
        updated_episode_ids.add(item.id)


@router.post(
    "/abort_session/{session_id}",
    summary="Abort a manual scraping session",
    operation_id="abort_manual_session",
    response_model=MessageResponse,
)
async def abort_manual_session(
    background_tasks: BackgroundTasks,
    session_id: Annotated[
        str,
        Path(
            description="Identifier of the scraping session containing item and torrent context."
        ),
    ],
) -> MessageResponse:
    session = scraping_session_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    background_tasks.add_task(scraping_session_manager.abort_session, session_id)

    return MessageResponse(message=f"Aborted session {session_id}")


@router.post(
    "/complete_session/{session_id}",
    summary="Complete a manual scraping session",
    operation_id="complete_manual_session",
    response_model=MessageResponse,
)
async def complete_manual_session(
    session_id: Annotated[
        str,
        Path(
            description="Identifier of the scraping session containing item and torrent context."
        ),
    ],
) -> MessageResponse:
    session = scraping_session_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    if not all([session.torrent_id, session.selected_files]):
        raise HTTPException(status_code=400, detail="Session is incomplete")

    scraping_session_manager.complete_session(session_id)

    return MessageResponse(message=f"Completed session {session_id}")


class ParseTorrentTitleResponse(BaseModel):
    message: str
    data: list[dict[str, Any]]


@router.post(
    "/parse",
    summary="Parse an array of torrent titles",
    operation_id="parse_torrent_titles",
    response_model=ParseTorrentTitleResponse,
)
async def parse_torrent_titles(
    titles: Annotated[
        list[str],
        Body(description="List of torrent titles to parse"),
    ],
) -> ParseTorrentTitleResponse:
    parsed_titles = list[dict[str, Any]]()

    if titles:
        for title in titles:
            parsed_titles.append(
                {
                    "raw_title": title,
                    **parse_title(title),
                }
            )

        if parsed_titles:
            return ParseTorrentTitleResponse(
                message="Parsed torrent titles",
                data=parsed_titles,
            )

        return ParseTorrentTitleResponse(message="No titles could be parsed", data=[])
    else:
        return ParseTorrentTitleResponse(message="No titles provided", data=[])


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

    from program.db.db_functions import item_exists_by_any_id
    from kink import di

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
            persisted_items = list[MediaItem]()

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

        # Scrape with overrides
        streams = scraper.scrape(
            item,
            ranking_overrides=body.ranking_overrides,
            manual=True,
        )

        # Filter out existing or blacklisted streams
        existing_infohashes = {s.infohash for s in item.streams}
        blacklisted_infohashes = {s.infohash for s in item.blacklisted_streams}

        new_streams = list[ItemStream]()

        for stream in streams.values():
            if (
                stream.infohash not in existing_infohashes
                and stream.infohash not in blacklisted_infohashes
            ):
                # Convert Pydantic Stream to RTN.Torrent to create ItemStream
                torrent_data = Torrent(
                    raw_title=stream.raw_title,
                    infohash=stream.infohash,
                    data=stream.parsed_data,
                    fetch=True,
                    rank=stream.rank,
                    lev_ratio=stream.lev_ratio,
                )
                new_streams.append(ItemStream(torrent=torrent_data))

        if new_streams:
            item.streams.extend(new_streams)

            item.store_state(States.Scraped)  # Force state update to trigger downloader

            logger.info(
                f"Auto scrape found {len(new_streams)} new streams for {item.log_string}"
            )

            # Commit changes to DB
            session.add(item)
            session.commit()

            # Emit event to trigger downloader
            di[Program].em.add_event(Event("Scraping", item_id=item.id))

            return MessageResponse(
                message=f"Auto scrape started. Found {len(new_streams)} new streams."
            )
        else:
            return MessageResponse(
                message="Auto scrape completed. No new streams found."
            )

