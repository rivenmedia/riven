from datetime import datetime, timedelta
from typing import Any, Dict, Literal, Optional, TypeAlias, Union
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from loguru import logger
from PTT import parse_title
from pydantic import BaseModel, RootModel
from RTN import ParsedData
from sqla_wrapper import Session
from sqlalchemy.orm import object_session

from program.db import db_functions
from program.db.db import db, get_db
from program.media.item import MediaItem
from program.media.stream import Stream as ItemStream
from program.services.downloaders import Downloader
from program.services.downloaders.models import (
    DebridFile,
    TorrentContainer,
    TorrentInfo,
)
from program.services.indexers import IndexerService
from program.services.scrapers import Scraping
from program.services.scrapers.shared import rtn
from program.types import Event
from program.utils.torrent import extract_infohash
from ..models.shared import MessageResponse


class Stream(BaseModel):
    infohash: str
    raw_title: str
    parsed_title: str
    parsed_data: ParsedData
    rank: int
    lev_ratio: float
    is_cached: bool = False


class ScrapeItemResponse(BaseModel):
    message: str
    streams: Dict[str, Stream]


class StartSessionResponse(BaseModel):
    message: str
    session_id: str
    torrent_id: str
    torrent_info: TorrentInfo
    containers: Optional[TorrentContainer]
    expires_at: str


class SelectFilesResponse(BaseModel):
    message: str
    download_type: Literal["cached", "uncached"]


class UpdateAttributesResponse(BaseModel):
    message: str


class SessionResponse(BaseModel):
    message: str


ContainerMap: TypeAlias = Dict[str, DebridFile]


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


SeasonEpisodeMap: TypeAlias = Dict[int, Dict[int, DebridFile]]


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
        item_id: str,
        media_type: Optional[Literal["movie", "tv"]] = None,
        imdb_id: Optional[str] = None,
        tmdb_id: Optional[str] = None,
        tvdb_id: Optional[str] = None,
        magnet: str = None,
    ):
        self.id = id
        self.item_id = item_id
        self.media_type = media_type
        self.imdb_id = imdb_id
        self.tmdb_id = tmdb_id
        self.tvdb_id = tvdb_id
        self.magnet = magnet
        self.torrent_id: Optional[Union[int, str]] = None
        self.torrent_info: Optional[TorrentInfo] = None
        self.containers: Optional[TorrentContainer] = None
        self.selected_files: Optional[Dict[str, Dict[str, Union[str, int]]]] = None
        self.created_at: datetime = datetime.now()
        self.expires_at: datetime = datetime.now() + timedelta(minutes=5)


class ScrapingSessionManager:
    def __init__(self):
        self.sessions: Dict[str, ScrapingSession] = {}
        self.downloader: Optional[Downloader] = None

    def set_downloader(self, downloader: Downloader):
        """Set the downloader for the session manager"""
        self.downloader = downloader

    def create_session(
        self,
        item_id: str,
        magnet: str,
        media_type: Optional[Literal["movie", "tv"]] = None,
        imdb_id: Optional[str] = None,
        tmdb_id: Optional[str] = None,
        tvdb_id: Optional[str] = None,
    ) -> ScrapingSession:
        """Create a new scraping session"""
        session_id = str(uuid4())
        session = ScrapingSession(
            session_id, item_id, media_type, imdb_id, tmdb_id, tvdb_id, magnet
        )
        self.sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[ScrapingSession]:
        """Get a scraping session by ID"""
        session = self.sessions.get(session_id)
        if not session:
            return None

        if datetime.now() > session.expires_at:
            self.abort_session(session_id)
            return None

        return session

    def update_session(self, session_id: str, **kwargs) -> Optional[ScrapingSession]:
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


session_manager = ScrapingSessionManager()

router = APIRouter(prefix="/scrape", tags=["scrape"])


def initialize_downloader(downloader: Downloader):
    """Initialize downloader if not already set"""
    if not session_manager.downloader:
        session_manager.set_downloader(downloader)


@router.get("/scrape", summary="Get streams for an item", operation_id="scrape_item")
def scrape_item(
    request: Request,
    item_id: Optional[str] = None,
    tmdb_id: Optional[str] = None,
    tvdb_id: Optional[str] = None,
    imdb_id: Optional[str] = None,
    media_type: Optional[Literal["movie", "tv"]] = None,
) -> ScrapeItemResponse:
    """Get streams for an item by any supported ID (item_id, tmdb_id, tvdb_id, imdb_id)"""

    if services := request.app.program.services:
        indexer = services[IndexerService]
        scraper = services[Scraping]
    else:
        raise HTTPException(status_code=412, detail="Scraping services not initialized")

    log_string = None
    item = None

    with db.Session() as db_session:
        if item_id:
            item = db_functions.get_item_by_id(item_id)
        elif tmdb_id and media_type == "movie":
            prepared_item = MediaItem(
                {
                    "tmdb_id": tmdb_id,
                    "requested_by": "riven",
                    "requested_at": datetime.now(),
                }
            )
            item = next(indexer.run(prepared_item), None)
        elif tvdb_id and media_type == "tv":
            prepared_item = MediaItem(
                {
                    "tvdb_id": tvdb_id,
                    "requested_by": "riven",
                    "requested_at": datetime.now(),
                }
            )
            item = next(indexer.run(prepared_item), None)
        elif imdb_id:
            prepared_item = MediaItem(
                {
                    "imdb_id": imdb_id,
                    "tvdb_id": tvdb_id,
                    "requested_by": "riven",
                    "requested_at": datetime.now(),
                }
            )
            item = next(indexer.run(prepared_item), None)
        else:
            raise HTTPException(status_code=400, detail="No valid ID provided")

        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        streams: Dict[str, Stream] = scraper.scrape(item)
        log_string = item.log_string

    return {
        "message": f"Manually scraped streams for item {log_string}",
        "streams": streams,
    }


@router.post(
    "/scrape/start_session",
    summary="Start a manual scraping session",
    operation_id="start_manual_session",
)
async def start_manual_session(
    request: Request,
    background_tasks: BackgroundTasks,
    item_id: Optional[str] = None,
    tmdb_id: Optional[str] = None,
    tvdb_id: Optional[str] = None,
    imdb_id: Optional[str] = None,
    media_type: Optional[Literal["movie", "tv"]] = None,
    magnet: Optional[str] = None,
) -> StartSessionResponse:
    session_manager.cleanup_expired(background_tasks)

    info_hash = extract_infohash(magnet)
    if not info_hash:
        raise HTTPException(status_code=400, detail="Invalid magnet URI")

    if services := request.app.program.services:
        indexer = services[IndexerService]
        downloader = services[Downloader]
    else:
        raise HTTPException(status_code=412, detail="Required services not initialized")

    initialize_downloader(downloader)

    if item_id:
        item = db_functions.get_item_by_id(item_id)
    elif tmdb_id and media_type == "movie":
        prepared_item = MediaItem(
            {
                "tmdb_id": tmdb_id,
                "requested_by": "riven",
                "requested_at": datetime.now(),
            }
        )
        item = next(indexer.run(prepared_item), None)
    elif tvdb_id and media_type == "tv":
        prepared_item = MediaItem(
            {
                "tvdb_id": tvdb_id,
                "requested_by": "riven",
                "requested_at": datetime.now(),
            }
        )
        item = next(indexer.run(prepared_item), None)
    elif imdb_id:
        prepared_item = MediaItem(
            {
                "imdb_id": imdb_id,
                "requested_by": "riven",
                "requested_at": datetime.now(),
            }
        )
        item = next(indexer.run(prepared_item), None)
    else:
        raise HTTPException(status_code=400, detail="No valid ID provided")

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    container = downloader.get_instant_availability(info_hash, item.type)

    if not container or not container.cached:
        raise HTTPException(
            status_code=400, detail="Torrent is not cached, please try another stream"
        )

    session = session_manager.create_session(
        item.id,
        info_hash,
        media_type=media_type,
        imdb_id=imdb_id,
        tmdb_id=tmdb_id,
        tvdb_id=tvdb_id,
    )

    try:
        torrent_id: str = downloader.add_torrent(info_hash)
        torrent_info: TorrentInfo = downloader.get_torrent_info(torrent_id)
        session_manager.update_session(
            session.id,
            torrent_id=torrent_id,
            torrent_info=torrent_info,
            containers=container,
        )
    except Exception as e:
        background_tasks.add_task(session_manager.abort_session, session.id)
        raise HTTPException(status_code=500, detail=str(e))

    data = {
        "message": "Started manual scraping session",
        "session_id": session.id,
        "torrent_id": torrent_id,
        "torrent_info": torrent_info,
        "containers": container,
        "expires_at": session.expires_at.isoformat(),
    }

    return StartSessionResponse(**data)


@router.post(
    "/scrape/select_files/{session_id}",
    summary="Select files for torrent id, for this to be instant it requires files to be one of /manual/instant_availability response containers",
    operation_id="manual_select",
)
def manual_select_files(
    request: Request, session_id: str, files: Container
) -> SelectFilesResponse:
    downloader: Downloader = request.app.program.services.get(Downloader)
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    if not session.torrent_id:
        session_manager.abort_session(session_id)
        raise HTTPException(status_code=500, detail="No torrent ID found")

    download_type = "uncached"
    if files.model_dump() in session.containers:
        download_type = "cached"

    try:
        downloader.select_files(
            session.torrent_id, [int(file_id) for file_id in files.root.keys()]
        )
        session.selected_files = files.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "message": f"Selected files for {session.item_id}",
        "download_type": download_type,
    }


@router.post(
    "/scrape/update_attributes/{session_id}",
    summary="Match container files to item",
    operation_id="manual_update_attributes",
)
async def manual_update_attributes(
    request: Request,
    session_id,
    data: Union[DebridFile, ShowFileData],
    session: Session = Depends(get_db),
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
    session = session_manager.get_session(session_id)
    log_string = None
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    if not session.item_id:
        session_manager.abort_session(session_id)
        raise HTTPException(status_code=500, detail="No item ID found")

    item = None
    if session.media_type == "tv" and session.tvdb_id:
        item = db_functions.get_item_by_external_id(tvdb_id=str(session.tvdb_id))
    elif session.media_type == "movie" and session.tmdb_id:
        item = db_functions.get_item_by_external_id(tmdb_id=str(session.tmdb_id))
    elif session.imdb_id:
        item = db_functions.get_item_by_external_id(imdb_id=session.imdb_id)

    if not item:
        item_data = {}
        if session.imdb_id:
            item_data["imdb_id"] = session.imdb_id
        if session.tmdb_id:
            item_data["tmdb_id"] = session.tmdb_id
        if session.tvdb_id:
            item_data["tvdb_id"] = session.tvdb_id

        if item_data:
            item_data["requested_by"] = "riven"
            item_data["requested_at"] = datetime.now()
            prepared_item = MediaItem(item_data)
            item = next(IndexerService().run(prepared_item), None)
            if item:
                session.merge(item)
                session.commit()

        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        item = session.merge(item)
        item_ids_to_submit = set()

        def update_item(item: MediaItem, data: DebridFile, session: ScrapingSession):
            """
            Prepare and attach a filesystem entry and stream to a MediaItem based on a selected DebridFile within a scraping session.

            Cancels any running processing job for the item and resets its state; ensures there is a staging FilesystemEntry for the given file (reusing an existing entry or creating a provisional one and persisting it), clears the item's existing filesystem_entries and links the staging entry, sets the item's active_stream to the session magnet and torrent id, appends a ranked ItemStream derived from the session, and records the item's id in the module-level item_ids_to_submit set.

            Parameters:
                item (MediaItem): The media item to update; will be merged into the active DB session as needed.
                data (DebridFile): Selected file metadata (filename, filesize, optional download_url) used to create or locate the staging entry.
                session (ScrapingSession): Scraping session containing the magnet and torrent_info used to set active_stream and rank the stream.
            """
            request.app.program.em.cancel_job(item.id)
            item.reset()

            # Ensure a staging MediaEntry exists and is linked
            from sqlalchemy import select
            from program.media.media_entry import MediaEntry

            fs_entry = None

            if item.filesystem_entry:
                fs_entry = item.filesystem_entry
                # Update source metadata on existing entry
                fs_entry.original_filename = data.filename
            else:
                # Create a provisional VIRTUAL entry (download_url/provider may be filled by downloader later)
                fs_entry = MediaEntry.create_virtual_entry(
                    original_filename=data.filename,
                    download_url=getattr(data, "download_url", None),
                    provider=None,
                    provider_download_id=None,
                    file_size=(data.filesize or 0),
                )
                session.add(fs_entry)
                session.commit()
                session.refresh(fs_entry)

                # Link MediaItem to FilesystemEntry
                # Clear existing entries and add the new one
                item.filesystem_entries.clear()
                item.filesystem_entries.append(fs_entry)
                item = session.merge(item)

            item.active_stream = {
                "infohash": session.magnet,
                "id": session.torrent_info.id,
            }
            torrent = rtn.rank(session.torrent_info.name, session.magnet)

            # Ensure the item is properly attached to the session before adding streams
            # This prevents SQLAlchemy warnings about detached objects
            if object_session(item) is not session:
                item = session.merge(item)

            item.streams.append(ItemStream(torrent))
            item_ids_to_submit.add(item.id)

        if item.type == "movie":
            update_item(item, data, session)

        else:
            for season_number, episodes in data.root.items():
                for episode_number, episode_data in episodes.items():
                    if item.type == "show":
                        if episode := item.get_absolute_episode(
                            episode_number, season_number
                        ):
                            update_item(episode, episode_data, session)
                        else:
                            logger.error(
                                f"Failed to find episode {episode_number} for season {season_number} for {item.log_string}"
                            )
                            continue
                    elif item.type == "season":
                        if episode := item.parent.get_absolute_episode(
                            episode_number, season_number
                        ):
                            update_item(episode, episode_data, session)
                        else:
                            logger.error(
                                f"Failed to find season {season_number} for {item.log_string}"
                            )
                            continue
                    elif item.type == "episode":
                        if (
                            season_number != item.parent.number
                            and episode_number != item.number
                        ):
                            continue
                        update_item(item, episode_data, session)
                        break
                    else:
                        logger.error(f"Failed to find item type for {item.log_string}")
                        continue

        item.store_state()
        log_string = item.log_string
        session.merge(item)
        session.commit()

    # Sync VFS to reflect any deleted/updated entries
    # Must happen AFTER commit so the database reflects the changes
    from program.services.filesystem import FilesystemService

    filesystem_service = request.app.program.services.get(FilesystemService)
    if filesystem_service and filesystem_service.riven_vfs:
        filesystem_service.riven_vfs.sync(item)
        logger.debug("VFS synced after manual scraping update")

    for item_id in item_ids_to_submit:
        request.app.program.em.add_event(Event("ManualAPI", item_id))

    return {"message": f"Updated given data to {log_string}"}


@router.post(
    "/scrape/abort_session/{session_id}",
    summary="Abort a manual scraping session",
    operation_id="abort_manual_session",
)
async def abort_manual_session(
    _: Request, background_tasks: BackgroundTasks, session_id: str
) -> SessionResponse:
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    background_tasks.add_task(session_manager.abort_session, session_id)
    return {"message": f"Aborted session {session_id}"}


@router.post(
    "/scrape/complete_session/{session_id}",
    summary="Complete a manual scraping session",
    operation_id="complete_manual_session",
)
async def complete_manual_session(_: Request, session_id: str) -> SessionResponse:
    session = session_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    if not all([session.torrent_id, session.selected_files]):
        raise HTTPException(status_code=400, detail="Session is incomplete")

    session_manager.complete_session(session_id)
    return {"message": f"Completed session {session_id}"}


class ParseTorrentTitleResponse(BaseModel):
    message: str
    data: list[dict[str, Any]]


@router.post(
    "/parse",
    summary="Parse an array of torrent titles",
    operation_id="parse_torrent_titles",
)
async def parse_torrent_titles(
    request: Request, titles: list[str]
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
)
async def overseerr_requests(
    request: Request,
    filter: Optional[str] = None,
    take: int = 100000,
    db: Session = Depends(get_db),
) -> MessageResponse:
    """Get all overseerr requests and make sure they exist in the database"""
    from program.apis.overseerr_api import OverseerrAPI
    from program.db.db_functions import item_exists_by_any_id
    from kink import di

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
        persisted_items: list[MediaItem] = []
        for item in overseerr_items:
            persisted = db.merge(item)
            persisted_items.append(persisted)
        db.commit()

        for persisted in persisted_items:
            request.app.program.em.add_item(persisted, service="Overseerr")

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


@router.post(
    "/auto",
    summary="Auto scrape an item with resolution overrides",
    operation_id="auto_scrape_item",
)
async def auto_scrape_item(
    request: Request,
    body: AutoScrapeRequest,
) -> MessageResponse:
    """
    Auto scrape an item with specific resolution overrides.
    This performs a one-time scrape using the provided resolutions
    and triggers the downloader if new streams are found.
    """
    if services := request.app.program.services:
        scraper = services[Scraping]
        indexer = services[IndexerService]
    else:
        raise HTTPException(status_code=412, detail="Services not initialized")

    item = None
    with db.Session() as db_session:
        if body.item_id:
            item = db_functions.get_item_by_id(body.item_id, session=db_session)
        elif body.tmdb_id and body.media_type == "movie":
            prepared_item = MediaItem(
                {
                    "tmdb_id": body.tmdb_id,
                    "requested_by": "riven",
                    "requested_at": datetime.now(),
                }
            )
            item = next(indexer.run(prepared_item), None)
        elif body.tvdb_id and body.media_type == "tv":
            prepared_item = MediaItem(
                {
                    "tvdb_id": body.tvdb_id,
                    "requested_by": "riven",
                    "requested_at": datetime.now(),
                }
            )
            item = next(indexer.run(prepared_item), None)
        elif body.imdb_id:
            prepared_item = MediaItem(
                {
                    "imdb_id": body.imdb_id,
                    "tvdb_id": body.tvdb_id, # imdb_id alone is not enough for TV, needs tvdb_id
                    "requested_by": "riven",
                    "requested_at": datetime.now(),
                }
            )
            item = next(indexer.run(prepared_item), None)
        
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
            db_session.add(item)
            db_session.commit()
            
            # Emit event to trigger downloader
            request.app.program.em.add_event(Event("Scraping", item_id=item.id))
            
            return {"message": f"Auto scrape started. Found {len(new_streams)} new streams."}
        else:
            return {"message": "Auto scrape completed. No new streams found."}
