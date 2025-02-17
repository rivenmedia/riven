import asyncio
import re
from datetime import datetime, timedelta
from typing import Dict, List, Literal, Optional, TypeAlias, Union
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, RootModel
from RTN import ParsedData
from sqlalchemy import select

from program.db import db_functions
from program.db.db import db
from program.media.item import Episode, MediaItem
from program.media.stream import Stream as ItemStream
from program.services.downloaders import Downloader
from program.services.indexers.trakt import TraktIndexer
from program.services.scrapers import Scraping
from program.services.scrapers.shared import rtn
from program.types import Event
from program.services.downloaders.models import TorrentContainer, TorrentInfo, DebridFile


class Stream(BaseModel):
    infohash: str
    raw_title: str
    parsed_title: str
    parsed_data: ParsedData
    rank: int
    lev_ratio: float
    is_cached: bool

class ScrapeItemResponse(BaseModel):
    message: str
    streams: Dict[str, Stream]

class StartSessionResponse(BaseModel):
    message: str
    session_id: str
    torrent_id: str
    torrent_info: TorrentInfo
    containers: Optional[List[TorrentContainer]]
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
    def __init__(self, id: str, item_id: str, magnet: str):
        self.id = id
        self.item_id = item_id
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
        """
        Assigns the provided Downloader instance to the session manager.
        
        Parameters:
            downloader (Downloader): An instance responsible for handling download operations. The instance must adhere to the expected downloader interface.
        
        Returns:
            None
        """
        self.downloader = downloader

    def create_session(self, item_id: str, magnet: str) -> ScrapingSession:
        """
        Creates a new scraping session with a unique identifier.
        
        This method generates a new session for the specified media item using the provided magnet link. It initializes a new ScrapingSession object with a unique session ID, stores it in the session manager's internal dictionary, and returns the session instance.
        
        Parameters:
            item_id (str): The identifier of the media item to be scraped.
            magnet (str): The magnet link associated with the media item for torrent retrieval.
        
        Returns:
            ScrapingSession: The newly created scraping session object.
        """
        session_id = str(uuid4())
        session = ScrapingSession(session_id, item_id, magnet)
        self.sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[ScrapingSession]:
        """
        Retrieve an active scraping session by its unique session ID.
        
        This method checks if a session exists in the internal session store. If found, it verifies whether the
        session has expired based on its expiration timestamp. If the session is expired, the method aborts the session
        and returns None. If the session is valid and active, it returns the corresponding ScrapingSession object.
        
        Parameters:
            session_id (str): The unique identifier for the scraping session.
        
        Returns:
            Optional[ScrapingSession]: The active scraping session if found and valid; otherwise, None.
        
        Side Effects:
            If the session is expired, the session is aborted and cleaned up.
        """
        session = self.sessions.get(session_id)
        if not session:
            return None

        if datetime.now() > session.expires_at:
            self.abort_session(session_id)
            return None

        return session

    def update_session(self, session_id: str, **kwargs) -> Optional[ScrapingSession]:
        """
        Update attributes for an existing scraping session.
        
        This method retrieves a scraping session using the provided session_id and updates
        its attributes with the given keyword arguments. Only attributes that exist on the
        session object are updated; any keyword arguments that do not correspond to an 
        existing attribute are ignored.
        
        Parameters:
            session_id (str): The unique identifier of the scraping session.
            **kwargs: Arbitrary keyword arguments representing attribute names and their new values.
        
        Returns:
            Optional[ScrapingSession]: The updated scraping session if found; otherwise, None.
        """
        session = self.get_session(session_id)
        if not session:
            return None

        for key, value in kwargs.items():
            if hasattr(session, key):
                setattr(session, key, value)

        return session

    def abort_session(self, session_id: str):
        """
        Abort an active scraping session and clean up associated resources.
        
        This method removes the scraping session identified by `session_id` from the session registry.
        If the session exists and is associated with a torrent (and a downloader is available), it attempts to delete the torrent.
        Any exceptions raised during the torrent deletion process are caught and logged, ensuring that the session abort process continues.
        The method logs the outcome of the session abortion and torrent deletion for debugging and auditing purposes.
        
        Parameters:
            session_id (str): The unique identifier for the scraping session to be aborted.
        
        Returns:
            None
        
        Side Effects:
            - Removes the session from the internal session registry.
            - Deletes the associated torrent if present.
            - Logs debug and error messages reflecting the operation's status.
        """
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
        """
        Complete a scraping session by removing it from the active sessions.
        
        This method attempts to retrieve the session with the given session_id by calling get_session().
        If the session exists, it logs a debug message indicating that the session is being completed and
        removes the session from the sessions registry. If the session does not exist, the method takes no
        action.
        
        Args:
            session_id (str): The unique identifier of the scraping session to complete.
        """
        session = self.get_session(session_id)
        if not session:
            return

        logger.debug(f"Completing session {session_id} for item {session.item_id}")
        self.sessions.pop(session_id)

    def cleanup_expired(self, background_tasks: BackgroundTasks):
        """
        Clean up expired scraping sessions.
        
        This method iterates over all active scraping sessions and checks if their expiration
        time has passed relative to the current time. For every session that has expired (i.e.,
        its 'expires_at' is less than the current datetime), it schedules a background task
        to abort the session asynchronously using the provided BackgroundTasks instance.
        This deferred cleanup prevents blocking the main application flow while ensuring
        that stale sessions are properly terminated.
        
        Parameters:
            background_tasks (BackgroundTasks): A FastAPI BackgroundTasks instance used to
                schedule the asynchronous abortion of expired sessions.
        """
        current_time = datetime.now()
        expired = [
            session_id for session_id, session in self.sessions.items()
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

@router.get(
    "/scrape/{id}",
    summary="Get streams for an item",
    operation_id="scrape_item"
)
def scrape_item(request: Request, id: str) -> ScrapeItemResponse:
    """
    Scrapes available streams for a media item based on the provided identifier.
    
    This function processes the given identifier to determine whether it represents an IMDb ID (if it starts with "tt") or a database item ID. Depending on the identifier type, it retrieves the corresponding media item either via the indexer service (for IMDb IDs) or from the database session (for standard item IDs). It then scrapes streams for the item using the scraping service and checks each stream's caching status with the downloader service, updating the stream's `is_cached` property accordingly.
    
    Parameters:
        request (Request): FastAPI request instance containing application services (indexer, scraping, and downloader).
        id (str): The media item identifier. If it starts with "tt", it is treated as an IMDb ID; otherwise, it is used as a database item ID.
    
    Returns:
        ScrapeItemResponse: A dictionary with the following keys:
            - message (str): Confirmation message including a log string from the media item.
            - streams (Dict[str, Stream]): A mapping of stream identifiers to their corresponding Stream objects.
    
    Raises:
        HTTPException: If the required scraping services are not initialized in the application context.
    
    Example:
        response = scrape_item(request, "tt1234567")
        # response: {
        #     "message": "Manually scraped streams for item [log details]",
        #     "streams": { "stream1": <Stream ...>, "stream2": <Stream ...>, ... }
        # }
    """
    if id.startswith("tt"):
        imdb_id = id
        item_id = None
    else:
        imdb_id = None
        item_id = id

    if services := request.app.program.services:
        indexer = services[TraktIndexer]
        scraper = services[Scraping]
        downloader = services[Downloader]
    else:
        raise HTTPException(status_code=412, detail="Scraping services not initialized")

    log_string = None
    with db.Session() as db_session:

        if imdb_id:
            prepared_item = MediaItem({"imdb_id": imdb_id})
            item = next(indexer.run(prepared_item))
        else:
            item: MediaItem = (
                db_session.execute(
                    select(MediaItem)
                    .where(MediaItem.id == item_id)
                )
                .unique()
                .scalar_one_or_none()
            )
        streams: Dict[str, Stream] = scraper.scrape(item)
        for stream in streams.values():
            container = downloader.get_instant_availability(stream.infohash, item.type)
            stream.is_cached = bool(container and container.cached)
        log_string = item.log_string

    return {
        "message": f"Manually scraped streams for item {log_string}",
        "streams": streams
    }

@router.post(
    "/scrape/start_session",
    summary="Start a manual scraping session",
    operation_id="start_manual_session"
)
async def start_manual_session(
    request: Request,
    background_tasks: BackgroundTasks,
    item_id: str,
    magnet: str
) -> StartSessionResponse:
    """
    Initiate a manual scraping session using a media item ID and a magnet URI.
    
    This asynchronous function validates the provided magnet URI by extracting its 40-character hexadecimal info hash and retrieves the corresponding media item details based on whether the item_id is an IMDb ID (prefixed with "tt") or a database ID. It then initializes the necessary services (TraktIndexer and Downloader), creates a new scraping session, and attempts to add the torrent using the Downloader. If successful, the session is updated with torrent details (torrent_id, torrent_info, and available containers) and a StartSessionResponse is returned. In case of failure during torrent processing, the session is aborted and an HTTPException is raised.
    
    Parameters:
        request (Request): FastAPI request object containing the application context and services.
        background_tasks (BackgroundTasks): Background tasks manager for scheduling cleanup or abort operations.
        item_id (str): Identifier for the media item; can be an IMDb ID (starting with "tt") or a database ID.
        magnet (str): Magnet URI containing the torrent's info hash.
    
    Raises:
        HTTPException: 
            - 400 if the magnet URI does not contain a valid 40-character hexadecimal info hash.
            - 412 if required services (TraktIndexer and Downloader) are not initialized.
            - 404 if the media item cannot be found.
            - 500 for errors encountered during torrent addition or information retrieval.
    
    Returns:
        StartSessionResponse: A response object containing:
            - message (str): Confirmation that the manual scraping session has started.
            - session_id (str): Unique identifier for the created session.
            - torrent_id (str): Identifier for the added torrent.
            - torrent_info (TorrentInfo): Information regarding the torrent.
            - containers (Optional[List[TorrentContainer]]): List of containers with instant availability, if available.
            - expires_at (str): ISO formatted expiration timestamp of the session.
    """
    session_manager.cleanup_expired(background_tasks)

    def get_info_hash(magnet: str) -> str:
        pattern = r"[A-Fa-f0-9]{40}"
        match = re.search(pattern, magnet)
        return match.group(0) if match else None

    info_hash = get_info_hash(magnet)
    if not info_hash:
        raise HTTPException(status_code=400, detail="Invalid magnet URI")

    # Identify item based on IMDb or database ID
    if item_id.startswith("tt"):
        imdb_id = item_id
        item_id = None
    else:
        imdb_id = None
        item_id = item_id

    if services := request.app.program.services:
        indexer = services[TraktIndexer]
        downloader = services[Downloader]
    else:
        raise HTTPException(status_code=412, detail="Required services not initialized")

    initialize_downloader(downloader)

    if imdb_id:
        prepared_item = MediaItem({"imdb_id": imdb_id})
        item = next(indexer.run(prepared_item))
    else:
        item = db_functions.get_item_by_id(item_id)

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    session = session_manager.create_session(item_id or imdb_id, info_hash)

    try:
        torrent_id: str = downloader.add_torrent(info_hash)
        torrent_info: TorrentInfo = downloader.get_torrent_info(torrent_id)
        container: Optional[TorrentContainer] = downloader.get_instant_availability(info_hash, item.type)
        session_manager.update_session(session.id, torrent_id=torrent_id, torrent_info=torrent_info, containers=container)
    except Exception as e:
        background_tasks.add_task(session_manager.abort_session, session.id)
        raise HTTPException(status_code=500, detail=str(e))

    data = {
        "message": "Started manual scraping session",
        "session_id": session.id,
        "torrent_id": torrent_id,
        "torrent_info": torrent_info,
        "containers": [container] if container else None,
        "expires_at": session.expires_at.isoformat()
    }

    return StartSessionResponse(**data)

@router.post(
    "/scrape/select_files/{session_id}",
    summary="Select files for torrent id, for this to be instant it requires files to be one of /manual/instant_availability response containers",
    operation_id="manual_select"
)
def manual_select_files(request: Request, session_id: str, files: Container) -> SelectFilesResponse:
    """
    Manually selects files for a scraping session and determines the download type.
    
    This function retrieves a scraping session using the provided session_id and then selects files based on the file identifiers contained in the provided files container.
    It verifies that the session exists and contains a valid torrent ID; if not, it aborts the session and raises an HTTP 404 or 500 error, respectively.
    If the dumped file data exists within the session's containers, the download type is set to "cached"; otherwise, it defaults to "uncached".
    The downloader service is then used to select the files, and the session's list of selected files is updated accordingly.
    
    Parameters:
        request (Request): The FastAPI request object containing the application context and services.
        session_id (str): The unique identifier for the scraping session.
        files (Container): A container object mapping file identifiers to their data. File IDs are extracted from the keys of its `root` attribute.
    
    Returns:
        SelectFilesResponse: A dictionary with a confirmation message and a 'download_type' key indicating whether the files are to be downloaded as "cached" or "uncached".
    
    Raises:
        HTTPException: 
            - 404: If the session is not found or has expired.
            - 500: If no torrent ID is present in the session or if an error occurs during file selection.
    """
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
        downloader.select_files(session.torrent_id, [int(file_id) for file_id in files.root.keys()])
        session.selected_files = files.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "message": f"Selected files for {session.item_id}",
        "download_type": download_type
    }

@router.post(
    "/scrape/update_attributes/{session_id}",
    summary="Match container files to item",
    operation_id="manual_update_attributes"
)
async def manual_update_attributes(request: Request, session_id, data: Union[DebridFile, ShowFileData]) -> UpdateAttributesResponse:
    """
    Update the file attributes of a media item associated with a scraping session.
    
    This asynchronous function retrieves a scraping session by its ID and updates the associated media item's attributes based on the provided data. The update strategy differs based on the type of media:
    - **Movie**: Cancels any scheduled jobs for the movie, resets its state, updates the file and folder paths using the provided filename, sets the alternative folder from the torrent info, assigns a new active stream, and appends a ranked stream.
    - **Show**: Cancels jobs for the show and its seasons, then iterates over the provided season and episode data. For each episode found, it cancels any scheduled job, resets the episode state, updates file and folder paths, assigns the alternative folder and active stream, and appends a ranked stream.
    
    If the item's data is not available in the database (and the item ID starts with "tt"), the function retrieves and merges the item using an external indexer via the TraktIndexer. After updating, it commits the changes to the database and schedules events for each updated item.
    
    Parameters:
        request (Request): The FastAPI request object containing the application context.
        session_id: The identifier of the scraping session.
        data (Union[DebridFile, ShowFileData]): The file data used to update the media item. For movies, this should include a 'filename' attribute; for shows, it should contain a 'root' dictionary mapping season and episode numbers to file details.
    
    Returns:
        UpdateAttributesResponse: A dictionary containing a message with the updated media item's log string.
    
    Raises:
        HTTPException: 
            - 404 if the session is not found or expired.
            - 500 if the session does not have an associated item ID.
            - 404 if the media item cannot be found in the database.
    """
    session = session_manager.get_session(session_id)
    log_string = None
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    if not session.item_id:
        session_manager.abort_session(session_id)
        raise HTTPException(status_code=500, detail="No item ID found")

    with db.Session() as db_session:
        if str(session.item_id).startswith("tt") and not db_functions.get_item_by_external_id(imdb_id=session.item_id) and not db_functions.get_item_by_id(session.item_id):
            prepared_item = MediaItem({"imdb_id": session.item_id})
            item = next(TraktIndexer().run(prepared_item))
            db_session.merge(item)
            db_session.commit()
        else:
          item = db_functions.get_item_by_id(session.item_id)

        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        item_ids_to_submit = []

        if item.type == "movie":
            request.app.program.em.cancel_job(item.id)
            item.reset()
            item.file = data.filename
            item.folder = data.filename
            item.alternative_folder = session.torrent_info.alternative_filename
            item.active_stream = {"infohash": session.magnet, "id": session.torrent_info.id}
            torrent = rtn.rank(session.magnet, session.magnet)
            item.streams.append(ItemStream(torrent))
            item_ids_to_submit.append(item.id)
        else:
            request.app.program.em.cancel_job(item.id)
            await asyncio.sleep(0.2)
            for season in item.seasons:
                request.app.program.em.cancel_job(season.id)
                await asyncio.sleep(0.2)
            for season, episodes in data.root.items():
                for episode, episode_data in episodes.items():
                    item_episode: Episode = next((_episode for _season in item.seasons if _season.number == season for _episode in _season.episodes if _episode.number == episode), None)
                    if item_episode:
                        request.app.program.em.cancel_job(item_episode.id)
                        await asyncio.sleep(0.2)
                        item_episode.reset()
                        item_episode.file = episode_data.filename
                        item_episode.folder = episode_data.filename
                        item_episode.alternative_folder = session.torrent_info.alternative_filename
                        item_episode.active_stream = {"infohash": session.magnet, "id": session.torrent_info.id}
                        torrent = rtn.rank(session.magnet, session.magnet)
                        item_episode.streams.append(ItemStream(torrent))
                        item_ids_to_submit.append(item_episode.id)
        item.store_state()
        log_string = item.log_string
        db_session.merge(item)
        db_session.commit()

    for item_id in item_ids_to_submit:
        request.app.program.em.add_event(Event("ManualAPI", item_id))

    return {"message": f"Updated given data to {log_string}"}

@router.post("/scrape/abort_session/{session_id}")
async def abort_manual_session(
    _: Request,
    background_tasks: BackgroundTasks,
    session_id: str
) -> SessionResponse:
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    background_tasks.add_task(session_manager.abort_session, session_id)
    return {"message": f"Aborted session {session_id}"}

@router.post(
    "/scrape/complete_session/{session_id}",
    summary="Complete a manual scraping session",
    operation_id="complete_manual_session"
)
async def complete_manual_session(_: Request, session_id: str) -> SessionResponse:
    session = session_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    if not all([session.torrent_id, session.selected_files]):
        raise HTTPException(status_code=400, detail="Session is incomplete")

    session_manager.complete_session(session_id)
    return {"message": f"Completed session {session_id}"}