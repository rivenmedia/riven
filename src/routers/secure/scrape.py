from datetime import datetime, timedelta
from typing import Annotated, Any, Literal, TypeAlias
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    HTTPException,
    Path,
    Query,
)
from kink import di
from loguru import logger
from PTT import parse_title  # pyright: ignore[reportUnknownVariableType]
from pydantic import BaseModel, ConfigDict, Field, RootModel
from sqla_wrapper import Session
from sqlalchemy.orm import object_session

from program.db import db_functions
from program.db.db import db_session
from program.media.item import Episode, MediaItem, Season, Show
from program.media.state import States
from program.media.stream import Stream as ItemStream
from program.services.downloaders import Downloader
from program.services.downloaders.models import (
    DebridFile,
    TorrentContainer,
    TorrentInfo,
)
from program.services.indexers import IndexerService
from program.services.scrapers.shared import rtn
from program.types import Event
from program.utils.torrent import extract_infohash
from program.program import Program
from program.media.models import ActiveStream
from program.program import Program
from program.media.models import ActiveStream
from ..models.shared import MessageResponse


class Stream(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    infohash: str
    raw_title: str
    parsed_title: str
    parsed_data: Any
    rank: int
    lev_ratio: float
    resolution: str


class ScrapeItemResponse(BaseModel):
    message: str
    streams: dict[str, Stream]


class StartSessionResponse(BaseModel):
    message: str
    session_id: str
    torrent_id: str | int
    torrent_info: TorrentInfo
    containers: TorrentContainer | None
    expires_at: str


class SelectFilesResponse(BaseModel):
    message: str
    download_type: Literal["cached", "uncached"]


class UpdateAttributesResponse(BaseModel):
    message: str


class SessionResponse(BaseModel):
    message: str


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


class ScrapingSession:
    def __init__(
        self,
        id: str,
        item_id: str | None = None,
        media_type: Literal["movie", "tv"] | None = None,
        imdb_id: str | None = None,
        tmdb_id: str | None = None,
        tvdb_id: str | None = None,
        magnet: str | None = None,
        service: str | None = None,
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
        magnet: str,
        item_id: str | None = None,
        media_type: Literal["movie", "tv"] | None = None,
        imdb_id: str | None = None,
        tmdb_id: str | None = None,
        tvdb_id: str | None = None,
        service: str | None = None,
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


@router.get(
    "/",
    summary="Get streams for an item",
    operation_id="scrape_item",
    response_model=ScrapeItemResponse,
)
def scrape_item(
    item_id: Annotated[
        int | None,
        Query(description="The ID of the media item"),
    ] = None,
    tmdb_id: Annotated[
        int | None,
        Query(description="The TMDB ID of the media item"),
    ] = None,
    tvdb_id: Annotated[
        int | None,
        Query(description="The TVDB ID of the media item"),
    ] = None,
    imdb_id: Annotated[
        int | None,
        Query(description="The IMDB ID of the media item"),
    ] = None,
    media_type: Annotated[
        Literal["movie", "tv"] | None,
        Query(description="The media type"),
    ] = None,
) -> ScrapeItemResponse:
    """Get streams for an item by any supported ID (item_id, tmdb_id, tvdb_id, imdb_id)"""

    if services := di[Program].services:
        indexer = services.indexer
        scraper = services.scraping
    else:
        raise HTTPException(status_code=412, detail="Scraping services not initialized")

    log_string = None
    item = None
    indexer_result = None

    with db_session():
        if item_id:
            item = db_functions.get_item_by_id(int(item_id))
        elif tmdb_id and media_type == "movie":
            prepared_item = MediaItem(
                {
                    "tmdb_id": tmdb_id,
                    "requested_by": "riven",
                    "requested_at": datetime.now(),
                }
            )
            indexer_result = next(indexer.run(prepared_item), None)
        elif tvdb_id and media_type == "tv":
            prepared_item = MediaItem(
                {
                    "tvdb_id": tvdb_id,
                    "requested_by": "riven",
                    "requested_at": datetime.now(),
                }
            )
            indexer_result = next(indexer.run(prepared_item), None)
        elif imdb_id:
            prepared_item = MediaItem(
                {
                    "imdb_id": imdb_id,
                    "tvdb_id": tvdb_id,
                    "requested_by": "riven",
                    "requested_at": datetime.now(),
                }
            )
            indexer_result = next(indexer.run(prepared_item), None)
        else:
            raise HTTPException(status_code=400, detail="No valid ID provided")

        if indexer_result:
            item = indexer_result.media_items[0]

        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        streams = scraper.scrape(item, manual=True)
        log_string = item.log_string

    return ScrapeItemResponse(
        message=f"Manually scraped streams for item {log_string}",
        streams={
            stream.infohash: Stream.model_validate(stream)
            for stream in streams.values()
        },
    )
    return ScrapeItemResponse(
        message=f"Manually scraped streams for item {log_string}",
        streams={
            stream.infohash: Stream.model_validate(stream)
            for stream in streams.values()
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
        str | None,
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
        indexer = services.indexer
        downloader = services.downloader
    else:
        raise HTTPException(status_code=412, detail="Required services not initialized")

    initialize_downloader(downloader)

    item = None
    
    # 1. Try to find existing item in DB
    if item_id:
        item = db_functions.get_item_by_id(int(item_id))
    else:
        try:
            item = db_functions.get_item_by_external_id(
                tmdb_id=tmdb_id,
                tvdb_id=tvdb_id,
                imdb_id=imdb_id
            )
        except ValueError:
            pass

    # 2. If not found, create/fetch it using indexer
    if not item:
        if tmdb_id and media_type == "movie":
            prepared_item = MediaItem(
                {
                    "tmdb_id": tmdb_id,
                    "requested_by": "riven",
                    "requested_at": datetime.now(),
                }
            )
            result = next(indexer.run(prepared_item), None)
            if result and result.media_items:
                item = result.media_items[0]
        elif tvdb_id and media_type == "tv":
            prepared_item = MediaItem(
                {
                    "tvdb_id": tvdb_id,
                    "requested_by": "riven",
                    "requested_at": datetime.now(),
                }
            )
            result = next(indexer.run(prepared_item), None)
            if result and result.media_items:
                item = result.media_items[0]
        elif imdb_id:
            prepared_item = MediaItem(
                {
                    "imdb_id": imdb_id,
                    "requested_by": "riven",
                    "requested_at": datetime.now(),
                }
            )
            result = next(indexer.run(prepared_item), None)
            if result and result.media_items:
                item = result.media_items[0]
        else:
            raise HTTPException(status_code=400, detail="No valid ID provided")

        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

    if item.type == "mediaitem":
        raise HTTPException(status_code=500, detail="Incorrect item type found")

    container = downloader.get_instant_availability(
        info_hash, item.type, limit_filesize=not disable_filesize_check
    )

    if not container or not container.cached:
        raise HTTPException(
            status_code=400, detail="Torrent is not cached, please try another stream"
        )

    session = scraping_session_manager.create_session(
        magnet,
        item_id=str(item.id) if item.id else None,
        media_type=media_type,
        imdb_id=imdb_id,
        tmdb_id=tmdb_id,
        tvdb_id=tvdb_id,
        service=container.service,
    )

    logger.debug(f"Created session {session.id} with item ID: {session.item_id}")

    try:
        service_instance = downloader.get_service(container.service) if container.service else None
        torrent_id = downloader.add_torrent(info_hash, service=service_instance)
        torrent_info = downloader.get_torrent_info(torrent_id, service=service_instance)
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
        expires_at=session.expires_at.isoformat() + "Z",
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
        service_instance = downloader.get_service(session.service) if session.service else None
        downloader.select_files(
            session.torrent_id, [int(file_id) for file_id in files.root.keys()], service=service_instance
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
    response_model=UpdateAttributesResponse,
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
    session: Session = Depends(db_session.__wrapped__),
) -> UpdateAttributesResponse:
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

    # Note: We removed the strict check for item_id here to allow for items that haven't been persisted yet.
    # The item lookup logic below handles cases where item_id is missing.

    item = None
    item_ids_to_submit = None

    if scraping_session.item_id:
        item = db_functions.get_item_by_id(int(scraping_session.item_id))

    if not item:
        # Try to find by any external ID
        try:
            item = db_functions.get_item_by_external_id(
                tmdb_id=str(scraping_session.tmdb_id) if scraping_session.tmdb_id else None,
                tvdb_id=str(scraping_session.tvdb_id) if scraping_session.tvdb_id else None,
                imdb_id=scraping_session.imdb_id
            )
        except ValueError:
            pass

    if not item:
        item_data = {
            k: v for k, v in {
                "imdb_id": scraping_session.imdb_id,
                "tmdb_id": scraping_session.tmdb_id,
                "tvdb_id": scraping_session.tvdb_id,
                "requested_by": "riven",
                "requested_at": datetime.now(),
            }.items() if v
        }

        if item_data:
            result = next(IndexerService().run(MediaItem(item_data)), None)
            if result and result.media_items:
                indexed = result.media_items[0]
                # Check if the indexed item actually exists (e.g. via a newly discovered ID)
                try:
                    if existing := db_functions.get_item_by_external_id(
                        tmdb_id=str(indexed.tmdb_id) if indexed.tmdb_id else None,
                        tvdb_id=str(indexed.tvdb_id) if indexed.tvdb_id else None,
                        imdb_id=str(indexed.imdb_id) if indexed.imdb_id else None,
                        session=session
                    ):
                        indexed.id = existing.id
                except ValueError:
                    pass
                
                item = session.merge(indexed)
                session.commit()

        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

    item = session.merge(item)
    item_ids_to_submit = set[int]()

    if services := di[Program].services:
        downloader = services.downloader
    else:
        raise HTTPException(status_code=412, detail="Required services not initialized")

    service_instance = downloader.get_service(scraping_session.service) if scraping_session.service else None

    def update_item(item: MediaItem, data: DebridFile):
        """
        Prepare and attach a filesystem entry and stream to a MediaItem based on a selected DebridFile within a scraping session.

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

        if item.media_entry and data.filename:
            fs_entry = item.media_entry
            # Update source metadata on existing entry
            fs_entry.original_filename = data.filename
        else:
            # Create a provisional VIRTUAL entry (download_url/provider may be filled by downloader later)
            provider = service_instance.key if service_instance else None

            # Get torrent ID from scraping session
            torrent_id = (
                scraping_session.torrent_info.id if scraping_session.torrent_info else None
            )
            
            download_url = data.download_url
            
            # If download_url is missing, try to refresh torrent info to get it
            if not download_url and torrent_id and service_instance:
                try:
                    logger.debug(f"Refreshing torrent info for {torrent_id} to resolve download_url")
                    fresh_info = service_instance.get_torrent_info(torrent_id)
                    
                    # Find matching file
                    for file in fresh_info.files.values():
                        if file.filename == data.filename:
                            if file.download_url:
                                download_url = file.download_url
                                logger.debug(f"Resolved download_url for {data.filename}: {download_url}")
                            break
                except Exception as e:
                    logger.warning(f"Failed to refresh torrent info: {e}")

            logger.debug(f"Manual Update Attributes: provider={provider}, torrent_id={torrent_id}, download_url={download_url}")

            fs_entry = MediaEntry.create_placeholder_entry(
                original_filename=data.filename,
                download_url=download_url,
                provider=provider,
                provider_download_id=str(torrent_id) if torrent_id else None,
                file_size=data.filesize or 0,
            )


            session.add(fs_entry)
            session.flush()
            
            # Link MediaItem to FilesystemEntry
            # Clear existing entries and add the new one
            item.filesystem_entries.clear()
            item.filesystem_entries.append(fs_entry)
            item = session.merge(item)

        assert scraping_session
        assert scraping_session.magnet
        assert scraping_session.torrent_info

        infohash = scraping_session.torrent_info.infohash
        if not infohash:
            infohash = extract_infohash(scraping_session.magnet)

        item.active_stream = ActiveStream(
            infohash=infohash,
            id=scraping_session.torrent_info.id,
        )

        torrent = rtn.rank(
            scraping_session.torrent_info.name,
            infohash,
        )

        # Ensure the item is properly attached to the session before adding streams
        # This prevents SQLAlchemy warnings about detached objects
        if object_session(item) is not session:
            item = session.merge(item)
        # Ensure the item is properly attached to the session before adding streams
        # This prevents SQLAlchemy warnings about detached objects
        if object_session(item) is not session:
            item = session.merge(item)

        item.streams.append(ItemStream(torrent=torrent))
        item_ids_to_submit.add(item.id)

    if isinstance(data, DebridFile):
        update_item(item, data)
    else:
        updated_episode_ids = set[int]()

        for season_number, episodes in data.root.items():
            for episode_number, episode_data in episodes.items():
                if isinstance(item, Show):
                    if episode := item.get_absolute_episode(
                        episode_number, season_number
                    ):
                        update_item(episode, episode_data)
                        updated_episode_ids.add(episode.id)
                    else:
                        logger.error(
                            f"Failed to find episode {episode_number} for season {season_number} for {item.log_string}"
                        )

                        continue
                elif isinstance(item, Season):
                    if episode := item.parent.get_absolute_episode(
                        episode_number, season_number
                    ):
                        update_item(episode, episode_data)
                        updated_episode_ids.add(episode.id)
                    else:
                        logger.error(
                            f"Failed to find season {season_number} for {item.log_string}"
                        )

                        continue
                elif isinstance(item, Episode):
                    if (
                        season_number != item.parent.number
                        and episode_number != item.number
                    ):
                        continue

                    update_item(item, episode_data)
                    updated_episode_ids.add(item.id)

                    break
                else:
                    logger.error(f"Failed to find item type for {item.log_string}")
                    continue

        # Set unselected episodes to paused
        if isinstance(item, Show):
            logger.debug(f"Checking {len(item.seasons)} seasons for unselected episodes to pause")
            for season in item.seasons:
                logger.debug(f"Season {season.number} has {len(season.episodes)} episodes")
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
                        logger.debug(f"Paused episode {episode.log_string} (ID: {episode.id})")
        elif isinstance(item, Season):
            logger.debug(f"Checking {len(item.episodes)} episodes in season {item.number} to pause")
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
                    logger.debug(f"Paused episode {episode.log_string} (ID: {episode.id})")

    item.store_state()

    log_string = item.log_string
    session.merge(item)
    session.commit()

    # Sync VFS to reflect any deleted/updated entries
    # Must happen AFTER commit so the database reflects the changes
    from program.services.filesystem import FilesystemService

    if filesystem_service := di[Program].services.filesystem:
        filesystem_service.riven_vfs.sync(item)
        logger.debug("VFS synced after manual scraping update")

    for item_id in item_ids_to_submit:
        di[Program].em.add_event(Event("ManualAPI", item_id))

    return UpdateAttributesResponse(message=f"Updated given data to {log_string}")


@router.post(
    "/abort_session/{session_id}",
    summary="Abort a manual scraping session",
    operation_id="abort_manual_session",
    response_model=SessionResponse,
)
async def abort_manual_session(
    background_tasks: BackgroundTasks,
    session_id: Annotated[
        str,
        Path(
            description="Identifier of the scraping session containing item and torrent context."
        ),
    ],
) -> SessionResponse:
    session = scraping_session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    background_tasks.add_task(scraping_session_manager.abort_session, session_id)
    return SessionResponse(message=f"Aborted session {session_id}")


@router.post(
    "/complete_session/{session_id}",
    summary="Complete a manual scraping session",
    operation_id="complete_manual_session",
    response_model=SessionResponse,
)
async def complete_manual_session(
    session_id: Annotated[
        str,
        Path(
            description="Identifier of the scraping session containing item and torrent context."
        ),
    ],
) -> SessionResponse:
    session = scraping_session_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    if not all([session.torrent_id, session.selected_files]):
        raise HTTPException(status_code=400, detail="Session is incomplete")

    scraping_session_manager.complete_session(session_id)
    return SessionResponse(message=f"Completed session {session_id}")


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
    parsed_titles = []
    if titles:
        for title in titles:
            data = {}
            data["raw_title"] = title
            parsed_data = parse_title(title)
            data = {**data, **parsed_data}
            parsed_titles.append(data)
        if parsed_titles:
            return ParseTorrentTitleResponse(
                message="Parsed torrent titles", data=parsed_titles
            )
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
    db: Session = Depends(db_session.__wrapped__),
) -> MessageResponse:
    """Get all overseerr requests and make sure they exist in the database"""
    from program.apis.overseerr_api import OverseerrAPI
    from program.db.db_functions import item_exists_by_any_id

    overseerr_api = di[OverseerrAPI]
    o_items = overseerr_api.get_media_requests("overseerr", filter, take)

    if not o_items:
        return MessageResponse(message="Submitted overseerr requests to the queue")

    overseerr_items = [
        item
        for item in o_items
        if not item_exists_by_any_id(
            tvdb_id=item.tvdb_id,
            tmdb_id=item.tmdb_id,
            session=db,
        )
    ]

    logger.info(f"Found {len(overseerr_items)} new overseerr requests")

    if overseerr_items:
        # Persist first, then enqueue
        persisted_items = list[MediaItem]()

        for item in overseerr_items:
            persisted = db.merge(item)
            persisted_items.append(persisted)

        db.commit()

        for persisted in persisted_items:
            di[Program].em.add_item(persisted, service="Overseerr")

    return MessageResponse(message="Submitted overseerr requests to the queue")

class AutoScrapeRequest(BaseModel):
    item_id: str | None = None
    tmdb_id: str | None = None
    tvdb_id: str | None = None
    imdb_id: str | None = None
    media_type: Literal["movie", "tv"] | None = None
    resolutions: list[str] | None = None
    quality: list[str] | None = None
    rips: list[str] | None = None
    hdr: list[str] | None = None
    audio: list[str] | None = None
    extras: list[str] | None = None
    trash: list[str] | None = None
    require: list[str] | None = None
    exclude: list[str] | None = None


@router.post(
    "/auto",
    summary="Auto scrape an item with resolution overrides",
    operation_id="auto_scrape_item",
)
async def auto_scrape_item(
    body: AutoScrapeRequest,
) -> MessageResponse:
    """
    Auto scrape an item with specific resolution overrides.
    This performs a one-time scrape using the provided resolutions
    and triggers the downloader if new streams are found.
    """
    if services := di[Program].services:
        scraper = services.scraping
        indexer = services.indexer
    else:
        raise HTTPException(status_code=412, detail="Services not initialized")

    item = None
    with db_session() as session:
        if body.item_id:
            item = db_functions.get_item_by_id(int(body.item_id), session=session)
        elif body.tmdb_id and body.media_type == "movie":
            prepared_item = MediaItem(
                {
                    "tmdb_id": body.tmdb_id,
                    "requested_by": "riven",
                    "requested_at": datetime.now(),
                }
            )
            if result := next(indexer.run(prepared_item), None):
                item = result.media_items[0] if result.media_items else None
        elif body.tvdb_id and body.media_type == "tv":
            prepared_item = MediaItem(
                {
                    "tvdb_id": body.tvdb_id,
                    "requested_by": "riven",
                    "requested_at": datetime.now(),
                }
            )
            if result := next(indexer.run(prepared_item), None):
                item = result.media_items[0] if result.media_items else None
        elif body.imdb_id:
            prepared_item = MediaItem(
                {
                    "imdb_id": body.imdb_id,
                    "tvdb_id": body.tvdb_id, # imdb_id alone is not enough for TV, needs tvdb_id
                    "requested_by": "riven",
                    "requested_at": datetime.now(),
                }
            )
            if result := next(indexer.run(prepared_item), None):
                item = result.media_items[0] if result.media_items else None
        
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        # Scrape with overrides
        streams = scraper.scrape(item, ranking_overrides=body.model_dump(exclude_unset=True))
        
        # Filter out existing or blacklisted streams
        new_streams = [
            stream
            for stream in streams.values()
            if stream not in item.streams and stream not in item.blacklisted_streams
        ]

        if new_streams:
            item.streams.extend(new_streams)
            from program.media.state import States
            item.store_state(States.Scraped) # Force state update to trigger downloader
            logger.info(f"Auto scrape found {len(new_streams)} new streams for {item.log_string}")
            
            # Commit changes to DB
            session.add(item)
            session.commit()
            
            # Emit event to trigger downloader
            di[Program].em.add_event(Event("Scraping", item_id=item.id))
            
            return {"message": f"Auto scrape started. Found {len(new_streams)} new streams."}
        else:
            return {"message": "Auto scrape completed. No new streams found."}