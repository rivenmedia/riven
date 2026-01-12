from datetime import datetime, timedelta
from typing import Annotated, Any, Literal, TypeAlias
from uuid import uuid4

from RTN import ParsedData, parse, Torrent
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

from program.db import db_functions
from program.db.db import db_session
from program.media.item import Episode, MediaItem, Season, Show, ProcessedItemType
from program.media.state import States
from program.media.stream import Stream as ItemStream
from program.services.downloaders import Downloader
from program.services.downloaders.models import (
    DebridFile,
    TorrentContainer,
    TorrentInfo,
)
from program.services.scrapers.shared import get_ranking_overrides
from program.types import Event
from program.utils.torrent import extract_infohash
from program.program import Program
from program.media.models import ActiveStream
from ..models.shared import MessageResponse
from program.settings import settings_manager
from program.settings.models import RTNSettingsModel




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
                        valid_files = []
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
    item = db_functions.get_or_create_media_item(
        session, item_id, tmdb_id, tvdb_id, imdb_id, media_type
    )
    
    if not item and raise_on_not_found:
        raise HTTPException(status_code=404, detail="Item not found")
    
    if item and item.type == "mediaitem":
        raise HTTPException(status_code=400, detail="Unresolved mediaitem type")
    
    return item

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
):
    """Get streams for an item. Set stream=true for SSE streaming as scrapers complete."""

    if services := di[Program].services:
        scraper = services.scraping
    else:
        raise HTTPException(status_code=412, detail="Scraping services not initialized")

    # Prepare overrides dictionary
    overrides = rtn_settings_override.model_dump() if rtn_settings_override else {}
    if min_filesize_override is not None:
        overrides["min_filesize"] = min_filesize_override
    if max_filesize_override is not None:
        overrides["max_filesize"] = max_filesize_override

    def apply_custom_params(item: MediaItem) -> None:
        """Apply custom scrape parameters (not persisted to DB)"""
        # If any custom param is used, clear strict metadata to allow overrides
        if custom_title or custom_imdb_id:
            item.tmdb_id = None
            item.tvdb_id = None
            item.year = None
            item.aired_at = None
        
        if custom_title:
            item.title = custom_title
            # If no custom IMDB ID provided, clear original IMDB ID to force text search
            if not custom_imdb_id:
                item.imdb_id = None

        if custom_imdb_id:
            item.imdb_id = custom_imdb_id

    if stream:
        # SSE streaming mode
        if not any([item_id, tmdb_id and media_type == "movie", tvdb_id and media_type == "tv", imdb_id]):
            raise HTTPException(status_code=400, detail="No valid ID provided")

        def generate_events():
            with db_session() as session:
                item = resolve_media_item(session, item_id, tmdb_id, tvdb_id, imdb_id, media_type)

                if not item:
                    error_event = ScrapeStreamEvent(event="error", message="Item not found")
                    yield f"data: {error_event.model_dump_json()}\n\n"
                    return
                
                # Detach item from session to avoid threading issues in scraper
                session.expunge(item)
                
                # Apply custom params to the detached item
                apply_custom_params(item)

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
                    for service_name, parsed_streams in scraper.scrape_streaming(
                        item, manual=True
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
                            message=f"{service_name} found {len(new_streams)} new streams" if new_streams else f"{service_name} completed",
                            streams=new_streams if new_streams else None,
                            total_streams=len(all_streams),
                            services_completed=services_completed,
                            total_services=total_services,
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

        return StreamingResponse(
            generate_events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    # Standard JSON response mode
    with db_session() as session:
        item = resolve_media_item(session, item_id, tmdb_id, tvdb_id, imdb_id, media_type)
        assert item
        apply_custom_params(item)

        with settings_manager.override(**overrides):
            streams = scraper.scrape(item, manual=True)

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

    item = None

    with db_session() as session:
        item = resolve_media_item(session, item_id, tmdb_id, tvdb_id, imdb_id, media_type)

        # ensure item is present
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        # Use async container resolution with fallback
        # Cast type to ProcessedItemType if it's not 'mediaitem'
        item_type: ProcessedItemType = cast(ProcessedItemType, item.type) if item.type != "mediaitem" else "movie"
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
                    parsed_data = parse_title(file.filename)
                    parsed_files.append(
                        ParsedFile(
                            file_id=file.file_id,
                            filename=file.filename,
                            filesize=file.filesize,
                            download_url=file.download_url,
                            parsed_metadata=parsed_data,
                        )
                    )
                except Exception as e:
                    logger.warning(f"Failed to parse title for {file.filename}: {e}")
                    continue

        return StartSessionResponse(
            message="Started manual scraping session",
            session_id=session_obj.id,
            item_id=item.id,
            media_type=media_type,
            tmdb_id=tmdb_id,
            tvdb_id=tvdb_id,
            imdb_id=imdb_id,
            torrent_id=torrent_id,
            torrent_info=torrent_info,
            containers=container,
            parsed_files=parsed_files,
            expires_at=session_obj.expires_at.isoformat(),
        )


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
    scraping_session = scraping_session_manager.get_session(session_id)
    
    if not scraping_session:
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
        
        data = request.file_data
        
        if services := di[Program].services:
            downloader = services.downloader
        else:
            raise HTTPException(status_code=500, detail="Downloader service not available")
        
        with db_session() as session:
            item = resolve_media_item(
                session=session,
                tmdb_id=scraping_session.tmdb_id,
                tvdb_id=scraping_session.tvdb_id,
                imdb_id=scraping_session.imdb_id,
                media_type=scraping_session.media_type,
            )
            
            if not item:
                raise HTTPException(status_code=404, detail="Item not found")
            
            # Ensure attached to session
            item = session.merge(item)
            
            # Extract selected file IDs and active seasons from payload
            file_ids = []
            active_seasons = set[int]()
            
            if isinstance(data, DebridFile):
                if data.file_id:
                    file_ids.append(data.file_id)
            elif isinstance(data, RootModel): # ShowFileData
                 # Extract file IDs and Season numbers
                 for season_num, episodes in data.root.items():
                     active_seasons.add(season_num)
                     for ep_data in episodes.values():
                         if ep_data.file_id:
                             file_ids.append(ep_data.file_id)

            # Construct synthetic Stream object for the downloader
            # We use RTN to parse the release title to satisfy Stream requirements
            parsed_data = parse(scraping_session.torrent_info.name)
            torrent = Torrent(
                raw_title=scraping_session.torrent_info.name,
                infohash=scraping_session.magnet,
                data=parsed_data,
                rank=0,
                lev_ratio=1.0
            )
            stream = ItemStream(torrent)
            
            # Start Manual Download via Downloader Service
            # This handles validation, downloading, and attribute updates in one go
            success = downloader.start_manual_download(
                item=item,
                stream=stream,
                service=downloader.service, # Use primary service
                file_ids=file_ids,
            )
            
            if not success:
               logger.error(f"Manual download failed for {item.log_string}")
               raise HTTPException(status_code=500, detail="Failed to start manual download")
            
            # Update Season States (Pause unselected / Unpause selected)
            # Update Season States (Pause unselected / Unpause selected)
            if isinstance(item, Show) and active_seasons:

                logger.info(f"Updating season states for {item.log_string}. Active seasons: {active_seasons}")
                
                for season in item.seasons:
                    if season.number in active_seasons:
                        if season.last_state == States.Paused:
                            season.store_state(States.Unknown)
                        # Ensure episodes are also unpaused
                        for episode in season.episodes:
                            if episode.last_state == States.Paused:
                                episode.store_state(States.Unknown)
                    else:
                        if season.last_state != States.Paused:
                            season.store_state(States.Paused)
                        # Ensure episodes are also paused
                        for episode in season.episodes:
                            if episode.last_state != States.Paused:
                                episode.store_state(States.Paused)
                
            session.commit()
            
            # Emit event as if Downloader just finished, to trigger Symlinker/Filesystem
            di[Program].em.add_event(Event("Downloader", item.id))
            
            return MessageResponse(message=f"Updated given data to {item.log_string}")

    # === ABORT ===
    if request.action == "abort":
        background_tasks.add_task(scraping_session_manager.abort_session, session_id)
        return MessageResponse(message=f"Aborted session {session_id}")

    # === COMPLETE ===
    if request.action == "complete":
        if not all([scraping_session.torrent_id, scraping_session.selected_files]):
            raise HTTPException(status_code=400, detail="Session is incomplete")
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

    rtn_settings_override_model = get_ranking_overrides(request.ranking_overrides)
    if not rtn_settings_override_model:
        rtn_settings_override_model = RTNSettingsModel(
            **settings_manager.settings.ranking.model_dump()
        )

    # Create overrides dict
    overrides = rtn_settings_override_model.model_dump()

    if request.min_filesize_override is not None:
        overrides["min_filesize"] = request.min_filesize_override
    if request.max_filesize_override is not None:
        overrides["max_filesize"] = request.max_filesize_override

    with db_session() as session:
        item = db_functions.get_or_create_media_item(
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
            from program.media.item import Season


            item = session.execute(
                select(Show)
                .options(selectinload(Show.seasons).selectinload(Season.episodes))
                .where(Show.id == item.id)
            ).scalar_one()

            seasons_to_scrape = []
            seasons_to_pause = []
            
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
                if season.last_state == States.Paused:
                    logger.info(f"Unpausing season {season.number}")
                    season.last_state = States.Unknown
                    session.merge(season)
                
                # Also unpause episodes in the selected season
                for episode in season.episodes:
                    if episode.last_state == States.Paused:
                        episode.last_state = States.Unknown
                        session.merge(episode)

            for season in seasons_to_pause:
                if season.state != States.Paused:
                    season.last_state = States.Paused
                    session.merge(season)
                
                for episode in season.episodes:
                    if episode.state not in (
                        States.Downloaded,
                        States.Symlinked,
                        States.Completed,
                        States.PartiallyCompleted,
                        States.Paused
                    ):
                        episode.last_state = States.Paused
                        session.merge(episode)            

            # Commit state changes so Event Manager sees them
            session.commit()

            # 2. Dispatch events
            for season in seasons_to_scrape:
                # Dispatch for Season (Packs)
                di[Program].em.add_event(
                    Event(
                        "API",
                        season.id,
                        overrides=overrides,
                    )
                )
                # Dispatch for Episodes (Individual files)
                for episode in season.episodes:
                    di[Program].em.add_event(
                        Event(
                            "API",
                            episode.id,
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
