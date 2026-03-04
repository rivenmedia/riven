from datetime import datetime, timedelta
from typing import Annotated, Any, Literal, cast, TypeAlias
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
from pydantic import BaseModel, Json, RootModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import InvalidRequestError

from program.db import db_functions
from program.db.db import db_session
from program.media.item import MediaItem, Show, Season, ProcessedItemType, Episode, Movie
from program.media.state import States
from program.media.stream import Stream as ItemStream
from program.services.downloaders import Downloader
from program.services.downloaders.models import (
    DebridFile,
    DownloadedTorrent,
    TorrentContainer,
    TorrentInfo,
)
from program.services.scrapers.shared import get_ranking_overrides
from program.types import Event
from program.utils.torrent import extract_infohash
from program.program import Program
from ..models.shared import MessageResponse
from program.settings import settings_manager
from program.settings.models import RTNSettingsModel
from program.services.scrapers import Scraping

class Stream(BaseModel):
    infohash: str
    raw_title: str
    parsed_title: str
    parsed_data: ParsedData
    rank: int
    lev_ratio: float
    is_cached: bool = False


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


class ParsedFile(BaseModel):
    file_id: int
    filename: str
    filesize: int
    download_url: str | None = None
    parsed_metadata: dict[str, Any]


class StartSessionResponse(MessageResponse):
    session_id: str
    item_id: int
    media_type: Literal["movie", "tv"] | None = None
    requested_season: int | None = None
    requested_episode: int | None = None
    tmdb_id: str | None = None
    tvdb_id: str | None = None
    imdb_id: str | None = None
    torrent_id: str | int
    torrent_info: TorrentInfo
    containers: TorrentContainer | None
    parsed_files: list[ParsedFile] | None = None
    expires_at: str


class SelectFilesResponse(MessageResponse):
    download_type: Literal["cached", "uncached"]


ContainerMap: TypeAlias = dict[str, DebridFile]


class Container(RootModel[ContainerMap]):
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

    root: ContainerMap


SeasonEpisodeMap: TypeAlias = dict[int, dict[int, DebridFile]]


class ShowFileData(RootModel[SeasonEpisodeMap]):
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

    root: SeasonEpisodeMap


class SessionActionRequest(BaseModel):
    """Unified request body for session actions."""
    action: Literal["select_files", "update_attributes", "abort", "complete"]
    files: Container | None = None  # For select_files action
    file_data: DebridFile | ShowFileData | None = None  # For update_attributes action


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
        min_filesize_override: int | None = None,
        max_filesize_override: int | None = None,
    ):
        self.id = id
        self.item_id = item_id
        self.media_type = media_type
        self.imdb_id = imdb_id
        self.tmdb_id = tmdb_id
        self.tvdb_id = tvdb_id
        self.magnet = magnet
        self.min_filesize_override = min_filesize_override
        self.max_filesize_override = max_filesize_override
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
        min_filesize_override: int | None = None,
        max_filesize_override: int | None = None,
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
            min_filesize_override,
            max_filesize_override,
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


async def resolve_torrent_container(
    infohash: str,
    downloader: Downloader,
    item_type: ProcessedItemType = "movie",
    min_filesize_override: int | None = None,
    max_filesize_override: int | None = None,
) -> tuple[TorrentContainer | None, str | None]:
    """
    Resolve a magnet infohash to a TorrentContainer.

    First tries instant availability check. Falls back to adding/probing
    the torrent temporarily if not cached.

    Args:
        infohash: The torrent infohash
        downloader: The downloader service to use
        item_type: "movie", "show", "season", or "episode" for file validation
        min_filesize_override: Optional min filesize override
        max_filesize_override: Optional max filesize override

    Returns:
        Tuple of (container, error_message). If container is None, error_message explains why.
    """
    import asyncio
    from program.services.downloaders.models import InvalidDebridFileException

    container = None
    last_error = None

    overrides = {}
    if min_filesize_override is not None:
        overrides["min_filesize"] = min_filesize_override
    if max_filesize_override is not None:
        overrides["max_filesize"] = max_filesize_override

    with settings_manager.override(**overrides):
        # Try instant availability check first
        try:
            container = await asyncio.to_thread(
                downloader.get_instant_availability, infohash, item_type
            )
            if container and container.files:
                return container, None
                
        except InvalidDebridFileException as e:
            last_error = str(e)
            logger.debug(f"Invalid debrid file: {e}")
        except Exception as e:
            last_error = f"Service error: {str(e)}"
            logger.debug(f"Error checking instant availability: {e}")

        # Fallback: probe torrent by adding temporarily
        if not container or not container.files:
            try:
                tid = await asyncio.to_thread(downloader.add_torrent, infohash)
                try:
                    info = await asyncio.to_thread(downloader.get_torrent_info, tid)
                    if info and info.files:
                        valid_files = list[DebridFile]()
                        for f in info.files.values():
                            try:
                                df = DebridFile.create(
                                    path=f.path,
                                    filename=f.filename,
                                    filesize_bytes=f.bytes,
                                    filetype=item_type,
                                    file_id=f.id,
                                )
                                valid_files.append(df)
                            except InvalidDebridFileException as e:
                                logger.debug(f"Skipping file {f.filename}: {e}")
                                continue

                        if valid_files:
                            container = TorrentContainer(
                                infohash=infohash,
                                files=valid_files,
                                torrent_id=tid,
                                torrent_info=info,
                            )
                        else:
                            last_error = "No valid video files found (all files filtered by type or size)"
                except Exception as e:
                    logger.error(f"Error getting torrent info: {e}")
                    last_error = f"Unable to get torrent info: {str(e)}"
                finally:
                    # Clean up temporary torrent if we're just probing
                    if not container or not container.files:
                        try:
                            await asyncio.to_thread(downloader.delete_torrent, tid)
                        except Exception:
                            pass
            except Exception as e:
                logger.error(f"Magnet resolution error: {e}")
                return None, f"Unable to resolve magnet: {str(e)}"

    if container and container.files:
        return container, None

    return None, last_error or "No files found in torrent"





def resolve_media_item(
    session: Session,
    item_id: int | None = None,
    tmdb_id: str | None = None,
    tvdb_id: str | None = None,
    imdb_id: str | None = None,
    media_type: Literal["movie", "tv"] | None = None,
    raise_on_not_found: bool = True,
) -> MediaItem | None:
    """
    Resolve or create a media item with common validation.
    
    Args:
        session: DB session
        item_id, tmdb_id, tvdb_id, imdb_id, media_type: Identifiers
        raise_on_not_found: If True, raise HTTPException on None result
        
    Returns:
        MediaItem or None (if raise_on_not_found=False)
    """
    item = None
    if item_id:
        item = db_functions.get_item_by_id(item_id, session=session)

    if not item and (tmdb_id or tvdb_id or imdb_id):
        try:
            item = db_functions.get_item_by_external_id(
                imdb_id=imdb_id,
                tvdb_id=tvdb_id,
                tmdb_id=tmdb_id,
                session=session
            )
        except ValueError:
            pass

    # If item not found locally, try to create it via Indexer if external IDs are provided
    if not item and (tmdb_id or tvdb_id or imdb_id):
        if services := di[Program].services:
            indexer = services.indexer
            prepared_item = None

            if tmdb_id and media_type == "movie":
                prepared_item = MediaItem({
                    "tmdb_id": tmdb_id,
                    "requested_by": "riven",
                    "requested_at": datetime.now(),
                })
            elif tvdb_id and media_type == "tv":
                prepared_item = MediaItem({
                    "tvdb_id": tvdb_id,
                    "requested_by": "riven",
                    "requested_at": datetime.now(),
                })
            elif imdb_id:
                prepared_item = MediaItem({
                    "imdb_id": imdb_id,
                    "tvdb_id": tvdb_id,
                    "requested_by": "riven",
                    "requested_at": datetime.now(),
                })

            if prepared_item:
                # Run indexer to fetch metadata
                indexer_result = next(indexer.run(prepared_item), None)
                if indexer_result and indexer_result.media_items:
                    item = indexer_result.media_items[0]
                    item.store_state()
                    # Persist new item
                    item = session.merge(item)
                    session.commit()

    if not item and raise_on_not_found:
        raise HTTPException(status_code=404, detail="Item not found")
    
    if item and item.type == "mediaitem":
        raise HTTPException(status_code=400, detail="Unresolved mediaitem type")
    
    return item

def get_overrides_dict(
    ranking_overrides: Json[dict[str, list[str]]] | dict[str, list[str]] | None = None,
    min_filesize_override: int | None = None,
    max_filesize_override: int | None = None,
) -> dict[str, Any]:
    """Helper to construct search rank/filter overrides from request params"""
    rtn_settings_override_model = get_ranking_overrides(ranking_overrides)
    if not rtn_settings_override_model:
        rtn_settings_override_model = RTNSettingsModel(
            **settings_manager.settings.ranking.model_dump()
        )

    overrides: dict[str, Any] = rtn_settings_override_model.model_dump()

    if min_filesize_override is not None:
        overrides["min_filesize"] = min_filesize_override
    if max_filesize_override is not None:
        overrides["max_filesize"] = max_filesize_override
    
    return overrides

def apply_custom_params(item: MediaItem, custom_title: str | None = None, custom_imdb_id: str | None = None) -> None:
    """Apply custom scrape parameters (not persisted to DB)"""
    # If any custom param is used, clear strict metadata to allow overrides
    if custom_title or custom_imdb_id:
        item.tmdb_id = None
        item.tvdb_id = None
        item.year = None  # pyright: ignore[reportAttributeAccessIssue]
        item.aired_at = None  # pyright: ignore[reportAttributeAccessIssue]
    
    if custom_title:
        item.title = custom_title
        # If no custom IMDB ID provided, clear original IMDB ID to force text search
        if not custom_imdb_id:
            item.imdb_id = None

    if custom_imdb_id:
        item.imdb_id = custom_imdb_id


@router.get(
    "",
    summary="Get streams for an item",
    operation_id="scrape_item",
)
def scrape_item(
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
        Query(description="Custom title to use for scraping (not persisted)"),
    ] = None,
    custom_imdb_id: Annotated[
        str | None,
        Query(description="Custom IMDB ID to use for scraping (not persisted)"),
    ] = None,
    ranking_overrides: Annotated[
        Json[dict[str, list[str]]] | None,
        Query(description="JSON-encoded ranking overrides, e.g. {\"resolutions\": [\"1080p\"]}"),
    ] = None,
    stream: Annotated[
        bool,
        Query(description="If true, stream results via SSE as scrapers complete"),
    ] = False,
    min_filesize_override: Annotated[
        int | None,
        Query(description="Minimum filesize in MB"),
    ] = None,
    max_filesize_override: Annotated[
        int | None,
        Query(description="Maximum filesize in MB"),
    ] = None,
):
    """Get streams for an item. Set stream=true for SSE streaming as scrapers complete."""

    services = di[Program].services
    if not services:
        raise HTTPException(status_code=412, detail="Scraping services not initialized")
    scraper = services.scraping
    
    # Prepare overrides dictionary
    target_media_type: Literal["movie", "tv"] | None = (
        media_type if media_type in ("movie", "tv") else None
    )
    
    overrides = get_overrides_dict(
        ranking_overrides=ranking_overrides,
        min_filesize_override=min_filesize_override,
        max_filesize_override=max_filesize_override,
    )

    if stream:
        # SSE streaming mode
        if not any([item_id, tmdb_id and media_type == "movie", tvdb_id and media_type == "tv", imdb_id]):
            raise HTTPException(status_code=400, detail="No valid ID provided")

        async def generate_events(scraper: Scraping):
            with db_session() as session:
                item = resolve_media_item(session, item_id, tmdb_id, tvdb_id, imdb_id, target_media_type)

                if not item:
                    error_event = ScrapeStreamEvent(event="error", message="Item not found")
                    yield f"data: {error_event.model_dump_json()}\n\n"
                    return
                
                # Detach item from session to avoid threading issues in scraper
                try:
                    # Explicitly link parents to avoid lazy-loading on detached objects
                    if isinstance(item, Show):
                        for season in item.seasons:
                            season.parent = item
                            for episode in season.episodes:
                                episode.parent = season
                                
                    elif isinstance(item, Season):
                        for episode in item.episodes:
                            episode.parent = item

                    session.expunge(item)
                    if isinstance(item, Show):
                        for season in item.seasons:
                            session.expunge(season)
                            for episode in season.episodes:
                                session.expunge(episode)
                    elif isinstance(item, Season):
                        for episode in item.episodes:
                            session.expunge(episode)

                except InvalidRequestError:
                    pass
                
                # Apply custom params to the detached item
                apply_custom_params(item, custom_title, custom_imdb_id)

                all_streams: dict[str, Stream] = {}
                total_services = len(scraper.initialized_services)
                services_completed = 0

                start_event = ScrapeStreamEvent(
                    event="start",
                    message=f"Starting scrape for {item.log_string}",
                    total_services=total_services,
                )
                yield f"data: {start_event.model_dump_json()}\n\n"

                with settings_manager.override(**overrides):
                    items_to_scrape = [item]
                    if isinstance(item, Show):
                        # For shows, scrape each season individually like auto-scraping does
                        items_to_scrape = [season for season in item.seasons if season.state != States.Unreleased]
                        if not items_to_scrape:
                            items_to_scrape = [item] # Fallback if no seasons

                    for target_item in items_to_scrape:
                        for service_name, parsed_streams in scraper.scrape_streaming(
                            target_item, manual=True
                        ):
                            services_completed += 1
                            new_streams: dict[str, Stream] = {}
    
                            for infohash, s in parsed_streams.items():
                                if infohash not in all_streams:
                                    stream_obj = Stream(
                                        infohash=s.infohash,
                                        raw_title=s.raw_title,
                                        parsed_title=s.parsed_title,
                                        parsed_data=s.parsed_data,
                                        rank=s.rank,
                                        lev_ratio=s.lev_ratio,
                                    )
                                    all_streams[infohash] = stream_obj
                                    new_streams[infohash] = stream_obj
    
                            event = ScrapeStreamEvent(
                                event="streams" if new_streams else "progress",
                                service=service_name,
                                message=f"{service_name} found {len(new_streams)} new streams for {target_item.log_string}" if new_streams else f"{service_name} completed for {target_item.log_string}",
                                streams=new_streams if new_streams else None,
                                total_streams=len(all_streams),
                                services_completed=services_completed,
                                total_services=total_services * len(items_to_scrape),
                            )
                            yield f"data: {event.model_dump_json()}\n\n"

                complete_event = ScrapeStreamEvent(
                    event="complete",
                    message=f"Scraping complete. Found {len(all_streams)} total streams.",
                    streams=all_streams,
                    total_streams=len(all_streams),
                    services_completed=services_completed,
                    total_services=total_services,
                )
                yield f"data: {complete_event.model_dump_json()}\n\n"

        scraper_mgr = scraper  # capture for closure
        return StreamingResponse(
            generate_events(scraper_mgr),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    # Standard JSON response mode
    with db_session() as session:
        item = resolve_media_item(session, item_id, tmdb_id, tvdb_id, imdb_id, target_media_type)
        assert item
        apply_custom_params(item, custom_title, custom_imdb_id)

        with settings_manager.override(**overrides):
            items_to_scrape = [item]
            if isinstance(item, Show):
                items_to_scrape = [season for season in item.seasons if season.state != States.Unreleased]
                if not items_to_scrape:
                    items_to_scrape = [item]
            
            streams = {}
            for target_item in items_to_scrape:
                target_streams = scraper.scrape(target_item, manual=True)
                for infohash, stream in target_streams.items():
                    if infohash not in streams:
                        streams[infohash] = stream

        return ScrapeItemResponse(
            message=f"Manually scraped streams for item {item.log_string}",
            streams={
                s.infohash: Stream(
                    infohash=s.infohash,
                    raw_title=s.raw_title,
                    parsed_title=s.parsed_title,
                    parsed_data=s.parsed_data,
                    rank=s.rank,
                    lev_ratio=s.lev_ratio,
                    is_cached=s.is_cached,
                )
                for s in streams.values()
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
    min_filesize_override: int | None = Query(None, description="Minimum filesize in MB"),
    max_filesize_override: int | None = Query(None, description="Maximum filesize in MB"),
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

    # Prepare overrides dictionary
    target_media_type: Literal["movie", "tv"] | None = (
        media_type if media_type in ("movie", "tv") else None
    )

    item = None

    with db_session() as session:
        item = resolve_media_item(session, item_id, tmdb_id, tvdb_id, imdb_id, target_media_type)

        # ensure item is present
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        # Use async container resolution with fallback
        # Cast type to ProcessedItemType if it's not 'mediaitem'
        item_type: ProcessedItemType = item.type if item.type != "mediaitem" else "movie"
        container, error = await resolve_torrent_container(
            info_hash,
            downloader,
            item_type=item_type,
            min_filesize_override=min_filesize_override,
            max_filesize_override=max_filesize_override,
        )

        if not container or not container.cached:
            raise HTTPException(
                status_code=400,
                detail=error or "Torrent is not cached, please try another stream"
            )

        session_obj = scraping_session_manager.create_session(
            item.id,
            info_hash,
            media_type=media_type,
            imdb_id=imdb_id,
            tmdb_id=tmdb_id,
            tvdb_id=tvdb_id,

        )

        try:
            # Use torrent_id from container if available (from fallback probing)
            if container.torrent_id:
                torrent_id = container.torrent_id
                torrent_info = container.torrent_info or downloader.get_torrent_info(torrent_id)
            else:
                torrent_id = downloader.add_torrent(info_hash)
                torrent_info = downloader.get_torrent_info(torrent_id)

            scraping_session_manager.update_session(
                session_id=session_obj.id,
                torrent_id=torrent_id,
                torrent_info=torrent_info,
                containers=container,
            )
        except Exception as e:
            background_tasks.add_task(scraping_session_manager.abort_session, session_obj.id)
            raise HTTPException(status_code=500, detail=str(e))

        parsed_files = list[ParsedFile]()

        if container:
            for file in container.files:
                if file.file_id is None:
                    continue

                try:
                    ptt_data = parse_title(file.filename)
                    ptt_data["raw_title"] = file.filename
                    parsed_metadata = ParsedData(**ptt_data)
                    parsed_files.append(
                        ParsedFile(
                            file_id=file.file_id,
                            filename=file.filename,
                            filesize=file.filesize,
                            download_url=file.download_url,
                            parsed_metadata=parsed_metadata.model_dump(),
                        )
                    )
                except Exception as e:
                    logger.warning(f"Failed to parse title for {file.filename}: {e}")
                    continue

        requested_season = None
        requested_episode = None
        if isinstance(item, Season):
            requested_season = item.number
        elif isinstance(item, Episode):
            requested_season = item.parent.number
            requested_episode = item.number

        return StartSessionResponse(
            message="Started manual scraping session",
            session_id=session_obj.id,
            item_id=item.id,
            media_type=media_type,
            requested_season=requested_season,
            requested_episode=requested_episode,
            tmdb_id=tmdb_id,
            tvdb_id=tvdb_id,
            imdb_id=imdb_id,
            torrent_id=torrent_id,
            torrent_info=torrent_info,
            containers=container,
            parsed_files=parsed_files,
            expires_at=session_obj.expires_at.isoformat(),
        )


def _download_and_update(scraping_session: ScrapingSession, file_ids: list[int]) -> str:
    """Resolve a torrent, match files to episodes, update states, and emit events.

    Shared by the ``update_attributes`` and ``complete`` session actions.
    Returns the item's log_string on success.
    """
    if services := di[Program].services:
        downloader = services.downloader
    else:
        raise HTTPException(status_code=500, detail="Downloader service not available")

    assert downloader.service
    debrid_service = downloader.service

    with db_session() as session:
        item = resolve_media_item(
            session=session,
            item_id=scraping_session.item_id,
            tmdb_id=scraping_session.tmdb_id,
            tvdb_id=scraping_session.tvdb_id,
            imdb_id=scraping_session.imdb_id,
            media_type=cast(Literal["movie", "tv"] | None, scraping_session.media_type),
        )

        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        item = session.merge(item)

        info = debrid_service.get_torrent_info(scraping_session.torrent_id)
        if not info or not info.files:
            raise HTTPException(
                status_code=500,
                detail="Failed to retrieve torrent info — torrent may have expired",
            )

        item_type = item.type if item.type != "mediaitem" else "movie"
        file_id_set = set(file_ids)
        container_files = list[DebridFile]()

        for fid, meta in info.files.items():
            if fid not in file_id_set:
                continue
            if not meta.download_url:
                logger.warning(f"No download URL for file {fid} ({meta.filename}), skipping")
                continue
            try:
                df = DebridFile.create(
                    path=meta.path,
                    filename=meta.filename,
                    filesize_bytes=meta.bytes,
                    filetype=item_type,
                    file_id=fid,
                )
                df.download_url = meta.download_url
                container_files.append(df)
            except Exception as e:
                logger.warning(f"Skipping file {meta.filename}: {e}")

        if not container_files:
            raise HTTPException(
                status_code=500,
                detail="No files with download URLs found — torrent may not be cached",
            )

        assert scraping_session.torrent_info
        assert scraping_session.magnet

        download_result = DownloadedTorrent(
            id=scraping_session.torrent_id,
            infohash=scraping_session.magnet,
            container=TorrentContainer(
                infohash=scraping_session.magnet,
                files=container_files,
            ),
            info=info,
        )

        processed_ids: set[str] = set()
        if not downloader.update_item_attributes(
            item, download_result, debrid_service, processed_ids
        ):
            raise HTTPException(status_code=500, detail="No files matched any episodes")

        # Matched episodes → Downloaded.
        # Unmatched episodes still in idle states → Paused.
        # Episodes already Downloaded/Symlinked/Completed are left untouched.
        _IDLE_STATES = frozenset({
            States.Indexed, States.Unknown, States.Requested, States.Scraped,
        })

        if isinstance(item, (Show, Season)):
            seasons = item.seasons if isinstance(item, Show) else [item]
            for season in seasons:
                for episode in season.episodes:
                    if str(episode.id) in processed_ids:
                        MediaItem.store_state(episode, States.Downloaded)
                    elif episode.last_state in _IDLE_STATES:
                        MediaItem.store_state(episode, States.Paused)
                MediaItem.store_state(season)
            if isinstance(item, Show):
                MediaItem.store_state(item)
        elif isinstance(item, Movie):
            if str(item.id) in processed_ids:
                MediaItem.store_state(item, States.Downloaded)

        session.commit()

        # Emit events for matched items → Filesystem → Symlinker
        if isinstance(item, (Show, Season)):
            for season in (item.seasons if isinstance(item, Show) else [item]):
                for episode in season.episodes:
                    if str(episode.id) in processed_ids:
                        di[Program].em.add_event(Event("Downloader", episode.id))
        else:
            di[Program].em.add_event(Event("Downloader", item.id))

        return item.log_string


@router.post(
    "/session/{session_id}",
    summary="Perform an action on a scraping session",
    operation_id="session_action",
)
async def session_action(
    background_tasks: BackgroundTasks,
    session_id: Annotated[
        str,
        Path(description="Identifier of the scraping session"),
    ],
    request: Annotated[
        SessionActionRequest,
        Body(description="Session action request"),
    ],
) -> MessageResponse | SelectFilesResponse:
    """
    Perform an action on a scraping session.
    
    Actions:
    - select_files: Select files from the torrent (requires `files` in body)
    - update_attributes: Apply file attributes to media item (requires `file_data` in body)
    - abort: Cancel the session and clean up
    - complete: Finalize the session
    """
    logger.debug(f"Session action: {request.action} for session {session_id}")
    scraping_session = scraping_session_manager.get_session(session_id)

    if not scraping_session:
        known_ids = list(scraping_session_manager.sessions.keys())
        logger.warning(f"Session {session_id} not found. Active sessions: {known_ids}")
        raise HTTPException(status_code=404, detail="Session not found or expired")

    # === SELECT FILES ===
    if request.action == "select_files":
        if not request.files:
            raise HTTPException(status_code=400, detail="files required for select_files action")
        
        if services := di[Program].services:
            downloader = services.downloader
        else:
            raise HTTPException(status_code=412, detail="Required services not initialized")
        
        if not scraping_session.torrent_id:
            scraping_session_manager.abort_session(session_id)
            raise HTTPException(status_code=500, detail="No torrent ID found")
        
        download_type: Literal["cached", "uncached"] = "uncached"
        if scraping_session.containers and request.files.model_dump() in scraping_session.containers:
            download_type = "cached"
        
        try:
            file_ids = [int(fid) for fid in request.files.root.keys() if fid.isdigit()]
            downloader.select_files(scraping_session.torrent_id, file_ids)
            scraping_session.selected_files = request.files.model_dump()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        
        return SelectFilesResponse(
            message=f"Selected files for {scraping_session.item_id}",
            download_type=download_type,
        )

    # === UPDATE ATTRIBUTES ===
    if request.action == "update_attributes":
        if not request.file_data:
            raise HTTPException(status_code=400, detail="file_data required for update_attributes action")

        if not scraping_session.item_id:
            scraping_session_manager.abort_session(session_id)
            raise HTTPException(status_code=500, detail="No item ID found")

        if not scraping_session.torrent_id:
            scraping_session_manager.abort_session(session_id)
            raise HTTPException(status_code=500, detail="No torrent ID found in session")

        data = request.file_data

        # Extract file IDs from payload
        file_ids = list[int]()
        if isinstance(data, DebridFile):
            if data.file_id is not None:
                file_ids.append(data.file_id)
        else:
            for season_num, episodes in data.root.items():
                for ep_num, ep_data in episodes.items():
                    if ep_data.file_id is not None:
                        file_ids.append(ep_data.file_id)

        if not file_ids:
            raise HTTPException(status_code=400, detail="No file IDs in payload")

        result = _download_and_update(scraping_session, file_ids)
        return MessageResponse(message=f"Updated given data to {result}")

    # === ABORT ===
    if request.action == "abort":
        background_tasks.add_task(scraping_session_manager.abort_session, session_id)
        return MessageResponse(message=f"Aborted session {session_id}")

    # === COMPLETE ===
    if request.action == "complete":
        if not all([scraping_session.torrent_id, scraping_session.selected_files]):
            raise HTTPException(status_code=400, detail="Session is incomplete")

        if not scraping_session.item_id:
            scraping_session_manager.abort_session(session_id)
            raise HTTPException(status_code=500, detail="No item ID found")

        # Extract file IDs from selected_files (set during select_files action)
        file_ids = [int(fid) for fid in scraping_session.selected_files.keys() if str(fid).isdigit()]
        if not file_ids:
            raise HTTPException(status_code=400, detail="No file IDs in selected files")

        _download_and_update(scraping_session, file_ids)
        scraping_session_manager.complete_session(session_id)
        return MessageResponse(message=f"Completed session {session_id}")

    raise HTTPException(status_code=400, detail=f"Unknown action: {request.action}")


class ParseTorrentTitleResponse(BaseModel):
    message: str
    data: list[dict[str, Any]]


class AutoScrapeRequest(BaseModel):
    media_type: Literal["movie", "tv"]
    item_id: int | None = None
    tmdb_id: str | None = None
    tvdb_id: str | None = None
    imdb_id: str | None = None
    ranking_overrides: dict[str, list[str]] | None = None
    season_numbers: list[int] | None = None  # If provided for TV, scrape specific seasons
    min_filesize_override: int | None = None
    max_filesize_override: int | None = None


class StatelessSelectFilesRequest(BaseModel):
    magnet: str
    items: Container
    item_id: int | None = None
    tmdb_id: str | None = None
    tvdb_id: str | None = None
    imdb_id: str | None = None
    media_type: Literal["movie", "tv"] | None = None


@router.post(
    "/auto",
    summary="Trigger auto scraping for an item or specific seasons",
    operation_id="auto_scrape",
    response_model=MessageResponse,
)
async def auto_scrape(
    request: Annotated[AutoScrapeRequest, Body(description="Auto scrape request")],
) -> MessageResponse:
    """Trigger auto scraping. For TV shows, optionally provide season_numbers to scrape specific seasons."""

    overrides = get_overrides_dict(
        ranking_overrides=request.ranking_overrides,
        min_filesize_override=request.min_filesize_override,
        max_filesize_override=request.max_filesize_override,
    )

    with db_session() as session:
        item = resolve_media_item(
            session,
            request.item_id,
            request.tmdb_id,
            request.tvdb_id,
            request.imdb_id,
            request.media_type,
        )

        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        # If season_numbers provided for TV, scrape specific seasons
        if request.season_numbers and request.media_type == "tv":
            if not isinstance(item, Show):
                raise HTTPException(status_code=400, detail="Item is not a TV show")

            # Re-query with eager loading to ensure seasons and episodes are available
            from sqlalchemy import select
            from sqlalchemy.orm import selectinload

            item = session.execute(
                select(Show)
                .options(selectinload(Show.seasons).selectinload(Season.episodes))
                .where(Show.id == item.id)
            ).scalar_one()

            seasons_to_scrape: list[Season] = []
            seasons_to_pause: list[Season] = []
            
            for season in item.seasons:
                if season.number in request.season_numbers:
                    seasons_to_scrape.append(season)
                else:
                    seasons_to_pause.append(season)

            if not seasons_to_scrape:
                logger.warning("No matching seasons found in DB for requested numbers")
                raise HTTPException(status_code=404, detail="No matching seasons found")

            # 1. Update states first (Unpause selected, Pause unselected)
            for season in seasons_to_scrape:
                # Unpause episodes first so season state correctly evaluates them
                for episode in season.episodes:
                    MediaItem.store_state(episode, None)

                if season.last_state == States.Paused:
                    logger.info(f"Unpausing season {season.number}")
                    MediaItem.store_state(season, None)

            for season in seasons_to_pause:
                # Find which episodes in this unselected season need to be paused
                episodes_to_pause = []
                has_active_episodes = False

                for episode in season.episodes:
                    if episode.state not in (
                        States.Downloaded,
                        States.Symlinked,
                        States.Completed,
                        States.PartiallyCompleted,
                        States.Paused,
                    ):
                        episodes_to_pause.append(episode)
                    elif episode.state != States.Paused:
                        has_active_episodes = True

                # Only pause the season itself if it has NO active/completed episodes
                if not has_active_episodes and season.state != States.Paused:
                    MediaItem.store_state(season, States.Paused)
                elif has_active_episodes and season.last_state == States.Paused:
                    # If it has active episodes but was paused, unpause it
                    MediaItem.store_state(season, None)
                
                # Pause the unselected/incomplete episodes
                for episode in episodes_to_pause:
                    MediaItem.store_state(episode, States.Paused)

            # Commit state changes so Event Manager sees them
            session.commit()

            # 2. Dispatch season-level events only.
            # The scraper will find season packs and individual episodes alike;
            # the downloader will match files to child episodes automatically.
            # Do NOT dispatch per-episode events here — they would race with the
            # season event and cause redundant per-episode scraping.
            for season in seasons_to_scrape:
                di[Program].em.add_event(
                    Event(
                        "API",
                        season.id,
                        overrides=overrides,
                    )
                )

            return MessageResponse(
                message=f"Started scrape for {len(seasons_to_scrape)} seasons of {item.log_string} (paused {len(seasons_to_pause)} others)"
            )

        # Scrape entire item
        di[Program].em.add_event(
            Event(
                "API",
                item.id,
                overrides=overrides,
            )
        )
        return MessageResponse(message=f"Started auto scrape for {item.log_string}")


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
